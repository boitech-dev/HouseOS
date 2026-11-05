import time
from sqlalchemy.orm import Session
from houseos import music, music_auto
from houseos.auth import Actor
from houseos.models import Record
from sqlalchemy import select

STATION = "11111111-2222-3333-4444-555555555555"


def kept(db, url, genre):
    db.add(
        Record(
            kind="music.download",
            owner_id="one",
            visibility="house",
            data={"state": "ready", "source_url": url, "title": url[-3:]},
        )
    )
    db.add(
        Record(
            id=music.history_key(url),
            kind="music.history",
            owner_id="one",
            visibility="house",
            data={"source_url": url, "genre": genre},
        )
    )


def test_library_and_radio_rotation(monkeypatch):
    from test_music_library import MusicLibraryTests

    fixture = MusicLibraryTests()
    fixture.setUp()
    monkeypatch.setattr(music_auto.settings, "audio_enabled", True, raising=False)
    actor = Actor("one", "One", "resident", frozenset({"music.read", "music.control", "music.queue"}))
    rock, jazz = "https://www.youtube.com/watch?v=rockrockroc", "https://www.youtube.com/watch?v=jazzjazzjaz"
    with Session(fixture.engine, expire_on_commit=False) as db:
        kept(db, rock, "rock")
        kept(db, jazz, "jazz")
        db.get(music.QueueItem, "track").status = "completed"
        db.commit()
        state = music_auto.auto_state(actor, db)
        assert state["kept"] == 2 and state["mode"] == "off"
        # Off: nothing is added.
        q = db.get(music.QueueState, 1)
        assert music_auto.fill(db, q) is None
        result = music_auto.set_auto(music_auto.Auto(mode="library", genres=["jazz"]), actor, db)
        assert result["started"] and q.desired == "playing"
        pick = music_auto.fill(db, q)
        assert pick.source_url == jazz and pick.metadata_json["auto"] == "library"
        # One pick at a time: while it loads, nothing more is added.
        assert music_auto.fill(db, q) is None
        pick.status = "completed"
        # Radio: stations take turns, each for its songs or minutes, and a request ends it early.
        music_auto.set_auto(
            music_auto.Auto(mode="radio", stations=[{"id": STATION, "name": "FIP", "songs": 2}]), actor, db
        )
        station = music_auto.fill(db, q)
        assert station.source_url == "radio:" + STATION and station.metadata_json["live_approved"]
        station.status = "playing"
        now = time.time()
        station.metadata_json = {**station.metadata_json, "auto_since": now, "titles_heard": 2}
        assert not music_auto.rotation_over(db, station, now)
        station.metadata_json = {**station.metadata_json, "titles_heard": 3}
        assert music_auto.rotation_over(db, station, now)
        station.metadata_json = {**station.metadata_json, "titles_heard": 0}
        assert music_auto.rotation_over(db, station, now + 12 * 60)  # no titles: 6 minutes a song
        # Paused 20 minutes in the middle: the turn counts what was heard (5 of its 12 minutes).
        station.metadata_json = {**station.metadata_json, "auto_heard": 5 * 60}
        assert not music_auto.rotation_over(db, station, now + 25 * 60)
        station.metadata_json = {**station.metadata_json, "auto_heard": 12 * 60}
        assert music_auto.rotation_over(db, station, now + 25 * 60)
        db.add(music.QueueItem(owner_id="two", source_url=rock, position=9, status="ready"))
        db.flush()
        assert music_auto.rotation_over(db, station, now)


def test_guests_cannot_change_it():
    import pytest
    from fastapi import HTTPException
    from test_music_library import MusicLibraryTests

    fixture = MusicLibraryTests()
    fixture.setUp()
    guest = Actor("two", "Two", "guest", frozenset({"music.read", "music.control"}))
    with Session(fixture.engine) as db, pytest.raises(HTTPException) as raised:
        music_auto.set_auto(music_auto.Auto(mode="library"), guest, db)
    assert raised.value.status_code == 403


def test_the_next_songs_can_be_seen_moved_trimmed_and_reshuffled(monkeypatch):
    import pytest
    from fastapi import HTTPException
    from test_music_library import MusicLibraryTests

    fixture = MusicLibraryTests()
    fixture.setUp()
    monkeypatch.setattr(music_auto.settings, "audio_enabled", True, raising=False)
    actor = Actor("one", "One", "resident", frozenset({"music.read", "music.control", "music.queue"}))
    urls = [f"https://www.youtube.com/watch?v=song{n:07d}" for n in range(6)]
    with Session(fixture.engine, expire_on_commit=False) as db:
        for url in urls:
            kept(db, url, "pop")
        db.get(music.QueueItem, "track").status = "completed"
        db.commit()
        music_auto.set_auto(music_auto.Auto(mode="library"), actor, db)
        plan = music_auto.upcoming(actor, db)
        order = [item["source_url"] for item in plan["items"]]
        assert sorted(order) == urls
        # Move the last first and drop the second: that is what plays, in that order.
        mine = [order[-1], order[0], *order[2:-1]]
        changed = music_auto.change_upcoming(music_auto.Plan(version=plan["version"], urls=mine), actor, db)
        assert [i["source_url"] for i in changed["items"]] == mine
        q = db.get(music.QueueState, 1)
        assert music_auto.fill(db, q).source_url == order[-1]
        with pytest.raises(HTTPException):  # a song started meanwhile: the list changed
            music_auto.change_upcoming(music_auto.Plan(version=changed["version"], urls=mine), actor, db)
        after = music_auto.upcoming(actor, db)
        assert order[1] not in [i["source_url"] for i in after["items"]]  # removed stays out
        shuffled = music_auto.change_upcoming(
            music_auto.Plan(version=after["version"], shuffle=True), actor, db
        )
        # A new list starts over: the removed song may come back; the playing one stays out.
        assert sorted(i["source_url"] for i in shuffled["items"]) == sorted(set(urls) - {order[-1]})


def test_quick_songs_one_top_song_then_four_kept_songs_leaning_to_yours():
    from collections import Counter
    from datetime import timedelta

    from houseos.db import utcnow
    from test_music_library import MusicLibraryTests

    fixture = MusicLibraryTests()
    fixture.setUp()
    actor = Actor("one", "One", "resident", frozenset({"music.read"}))
    now = utcnow()
    name = lambda pick: pick["source_url"][-11:].rstrip("x")  # noqa: E731
    with Session(fixture.engine, expire_on_commit=False) as db:
        for song, days, plays in (("hot", 1, 6), ("warm", 10, 6), ("cold", 30, 9)):
            url = "https://www.youtube.com/watch?v=" + song.ljust(11, "x")
            kept(db, url, "pop")
            db.flush()
            for _ in range(plays):
                db.add(Record(kind="music.play", owner_id="two", visibility="house",
                              data={"key": music.history_key(url)}, created_at=now - timedelta(days=days)))  # fmt: skip
        for n in range(8):
            kept(db, f"https://www.youtube.com/watch?v=lib{n}".ljust(43, "x"), "jazz")
        db.flush()
        for row in db.scalars(select(Record).where(Record.kind == "music.download")):
            row.owner_id = "one" if row.data["source_url"].endswith(("lib0xxxxxxx", "lib1xxxxxxx")) else "two"
        db.commit()
        top, library = Counter(), Counter()
        for _ in range(200):
            picks = music.quick_songs(actor, db)["items"]
            assert [p["why"] for p in picks] == ["lately", "library", "library", "library", "library"]
            assert len({p["source_url"] for p in picks}) == 5
            top[name(picks[0])] += 1
            library.update(name(p) for p in picks[1:])
            assert all(p["mine"] == (name(p) in {"lib0", "lib1"}) for p in picks)
        # Only the last two weeks count for the top song, and the more lately the likelier.
        assert set(top) == {"hot", "warm"} and top["hot"] > top["warm"]
        # Songs you kept come up more than the house's others played as little.
        theirs = sum(library[f"lib{n}"] for n in range(2, 8)) / 6
        assert min(library["lib0"], library["lib1"]) > 1.5 * theirs


def test_auto_plays_failed_picks_leave_up_next_but_requests_stay():
    from test_music_library import MusicLibraryTests

    fixture = MusicLibraryTests()
    fixture.setUp()
    actor = Actor("one", "One", "resident", frozenset({"music.read"}))
    with Session(fixture.engine, expire_on_commit=False) as db:
        for n, meta in ((1, {"auto": "library"}), (2, {})):
            db.add(
                music.QueueItem(
                    id=f"failed-{n}", owner_id="one", source_url=f"https://www.youtube.com/watch?v=fail{n:07d}",
                    position=50 + n, status="failed", error_code="PLAYBACK_FAILED", metadata_json=meta,
                )
            )  # fmt: skip
        db.commit()
        shown = {item["id"] for item in music.state(actor, db)["items"]}
        assert "failed-2" in shown and "failed-1" not in shown


def test_auto_play_from_some_people_and_a_time_window():
    import pytest
    from datetime import timedelta
    from fastapi import HTTPException
    from houseos.db import utcnow
    from test_music_library import MusicLibraryTests

    fixture = MusicLibraryTests()
    fixture.setUp()
    actor = Actor("one", "One", "resident", frozenset({"music.read", "music.control", "music.queue"}))
    mine, theirs, old = (f"https://www.youtube.com/watch?v={k * 11}" for k in ("a", "b", "c"))
    with Session(fixture.engine, expire_on_commit=False) as db:
        for url, owner, age in ((mine, "one", 1), (theirs, "two", 1), (old, "one", 400)):
            db.add(
                Record(
                    kind="music.download",
                    owner_id=owner,
                    data={"state": "ready", "source_url": url, "title": url[-3:]},
                    created_at=utcnow() - timedelta(days=age),
                )
            )
        # "two" played the old song three days ago.
        db.add(
            Record(
                kind="music.play",
                owner_id="two",
                data={"key": music.history_key(old)},
                created_at=utcnow() - timedelta(days=3),
            )
        )
        db.commit()

        def pick(**filters):
            return set(music_auto.candidates(db, filters))

        assert pick(people=["one"]) == {mine, old}
        assert pick(people=["two"]) == {theirs, old}
        assert pick(days=30) == {mine, theirs, old}
        assert pick(people=["one"], days=30) == {mine}  # one kept the old song long ago
        with pytest.raises(HTTPException) as nothing:
            music_auto.set_auto(music_auto.Auto(mode="library", people=["nobody"]), actor, db)
        assert nothing.value.status_code == 409


def test_the_list_starts_with_the_picks_already_queued_and_songs_go_quickly(monkeypatch):
    from test_music_library import MusicLibraryTests

    fixture = MusicLibraryTests()
    fixture.setUp()
    monkeypatch.setattr(music_auto.settings, "audio_enabled", True, raising=False)
    actor = Actor("one", "One", "resident", frozenset({"music.read", "music.control", "music.queue"}))
    urls = [f"https://www.youtube.com/watch?v=queuedpick{n}" for n in range(4)]
    with Session(fixture.engine, expire_on_commit=False) as db:
        for url in urls:
            kept(db, url, "rock")
        db.get(music.QueueItem, "track").status = "completed"
        db.commit()
        music_auto.set_auto(music_auto.Auto(mode="library"), actor, db)
        q = db.get(music.QueueState, 1)
        picks = []
        for _ in range(2):  # auto play queues its next picks ahead
            pick = music_auto.fill(db, q)
            picks.append(pick)
            pick.status = "ready"
            db.commit()
        shown = music_auto.upcoming(actor, db)
        assert shown["queued"]
        assert [p["id"] for p in shown["queued"]] == [p.id for p in picks if p.id != q.current_id]
        assert all(p["removable"] for p in shown["queued"])
        # Removing songs quickly: a page's stale queue version no longer refuses the next one.
        version = q.version
        for pick in picks:
            if pick.id != q.current_id:
                music.remove(pick.id, version, actor, db)
                music.remove(pick.id, version, actor, db)  # twice is fine
        shown = music_auto.upcoming(actor, db)
        assert not shown["queued"]
        # A removed pick stays out of the next ones too.
        assert not {p.source_url for p in picks} & {i["source_url"] for i in shown["items"]}
        # Removing from the list needs no version either: a pick queued meanwhile can't refuse it.
        first, second = shown["items"][0]["source_url"], shown["items"][1]["source_url"]
        music_auto.change_upcoming(music_auto.Plan(version=0, remove=[first]), actor, db)
        after = music_auto.change_upcoming(music_auto.Plan(version=0, remove=[second]), actor, db)
        assert not {first, second} & {i["source_url"] for i in after["items"]}
