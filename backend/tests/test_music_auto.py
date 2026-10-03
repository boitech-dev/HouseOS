import time
from sqlalchemy.orm import Session
from houseos import music, music_auto
from houseos.auth import Actor
from houseos.models import Record

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


def test_quick_songs_mix_lately_loved_and_missed():
    from datetime import timedelta

    from houseos.db import utcnow
    from test_music_library import MusicLibraryTests

    fixture = MusicLibraryTests()
    fixture.setUp()
    actor = Actor("one", "One", "resident", frozenset({"music.read"}))
    now = utcnow()
    with Session(fixture.engine, expire_on_commit=False) as db:
        for name, days, plays in (
            ("hot", 1, 5),
            ("warm", 2, 3),
            ("old", 7, 4),
            ("both", 7, 2),
            ("both", 1, 1),
        ):
            url = "https://www.youtube.com/watch?v=" + name.ljust(11, "x")
            if not db.get(Record, music.history_key(url)):
                kept(db, url, "pop")
                db.flush()
            for _ in range(plays):
                db.add(
                    Record(
                        kind="music.play",
                        owner_id="one",
                        visibility="house",
                        data={"key": music.history_key(url)},
                        created_at=now - timedelta(days=days),
                    )
                )
        db.commit()
        picks = music.quick_songs(actor, db)["items"]
        why = {p["source_url"][-11:].rstrip("x"): p["why"] for p in picks}
        assert len(picks) == 3 and why["old"] == "missed"  # "both" was heard lately: not missed
        assert sorted(k for k, w in why.items() if w == "lately") in (
            ["hot", "warm"],
            ["both", "hot"],
            ["both", "warm"],
        )


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
