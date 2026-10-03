"""Configured addon contract with synthetic provider replies, never account requests."""

from urllib.parse import urlsplit
from cryptography.fernet import Fernet
import pytest
from houseos import cinema_sources as sources
from houseos.cinema_models import CinemaWorkflow
from houseos.playback import MediaError

KEY = "fixturekey"
HOST = "addon.example"
HASH = "a" * 40
LINK = f"https://addon.example/resolve/realdebrid/{KEY}/{HASH}/null/4/Movie.mkv"


def test_only_exact_configured_rd_plus_preserves_provider_order():
    rows = [
        None,
        {"name": "[RD] Add-on", "url": LINK},
        {"name": "[RD+] Add-on 1080p", "url": LINK, "title": "Movie 👤 12", "behaviorHints": None},
        {
            "name": "[RD+] Add-on 2160p",
            "url": LINK.replace("/4/", "/5/"),
            "behaviorHints": {"videoSize": 123},
        },
        {"name": "[RD+]", "url": LINK},
        {"name": "[RD+]", "url": LINK.replace(KEY, "otherkey")},
        {"name": "[RD+]", "url": LINK.replace("addon.example", "evil.invalid")},
    ]
    result = sources.normalize_streams({"streams": rows}, HOST, KEY)
    assert [r["file_index"] for r in result] == [4, 5]
    assert [r["height_claim"] for r in result] == [1080, 2160]
    assert result[0]["seeders_claim"] == 12
    assert KEY not in str(result) and "https://" not in str(result)
    assert sources.normalize_streams({"streams": None}, HOST, KEY) == []


@pytest.fixture
def resolver(monkeypatch):
    monkeypatch.setattr(sources.settings, "encryption_key", Fernet.generate_key().decode())
    monkeypatch.setattr(
        sources,
        "integration_config",
        lambda *_: {"manifest_url": f"https://addon.example/realdebrid={KEY}/manifest.json"},
    )
    monkeypatch.setattr(sources, "public_url", lambda u: (urlsplit(u), "203.0.113.1"))
    calls = []
    reply = {"url": "https://cdn.example.invalid/opaque-file", "status": 302}

    def request(url, host, limit=0):
        calls.append(url)
        if reply["status"] == 403:
            raise MediaError("PROVIDER_ACCESS_DENIED", "Provider denied", "resolve")
        return {"status": reply["status"], "location": reply["url"]}

    monkeypatch.setattr(sources, "addon_request", request)
    monkeypatch.setattr(
        "houseos.cinema_adapters.public_stream",
        lambda *_: (206, {"Content-Range": "bytes 0-0/123"}, iter([b"x"])),
    )
    source = sources.normalize_streams(
        {"streams": [{"name": "[RD+]", "url": LINK, "behaviorHints": {"videoSize": 123}}]}, HOST, KEY
    )[0]
    return source, calls, reply


def test_resolve_accepts_public_cdn_and_reuses_encrypted_lease(resolver):
    source, calls, reply = resolver
    assert sources.resolve_media(None, source) == (reply["url"], 123)
    assert len(calls) == 1 and reply["url"] not in source["_resolved_url"]
    assert calls[0].startswith(f"https://{HOST}/resolve/realdebrid/{KEY}/")  # the pasted add-on's host
    assert sources.resolve_media(None, source) == (reply["url"], 123)
    assert len(calls) == 1


@pytest.mark.parametrize(
    "path,code",
    [
        ("/videos/failed_infringement_v3.mp4", "RD_FILE_BLOCKED"),
        ("/videos/downloading_v3.mp4", "SOURCE_NOT_READY"),
        ("/videos/failed_access_v3.mp4", "RD_ACCESS_DENIED"),
    ],
)
def test_static_explanatory_videos_are_not_playable(resolver, path, code):
    source, calls, reply = resolver
    reply["url"] = "https://addon.example" + path
    with pytest.raises(MediaError) as error:
        sources.resolve_media(None, source)
    assert error.value.code == code
    assert "_resolved_url" not in source
    assert len(calls) == 1


def test_cloudflare_denial_is_not_reported_as_rd_file_block(resolver):
    source, _, reply = resolver
    reply["status"] = 403
    with pytest.raises(MediaError) as error:
        sources.resolve_media(None, source)
    assert error.value.code == "PROVIDER_ACCESS_DENIED"


def test_the_addon_is_whatever_link_was_pasted(monkeypatch):
    old = "https://torrentio.strem.fun/sort=qualitysize|realdebrid=K1/manifest.json"
    assert sources.configured_base({"manifest_url": old}) == (old.removesuffix("/manifest.json"), "K1")
    other = "https://other.example/realdebrid=K2/manifest.json"
    assert sources.configured_base({"manifest_url": other}) == ("https://other.example/realdebrid=K2", "K2")
    for bad in ("https://other.example:8443/realdebrid=K2/manifest.json", "https://other.example/x.json"):
        with pytest.raises(MediaError):
            sources.configured_base({"manifest_url": bad})
    # Requests stay on the configured add-on's host, never another one.
    monkeypatch.setattr(sources, "public_url", lambda u: (urlsplit(u), "203.0.113.1"))
    with pytest.raises(MediaError) as error:
        sources.addon_request("https://evil.invalid/stream/movie/tt1.json", "other.example")
    assert error.value.code == "UNSAFE_SOURCE"


def test_migration_renames_the_stored_addon_and_films_in_progress(setup):
    import importlib.util
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from houseos.models import Integration

    db, (actor, _) = setup
    db.add(Integration(name="torrentio", config={"torrent_player": True}, encrypted_secret="x", enabled=True))
    db.add(Integration(name="health_confirmed", config={"torrentio": {"by": "a", "at": "t"}}, enabled=True))
    old = {"provider": "torrentio", "_torrentio_cached": "null", "_torrentio_filename": "f.mkv"}
    old["cache_evidence"] = "torrentio_cached"
    db.add(
        CinemaWorkflow(id="w", owner_id=actor.id, media_id="m", idempotency_key="k", data={"_sources": [old]})
    )
    db.commit()
    path = Path(__file__).parents[1] / "migrations/versions/0009_stream_addon.py"
    spec = importlib.util.spec_from_file_location("stream_addon_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    for _ in range(2):  # safe to run twice
        with db.bind.connect() as connection, Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            connection.commit()
    db.expire_all()
    row = db.get(Integration, "stream_addon")
    assert (
        db.get(Integration, "torrentio") is None
        and row.encrypted_secret == "x"
        and row.config["torrent_player"]
    )
    assert list(db.get(Integration, "health_confirmed").config) == ["stream_addon"]
    assert db.get(CinemaWorkflow, "w").data == {
        "_sources": [
            {
                "provider": "stream_addon",
                "_addon_cached": "null",
                "_addon_filename": "f.mkv",
                "cache_evidence": "addon_cached",
            }
        ]
    }


@pytest.fixture
def cinema_fixture(monkeypatch, tmp_path):
    import test_cinema
    from houseos import cinema

    fixture = test_cinema.CinemaTests()
    fixture.setUp()
    monkeypatch.setattr(cinema.settings, "runtime_root", tmp_path)

    def config(_db, name):
        if name == "stream_addon":
            return {
                "enabled": True,
                "manifest_url": f"https://addon.example/sort=qualitysize|realdebrid={KEY}/manifest.json",
            }
        if name == "real_debrid":
            return {"enabled": True, "token": KEY}
        return {"enabled": False}

    monkeypatch.setattr(cinema, "integration_config", config)
    yield fixture
    fixture.tearDown()


def test_configured_discovery_and_preflight_preserve_exact_files_and_order(cinema_fixture, monkeypatch):
    """Shared hashes do not erase distinct files; preflight never recreates RD torrents."""
    from unittest.mock import Mock
    from sqlalchemy.orm import Session
    from houseos import cinema

    entries = [
        {"name": "[RD+] Add-on 1080p", "title": "Edition one", "url": LINK},
        {"name": "[RD+] Add-on 2160p", "title": "Edition two", "url": LINK.replace("/4/", "/5/")},
        {"name": "[RD+] Add-on 720p", "title": "Edition three", "url": LINK.replace(HASH, "b" * 40)},
    ]
    candidates = sources.normalize_streams({"streams": entries}, HOST, KEY)
    streams = Mock(return_value=candidates)
    monkeypatch.setattr(sources.StreamAddon, "streams", streams)
    rd = Mock()
    monkeypatch.setattr(cinema, "RealDebrid", rd)
    result = cinema_fixture.client.post(
        "/api/v1/cinema/discover",
        json={"media_id": cinema_fixture.title_id, "idempotency_key": "configured-order-fixture"},
    )
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["state"] == "discovered"
    page = cinema_fixture.client.get(f"/api/v1/cinema/workflows/{body['id']}/sources").json()
    assert [item["release"] for item in page["items"]] == ["Edition one", "Edition two", "Edition three"]
    assert all(item["rd_cached"] for item in page["items"])
    assert KEY not in str(body) and "_addon_" not in str(body) and "https://" not in str(body)
    streams.assert_called_once_with("tt123", "movie", None, None)
    rd.assert_not_called()
    seen = []

    def resolve(_db, source, refresh=False):
        seen.append((source["info_hash"], source["file_index"]))
        source["_resolved_url"] = "encrypted-private-lease"
        return f"https://cdn.example.invalid/{source['file_index']}", 123

    monkeypatch.setattr(sources, "resolve_media", resolve)
    monkeypatch.setattr(
        sources,
        "probe_media",
        lambda url, directory: {
            **cinema_fixture.media,
            "video": {**cinema_fixture.media["video"], "height": 2160 if url.endswith("/5") else 1080},
        },
    )
    with Session(cinema_fixture.engine, expire_on_commit=False) as db:
        row = db.get(cinema.CinemaWorkflow, body["id"])
        row.state = "preparing"
        selected = [source["id"] for source in row.data["_sources"]]
        row.data = {**row.data, "_validation_selection": selected}
        db.commit()
        output = cinema.validate_rd(db, row, selected)
    assert seen == [(HASH, 4), (HASH, 5), ("b" * 40, 4)]
    assert output["validation_summary"]["usable"] == 3
    assert [item["release"] for item in output["choice_set"]["candidates"]] == [
        "Edition one",
        "Edition two",
        "Edition three",
    ]
    assert "_resolved_url" not in str(output) and "encrypted-private-lease" not in str(output)
    assert "_addon_" not in str(output) and KEY not in str(output)
    for name in ["inventory", "add", "select", "info", "resolve"]:
        getattr(rd.return_value, name).assert_not_called()


def test_anime_api_preserves_poster_kind_identity_and_episode_mapping(cinema_fixture, monkeypatch):
    from unittest.mock import Mock
    from houseos import cinema, anime_catalog

    item = {
        "canonical_id": "mal:1",
        "title": "Cowboy Bebop",
        "kind": "series",
        "year": "1998",
        "genres": ["Action"],
        "_poster_url": "https://cdn.myanimelist.net/anime/fixture.jpg",
    }
    monkeypatch.setattr(anime_catalog.AnimeCatalog, "browse", lambda *_: {"items": [item], "next_offset": 24})
    monkeypatch.setattr(anime_catalog.AnimeCatalog, "search", lambda *_: [item])
    monkeypatch.setattr(
        anime_catalog.AnimeCatalog,
        "details",
        lambda *_: {**item, "episodes": [{"season": 1, "episode": 3, "title": "Fixture episode"}]},
    )
    browse = cinema_fixture.client.get("/api/v1/cinema/browse?kind=anime")
    assert browse.status_code == 200, browse.text
    public = browse.json()["items"][0]
    assert public["kind"] == "series" and public["canonical_id"] == "mal:1"
    assert public["poster"].startswith("/api/v1/cinema/titles/")
    assert public["genres"] == ["Action"] and "_poster_url" not in public
    search = cinema_fixture.client.get("/api/v1/cinema/search?kind=anime&q=Cowboy")
    assert search.status_code == 200, search.text
    assert search.json()["items"][0]["id"] == public["id"]
    details = cinema_fixture.client.get("/api/v1/cinema/titles/" + public["id"]).json()
    assert details["episodes"][0]["episode"] == 3
    mapping = Mock(return_value="kitsu:1:3")
    monkeypatch.setattr(anime_catalog, "resolve_stream", mapping)
    streams = Mock(return_value=[])
    monkeypatch.setattr(sources.StreamAddon, "streams", streams)
    no_rd = Mock(side_effect=AssertionError("Configured anime discovery must not query RD inventory"))
    monkeypatch.setattr(cinema, "RealDebrid", no_rd)
    discovery = cinema_fixture.client.post(
        "/api/v1/cinema/discover",
        json={
            "media_id": public["id"],
            "season": 1,
            "episode": 3,
            "idempotency_key": "anime-configured-fixture",
        },
    )
    assert discovery.status_code == 200, discovery.text
    mapping.assert_called_once_with("mal:1", 3)
    streams.assert_called_once_with("kitsu:1:3", "series", 1, 3)
    no_rd.assert_not_called()


@pytest.fixture
def autoplay_fixture(cinema_fixture, monkeypatch, tmp_path):
    from datetime import timedelta
    from unittest.mock import Mock
    from sqlalchemy.orm import Session
    from houseos import cinema

    (tmp_path / "cinema").mkdir()
    cinema_fixture.workflow()
    source = {
        **sources.normalize_streams({"streams": [{"name": "[RD+]", "url": LINK}]}, HOST, KEY)[0],
        "id": "source-one",
        "layer": "ON_DEMAND",
    }
    plan = cinema.compatibility(cinema_fixture.media, cinema_fixture.caps, {})
    with Session(cinema_fixture.engine) as db:
        db.add(
            cinema.CinemaTitle(
                id="parent-series", canonical_id="tt999", title="Series", kind="series", data={}
            )
        )
        db.get(cinema.CinemaTitle, cinema_fixture.title_id).data = {"parent_id": "parent-series"}
        row = db.get(cinema.CinemaWorkflow, "workflow-one")
        row.data = {
            **row.data,
            "request": {"autoplay": True},
            "_autoplay_expires_at": (cinema.utcnow() + timedelta(hours=1)).isoformat(),
            "_boot_id": cinema.boot_identity(),
            "_selected_source": source["id"],
            "season": 1,
            "episode": 1,
            "_sources": [source],
            "plan": {**plan, "expected_item": "completed-fixture"},
        }
        db.commit()
    monkeypatch.setattr(cinema, "next_episode", lambda *_: {"episode": {"season": 1, "episode": 2}})
    monkeypatch.setattr("houseos.cinema_cast.preflight_cast", lambda *_: None)
    monkeypatch.setattr(sources, "probe_media", lambda *_: cinema_fixture.media)
    resolve = Mock(return_value=("https://cdn.example.invalid/episode-two", 123))
    monkeypatch.setattr(sources, "resolve_media", resolve)
    next_file = {**source, "file_index": 5, "release": "Next episode"}
    streams = Mock(return_value=[next_file])
    monkeypatch.setattr(sources.StreamAddon, "streams", streams)
    no_rd = Mock(side_effect=AssertionError("Configured pack autoplay must not mutate RD"))
    monkeypatch.setattr(cinema, "RealDebrid", no_rd)
    yield cinema_fixture, streams, resolve, no_rd


def test_autoplay_continues_only_unique_same_pack_rd_plus(autoplay_fixture):
    from sqlalchemy.orm import Session
    from houseos import cinema

    fixture, streams, resolve, no_rd = autoplay_fixture
    with Session(fixture.engine, expire_on_commit=False) as db:
        row = db.get(cinema.CinemaWorkflow, "workflow-one")
        identity = cinema.prepare_autoplay(db, row, fixture.actor)
        child = db.get(cinema.CinemaWorkflow, identity)
        assert child.state == "autoplay_countdown"
        assert child.data["episode"] == 2
        assert child.data["_sources"][0]["info_hash"] == HASH
        assert child.data["_sources"][0]["file_index"] == 5
        assert child.data["plan"]["release_key"] == HASH + ":6"
        assert child.data["_autoplay_depth"] == 1
    streams.assert_called_once_with("tt999", "series", 1, 2)
    resolve.assert_called_once()
    no_rd.assert_not_called()


@pytest.mark.parametrize("change", ["other-pack", "same-file", "ambiguous", "not-cached"])
def test_autoplay_does_not_silently_choose_new_or_ambiguous_release(autoplay_fixture, change):
    from sqlalchemy.orm import Session
    from houseos import cinema

    fixture, streams, resolve, no_rd = autoplay_fixture
    candidate = streams.return_value[0].copy()
    if change == "other-pack":
        candidate["info_hash"] = "b" * 40
    elif change == "same-file":
        candidate["file_index"] = 4
    elif change == "not-cached":
        candidate["rd_cached"] = False
    streams.return_value = (
        [candidate, {**candidate, "file_index": 6}] if change == "ambiguous" else [candidate]
    )
    with Session(fixture.engine, expire_on_commit=False) as db:
        with pytest.raises(MediaError, match="AUTOPLAY_NEEDS_SELECTION"):
            cinema.prepare_autoplay(db, db.get(cinema.CinemaWorkflow, "workflow-one"), fixture.actor)
    resolve.assert_not_called()
    no_rd.assert_not_called()


def test_autoplay_async_preparation_is_not_reported_as_command_sent(autoplay_fixture, monkeypatch):
    from datetime import timedelta
    from sqlalchemy.orm import Session
    from houseos import cinema

    fixture, _, _, _ = autoplay_fixture
    with Session(fixture.engine, expire_on_commit=False) as db:
        parent = db.get(cinema.CinemaWorkflow, "workflow-one")
        identity = cinema.prepare_autoplay(db, parent, fixture.actor)
        child = db.get(cinema.CinemaWorkflow, identity)
        child.data = {
            **child.data,
            "preview": {
                **child.data["preview"],
                "countdown_until": (cinema.utcnow() - timedelta(seconds=1)).isoformat(),
            },
        }
        db.get(cinema.CinemaDevice, fixture.device_id).owner_workflow = parent.id
        db.commit()
        monkeypatch.setattr(
            cinema,
            "inspect_destination",
            lambda *_: {"state": "idle", "idle_reason": "FINISHED", "item_id": "completed-fixture"},
        )
        monkeypatch.setattr("houseos.cinema_cast.execute_cast", lambda *_: False)
        cinema.process_autoplay(db)
        db.refresh(child)
        assert child.state == "preparing"
        assert child.data.get("observation", {}).get("state") != "command_sent"
