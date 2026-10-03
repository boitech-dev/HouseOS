from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from houseos import files
from houseos.activity import describe
from houseos.auth import Actor, require_actor
from houseos.db import get_db, new_id
from houseos.models import Event, Record
from houseos.music import history_key
from houseos.music_duplicates import KIND, flag, group_key, groups, same_song


def song(title, uploader="", duration=None, id=None):
    return {"id": id or title, "title": title, "uploader": uploader, "duration": duration}


OFFICIAL = song("Queen - Bohemian Rhapsody (Official Video Remastered)", "Queen Official", 359)
TOPIC = song("Bohemian Rhapsody - Remastered 2011", "Queen - Topic", 355)
LYRICS = song("Queen – Bohemian Rhapsody [Lyrics]", "7clouds", 357)
SWAPPED = song("Bohemian Rhapsody - Queen (lyrics)", "Lyrics Hub", 356)
COVER = song("Panic! At The Disco - Bohemian Rhapsody (Official Video)", "Fueled By Ramen", 357)


def test_the_same_song_uploaded_differently_is_a_possible_duplicate():
    assert same_song(OFFICIAL, TOPIC)  # the channel names the artist the title doesn't
    assert not same_song(COVER, TOPIC)
    assert same_song(OFFICIAL, LYRICS)  # the title names the artist, not the lyrics channel
    assert same_song(LYRICS, SWAPPED)  # "Track - Artist" meets "Artist - Track"
    assert same_song(
        song("Beyoncé - Halo", duration=261), song("Beyonce - HALO (Official Music Video)", duration=264)
    )
    assert same_song(
        song("Daft Punk - Get Lucky ft. Pharrell Williams, Nile Rodgers (Official Audio)", duration=248),
        song("Daft Punk - Get Lucky (feat. Pharrell Williams)", duration=250),
    )


def test_other_songs_versions_and_covers_are_not():
    assert not same_song(OFFICIAL, COVER)  # another artist named in the title
    assert not same_song(
        song("Daft Punk - Get Lucky (Radio Edit)", duration=248), song("Daft Punk - Get Lucky", duration=369)
    )  # the album version is two minutes longer
    assert not same_song(song("Halo", "Beyoncé", 261), song("Halo", "Karaoke Hits", 262))
    assert not same_song(OFFICIAL, song("Queen - Don't Stop Me Now", "Queen Official", 359))


def test_without_a_length_the_title_and_artist_must_agree():
    assert same_song(
        song("Stromae - Alors on danse"), song("Stromae - Alors On Danse (Official Music Video)", "", 208)
    )
    assert same_song(song("Alors on danse", "StromaeVEVO"), song("Alors on danse (Clip officiel)", "Stromae"))
    assert not same_song(song("Alors on danse", "Stromae"), song("Alors on danse", "Karaoke Hits"))
    assert not same_song(song("Stromae - Alors on danse"), song("Alors on danse", "Karaoke Hits", 208))


def test_groups_join_chains_and_keep_what_was_dismissed_apart():
    library = [OFFICIAL, COVER, TOPIC, song("Queen - Don't Stop Me Now", "Queen", 209), SWAPPED, LYRICS]
    (group,) = groups(library)
    assert {s["id"] for s in group} == {OFFICIAL["id"], TOPIC["id"], LYRICS["id"], SWAPPED["id"]}
    two = [OFFICIAL, TOPIC]
    assert groups(two, [[OFFICIAL["id"], TOPIC["id"]]]) == []
    assert groups([OFFICIAL, COVER]) == []


def kept(db, owner, title, uploader, duration, plays=0):
    url = "https://www.youtube.com/watch?v=" + new_id()[:11]
    row = Record(
        id=new_id(),
        kind="music.download",
        owner_id=owner,
        visibility="house",
        data={"state": "ready", "title": title, "uploader": uploader, "duration": duration, "size": 3},
    )
    row.data = {**row.data, "source_url": url, "path": f"music-downloads/{row.id}.media"}
    db.add(row)
    if plays:
        db.add(Record(id=history_key(url), kind="music.history", owner_id=owner, data={"plays": plays}))
    db.commit()
    return row


def test_a_new_duplicate_is_flagged_once_listed_for_admins_and_can_be_dismissed(domain):
    db, (alice, bob, _) = domain
    first = kept(db, alice.id, "Queen - Bohemian Rhapsody (Official Video)", "Queen Official", 359, plays=7)
    second = kept(db, bob.id, "Bohemian Rhapsody (Remastered 2011)", "Queen - Topic", 356)
    ids = sorted([first.id, second.id])
    flagged = lambda: db.scalars(  # noqa: E731
        select(Event).where(Event.topic == "music.duplicate_kept")
    ).all()
    before = len([e for e in flagged() if e.payload.get("ids") == ids])
    flag(db, second.id, bob.id)
    flag(db, second.id, bob.id)  # the same group again: no second notice
    notices = [e for e in flagged() if e.payload.get("ids") == ids]
    assert len(notices) == before + 1 and db.get(Record, group_key(ids)).kind == KIND
    line = describe(notices[-1], {})
    assert line["template"] == "Possible duplicate kept: {title}" and "Remastered" in line["values"]["title"]

    app = FastAPI()
    app.include_router(files.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[require_actor] = lambda: bob
    with TestClient(app) as client:
        assert client.get("/files/library/duplicates").status_code == 403
        app.dependency_overrides[require_actor] = lambda: Actor(
            alice.id, alice.name, "admin", alice.permissions
        )
        body = client.get("/files/library/duplicates").json()
        (group,) = [g for g in body["groups"] if g["ids"] == ids]
        keep, other = group["songs"]
        assert keep["id"] == first.id and keep["suggested"] and keep["plays"] == 7 and not other["suggested"]
        assert other["delete"] == f"/files/library/music/{second.id}?version={second.version}"
        assert {"title", "uploader", "duration", "size", "last_played", "kept_at", "source_url"} <= set(keep)
        assert client.post("/files/library/duplicates/dismiss", json={"ids": [first.id]}).status_code == 422
        assert client.post("/files/library/duplicates/dismiss", json={"ids": ids}).status_code == 200
        body = client.get("/files/library/duplicates").json()
        assert not [g for g in body["groups"] if set(ids) & set(g["ids"])]
