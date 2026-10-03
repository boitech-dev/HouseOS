"""Assistant discovery cannot turn movie sentinels into a wrong episode job."""

from unittest.mock import patch

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import test_cinema
from houseos import cinema
from houseos.assistant_cinema_contract import AgentDiscover, discover
from houseos.auth import Actor
from houseos.models import Operation


@pytest.fixture
def fixture():
    value = test_cinema.CinemaTests()
    value.setUp()
    yield value
    value.tearDown()


def test_movie_zero_fields_enqueue_with_exact_request_and_no_device_calls(fixture):
    payload = dict(
        media_id=fixture.title_id,
        season=0,
        episode=0,
        position=840,
        idempotency_key="movie-contract-test",
        preferences={"audio_language": "fr", "subtitles_on": False, "quality": "1080p"},
    )
    with pytest.raises(ValidationError):
        cinema.Discover(**payload)  # The reported raw tool failure.
    with (
        Session(fixture.engine) as db,
        patch.object(cinema, "inspect_destination") as inspect,
        patch.object(cinema, "Comet") as comet,
    ):
        result = discover(AgentDiscover(**payload), fixture.actor, db)
        row = db.get(Operation, result["operation_id"])
        assert row.state == "accepted"
        assert row.data["season"] is None and row.data["episode"] is None
        assert row.data["position"] == 840
        assert row.data["preferences"]["audio_language"] == "fr"
        assert row.data["preferences"]["subtitles_on"] is False
        assert row.data["preferences"]["quality"] == "1080p"
        inspect.assert_not_called()
        comet.assert_not_called()


@pytest.mark.parametrize(
    "kind,season,episode", [("series", 1, 0), ("series", None, None), ("episode", 1, 0), ("movie", 1, 2)]
)
def test_inapplicable_or_ambiguous_episode_never_enqueues(fixture, kind, season, episode):
    with Session(fixture.engine) as db:
        title = db.get(cinema.CinemaTitle, fixture.title_id)
        title.kind, title.data = kind, {"season": 1, "episode": 2}
        if kind == "episode":
            db.add(
                cinema.CinemaTitle(
                    id="parent-series", canonical_id="tt456", title="Series", kind="series", data={}
                )
            )
            title.data = {**title.data, "parent_id": "parent-series"}
        db.commit()
        with pytest.raises(HTTPException) as error:
            discover(
                AgentDiscover(
                    media_id=title.id, season=season, episode=episode, idempotency_key="invalid-episode"
                ),
                fixture.actor,
                db,
            )
        assert error.value.status_code == 422
        assert db.scalar(select(func.count()).select_from(Operation)) == 0


def test_permission_and_canonical_title_checked_before_enqueue(fixture):
    with Session(fixture.engine) as db:
        body = AgentDiscover(media_id="invented-title", idempotency_key="canonical-check")
        with pytest.raises(HTTPException) as error:
            discover(body, Actor("guest", "Guest", "guest", frozenset()), db)
        assert error.value.status_code == 403
        with pytest.raises(HTTPException) as error:
            discover(body, fixture.actor, db)
        assert error.value.status_code == 404
        assert db.scalar(select(func.count()).select_from(Operation)) == 0


def test_series_specials_keep_season_zero_and_exact_episode(fixture):
    with Session(fixture.engine) as db:
        title = db.get(cinema.CinemaTitle, fixture.title_id)
        title.kind = "series"
        db.commit()
        result = discover(
            AgentDiscover(media_id=title.id, season=0, episode=3, idempotency_key="specials-valid"),
            fixture.actor,
            db,
        )
        row = db.get(Operation, result["operation_id"])
        assert row.data["season"] == 0 and row.data["episode"] == 3


def test_canonical_episode_enqueues_parent_and_exact_mapping(fixture):
    with Session(fixture.engine) as db:
        parent = db.get(cinema.CinemaTitle, fixture.title_id)
        parent.kind = "series"
        db.add(
            cinema.CinemaTitle(
                id="exact-episode",
                canonical_id="tt123:2:4",
                title="Episode four",
                kind="episode",
                data={"parent_id": parent.id, "season": 2, "episode": 4},
            )
        )
        db.commit()
        result = discover(
            AgentDiscover(media_id="exact-episode", idempotency_key="canonical-episode"), fixture.actor, db
        )
        row = db.get(Operation, result["operation_id"])
        assert row.data["media_id"] == parent.id
        assert row.data["season"] == 2 and row.data["episode"] == 4


@pytest.mark.parametrize("requested,expected", [(840, 840), (0, 0), (None, 300)])
def test_requested_position_overrides_watch_history_in_preflight(fixture, requested, expected):
    fixture.media["duration"] = 1000
    fixture.workflow()
    with (
        Session(fixture.engine) as db,
        patch.object(cinema, "inspect_destination", return_value={"state": "idle"}) as inspect,
    ):
        row = db.get(cinema.CinemaWorkflow, "workflow-one")
        row.data = {**row.data, "_requested_position": requested}
        db.add(
            cinema.CinemaState(
                owner_id=fixture.actor.id,
                media_id=fixture.title_id,
                data={"position": 300, "release_key": "release-one"},
            )
        )
        db.commit()
        result = cinema.prepare_plan(db, row, row.data["_sources"][0])
        assert result["plan"]["position"] == expected
        assert result["plan"]["duration"] == 1000
        assert result["confirmation_id"]
        inspect.assert_called_once()
