"""Watch: the suggestion ranks releases by the household's defaults, one tap plays the
reviewed choice from a chosen time, and Continue Watching follows series."""

from unittest.mock import patch

from sqlalchemy.orm import Session

import test_cinema
from houseos import cinema
from houseos.cinema_suggest import consensus_language, rank_inspected, rank_provisional
from houseos.db import utcnow

CAPS = {
    "inspected_at": "2026-09-23T00:00:00",
    "video_codecs": ["h264", "hevc"],
    "audio_codecs": ["aac", "eac3"],
    "hdr_modes": ["sdr", "hdr10"],
    "maximum_resolution": 2160,
    "max_audio_channels": 6,
    "containers": ["matroska", "mp4"],
    "embedded_subtitle_codecs": ["subrip"],
    "external_webvtt": True,
}


def media(height, audio=("en",), subtitles=(), codec="hevc", default=0):
    return {
        "video": {"index": 0, "codec": codec, "height": height, "hdr": "sdr"},
        "audio": [
            {"id": str(i + 1), "codec": "eac3", "language": lang, "channels": 6, "default": i == default}
            for i, lang in enumerate(audio)
        ],
        "subtitles": [
            {"id": str(10 + i), "codec": kind, "language": lang} for i, (lang, kind) in enumerate(subtitles)
        ],
        "container": "matroska",
        "duration": 6000,
        "evidence": "ffprobe",
    }


def source(identity, inspection, **extra):
    return {"id": identity, "release": identity, "rd_cached": True, "inspection": inspection, **extra}


def test_embedded_french_subtitles_beat_4k_without_them():
    sources = [
        source("4k-plain", media(2160)),
        source("1080-subs", media(1080, subtitles=[("fr", "subrip")])),
    ]
    ranked = rank_inspected(sources, CAPS, {"languages": ["fr", "en"]})
    assert [entry[0]["id"] for entry in ranked] == ["1080-subs", "4k-plain"]
    top_plan, reasons = ranked[0][1], ranked[0][3]
    assert top_plan["subtitle"]["language"] == "fr" and "fr subtitles in the file" in reasons


def test_french_dub_ranks_low_but_stays_available():
    sources = [
        source("dub-4k", media(2160, audio=("fr",))),
        source("multi-1080", media(1080, audio=("fr", "en"), default=0, subtitles=[("fr", "subrip")])),
        source("vo-1080", media(1080, audio=("en",))),
    ]
    assert consensus_language(sources) == "en"
    ranked = rank_inspected(sources, CAPS, {"audio_language": "fr"})
    order = [entry[0]["id"] for entry in ranked]
    assert order[0] == "multi-1080" and order[-1] == "dub-4k"
    multi_plan = ranked[0][1]
    assert multi_plan["audio"]["language"] == "en"  # original audio, not the default dub track


def test_always_subtitles_puts_a_subtitled_version_before_4k_even_in_the_first_language():
    sources = [
        source("4k-plain", media(2160)),
        source("1080-subs", media(1080, subtitles=[("fr", "subrip")])),
    ]
    usual = rank_inspected(sources, CAPS, {"languages": ["en", "fr"]})
    assert usual[0][0]["id"] == "4k-plain"  # English is understood: no subtitles needed
    always = rank_inspected(sources, CAPS, {"languages": ["en", "fr"], "always_subtitles": True})
    assert always[0][0]["id"] == "1080-subs" and always[0][1]["subtitle"]["language"] == "fr"
    assert "no subtitles in your languages" in always[1][3]


def test_cropped_films_keep_their_class_for_quality_and_ranking():
    from houseos.playback import compatibility, resolution

    scope = media(1600)
    scope["video"]["width"] = 3840
    assert resolution(scope["video"]) == 2160
    assert resolution({"width": 1920, "height": 800}) == 1080
    assert resolution({"width": 720, "height": 576}) == 576  # a DVD is not 720p
    compatibility(scope, CAPS, {"quality": "4k", "audio_language": "en"})  # no QUALITY_MISMATCH
    ranked = rank_inspected([source("scope", scope)], CAPS, {"languages": ["en"]})
    assert ranked[0][0]["id"] == "scope"


def test_hard_limits_still_reject():
    sources = [source("av1", media(1080, codec="av1")), source("fine", media(1080))]
    ranked = rank_inspected(sources, CAPS, {"audio_language": "de", "subtitle_language": "it"})
    assert [entry[0]["id"] for entry in ranked] == ["fine"]
    assert sources[0]["rejection"]["code"] == "VIDEO_MODE_UNSUPPORTED"


def test_a_film_nobody_follows_ranks_below_one_they_do():
    """Polish audio with only Polish subtitles, even in 4K, loses to 1080p they can follow."""
    polish = media(2160, audio=("pl",), subtitles=[("pl", "subrip")])
    sources = [
        source("pl-4k", polish),
        source("en-subs-1080", media(1080, audio=("pl",), subtitles=[("en", "subrip")])),
        source("fr-dub-720", media(720, audio=("pl", "fr"))),
    ]
    ranked = rank_inspected(sources, CAPS, {"languages": ["fr", "en"]}, original="pl")
    order = {entry[0]["id"]: entry for entry in ranked}
    assert ranked[-1][0]["id"] == "pl-4k" and "no audio or subtitles in your languages" in ranked[-1][3]
    assert order["fr-dub-720"][1]["audio"]["language"] == "fr"  # the dub they understand
    assert order["en-subs-1080"][1]["subtitle"]["language"] == "en"


def test_a_file_without_subtitles_is_ranked_not_rejected():
    """Subtitles on by default must not turn a file with none (or only bitmap ones) away."""
    bitmap = media(1080, subtitles=[("fr", "hdmv_pgs_subtitle")])
    sources = [source("none", media(1080)), source("bitmap", bitmap)]
    ranked = rank_inspected(sources, CAPS, {"subtitles_on": True, "subtitle_language": "fr"})
    assert {entry[0]["id"] for entry in ranked} == {"none", "bitmap"}
    assert all(entry[1]["subtitle_mode"] == "off" for entry in ranked)


def test_dolby_vision_remuxes_are_checked_last():
    sources = [
        {
            "id": "remux",
            "info_hash": "a",
            "release": "Film.2160p.REMUX.DV.HDR\nx",
            "height_claim": 2160,
            "rd_cached": True,
        },
        {
            "id": "x265",
            "info_hash": "b",
            "release": "Film.2160p.HDR.x265",
            "height_claim": 2160,
            "rd_cached": True,
        },
        {"id": "hd", "info_hash": "c", "release": "Film.1080p", "height_claim": 1080, "rd_cached": True},
    ]
    assert [s["id"] for s in rank_provisional(sources)] == ["x265", "hd", "remux"]


def test_probe_first_the_promising_releases():
    sources = [
        {
            "id": "a",
            "info_hash": "a",
            "release": "Film.2160p.TRUEFRENCH",
            "height_claim": 2160,
            "rd_cached": True,
        },
        {
            "id": "b",
            "info_hash": "b",
            "release": "Film.1080p.MULTI.VOSTFR",
            "height_claim": 1080,
            "rd_cached": True,
        },
        {"id": "c", "info_hash": "c", "release": "Film.4320p", "height_claim": 4320, "rd_cached": True},
        {"id": "d", "info_hash": "d", "release": "Film.1080p", "height_claim": 1080, "error": {"code": "X"}},
    ]
    assert [s["id"] for s in rank_provisional(sources)] == ["b", "a", "c"]


def test_a_4k_screen_probes_4k_before_a_1080p_multi_release():
    sources = [
        {
            "id": "multi",
            "info_hash": "a",
            "release": "Film 1080p MULTI",
            "height_claim": 1080,
            "rd_cached": True,
        },
        {
            "id": "dual",
            "info_hash": "b",
            "release": "Film.1080P-Dual-Lat",
            "height_claim": 1080,
            "rd_cached": True,
        },
        {
            "id": "uhd",
            "info_hash": "c",
            "release": "Film 2160p BluRay",
            "height_claim": 2160,
            "rd_cached": True,
        },
    ]
    assert rank_provisional(sources)[0]["id"] == "uhd"
    # A 1080p screen still starts with what it can show.
    assert rank_provisional(sources, maximum=1080)[-1]["id"] == "uhd"


def test_launch_plays_reviewed_tracks_from_the_chosen_time():
    f = test_cinema.CinemaTests()
    f.setUp()
    f.workflow()
    try:
        with Session(f.engine) as db:
            row = db.get(cinema.CinemaWorkflow, "workflow-one")
            row.data = {**row.data, "request": {"quality": "4k", "audio_language": "de"}}
            db.commit()
        played = {}

        def execute(db, row):
            played.update(row.data["plan"])
            return cinema.save_workflow(db, row, "command_sent")

        with (
            patch.object(cinema, "inspect_destination", return_value={"state": "idle"}),
            patch.object(cinema, "execute_play", side_effect=execute),
        ):
            result = f.client.post(
                "/api/v1/cinema/workflows/workflow-one/launch",
                json={
                    "version": 1,
                    "source_id": "source-one",
                    "device_id": f.device_id,
                    "audio_track": "1",
                    "subtitle_track": "off",
                    "position": 42,
                },
            )
        assert result.status_code == 200, result.text
        assert result.json()["state"] == "command_sent"
        assert played["position"] == 42 and played["audio"]["id"] == "1" and played["subtitle"] is None
        with Session(f.engine) as db:
            assert db.get(cinema.CinemaDevice, f.device_id).owner_workflow == "workflow-one"
        current = f.client.get("/api/v1/cinema/current").json()["current"]
        assert current["phase"] == "sending" and current["title"] == "Synthetic Film"
    finally:
        f.tearDown()


def test_shelves_resume_movies_and_start_the_next_episode():
    f = test_cinema.CinemaTests()
    f.setUp()
    try:
        with Session(f.engine) as db:
            series = cinema.CinemaTitle(
                id="series",
                canonical_id="tt9",
                title="Show",
                kind="series",
                data={"episodes": [{"season": 1, "episode": n, "title": f"Ep {n}"} for n in (1, 2, 3)]},
            )
            db.add(series)
            for n, position in ((1, 1190), (2, 1195)):
                episode = cinema.CinemaTitle(
                    id=f"ep{n}",
                    canonical_id=f"tt9:1:{n}",
                    title=f"Show · S01E0{n}",
                    kind="episode",
                    data={"parent_id": "series", "season": 1, "episode": n},
                )
                db.add(episode)
                db.flush()
                db.add(
                    cinema.CinemaState(
                        owner_id=f.actor.id,
                        media_id=episode.id,
                        data={"position": position, "duration": 1200},
                        last_watched_at=utcnow(),
                    )
                )
            db.add(
                cinema.CinemaState(
                    owner_id=f.actor.id,
                    media_id=f.title_id,
                    data={"position": 4416, "duration": 6000, "watchlist": True},
                    last_watched_at=utcnow(),
                )
            )
            db.commit()
        shelves = f.client.get("/api/v1/cinema/shelves").json()
        cards = {c["media_id"]: c for c in shelves["continue"]}
        assert cards[f.title_id]["action"] == "resume" and cards[f.title_id]["position"] == 4416
        nxt = cards["series"]
        assert nxt["action"] == "next" and (nxt["season"], nxt["episode"]) == (1, 3)
        assert len(shelves["continue"]) == 2  # one card per series
        assert [c["media_id"] for c in shelves["watchlist"]] == [f.title_id]
        assert shelves["saved"] == [] and set(shelves["sources"]) == {"jellyfin", "real_debrid", "streams"}
    finally:
        f.tearDown()


def test_opening_a_title_checks_the_three_best_releases():
    from houseos.cinema_jobs import start_suggestion
    from houseos.models import Job

    f = test_cinema.CinemaTests()
    f.setUp()
    f.workflow()
    try:
        releases = [
            {"id": f"r{n}", "info_hash": f"{n:040x}", "release": name, "height_claim": h, "rd_cached": True}
            for n, (name, h) in enumerate(
                [("A.2160p.FRENCH", 2160), ("B.1080p.MULTI", 1080), ("C.2160p", 2160), ("D.720p", 720)]
            )
        ]
        with Session(f.engine) as db:
            row = db.get(cinema.CinemaWorkflow, "workflow-one")
            row.data = {**row.data, "_sources": releases, "choice_set": {"candidates": []}}
            db.commit()
            result = start_suggestion(db, "workflow-one", "session")
            assert result["state"] == "preparing"
            assert result["suggestion_progress"] == {"checked": 0, "total": 3, "round": 1, "setbacks": []}
            row = db.get(cinema.CinemaWorkflow, "workflow-one")
            assert row.data["_validation_selection"] == ["r2", "r1", "r0"]  # 4K, then MULTI, dub last
            assert db.query(Job).filter(Job.kind == "cinema.validate").count() == 1
            # Nothing to do when a checked release is already on offer.
            row.state, row.data = "awaiting_choice", {**row.data, "choice_set": {"candidates": [{"id": "x"}]}}
            db.commit()
            assert start_suggestion(db, "workflow-one", "session") is None
    finally:
        f.tearDown()


def test_multi_and_dubbed_releases_do_not_outvote_the_original():
    sources = [
        source("multi", media(1080, audio=("en", "fr"))),
        source("vff", media(1080, audio=("fr",))),
        source("untagged", media(1080, audio=("und",))),
        source("vo", media(1080, audio=("en",))),
    ]
    assert consensus_language(sources) == "en"


def test_a_local_dub_listed_first_does_not_pass_for_the_original():
    # The Ministry of Ungentlemanly Warfare: Polish MULTi releases put their Polish dub first.
    sources = [
        source("pl1", media(2160, audio=("pl", "en", "en"))),
        source("fr", media(2160, audio=("fr", "en"))),
        source("pl2", media(2160, audio=("pl", "en", "en"))),
    ]
    assert consensus_language(sources) == "en"
    best = rank_inspected(sources, CAPS, {"languages": ["fr", "en"], "subtitle_language": "fr"})[0]
    assert best[1]["audio"]["language"] == "en" and "original audio" in best[3]


def test_forced_subtitles_are_never_the_default_choice():
    forced_default = media(1080, subtitles=[("fr", "subrip"), ("fr", "subrip")])
    forced_default["subtitles"][0].update(forced=True, default=True)
    plan = rank_inspected([source("s", forced_default)], CAPS, {"languages": ["fr"]})[0][1]
    assert plan["subtitle"]["id"] == forced_default["subtitles"][1]["id"]


def test_launch_asks_before_replacing_what_is_on_the_screen():
    f = test_cinema.CinemaTests()
    f.setUp()
    f.workflow()
    try:
        body = {"version": 1, "source_id": "source-one", "device_id": f.device_id, "subtitle_track": "off"}
        with (
            patch.object(
                cinema, "inspect_destination", return_value={"state": "playing", "item_id": "other"}
            ),
            patch.object(cinema, "execute_play", side_effect=AssertionError("played without asking")),
        ):
            asked = f.client.post("/api/v1/cinema/workflows/workflow-one/launch", json=body)
        assert asked.status_code == 200, asked.text
        assert asked.json()["state"] == "awaiting_playback_confirmation"
        assert asked.json()["plan"]["interrupts"]
    finally:
        f.tearDown()
