"""Show on the TV: the YouTube link, the screen key and its door, the handover to the desktop
helper, the TV, Nox's card, and the helper's Sunshine app id. Home Assistant and the helper are
fakes; no TV, browser or Sunshine is contacted."""

import importlib.util
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from houseos import home, screen_tv, tool_tv
from houseos.auth import RESIDENT, Actor
from houseos.config import settings

TV = "media_player.oled_tv"
HOST = "0F1E2D3C-4B5A-6978-8796-A5B4C3D2E1F0"
DESKTOP = 881448767


@pytest.fixture(autouse=True)
def fresh(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "runtime_root", tmp_path)
    # No real waiting: the TV "boots" and retries at once (the helper's long poll still waits).
    monkeypatch.setattr(
        screen_tv, "time", SimpleNamespace(time=time.time, monotonic=time.monotonic, sleep=lambda s: None)
    )
    screen_tv.HELPER.clear()
    screen_tv.JOB.clear()
    yield
    screen_tv.HELPER.clear()
    screen_tv.JOB.clear()


class FakeHA:
    """The TV as Home Assistant reports it (attributes of a real LG webOS OLED), and the
    services HouseOS calls on it."""

    def __init__(self, state="off", source=None, webos=True, shown=(TV,)):
        self.state, self.source, self.webos, self.shown, self.calls = state, source, webos, shown, []

    def tv(self):
        attributes = {"friendly_name": "OLED TV", "source_list": ["HDMI 1", "Moonlight", "Netflix"]}
        if self.state == "on":
            attributes["source"] = self.source
        return {"entity_id": TV, "state": self.state, "attributes": attributes}

    def connection(self, db):
        return "http://ha.test", {"Authorization": "Bearer t"}, {"curated": True, "shown": list(self.shown)}

    def ha(self, base, headers, path, method="GET", payload=None, timeout=5):
        if path == "/api/states":
            return [self.tv(), {"entity_id": "media_player.radio", "state": "off", "attributes": {}}]
        if path == "/api/states/" + TV:
            return self.tv()
        service = path.removeprefix("/api/services/")
        self.calls.append((service, payload))
        if service == "webostv/command" and not self.webos:
            raise HTTPException(503, "no such service")
        if service == "media_player/turn_on":
            self.state, self.source = "on", None
        if service == "media_player/select_source":
            self.source = payload["source"]
        return []


@pytest.fixture
def ha(monkeypatch):
    fake = FakeHA()
    monkeypatch.setattr(home, "connection", fake.connection)
    monkeypatch.setattr(home, "ha", fake.ha)
    return fake


class FakeDB:
    def __init__(self):
        self.events = []

    def add(self, row):
        self.events.append(row)

    def commit(self):
        pass


def resident():
    return Actor("u1", "Alice", "resident", RESIDENT)


def helper(streaming=False, outcome="opened", taken=None):
    """The desktop helper: one long poll, then it claims the video and reports."""

    def work():
        reply = screen_tv.next_job(HOST, DESKTOP, streaming, "house-pc", "google-chrome", 5, None)
        job = reply["job"]
        if taken is not None:
            taken.append(job)
        if job:
            screen_tv.job_report(job["id"], screen_tv.Report(state="claimed", streaming=streaming), None)
            screen_tv.job_report(job["id"], screen_tv.Report(state=outcome), None)

    thread = threading.Thread(target=work)
    thread.start()
    deadline = time.monotonic() + 2
    while not screen_tv.HELPER and time.monotonic() < deadline:
        time.sleep(0.01)
    return thread


# ---------- the link ----------
@pytest.mark.parametrize(
    "shared, url, start",
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "https://www.youtube.com/watch?v=dQw4w9WgXcQ", 0),
        # Android's YouTube app shares a short link with a tracking id; iOS sends the same link.
        ("https://youtu.be/dQw4w9WgXcQ?si=AbCdEf123", "https://www.youtube.com/watch?v=dQw4w9WgXcQ", 0),
        ("Watch this! https://youtu.be/dQw4w9WgXcQ?t=95", "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=95s", 95),
        ("https://m.youtube.com/watch?v=dQw4w9WgXcQ&t=1m30s&feature=share", "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=90s", 90),
        ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "https://www.youtube.com/watch?v=dQw4w9WgXcQ", 0),
        ("https://music.youtube.com/watch?v=dQw4w9WgXcQ&list=PLx0sYbCqOb8TBPRdmBHs5Iftvv9TPboYG",
         "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLx0sYbCqOb8TBPRdmBHs5Iftvv9TPboYG", 0),
    ],
)  # fmt: skip
def test_a_shared_youtube_link_becomes_one_clean_watch_link(shared, url, start):
    video = screen_tv.youtube(shared)
    assert video == {"id": "dQw4w9WgXcQ", "url": url, "start": start}


def test_the_page_position_wins_over_the_link_and_other_sites_are_refused():
    assert screen_tv.youtube("https://youtu.be/dQw4w9WgXcQ?t=10", at=754.6)["start"] == 754
    for text in (
        "https://vimeo.com/123456",
        "https://www.youtube.com/channel/UC123",
        "https://youtube.com.evil.example/watch?v=dQw4w9WgXcQ",
        "https://www.youtube.com/watch?v=short",
        "no link here",
    ):
        assert screen_tv.youtube(text) is None


# ---------- the key and its door ----------
def admin(c):
    response = c.post(
        "/api/v1/auth/bootstrap",
        json={
            "name": "Test Admin",
            "username": "testadmin",
            "password": "test-only-password-very-long",
            "setup_token": settings.bootstrap_token,
        },
    )
    assert response.status_code == 200, response.text
    c.headers["X-CSRF-Token"] = response.json()["csrf_token"]


def test_the_key_is_shown_once_reaches_only_the_screen_and_skips_only_its_origin_check(client):
    c, db = client
    admin(c)
    key = c.post("/api/v1/tv/screen/key").json()["key"]
    assert key.startswith("hos_screen_")
    assert key not in (Path(settings.runtime_root) / "run/screen/key.json").read_text()
    assert c.get("/api/v1/tv/screen").json()["key"]["by"] == "Test Admin"

    # A shortcut or the helper: no cookie, no Origin, only the key.
    bare = {"Origin": "", "X-CSRF-Token": "", "Cookie": ""}
    c.cookies.clear()
    poll = c.get("/api/v1/tv/screen/next?wait=0", headers={"Authorization": "Bearer " + key})
    assert poll.status_code == 200 and poll.json() == {"job": None}
    refused = c.post(
        "/api/v1/tv/screen/show",
        json={"url": "https://youtu.be/dQw4w9WgXcQ"},
        headers=bare | {"Authorization": "Bearer wrong"},
    )
    assert refused.status_code == 401
    # Without the key, the Origin check still applies to the screen, and the key opens nothing else.
    assert c.post("/api/v1/tv/screen/show", json={"url": "x" * 20}, headers=bare).status_code == 403
    elsewhere = c.post("/api/v1/tv/screen/key", headers=bare | {"Authorization": "Bearer " + key})
    assert elsewhere.status_code == 403  # an admin route keeps its Origin check, key or not
    assert c.get("/api/v1/tv", headers={"Authorization": "Bearer " + key}).status_code == 401


def test_a_new_key_replaces_the_old_one(client):
    c, db = client
    admin(c)
    first = c.post("/api/v1/tv/screen/key").json()["key"]
    second = c.post("/api/v1/tv/screen/key").json()["key"]
    poll = lambda key: c.get("/api/v1/tv/screen/next?wait=0", headers={"Authorization": "Bearer " + key})  # noqa: E731
    assert poll(first).status_code == 401 and poll(second).status_code == 200
    assert c.delete("/api/v1/tv/screen/key").status_code == 200
    assert poll(second).status_code == 401


# ---------- the whole press ----------
def test_tv_off_turns_on_and_opens_moonlight_straight_on_the_desktop(ha):
    db, taken = FakeDB(), []
    thread = helper(taken=taken)
    result = screen_tv.show(db, resident(), "https://youtu.be/dQw4w9WgXcQ?t=42")
    thread.join(5)
    assert taken[0]["url"] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42s"
    assert taken[0]["expect_stream"] is True  # the helper waits for the TV before playing
    assert result["status"] == "sent"
    assert result["tv"] == {"name": "OLED TV", "done": ["turned on", "opened Moonlight on the computer"]}
    assert ha.calls == [
        ("media_player/turn_on", {"entity_id": TV}),
        (
            "webostv/command",
            {
                "entity_id": TV,
                "command": "system.launcher/launch",
                "payload": {
                    "id": "com.limelight.webos",
                    "params": {"host_uuid": HOST, "host_app_id": DESKTOP},
                },
            },
        ),
    ]
    assert db.events[0].topic == "audit.tv.screen_show"


def test_already_streaming_leaves_the_tv_alone(ha):
    ha.state, ha.source = "on", "Moonlight"
    thread = helper(streaming=True)
    result = screen_tv.show(FakeDB(), resident(), "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    thread.join(5)
    assert result["tv"]["done"] == ["already on the computer"] and ha.calls == []


def test_moonlight_open_but_idle_restarts_so_it_reads_the_launch_parameters(ha):
    ha.state, ha.source = "on", "Moonlight"
    thread = helper(streaming=False)
    screen_tv.show(FakeDB(), resident(), "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    thread.join(5)
    assert [(s, p["command"]) for s, p in ha.calls] == [
        ("webostv/command", "system.launcher/close"),
        ("webostv/command", "system.launcher/launch"),
    ]


def test_a_tv_without_webos_commands_gets_moonlight_by_its_input(ha):
    ha.state, ha.source, ha.webos = "on", "Netflix", False
    thread = helper()
    result = screen_tv.show(FakeDB(), resident(), "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    thread.join(5)
    assert ha.calls[-1] == ("media_player/select_source", {"entity_id": TV, "source": "Moonlight"})
    assert result["tv"]["done"] == ["opened Moonlight"]


def test_a_tv_hidden_from_houseos_is_never_touched(ha):
    ha.shown = ()
    taken = []
    thread = helper(taken=taken)
    result = screen_tv.show(FakeDB(), resident(), "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    thread.join(5)
    assert taken[0]["expect_stream"] is False  # nothing to wait for: plays on the computer at once
    assert result["tv"] == {"name": None, "done": []} and ha.calls == []


def test_honest_failures(ha, monkeypatch):
    with pytest.raises(HTTPException) as offline:
        screen_tv.show(FakeDB(), resident(), "https://youtu.be/dQw4w9WgXcQ")
    assert offline.value.detail["code"] == "SCREEN_HELPER_OFFLINE"
    with pytest.raises(HTTPException) as other:
        screen_tv.show(FakeDB(), resident(), "https://vimeo.com/1")
    assert other.value.detail["code"] == "SCREEN_NOT_YOUTUBE"

    # The helper was seen but doesn't take the video.
    monkeypatch.setattr(screen_tv, "CLAIM_WAIT", 0.2)
    screen_tv.HELPER.update(at=time.time(), host_uuid=HOST, app_id=DESKTOP)
    with pytest.raises(HTTPException) as silent:
        screen_tv.show(FakeDB(), resident(), "https://youtu.be/dQw4w9WgXcQ")
    assert silent.value.detail["code"] == "SCREEN_HELPER_SILENT" and screen_tv.JOB["state"] == "failed"
    assert ha.calls == []  # the TV isn't woken for a video nobody will play

    # Someone without the TV permissions.
    with pytest.raises(HTTPException) as denied:
        screen_tv.show(FakeDB(), Actor("u2", "Guest", "guest", frozenset()), "https://youtu.be/dQw4w9WgXcQ")
    assert denied.value.status_code == 403


def test_a_tv_that_does_not_wake_says_so(ha, monkeypatch):
    monkeypatch.setattr(screen_tv, "TV_BOOT", 0.05)
    real = ha.ha

    def asleep(base, headers, path, **kw):
        if path == "/api/services/media_player/turn_on":
            ha.calls.append(("media_player/turn_on", kw.get("payload")))
            return []  # no Wake on LAN in Home Assistant: nothing happens
        return real(base, headers, path, **kw)

    monkeypatch.setattr(home, "ha", asleep)
    thread = helper()
    with pytest.raises(HTTPException) as error:
        screen_tv.show(FakeDB(), resident(), "https://youtu.be/dQw4w9WgXcQ")
    thread.join(5)
    assert error.value.detail["code"] == "SCREEN_TV_ASLEEP"


# ---------- Nox ----------
def test_nox_asks_before_showing(ha, setup):
    db, (alice, _) = setup
    screen_tv.HELPER.update(at=time.time())
    card = tool_tv.tv_show_video(tool_tv.TvShowVideo(url="https://youtu.be/dQw4w9WgXcQ?si=x"), alice, db)
    assert card["status"] == "needs_confirmation" and card["preview"]["may_interrupt"] is True
    assert ha.calls == []
    refused = tool_tv.tv_show_video(tool_tv.TvShowVideo(url="https://vimeo.com/123456"), alice, db)
    assert refused["status"] == "failed"


# ---------- the desktop helper ----------
def load_helper():
    path = Path(__file__).resolve().parents[2] / "docs/native/houseos_screen.py"
    spec = importlib.util.spec_from_file_location("houseos_screen", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_helper_computes_sunshines_app_id(tmp_path, monkeypatch):
    screen = load_helper()
    # A real Sunshine 2026.516 install: "Desktop" with its stock desktop.png answers 881448767.
    assert (
        screen.sunshine_id("Desktop", "477c3fbcd1e9c796a0e23bd201220706c30cd787e5be5753f9e0d385b7577761")
        == DESKTOP
    )

    assets, config = tmp_path / "assets", tmp_path / "sunshine"
    assets.mkdir(), config.mkdir()
    (assets / "desktop.png").write_bytes(screen.PNG + b"picture")
    (assets / "broken.png").write_bytes(b"not a png")
    (config / "apps.json").write_text(
        '{"apps": [{"name": "Desktop", "image-path": "desktop.png"}, {"name": "Steam", "image-path": "broken.png"},'
        ' {"name": "Kodi"}]}'
    )
    monkeypatch.setattr(screen, "SUNSHINE_CONFIG", config)
    monkeypatch.setenv("HOUSEOS_SUNSHINE_ASSETS", str(assets))
    import hashlib

    picture = hashlib.sha256(screen.PNG + b"picture").hexdigest()
    assert screen.app_id("desktop") == screen.sunshine_id("Desktop", picture)
    assert screen.app_id("Steam") == screen.sunshine_id("Steam")  # not a PNG: Sunshine's default art
    assert screen.app_id("Kodi") == screen.sunshine_id("Kodi")
    assert screen.app_id("Missing") == 0
