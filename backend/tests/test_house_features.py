"""Plays and genres, house favourites, the week digest, private calendar
items, file links in messages, the house library, stats, radio titles, voice confidence
and the cinema inspection cache."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from houseos import assistant as a, files as f, household as h, music as m, nox_presets, stats
from houseos.auth import Actor
from houseos.cinema import cached_inspection, inspection_key, remember_inspection
from houseos.db import new_id
from houseos.models import Record
from houseos.music_genre import genre_of
from houseos.radio import parse_icy
from houseos.voice import confident
from test_household_files import create


def played(db, owner, source, genre="rock"):
    item = m.QueueItem(
        owner_id=owner.id,
        source_url=source,
        title="Song " + source[-6:],
        position=0,
        status="playing",
        metadata_json={"duration": 200, "genre": genre},
    )
    db.add(item)
    db.flush()
    m.record_played(db, item, {"status": "observed", "item_id": item.id, "idle": False, "paused": False})
    db.commit()
    return item


def song():
    return "https://soundcloud.com/test-" + new_id() + "/song"


def test_genre_from_explicit_genre_tags_or_title():
    assert genre_of({"genre": "Deep House"}) == "house / techno"
    assert genre_of({"tags": ["synthpop"]}) == "electro"
    assert genre_of({"genre": "Hip-hop & Rap", "tags": ["rock"]}) == "rap / hip-hop"
    assert genre_of({"title": "Aznavour - Hier encore"}) == "other"


def test_every_play_counts_and_history_filters_by_who_played(music_domain):
    db, (alice, bob, _), _ = music_domain
    first, second = song(), song()
    played(db, alice, first)
    played(db, bob, first)
    played(db, alice, second, genre="jazz")
    row = db.get(Record, m.history_key(first))
    assert row.data["plays"] == 2 and row.owner_id == bob.id
    log = db.scalars(select(Record).where(Record.kind == "music.play", Record.owner_id == alice.id)).all()
    assert {r.data["key"] for r in log} == {m.history_key(first), m.history_key(second)}
    mine = m.history(offset=0, limit=50, by=alice.id, actor=alice, db=db)["items"]
    assert {i["source_url"] for i in mine} == {first, second}  # bob played `first` last; alice still did
    theirs = m.history(offset=0, limit=50, by=bob.id, actor=alice, db=db)["items"]
    assert [i["source_url"] for i in theirs] == [first] and theirs[0]["plays"] == 2


def test_house_favourites_come_from_history_and_skip_waiting_songs(music_domain):
    db, (alice, _, _), q = music_domain
    for _ in range(3):
        played(db, alice, song())
    waiting = {i.source_url for i in db.scalars(select(m.QueueItem).where(m.QueueItem.status == "ready"))}
    result = m.queue_favorites(db, alice, count=5)
    added = [db.get(m.QueueItem, i["item_id"]) for i in result["items"]]
    assert 1 <= result["count"] <= 5 and all(i.owner_id == alice.id for i in added)
    assert not {i.source_url for i in added} & waiting
    assert all(db.get(Record, m.history_key(i.source_url)) for i in added)
    assert q.desired == "playing"  # an explicit request starts playback when idle


def test_private_events_and_tasks_stay_with_their_author(domain):
    db, (alice, bob, _) = domain
    today = datetime.now(timezone.utc).date()  # the house counts days in its zone (UTC here)
    tomorrow = (today + timedelta(days=1)).isoformat()
    after = (today + timedelta(days=2)).isoformat()
    event = dict(title="Dentist", all_day=True, start=tomorrow, end=after)
    mine = create(db, alice, "calendar", {**event, "private": True})
    house = create(db, alice, "calendar", {**event, "title": "House dinner", "participants": [bob.id]})
    task = create(db, alice, "tasks", {"title": "Call bank", "private": True, "due_date": tomorrow})
    ids = lambda actor, kind: {r.id for r in db.scalars(h.visible_query(actor, kind))}  # noqa: E731
    assert {mine["id"], house["id"]} <= ids(alice, "calendar") and task["id"] in ids(alice, "tasks")
    assert mine["id"] not in ids(bob, "calendar") and task["id"] not in ids(bob, "tasks")
    assert house["id"] in ids(bob, "calendar")
    with pytest.raises(HTTPException) as err:
        create(db, alice, "calendar", {**event, "private": True, "participants": [bob.id]})
    assert err.value.status_code == 422
    with pytest.raises(HTTPException) as err:
        h.update_record(db, bob, "calendar", house["id"], h.EditRecord(data={"private": True}, version=1))
    assert err.value.status_code == 403
    digest = h.calendar_digest(db, bob)
    titles = {i["title"]: i for i in digest["week"]}
    assert "Dentist" not in titles and titles["House dinner"]["for_you"]
    text = nox_presets.week_text(h.calendar_digest(db, alice), "fr")
    assert "Demain" in text and "Dentist" in text and "privé" in text


def test_the_tour_names_every_room_in_both_languages():
    for word in ("Home", "Listen", "Watch", "Games", "House", "Files", "Me", "My Space"):
        assert f"**{word}**" in nox_presets.TOUR["en"]
    for word in ("Accueil", "Écouter", "Regarder", "Jeux", "Maison", "Fichiers", "Moi", "Mon espace"):
        assert f"**{word}**" in nox_presets.TOUR["fr"]


def test_code_presets_answer_without_any_ai_provider(domain):
    db, (alice, _, _) = domain
    reply = a.chat(a.Chat(message="Explain the house", preset="tour", idempotency_key=new_id()), alice, db)
    assert reply["status"] == "completed" and reply["reply"] in nox_presets.TOUR.values()
    # Taking the tour once takes the dot off Nox.
    from houseos.models import User

    db.expire_all()
    assert db.get(User, alice.id).preferences.get("tour_seen") is True


def test_sending_your_file_in_a_message_shares_it_with_the_recipients(domain):
    db, (alice, bob, cara) = domain
    entry = f.FileEntry(id=new_id(), owner_id=alice.id, scope="personal", name="plan.pdf", size=3)
    db.add(entry)
    db.commit()
    create(db, alice, "messages", {"body": "Here", "recipient_ids": [bob.id], "attachments": [entry.id]})
    grants = db.scalars(select(f.FileGrant).where(f.FileGrant.file_id == entry.id)).all()
    assert [g.user_id for g in grants] == [bob.id] and grants[0].expires_at
    with pytest.raises(HTTPException):  # bob may not re-share alice's file onwards
        create(db, bob, "messages", {"body": "Fwd", "recipient_ids": [cara.id], "attachments": [entry.id]})


def test_house_library_lists_kept_songs_for_residents_only(domain):
    db, (alice, _, _) = domain
    marker = "Library " + new_id()[:8]
    db.add(
        Record(
            kind="music.download",
            owner_id=alice.id,
            visibility="house",
            data={"state": "ready", "title": marker, "source_url": song(), "size": 10},
        )
    )
    db.commit()
    items = f.library(kind="music", q=marker, offset=0, actor=alice, db=db)["items"]
    assert [i["title"] for i in items] == [marker] and items[0]["first_by"] == "Alice"
    guest = Actor(alice.id, "Guest", "guest", alice.permissions)
    with pytest.raises(HTTPException):
        f.library(kind="music", q="", offset=0, actor=guest, db=db)
    assert f.audio_type(b"\x00\x00\x00\x20ftypM4A ") == (".m4a", "audio/mp4")


def test_house_stats_are_aggregates(music_domain):
    db, (alice, _, _), _ = music_domain
    played(db, alice, song())
    data = stats.compute(db)
    assert data["music"]["plays"] >= 1 and len(data["music"]["hours_of_day"]) == 24
    assert any(t["key"] == "dj" for t in data["titles"])
    assert set(data["movies"]) == {"month", "ever"}  # house totals only: no per-person films
    assert set(data["movies"]["month"]) == {"finished", "episodes", "hours", "kinds", "genres"}
    assert {t["family"] for t in data["titles"]} <= {"music", "house", "games"}
    assert all(0 <= t["stars"] <= 3 for t in data["titles"])
    assert any(t["key"] == "dj" for t in data["week"]) and all(t["stars"] == 0 for t in data["week"])


def test_an_empty_period_has_no_titles_and_no_crash():
    from zoneinfo import ZoneInfo

    scores = stats.boards_for([], ZoneInfo("Europe/Paris"), {})
    assert scores["songs"] == [] and stats.award(scores, {}, lambda key: {}, stars=False) == []


def test_the_radio_host_is_whoever_tunes_in_most_stations():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    when = datetime(2026, 9, 24, 20)
    plays = [
        ("a", when, {"key": "song", "radio": False}),
        ("b", when, {"key": "fip", "radio": True}),
        ("b", when, {"key": "old-station"}),  # recorded before the flag: known from history
        ("a", when, {"key": "old-station"}),
    ]
    scores = stats.boards_for(plays, ZoneInfo("Europe/Paris"), {}, frozenset({"old-station"}))
    assert scores["boards"]["radio_host"] == {"b": 2, "a": 1}
    titles = stats.award(scores, {}, lambda key: {"title": "?"}, stars=True)
    assert next(t for t in titles if t["key"] == "radio_host")["person"]["id"] == "b"


def test_a_title_is_always_its_leaders():
    from collections import Counter

    # The week once passed titles to runners-up: 1 rap song "guarded" rap over 160 and 105.
    boards = {key: Counter({"a": 9, "b": 2}) for key in ("dj", "explorer", "night_owl", "early_bird")}
    boards["genre_guardian"] = Counter({"a": 160, "c": 105, "b": 1})
    scores = {"boards": boards, "extra": {"genre_guardian": {"genre": "rap / hip-hop"}}, "songs": []}
    for stars in (False, True):
        titles = stats.award(scores, {}, lambda key: {"title": "?"}, stars=stars)
        assert {t["person"]["id"] for t in titles} == {"a"}
        assert next(t for t in titles if t["key"] == "genre_guardian")["value"] == 160
    assert all(t["stars"] == 0 for t in stats.award(scores, {}, lambda key: {}, stars=False))


def test_the_nudge_names_the_closest_title_the_viewer_does_not_hold():
    from collections import Counter

    boards = {"dj": Counter({"a": 10, "b": 8}), "planner": Counter({"a": 3, "b": 1}), "night_owl": Counter()}
    assert stats.nudge(boards, "b") == {"key": "dj", "n": 3} or stats.nudge(boards, "b") == {
        "key": "planner",
        "n": 3,
    }
    assert stats.nudge({"dj": Counter({"a": 10})}, "a") is None  # already holds it
    assert stats.nudge({"dj": Counter({"a": 100})}, "b") is None  # too far to tease


def test_finishing_a_task_records_who_and_when(domain):
    db, (alice, bob, _) = domain
    task = create(db, alice, "tasks", {"title": "Bins"})
    done = h.task_action(task["id"], h.TaskAction(action="complete", version=1), bob, db)
    assert done["data"]["completed_by"] == bob.id and done["data"]["completed_at"]
    assert stats.house_counters(db)["task_hero"][bob.id] >= 1
    assert stats.house_counters(db, stats.utcnow() - stats.timedelta(days=7))["task_hero"][bob.id] >= 1


def test_twenty_titles_and_favourites_make_a_curator(domain):
    from houseos.models import Record

    db, (alice, _, _) = domain
    assert len(stats.TITLES) % 5 == 0 and len({key for key, _, _ in stats.TITLES}) == len(stats.TITLES)
    db.add(Record(kind="saved_track", owner_id=alice.id, data={"source_url": "https://soundcloud.com/x/y"}))
    db.flush()
    try:
        assert stats.house_counters(db)["curator"][alice.id] >= 1
    finally:
        db.rollback()


def test_radio_title_from_icy_metadata():
    meta = b"StreamTitle='Daft Punk - One More Time';StreamUrl='';"
    blocks = (len(meta) + 15) // 16
    assert parse_icy(bytes([blocks]) + meta.ljust(blocks * 16, b"\0")) == "Daft Punk - One More Time"
    assert parse_icy(b"\x00") is None and parse_icy(b"") is None


def test_voice_auto_sends_only_clear_speech():
    good = [SimpleNamespace(avg_logprob=-0.2, no_speech_prob=0.05)]
    assert confident("mets du jazz", good, 0.95)
    assert not confident("jazz", good, 0.95)  # one word: probably a fragment
    assert not confident("mets du jazz", [SimpleNamespace(avg_logprob=-1.2, no_speech_prob=0.1)], 0.95)
    assert not confident("mets du jazz", [SimpleNamespace(avg_logprob=-0.2, no_speech_prob=0.7)], 0.95)
    assert not confident("mets du jazz", good, 0.4)


def test_a_file_already_inspected_is_not_probed_again(domain):
    db, (alice, _, _) = domain
    source = {"info_hash": new_id(), "file_id": "3", "inspection": {"audio": ["fre"]}}
    assert inspection_key({"file_id": "3"}) is None
    assert cached_inspection(db, source) is None
    remember_inspection(db, alice.id, source)
    db.commit()
    assert cached_inspection(db, {**source, "inspection": None}) == {"audio": ["fre"]}
    assert cached_inspection(db, {**source, "file_id": "4"}) is None


def test_a_song_replayed_from_the_house_copy_keeps_its_artwork(music_domain):
    from houseos import worker

    db, (alice, _, _), _ = music_domain
    source = "https://www.youtube.com/watch?v=" + new_id()[:11].replace("-", "a")
    db.add(
        m.QueueItem(
            owner_id=alice.id,
            source_url=source,
            title="First play",
            position=0,
            status="completed",
            metadata_json={"thumbnail": "https://i.ytimg.com/vi/x/hq.jpg", "genre": "rap / hip-hop"},
        )
    )
    db.commit()
    known = worker.remembered(db, source)
    assert known == {"thumbnail": "https://i.ytimg.com/vi/x/hq.jpg", "genre": "rap / hip-hop"}
    assert genre_of({**known, "title": "Vald - Gris"}) == "rap / hip-hop"
    assert worker.remembered(db, source + "x") == {}


def test_container_storage_is_a_real_writable_volume(monkeypatch, tmp_path):
    from pathlib import Path

    from houseos.config import settings

    monkeypatch.setattr(settings, "storage_container", True)
    monkeypatch.setattr(settings, "storage_mount", tmp_path)  # a plain folder, not a mount
    monkeypatch.setattr(settings, "data_root", tmp_path / "houseos")
    with pytest.raises(HTTPException):
        f.storage_check()
    monkeypatch.setattr(settings, "storage_mount", Path("/dev/shm"))  # a real tmpfs mount
    monkeypatch.setattr(settings, "data_root", Path("/dev/shm/houseos-storage-test"))
    assert f.storage_check()["status"] == "healthy"


def test_the_theme_studio_opens_with_five_questions_without_any_ai(domain):
    db, (alice, _, _) = domain
    admin = Actor(alice.id, alice.name, "admin", alice.permissions)
    # The studio lane runs in the background: the turn is run inline here.
    turn = a.open_turn(
        a.Chat(message="Start", purpose="themes", preset="theme_questions", idempotency_key=new_id()), admin, db
    )
    reply = a.finish_turn(turn, db)
    assert reply["status"] == "completed" and reply["reply"] in nox_presets.THEME_QUESTIONS.values()
    for text in nox_presets.THEME_QUESTIONS.values():
        assert text.count("?") <= 6 and len(text.split()) < 140  # five short questions, no wall
