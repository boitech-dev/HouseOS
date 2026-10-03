"""Links and addresses people paste from other apps get a sentence, not a 500. Fixtures only."""

import os
import socket
import ssl
import httpx
import pytest
from fastapi import HTTPException
from houseos import files as f, integrations, music
from houseos.cinema_adapters import Jellyfin
from houseos.integrations import endpoint_url
from test_providers import mock_catalog

RD_ONLY = "HouseOS doesn't support this debrid service on add-on links yet"


def save_addon(db, actor, link, **config):
    body = integrations.IntegrationInput(enabled=True, secret=link, config=config)
    return integrations.save_integration("stream_addon", body, actor, db)


@pytest.mark.parametrize("option", ["alldebrid=k", "premiumize=k", "torbox=k", "debridlink=k"])
def test_other_debrid_addon_links_are_a_sentence(setup, option):
    db, (actor, _) = setup
    with pytest.raises(HTTPException) as error:
        save_addon(db, actor, f"stremio://addon.example/sort=qualitysize|{option}/manifest.json")
    assert error.value.status_code == 422 and error.value.detail.startswith(RD_ONLY)
    with pytest.raises(HTTPException) as error:
        save_addon(db, actor, "https://addon.example/realdebrid=abc123/")  # not the manifest link
    assert error.value.status_code == 422


def test_stremio_install_link_saves_as_https(setup):
    db, (actor, _) = setup
    # A house's existing link, unchanged, still saves: the add-on is whatever link is pasted.
    link = "stremio://torrentio.strem.fun/realdebrid=abc123/manifest.json"
    assert save_addon(db, actor, link)["status"] == "completed"
    assert integrations.integration_config(db, "stream_addon")["manifest_url"] == (
        "https://torrentio.strem.fun/realdebrid=abc123/manifest.json"
    )


def test_any_addon_host_saves_and_its_link_is_never_shown_back(setup):
    db, (actor, _) = setup
    link = "https://another-addon.example/opts|realdebrid=secretkey42/manifest.json"
    assert save_addon(db, actor, link, torrent_player=False)["status"] == "completed"
    assert integrations.integration_config(db, "stream_addon")["manifest_url"] == link
    listed = next(r for r in integrations.list_integrations(actor, db) if r["name"] == "stream_addon")
    assert listed["has_secret"] and "secretkey42" not in str(listed) and "another-addon" not in str(listed)
    for bad in (
        "http://another-addon.example/manifest.json",
        "https://u:p@another-addon.example/manifest.json",
    ):
        with pytest.raises(HTTPException):
            save_addon(db, actor, bad)


@pytest.mark.parametrize("name,service", [("home_assistant", "Home Assistant"), ("jellyfin", "Jellyfin")])
def test_untrusted_certificate_is_named(setup, monkeypatch, name, service):
    db, (actor, _) = setup
    integrations.save_integration(
        name,
        integrations.IntegrationInput(
            enabled=True, config={"base_url": "https://192.0.2.18:8123"}, secret="k"
        ),
        actor,
        db,
    )

    def reply(request):
        if name == "jellyfin":
            assert request.headers["x-emby-token"] == "k"
        raise httpx.ConnectError("handshake") from ssl.SSLCertVerificationError("self-signed")

    mock_catalog(monkeypatch, reply)
    result = integrations.test_integration(name, actor, db)
    assert result["status"] == "unreachable"
    assert result["message"].startswith(f"{service}'s certificate isn't valid for this address")


def test_local_names_explain_docker(monkeypatch):
    def missing(*args, **kwargs):
        raise socket.gaierror()

    monkeypatch.setattr(integrations.socket, "getaddrinfo", missing)
    monkeypatch.setattr(integrations.settings, "storage_container", True)
    with pytest.raises(ValueError, match="Names ending in .local don't work from inside Docker"):
        endpoint_url("http://homeassistant.local:8123", resolve=True)
    with pytest.raises(ValueError, match="^This address could not be found$"):
        endpoint_url("http://nas.lan:8123", resolve=True)


def test_jellyfin_also_sends_the_emby_header():
    adapter = Jellyfin(
        {"enabled": True, "api_key": "k", "user_id": "u", "base_url": "http://192.0.2.17:8096"}
    )
    assert adapter.headers["X-Emby-Token"] == "k" and 'Token="k"' in adapter.headers["Authorization"]


def test_shared_folder_may_live_on_another_disk_under_the_import_root(tmp_path, monkeypatch):
    root = tmp_path / "import"
    (root / "films").mkdir(parents=True)
    (root / "films" / "a.mkv").write_bytes(b"x")
    (root / "escape").symlink_to("/etc")
    monkeypatch.setattr(f.settings, "import_root", root)
    # HouseOS storage is elsewhere: another device than the import folder.
    monkeypatch.setattr(f, "storage_check", lambda: {"status": "healthy", "device": -1})
    with f.readonly_fd(str(root / "films")) as fd:
        assert os.listdir(fd) == ["a.mkv"]
    for path, code in [(root / "escape", 503), ("/etc", 422), (root, 422), (root / "films/../escape", 422)]:
        with pytest.raises(HTTPException) as error:
            with f.readonly_fd(str(path)):
                pass
        assert error.value.status_code == code


def test_streaming_service_links_say_what_to_do():
    for link in [
        "https://open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC",
        "https://www.deezer.com/fr/track/3135556",
        "https://music.apple.com/fr/album/x/1440833098?i=1440833375",
        "https://tidal.com/browse/track/1234",
    ]:
        for check in (music.canonical_source, music.playlist_source):
            with pytest.raises(HTTPException) as error:
                check(link)
            assert error.value.status_code == 422 and error.value.detail.startswith("Spotify, Deezer")


def test_youtube_music_and_mobile_playlists_are_accepted():
    for host in ("music.youtube.com", "m.youtube.com"):
        assert (
            music.playlist_source(f"https://{host}/playlist?list=PLabcdefghij")
            == "https://www.youtube.com/playlist?list=PLabcdefghij"
        )


def test_jellyfin_not_set_up_reads_as_unconfigured_even_where_its_default_address_is_refused(monkeypatch):
    import pytest
    from houseos import integrations
    from houseos.cinema_adapters import Jellyfin, MediaError

    def refused(*args, **kwargs):  # Docker: the loopback default is not a valid address there
        raise ValueError("Inside Docker, use host.docker.internal or the server's LAN address")

    monkeypatch.setattr(integrations, "endpoint_url", refused)
    with pytest.raises(MediaError) as error:
        Jellyfin({})
    assert error.value.code == "JELLYFIN_UNCONFIGURED"
