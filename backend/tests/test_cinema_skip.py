"""Skipping openings and endings: each episode's own marks, once, never a guess."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

from houseos import cinema, cinema_skip
from houseos.playback import MediaError

EPISODE = [  # chapters as an anime release names them
    {"start": 0, "end": 30, "title": "Avant"},
    {"start": 30, "end": 120, "title": "OP"},
    {"start": 120, "end": 603, "title": "Part A"},
    {"start": 603, "end": 1345, "title": "Part B"},
    {"start": 1345, "end": 1435, "title": "ED"},
    {"start": 1435, "end": 1446, "title": "Next"},
]


def test_chapters_name_the_opening_and_ending_and_nothing_else():
    assert cinema_skip.from_chapters(EPISODE) == [
        {"kind": "op", "start": 30, "end": 120},
        {"kind": "ed", "start": 1345, "end": 1435},
    ]
    # A label on half the episode is not an opening; an episode titled "Opening Night" is not one.
    assert not cinema_skip.from_chapters([{"start": 0, "end": 700, "title": "Opening"}])
    assert not cinema_skip.from_chapters([{"start": 0, "end": 90, "title": "Opening Night"}])


def test_aniskip_times_count_only_for_an_episode_as_long_as_this_file(monkeypatch):
    answer = {
        "results": [
            {"skipType": "op", "interval": {"startTime": 153.3, "endTime": 243.3}, "episodeLength": 1469.9},
            {"skipType": "ed", "interval": {"startTime": 1370, "endTime": 1460}, "episodeLength": 1490},
        ]
    }
    monkeypatch.setattr(cinema_skip, "public_fetch", lambda url: (json.dumps(answer).encode(), {}))
    assert cinema_skip.from_aniskip("mal:1", 5, 1470) == [{"kind": "op", "start": 153.3, "end": 243.3}]
    assert cinema_skip.from_aniskip("tmdb:1", 5, 1470) == []  # only anime are listed there

    def missing(url):
        raise MediaError("SOURCE_NOT_READY", "404", "resolve")

    monkeypatch.setattr(cinema_skip, "public_fetch", missing)
    assert cinema_skip.from_aniskip("mal:2", 1, 1446) == []


def test_it_skips_each_mark_once_and_an_ending_lands_just_before_the_end(monkeypatch):
    seeks = []
    monkeypatch.setattr(cinema, "control", lambda identity, body, actor, db: seeks.append(body.position))
    row = SimpleNamespace(
        id="w",
        version=3,
        state="playing_observed",
        data={
            "request": {"skip_intros": True},
            "observation": {"state": "active"},
            "plan": {"duration": 1446},
            "_skips": [{"kind": "op", "start": 30, "end": 120}, {"kind": "ed", "start": 1350, "end": 1446}],
            "checkpoint": {"position": 33},
        },
    )
    db = SimpleNamespace(commit=Mock(), rollback=Mock())
    cinema_skip.skip_now(db, row, None)
    assert seeks == [120] and row.data["_skip_note"]["kind"] == "op"
    cinema_skip.skip_now(db, row, None)  # sent back to watch it: it plays
    assert seeks == [120]
    row.data["checkpoint"] = {"position": 1352}
    cinema_skip.skip_now(db, row, None)
    assert seeks == [120, 1440]
    # Turned off at launch: nothing is skipped.
    row.data = {**row.data, "request": {}, "_skipped": [], "checkpoint": {"position": 40}}
    cinema_skip.skip_now(db, row, None)
    assert seeks == [120, 1440]
