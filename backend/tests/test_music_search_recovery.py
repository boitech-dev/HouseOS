"""A bad candidate reference must be repairable without partial queue writes."""

import json
import pytest
from sqlalchemy import select
from houseos import assistant as a, music as m
from houseos.db import new_id
from houseos.models import Record
from test_security import stub_provider_setup


@pytest.mark.parametrize("repeat_invalid", [False, True])
def test_music_selection_can_repair_once_without_research(music_domain, monkeypatch, repeat_invalid):
    db, (actor, _, _), queue = music_domain
    stub_provider_setup(monkeypatch)
    candidates = []
    for i in range(10):
        row = Record(
            kind="music_candidate",
            owner_id=actor.id,
            data={"title": f"Song {i}", "source_url": f"https://soundcloud.com/fixture/track-{i}"},
        )
        db.add(row)
        db.flush()
        candidates.append({"id": row.id, **row.data})
    db.commit()
    monkeypatch.setattr(m, "search", lambda *args, **kwargs: {"status": "completed", "items": candidates})
    rounds = []

    def provider(*args):
        rounds.append(1)
        if not args[3]:
            return (
                "Those song references could not be resolved. No songs were added.",
                [],
                [],
                {"input_tokens": 1, "output_tokens": 1},
            )
        if len(rounds) == 1:
            call = {"id": "search", "name": "music_search", "args": {"query": "Yung Beef"}}
        elif len(rounds) == 2:
            call = {
                "id": "bad",
                "name": "music_add_candidates",
                "args": {"candidate_ids": [new_id()], "idempotency_key": "fixture-invalid"},
            }
        else:
            feedback = json.loads(args[2][-1].get("content", args[2][-1].get("output")))
            assert feedback["code"] == "INVALID_CANDIDATE_REFERENCE"
            assert len(feedback["candidates"]) == 10
            assert not list(db.scalars(select(m.QueueItem).where(m.QueueItem.owner_id == actor.id)))
            call = {
                "id": "fixed",
                "name": "music_add_candidates",
                "args": {
                    "candidate_ids": [new_id()] if repeat_invalid else [r["id"] for r in candidates],
                    "idempotency_key": "fixture-valid",
                },
            }
        return "", [call], {"role": "assistant", "content": None}, {"input_tokens": 1, "output_tokens": 1}

    monkeypatch.setattr(a, "provider_round", provider)
    result = a.chat(
        a.Chat(message="Add 10 Yung Beef songs, no duplicates", context="music", idempotency_key=new_id()),
        actor,
        db,
    )
    assert len(rounds) == 3  # a stopped action or queued batch needs no narration round
    if repeat_invalid:
        assert result["status"] == "action_stopped"
    else:
        assert result["cards"][-1]["count"] == 10
    assert len(list(db.scalars(select(m.QueueItem).where(m.QueueItem.owner_id == actor.id)))) == (
        0 if repeat_invalid else 10
    )


def test_ten_result_search_and_queue_duplicate_filter(music_domain, monkeypatch):
    from houseos import worker, fetcher

    db, (actor, _, _), q = music_domain
    entries = [{"url": f"https://soundcloud.com/fixture/song-{i}", "title": f"Song {i}"} for i in range(10)]
    observed = []

    def process(args, *rest):
        observed.append(args)
        return json.dumps({"entries": entries})

    monkeypatch.setattr(fetcher, "bounded_process", process)
    monkeypatch.setattr(worker, "fetch", lambda action, **kw: fetcher.execute({"action": action, **kw}))
    result = m.search("Yung Beef", "soundcloud", actor, db, limit=10)
    assert len(result["items"]) == 10
    assert observed[0][-1] == "scsearch10:Yung Beef"
    ids = [x["id"] for x in result["items"]]
    first = m.add_candidates(m.CandidateBatch(candidate_ids=ids[:1], idempotency_key=new_id()), actor, db)
    body = m.CandidateBatch(candidate_ids=ids, avoid_duplicates=True, idempotency_key=new_id())
    rest = m.add_candidates(body, actor, db)
    assert first["count"] == 1 and rest["count"] == 9 and rest["duplicates_skipped"] == 1
    assert m.add_candidates(body, actor, db) == rest
    assert len(list(db.scalars(select(m.QueueItem).where(m.QueueItem.owner_id == actor.id)))) == 10
    for message in (
        "add 10 songs to the queue from yung beef, no duplicates",
        "ajoute 10 chansons à la file",
    ):
        assert {"music_search", "music_add_candidates"} <= set(a.tool_registry(a.initial_context(message)))


def test_a_song_kept_at_home_comes_first_and_works_offline(music_domain, monkeypatch):
    from houseos import worker

    db, (actor, _, _), q = music_domain
    kept = "https://www.youtube.com/watch?v=keptathome1"
    db.add(
        Record(
            kind="music.download",
            owner_id=actor.id,
            data={"state": "ready", "source_url": kept, "title": "Lucid Dreams", "uploader": "Juice WRLD"},
        )
    )
    db.commit()
    online = [
        {"source_url": kept, "title": "Lucid Dreams (video)"},
        {"source_url": "https://www.youtube.com/watch?v=online00001", "title": "Lucid Dreams live"},
    ]
    monkeypatch.setattr(worker, "fetch", lambda action, **kw: {"status": "completed", "items": online})
    found = m.search("juice luci", "youtube", actor, db, limit=5)["items"]
    assert [(i["source_url"], i.get("at_home")) for i in found] == [
        (kept, True),
        (online[1]["source_url"], None),
    ]
    # Offline: the song at home still shows; nothing at home keeps the fetcher's answer.
    monkeypatch.setattr(
        worker, "fetch", lambda action, **kw: {"status": "failed", "code": "FETCH_UNAVAILABLE"}
    )
    assert [i["source_url"] for i in m.search("lucid", "youtube", actor, db, limit=5)["items"]] == [kept]
    assert m.search("nothing here", "youtube", actor, db, limit=5)["code"] == "FETCH_UNAVAILABLE"
