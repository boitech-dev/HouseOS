"""cinema_play: one call from a title to a film on the screen, picking by what was asked; and
cinema_versions, every version filtered. The house's own steps (discovery, checks, launch) are
faked here; their own tests cover them."""

import json
from unittest.mock import patch

from sqlalchemy.orm import Session

import test_cinema
from houseos import cinema, cinema_play
from houseos.agent_mcp import fitted
from houseos.cinema_models import CinemaWorkflow
from houseos.cinema_play import Play, choose, tracks, worth_checking
from houseos.models import Operation


def version(identity, resolution, size, subtitles=(), rank=1):
    return {
        "id": identity,
        "rank": rank,
        "resolution": resolution,
        "height": resolution,
        "size": size,
        "audio": [{"id": "1", "language": "en"}],
        "subtitles": [{"id": f"s-{code}", "language": code} for code in subtitles],
        "suggested_audio": {"id": "1", "language": "en"},
        "suggested_subtitle": {"id": "s-en", "language": "en"} if "en" in subtitles else None,
    }


def test_the_smallest_4k_with_french_inside_is_chosen_else_french_is_found_online():
    row = CinemaWorkflow(state="awaiting_choice", data={"choice_set": {"candidates": [
        version("big-4k-fr", 2160, 60e9, ["fr", "en"]),
        version("small-4k-en", 2160, 15e9, ["en"]),
        version("small-4k-fr", 2160, 20e9, ["fr"]),
        version("tiny-1080", 1080, 3e9, ["fr"]),
    ]}})  # fmt: skip
    asked = Play(title="x", resolution=2160, smallest=True, subtitles="fr", subtitles_inside=True)
    chosen = choose(row, asked, "fr")
    assert chosen["id"] == "small-4k-fr"
    assert tracks(chosen, asked, "fr") == ("1", "s-fr", None)  # from the file: timed to it
    smallest = choose(row, Play(title="x", resolution=2160, smallest=True), None)
    assert smallest["id"] == "small-4k-en"
    # French asked for, none in the file: found online, never the English ones standing in.
    assert tracks(smallest, Play(title="x", subtitles="fr"), "fr") == ("1", "auto", "fr")
    assert tracks(smallest, Play(title="x", subtitles="off"), None)[1] == "off"
    assert tracks(smallest, Play(title="x"), None)[1] == "s-en"  # the person's usual ones


def test_smaller_cached_versions_not_checked_yet_are_checked_once():
    row = CinemaWorkflow(state="awaiting_choice", data={
        "choice_set": {"candidates": [version("checked", 2160, 30e9)]},
        "_sources": [
            {"id": "checked", "info_hash": "a" * 40, "rd_cached": True, "inspection": {}},
            {"id": "smaller", "info_hash": "b" * 40, "rd_cached": True, "height_claim": 2160, "size": 9e9},
            {"id": "uncached", "info_hash": "c" * 40, "rd_cached": False, "height_claim": 2160, "size": 5e9},
            {"id": "hd", "info_hash": "d" * 40, "rd_cached": True, "height_claim": 1080, "size": 2e9},
        ],
    })  # fmt: skip
    asked = Play(title="x", resolution=2160, smallest=True)
    chosen = choose(row, asked, None)
    assert worth_checking(row, asked, None, chosen) == ["smaller"]
    row.data = {**row.data, "_play_checked_more": True}
    assert worth_checking(row, asked, None, chosen) == []  # one more round only
    assert worth_checking(row, Play(title="x"), None, chosen) == []  # nothing asked beyond the best


def test_one_call_plays_the_film_and_says_what_plays_in_one_line():
    f = test_cinema.CinemaTests()
    f.setUp()
    f.workflow()
    with Session(f.engine) as db:
        row = db.get(CinemaWorkflow, "workflow-one")
        row.data = {**row.data, "choice_set": {"candidates": [version("source-one", 1080, 4e9, ["fr"])]}}
        db.add(Operation(id="op-play", actor_id=f.actor.id, kind="cinema.discover", state="completed",
                         data={}, result={"workflow_id": "workflow-one"}))  # fmt: skip
        db.commit()
    launched = []

    def launch(identity, body, actor, db):
        launched.append(body)
        row = db.get(CinemaWorkflow, identity)
        row.state = "playing_observed"
        row.data = {**row.data, "plan": {"audio": {"language": "en"}, "subtitle": {"language": "fr"}}}
        db.commit()
        return {"state": "command_sent"}

    try:
        with (
            Session(f.engine) as db,
            patch.object(
                cinema_play.cinema_jobs, "enqueue_discovery", return_value={"operation_id": "op-play"}
            ),
            patch.object(cinema, "launch", side_effect=launch),
            patch.object(cinema_play.time, "sleep"),
        ):
            # By its IMDb id: no search needed.
            said = cinema_play.play(
                Play(title="tt123", subtitles="fr", position=0, device_id=f.device_id), f.actor, db
            )
        assert said["status"] == "playing", said
        assert said["message"].startswith(
            "Playing Synthetic Film on Test: 1080p, 4.0 GB, en audio, fr subtitles"
        )
        body = launched[0]
        assert (body.source_id, body.subtitle_track, body.subtitle_language, body.position) == (
            "source-one", "s-fr", "fr", 0,
        )  # fmt: skip
    finally:
        f.tearDown()


def test_a_relaunch_with_other_subtitles_prepares_the_stream_again():
    f = test_cinema.CinemaTests()
    f.setUp()
    f.workflow()
    with Session(f.engine) as db:
        row = db.get(CinemaWorkflow, "workflow-one")
        row.state = "recovery_required"
        row.data = {**row.data, "plan": {"source_id": "source-one", "audio": {"id": "1"}, "subtitle": {"id": "2"}},
                    "_prepared": {"path": "/x/master.m3u8", "streaming": True}}  # fmt: skip
        db.commit()
    seen = []
    try:
        with patch.object(
            cinema,
            "prepare_plan",
            side_effect=lambda db, row, source: (
                seen.append(row.data["_prepared"]) or {"plan": {"interrupts": True}}
            ),
        ):
            f.client.post("/api/v1/cinema/workflows/workflow-one/launch", json={
                "version": 1, "source_id": "source-one", "device_id": f.device_id,
                "audio_track": "1", "subtitle_track": "3"})  # fmt: skip
        assert seen == [None]  # English built in last time: French needs a stream of its own
    finally:
        f.tearDown()


def test_long_answers_stay_valid_json_shortening_lists_first():
    result = {"items": [{"title": "Song " + str(n), "detail": "x" * 200} for n in range(80)], "total": 80}
    text = fitted(result)
    assert len(text) <= 4000
    shown = json.loads(text)  # never cut in the middle
    assert shown["total"] == 80 and shown["items"][-1].endswith("more")


def test_playing_again_after_a_failed_try_starts_clean():
    from houseos.cinema import CinemaRelay
    from houseos.db import utcnow

    f = test_cinema.CinemaTests()
    f.setUp()
    f.workflow()
    with Session(f.engine) as db:
        row = db.get(CinemaWorkflow, "workflow-one")
        row.state = "recovery_required"
        row.data = {**row.data, "_release_after_load": "the-film-before", "_seek_previous": {"state": "playing"},
                    "_prepared": {"path": "/x/master.m3u8", "streaming": True}}  # fmt: skip
        db.add(CinemaRelay(token_hash="t" * 64, workflow_id=row.id, device_address="192.0.2.17", path="/x/master.m3u8",
                           mime="application/x-mpegURL", expires_at=utcnow()))  # fmt: skip
        db.commit()
    seen = []
    try:
        with patch.object(
            cinema,
            "prepare_plan",
            side_effect=lambda db, row, source: (
                seen.append(
                    (dict(row.data), db.query(CinemaRelay).filter(CinemaRelay.workflow_id == row.id).count())
                )
                or {"plan": {"interrupts": True}}
            ),
        ):
            f.client.post("/api/v1/cinema/workflows/workflow-one/launch", json={
                "version": 1, "source_id": "source-one", "device_id": f.device_id})  # fmt: skip
        data, links = seen[0]
        assert not data["_release_after_load"] and not data["_seek_previous"] and not data["_prepared"]
        assert links == 0  # the failed try's stream links are gone
    finally:
        f.tearDown()


def test_a_dub_asked_for_only_picks_versions_that_have_it():
    fr = {
        **version("fr-av1", 1080, 2e8),
        "audio": [{"id": "3", "language": "fr"}, {"id": "1", "language": "ja"}],
    }
    row = CinemaWorkflow(
        state="awaiting_choice", data={"choice_set": {"candidates": [version("ja-only", 1080, 2e9), fr]}}
    )
    asked = Play(title="x", audio="fr", subtitles="off")
    chosen = choose(row, asked, None)
    assert chosen["id"] == "fr-av1" and tracks(chosen, asked, None) == ("3", "off", None)


def test_nothing_found_is_said_at_once_and_the_next_call_searches_again():
    f = test_cinema.CinemaTests()
    f.setUp()
    f.workflow()
    with Session(f.engine) as db:
        row = db.get(CinemaWorkflow, "workflow-one")
        row.state, row.data = "discovered", {**row.data, "_sources": [], "choice_set": {"candidates": []}}
        db.add(Operation(id="op-none", actor_id=f.actor.id, kind="cinema.discover", state="completed",
                         data={}, result={"workflow_id": "workflow-one"}))  # fmt: skip
        db.commit()
    try:
        with (
            Session(f.engine) as db,
            patch.object(
                cinema_play.cinema_jobs, "enqueue_discovery", return_value={"operation_id": "op-none"}
            ),
            patch.object(cinema_play.time, "sleep"),
        ):
            started = cinema_play.time.monotonic()
            said = cinema_play.play(Play(title="tt123", device_id=f.device_id), f.actor, db)
            assert said["status"] == "not_found" and cinema_play.time.monotonic() - started < 5
            assert db.get(CinemaWorkflow, "workflow-one").data["_play_key"] is None  # not reused
    finally:
        f.tearDown()


def test_busy_answers_say_when_to_call_again_and_a_repeat_never_launches_twice():
    from houseos.cinema_play import answer, progress

    busy = answer("working", "Still checking versions.", progress={"step": "checking", "done": 1, "total": 3})
    assert busy["retry_after"] == 5 and busy["progress"]["done"] == 1
    assert "retry_after" not in answer("failed", "No.")
    row = CinemaWorkflow(
        state="preparing", data={"plan": {"source_id": "s"}, "download": {"bytes": 300, "total": 1200}}
    )
    assert progress(row) == {"step": "preparing", "percent": 25}

    f = test_cinema.CinemaTests()
    f.setUp()
    f.workflow()
    with Session(f.engine) as db:
        row = db.get(CinemaWorkflow, "workflow-one")
        key = ["title-one", None, None, "original", None, False, None, False, f.device_id]
        row.state = "playing_observed"
        row.data = {
            **row.data,
            "_play_key": key,
            "plan": {"source_id": "source-one", "audio": {"language": "en"}},
        }
        db.commit()
    try:
        with (
            Session(f.engine) as db,
            patch.object(cinema, "launch") as launch,
            patch.object(cinema_play.time, "sleep"),
        ):
            said = cinema_play.play(Play(title="tt123", device_id=f.device_id), f.actor, db)
        assert said["status"] == "playing" and not launch.called  # reported, not launched again
    finally:
        f.tearDown()


def test_a_version_to_fetch_is_fetched_checked_every_minute_and_played_once_there(monkeypatch):
    from datetime import timedelta

    from houseos.db import utcnow

    f = test_cinema.CinemaTests()
    f.setUp()
    f.workflow()
    fetchable = {"id": "fetch-me", "info_hash": "b" * 40, "release": "Show VF 1080p", "height_claim": 1080,
                 "rd_cached": False, "cache_evidence": "rd_download", "provider": "rd_download", "provider_order": 0}  # fmt: skip
    with Session(f.engine) as db:
        row = db.get(CinemaWorkflow, "workflow-one")
        row.data = {**row.data, "_sources": [fetchable], "choice_set": {"candidates": []}}
        db.commit()
    queued = []
    monkeypatch.setattr(
        "houseos.cinema_jobs.enqueue_validation", lambda db, row, ids, s: queued.append(ids) or {"id": row.id}
    )
    try:
        # Picked: added to the debrid account (a check of that one), to play on the screen once there.
        made = f.client.post("/api/v1/cinema/workflows/workflow-one/fetch",
                             json={"version": 1, "source_id": "fetch-me", "device_id": f.device_id, "position": 0})  # fmt: skip
        assert made.status_code == 200, made.text
        assert queued == [["fetch-me"]]
        with Session(f.engine) as db:
            row = db.get(CinemaWorkflow, "workflow-one")
            assert row.state == "preparing" and row.data["_fetching"]["play"]["device_id"] == f.device_id
            # Still fetching: the next round (a minute later) checks it again.
            row.state = "awaiting_choice"
            row.data = {
                **row.data,
                "_fetching": {
                    **row.data["_fetching"],
                    "checked_at": (utcnow() - timedelta(minutes=2)).isoformat(),
                },
            }
            db.commit()
            cinema.fetch_rounds(db)
            assert queued == [["fetch-me"], ["fetch-me"]]
            # There: it plays as asked.
            row = db.get(CinemaWorkflow, "workflow-one", populate_existing=True)
            row.state = "awaiting_choice"
            row.data = {**row.data, "_fetching": {**row.data["_fetching"], "status": "ready"}}
            db.commit()
            with patch.object(cinema_play, "launch_fetched") as played:
                cinema.fetch_rounds(db)
            assert played.called
            # Six hours without it: given up, with why.
            row = db.get(CinemaWorkflow, "workflow-one", populate_existing=True)
            row.data = {
                **row.data,
                "_fetching": {
                    **row.data["_fetching"],
                    "status": "fetching",
                    "since": (utcnow() - timedelta(hours=7)).isoformat(),
                },
            }
            db.commit()
            cinema.fetch_rounds(db)
            assert (
                db.get(CinemaWorkflow, "workflow-one", populate_existing=True).data["_fetching"]["status"]
                == "failed"
            )
    finally:
        f.tearDown()


def test_cinema_play_fetches_when_nothing_instant_fits():
    row = CinemaWorkflow(
        state="discovered",
        data={"_sources": [{"id": "x", "cache_evidence": "rd_download", "info_hash": "c" * 40}]},
    )
    from houseos.cinema_play import checkable

    assert not checkable(row)  # nothing the house checks on its own: no waiting on it
    said = cinema_play.fetching_answer(CinemaWorkflow(id="w", data={"_fetching": {"progress": 35}}),
                                       type("T", (), {"title": "Show"})(), type("D", (), {"name": "TV"})())  # fmt: skip
    assert (
        said["status"] == "working"
        and said["retry_after"] == 60
        and said["progress"] == {"step": "fetching", "percent": 35}
    )


def test_a_fetched_version_without_the_dub_asked_for_is_never_played_in_another_language():
    f = test_cinema.CinemaTests()
    f.setUp()
    f.workflow()
    with Session(f.engine) as db:
        row = db.get(CinemaWorkflow, "workflow-one")
        row.data = {**row.data, "choice_set": {"candidates": [version("got", 1080, 2e9)]}}  # English only
        db.commit()
        fetching = {
            "source_id": "got",
            "status": "done",
            "play": {"device_id": f.device_id, "audio_language": "fr"},
        }
        with patch.object(cinema, "launch") as launch:
            cinema_play.launch_fetched(db, db.get(CinemaWorkflow, "workflow-one"), fetching)
        assert not launch.called
        said = db.get(CinemaWorkflow, "workflow-one", populate_existing=True).data["_fetching"]
        assert said["status"] == "failed" and "no fr audio" in said["error"]
    f.tearDown()


def test_check_only_says_what_exists_and_plays_nothing_then_play_reuses_it():
    f = test_cinema.CinemaTests()
    f.setUp()
    f.workflow()
    with Session(f.engine) as db:
        row = db.get(CinemaWorkflow, "workflow-one")
        row.data = {**row.data, "choice_set": {"candidates": [version("source-one", 1080, 4e9, ["fr"])]}}
        db.add(Operation(id="op-look", actor_id=f.actor.id, kind="cinema.discover", state="completed",
                         data={}, result={"workflow_id": "workflow-one"}))  # fmt: skip
        db.commit()
    try:
        with (
            Session(f.engine) as db,
            patch.object(
                cinema_play.cinema_jobs, "enqueue_discovery", return_value={"operation_id": "op-look"}
            ) as found,
            patch.object(cinema, "launch") as launch,
            patch.object(cinema_play.time, "sleep"),
            patch.object(cinema_play, "WAIT", 0.2),
        ):
            said = cinema_play.play(Play(title="tt123", device_id=f.device_id, check_only=True), f.actor, db)
            assert said["status"] == "found" and not launch.called
            assert "it would play 1080p, 4.0 GB, audio en, subtitles fr" in said["message"]
            assert said["versions"][0] == {
                "id": "source-one",
                "instant": True,
                "summary": "1080p, 4.0 GB, audio en, subtitles fr",
            }
            launch.return_value = {"state": "command_sent"}
            cinema_play.play(Play(title="tt123", device_id=f.device_id), f.actor, db)
            assert launch.called and found.call_count == 1  # the same checked versions, not a new search
    finally:
        f.tearDown()


def test_what_played_on_the_screens_is_the_house_s_to_see():
    from houseos.db import utcnow

    f = test_cinema.CinemaTests()
    f.setUp()
    f.workflow()
    with Session(f.engine) as db:
        row = db.get(CinemaWorkflow, "workflow-one")
        row.state = "completed"
        row.data = {
            **row.data,
            "checkpoint": {"position": 3000, "duration": 6000, "at": utcnow().isoformat()},
        }
        db.commit()
        items = cinema_play.screen_history(cinema_play.ScreenHistory(), f.actor, db)["items"]
    f.tearDown()
    assert (
        items[0]["title"] == "Synthetic Film"
        and items[0]["progress"] == "50%"
        and items[0]["screen"] == "Test"
    )
