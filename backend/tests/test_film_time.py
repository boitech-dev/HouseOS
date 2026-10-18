"""What the film bar and the controls show is where the film really is (2026-10-18 review)."""

from unittest.mock import patch

from sqlalchemy.orm import Session

import houseos.cinema_sleep  # noqa: F401 (registers the sleep routes)
import test_cinema
from houseos import cinema
from test_cinema_current_queue import setup_active


def report(state, position=50):
    return {"item_id": "fixture-film", "state": state, "session_id": 1, "position": position, "duration": 100}


def playing_on_cast(f):
    setup_active(f)
    with Session(f.engine) as db:
        device = db.get(cinema.CinemaDevice, f.device_id)
        device.adapter = "cast"
        device.capabilities = {**device.capabilities, "seek": True}
        db.commit()


def observe(f, receiver):
    version = f.client.get("/api/v1/cinema/workflows/workflow-one").json()["version"]
    with patch.object(cinema, "inspect_destination", return_value=receiver):
        return f.client.post("/api/v1/cinema/workflows/workflow-one/observe", json={"version": version})


def current(f):
    return f.client.get("/api/v1/cinema/current").json()["current"]


def test_buffering_and_a_seek_keep_the_film_in_the_bar_at_the_right_place():
    f = test_cinema.CinemaTests()
    f.setUp()
    try:
        playing_on_cast(f)
        before = current(f)["checkpoint"]["position"]
        observe(f, report("buffering"))
        assert current(f)["checkpoint"]["position"] == before  # still in the bar, where it was
        observe(f, report("active", 52))
        with patch("houseos.cinema_cast.cast_control"):
            sought = f.client.post(
                "/api/v1/cinema/workflows/workflow-one/control",
                json={"version": 1, "action": "seek", "position": 80},
            )
        assert sought.status_code == 200, sought.text
        assert current(f)["checkpoint"]["position"] == 80  # the bar shows where it goes at once
        observe(f, report("buffering", 80))
        shown = current(f)
        assert shown and shown.get("phase") is None and shown["can_seek"]  # controls stay
        assert shown["checkpoint"]["position"] == 80
    finally:
        f.tearDown()


def test_the_sleep_timer_takes_a_tap_made_a_few_reports_ago():
    f = test_cinema.CinemaTests()
    f.setUp()
    try:
        playing_on_cast(f)
        seen = current(f)["version"]
        observe(f, report("active", 47))  # the receiver reported meanwhile
        made = f.client.post(
            "/api/v1/cinema/workflows/workflow-one/sleep", json={"version": seen, "minutes": 60}
        )
        assert made.status_code == 200, made.text
        assert f.client.get("/api/v1/cinema/workflows/workflow-one/sleep").json()["timer"]
    finally:
        f.tearDown()


def test_a_film_watched_to_the_end_starts_again_from_the_beginning():
    f = test_cinema.CinemaTests()
    f.setUp()
    f.workflow()
    try:
        with Session(f.engine) as db:
            row = db.get(cinema.CinemaWorkflow, "workflow-one")
            duration = f.media.get("duration")
            state = cinema.own_state(db, "resident-one", row.media_id)
            state.data = {
                **state.data,
                "position": duration,
                "duration": duration,
                "watched": True,
                "release_key": "release-one",
            }
            db.commit()
        with patch("houseos.cinema.inspect_destination", return_value={"state": "idle"}):
            changed = f.client.post(
                "/api/v1/cinema/workflows/workflow-one/change",
                json={"version": 1, "source_choice": "source-one"},
            )
        assert changed.status_code == 200, changed.text
        assert changed.json()["plan"]["position"] == 0
    finally:
        f.tearDown()


def test_watching_again_from_earlier_offers_to_resume_until_the_end():
    seen = {"watched": True}
    assert not cinema.watched_now(seen, {"position": 0}, 3600, 7200)  # halfway on a rewatch
    assert cinema.watched_now(seen, {"position": 6900}, 6950, 7200)  # resumed near the end
    assert cinema.watched_now({}, {"position": 0}, 6900, 7200)  # 95 %
    assert not cinema.watched_now({}, {"position": 0}, 3600, 7200)
