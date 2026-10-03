"""Music outputs: the computer's own speakers with no setup, phones in Speaker mode, a Cast
or DLNA device following the house clock, and a radio station replacing the one on air. No
real sound server, player, speaker, Cast or DLNA device is touched."""

import os
import subprocess
import uuid
from datetime import timedelta
from types import SimpleNamespace
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from houseos import audio, music_outputs as mo, radio
from houseos.auth import Actor, require_actor
from houseos.cinema_models import CinemaDevice
from houseos.config import settings
from houseos.db import Base, get_db, utcnow
from houseos.models import Integration, User
from houseos.music import QueueItem, QueueState, router

WEBM = b"\x1aE\xdf\xa3" + b"\0" * 60
READ = frozenset({"music.read", "music.queue", "music.control"})


@pytest.fixture
def house(tmp_path, monkeypatch):
    """A sqlite house with one playing song, one next and one later; the API and the relay."""
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    ids = [str(uuid.uuid4()) for _ in range(3)]
    with Session(engine) as db:
        db.add(User(id="one", name="One", username="one", password_hash="unused", role="resident"))
        db.add(QueueState(id=1, desired="playing", current_id=ids[0]))
        for position, identity in enumerate(ids):
            db.add(
                QueueItem(
                    id=identity,
                    owner_id="one",
                    source_url="https://www.youtube.com/watch?v=abcdefghij" + str(position),
                    title="Song " + str(position),
                    position=position,
                    status="playing" if position == 0 else "ready",
                    metadata_json={"duration": 200},
                )
            )
        db.commit()
    (tmp_path / "audio").mkdir()
    for identity in ids:
        (tmp_path / "audio" / (identity + ".media")).write_bytes(WEBM)
    monkeypatch.setattr(settings, "runtime_root", tmp_path)
    monkeypatch.setattr(settings, "receiver_base_url", "")
    monkeypatch.setattr(mo, "SessionLocal", lambda: Session(engine, expire_on_commit=False))
    app = FastAPI()
    app.include_router(router)
    app.include_router(mo.relay_router)
    state = SimpleNamespace(engine=engine, ids=ids, actor=Actor("one", "One", "resident", READ))
    app.dependency_overrides[require_actor] = lambda: state.actor

    def session():
        with Session(engine, expire_on_commit=False) as db:
            yield db

    app.dependency_overrides[get_db] = session
    state.client = TestClient(app)
    yield state
    mo.FOLLOW.clear()


# ---------- this computer's speakers ----------
def test_default_output_follows_the_sound_server_and_never_needs_pactl(monkeypatch, tmp_path):
    def no_pactl(*args, **kwargs):
        raise FileNotFoundError("pactl")

    monkeypatch.setattr(audio.subprocess, "run", no_pactl)
    monkeypatch.delenv("PULSE_SERVER", raising=False)
    monkeypatch.setattr(audio, "Path", lambda path: tmp_path)  # an empty /dev/snd
    assert audio.detect_server() == "none"
    (tmp_path / "pcmC0D0p").touch()
    assert audio.detect_server() == "alsa"
    monkeypatch.setattr(audio, "default_sink", lambda: "hdmi")
    assert audio.detect_server() == "pulse"

    for server, expected in [("pulse", "pulse/hdmi"), ("alsa", "alsa/default"), ("none", None)]:
        monkeypatch.setattr(audio, "server", server)
        assert audio.device("default") == expected
        assert audio.device("none") is None
    monkeypatch.setattr(audio, "server", "alsa")
    assert [o["id"] for o in audio.outputs()] == ["default", "none"]

    # No sound server: the clock still plays (silently) so phones and Cast can follow.
    monkeypatch.setattr(audio, "server", "none")
    monkeypatch.setattr(audio, "policy", lambda: {})
    monkeypatch.setattr(audio.settings, "audio_enabled", True)
    monkeypatch.setattr(audio, "MEDIA", tmp_path)
    item = str(uuid.uuid4())
    (tmp_path / (item + ".media")).write_bytes(WEBM)
    commands = []
    monkeypatch.setattr(audio, "mpv", lambda command: commands.append(command))
    assert audio.execute({"command": "outputs"})["sound_server"] == "none"
    assert audio.execute({"command": "load", "item_id": item})["status"] == "command_sent"
    assert ["loadfile", str(tmp_path / (item + ".media")), "replace"] in commands

    launched = []

    class Player:
        def poll(self):
            return None

    def popen(args, **kwargs):
        launched.append(args)
        audio.SOCKET.touch()
        return Player()

    monkeypatch.setattr(audio, "SOCKET", tmp_path / "mpv.sock")
    monkeypatch.setattr(audio, "player", None)
    monkeypatch.setattr(audio.volume_ramp, "cancel", lambda: None)
    monkeypatch.setattr(audio.subprocess, "Popen", popen)
    audio.start_player("default")
    assert "--ao=null" in launched[-1]
    monkeypatch.setattr(audio, "server", "alsa")
    monkeypatch.setattr(audio, "player", None)
    audio.start_player("default")
    assert "--ao=alsa" in launched[-1] and "--audio-device=alsa/default" in launched[-1]


def test_a_slow_sound_server_is_not_a_crash(monkeypatch, tmp_path):
    def slow(*args, **kwargs):
        raise subprocess.TimeoutExpired("pactl", 3)

    monkeypatch.setattr(audio.subprocess, "run", slow)
    monkeypatch.setattr(audio, "Path", lambda path: tmp_path)
    monkeypatch.setenv("PULSE_SERVER", "unix:/nowhere")
    assert audio.detect_server(wait=0) == "none"


# ---------- Speaker mode ----------
def test_phones_get_only_the_current_or_next_song_with_ranges(house, monkeypatch):
    now, following, later = house.ids
    whole = house.client.get("/music/audio/" + now)
    assert whole.status_code == 200 and whole.headers["content-type"] == "audio/webm"
    assert whole.content == WEBM
    part = house.client.get("/music/audio/" + following, headers={"Range": "bytes=0-3"})
    assert part.status_code == 206 and part.content == WEBM[:4]
    assert part.headers["content-range"] == "bytes 0-3/" + str(len(WEBM))
    assert house.client.get("/music/audio/" + later).status_code == 404
    house.actor = Actor("one", "One", "guest", frozenset())
    assert house.client.get("/music/audio/" + now).status_code == 403

    house.actor = Actor("one", "One", "resident", READ)
    (settings.runtime_root / "audio" / (now + ".media")).unlink()
    os.mkfifo(settings.runtime_root / "audio" / (now + ".media"))
    live = house.client.get("/music/audio/" + now)
    assert live.status_code == 409 and "server's speakers only" in live.json()["detail"]


def test_audio_types_come_from_the_file_not_its_name(tmp_path):
    for head, expected in [
        (b"\0\0\0\x20ftypM4A ", "audio/mp4"),
        (b"ID3\x04\0\0\0\0\0\0\0\0", "audio/mpeg"),
        (b"\xff\xfb\x90\0" + b"\0" * 8, "audio/mpeg"),
        (b"OggS" + b"\0" * 8, "audio/ogg"),
        (WEBM[:12], "audio/webm"),
    ]:
        path = tmp_path / "sample.media"
        path.write_bytes(head)
        assert mo.audio_type(path) == expected


def test_radio_followers_play_the_https_stream_directly(house, monkeypatch):
    now = house.ids[0]
    with Session(house.engine) as db:
        db.get(QueueItem, now).source_url = "radio:" + str(uuid.uuid4())
        db.commit()
    station = {"url": "https://radio.example/stream", "codec": "MP3"}
    monkeypatch.setattr(radio, "cached_station", lambda identity, bucket: station)
    moved = house.client.get("/music/audio/" + now, follow_redirects=False)
    assert moved.status_code == 307 and moved.headers["location"] == station["url"]
    station["url"] = "http://radio.example/stream"
    only = house.client.get("/music/audio/" + now)
    assert only.status_code == 409 and only.json()["detail"] == mo.RADIO_SERVER_ONLY


# ---------- the relay ----------
def test_relay_heartbeat_reports_its_lan_address(house, monkeypatch):
    monkeypatch.setattr(mo, "lan_address", lambda target: "192.0.2.21")
    monkeypatch.setattr(mo.sys, "argv", ["uvicorn", "houseos.relay:app", "--port", "8991"])
    with Session(house.engine) as db:
        assert mo.write_relay_heartbeat(db) == "http://192.0.2.21:8991"
        assert mo.relay_base_url(db) == "http://192.0.2.21:8991"
        db.get(Integration, mo.HEARTBEAT).updated_at = utcnow() - timedelta(minutes=5)
        db.commit()
        assert mo.relay_base_url(db) == ""  # no relay running
        monkeypatch.setattr(settings, "receiver_base_url", "http://192.0.2.17:8991")
        assert mo.relay_base_url(db) == "http://192.0.2.17:8991"


def test_lan_address_setting_wins_over_the_default_route(monkeypatch):
    # A VPN or Tailscale exit node owns the default route; the house's address is set by hand.
    monkeypatch.setattr(settings, "lan_address", "192.0.2.21")
    assert mo.lan_address() == "192.0.2.21"
    monkeypatch.setattr(settings, "lan_address", "")
    assert mo.lan_address("127.0.0.1") == "127.0.0.1"


def test_relay_serves_the_current_song_only_to_its_device(house):
    now = house.ids[0]
    token = "t" * 43
    with Session(house.engine) as db:
        db.add(CinemaDevice(id="tv", name="TV", adapter="cast", address="192.0.2.19"))
        mo.save_output_choice(
            db,
            cast_device_id="tv",
            grant={
                "token_hash": mo.hashlib.sha256(token.encode()).hexdigest(),
                "item_id": now,
                "device_id": "tv",
                "address": "testclient",  # the test client's address plays the device
                "expires_at": mo.time.time() + 60,
            },
        )
        db.commit()
    served = house.client.get("/receiver/music/" + token + "/audio", headers={"Range": "bytes=0-"})
    assert served.status_code == 206 and served.headers["content-type"] == "audio/webm"
    assert house.client.get("/receiver/music/" + "x" * 43 + "/audio").status_code == 404
    with Session(house.engine) as db:
        db.get(QueueState, 1).current_id = house.ids[1]  # the song moved on: the grant is spent
        db.commit()
    assert house.client.get("/receiver/music/" + token + "/audio").status_code == 404


# ---------- the Cast follower ----------
def test_cast_follows_the_house_clock(house, monkeypatch):
    from houseos import cinema_cast

    calls = []
    monkeypatch.setattr(settings, "receiver_base_url", "http://192.0.2.17:8991")
    monkeypatch.setattr(cinema_cast, "cast_music", lambda *args: calls.append(("load",) + args[3:6]))
    monkeypatch.setattr(
        cinema_cast, "cast_control", lambda address, action, value: calls.append((action, value))
    )
    seen = {}
    monkeypatch.setattr(cinema_cast, "cast_observe", lambda address: seen)
    clock = {"status": "observed", "idle": False, "paused": False, "position": 10.0, "item_id": house.ids[0]}
    monkeypatch.setattr(mo, "bridge", lambda command: dict(clock))
    now = [0.0]
    monkeypatch.setattr(mo.time, "monotonic", lambda: now[0])
    with Session(house.engine) as db:
        db.add(CinemaDevice(id="tv", name="TV", adapter="cast", address="192.0.2.19"))
        mo.save_output_choice(db, cast_device_id="tv")
        db.commit()

    def tick(at, **changes):
        now[0] = at
        clock.update(changes)
        mo.follow_cast()
        return calls[-1] if calls else None

    assert tick(0) == ("load", 10.0, False, False)  # starts where the house is
    url = mo.FOLLOW["url"]
    assert url.startswith("http://192.0.2.17:8991/receiver/music/")
    assert tick(1, paused=True, position=11.0) == ("pause", 0)
    seen["volume"] = 15  # the TV's own level
    with Session(house.engine) as db:
        q = db.get(QueueState, 1)
        q.volume += 5
        db.commit()
    assert tick(2) == ("volume", 20)  # moved from the TV's level, never jumped to the house's
    assert tick(3, position=90.0) == ("seek", 90.0)  # someone seeked on the house player
    assert tick(4, paused=False) == ("resume", 0)
    count = len(calls)
    tick(10, position=96.0)
    assert len(calls) == count  # on time: nothing to do
    # Every 15 s the device is checked; drift above 2 s is corrected.
    seen.update(item_id=mo.hashlib.sha256(url.encode()).hexdigest(), position=120.0)
    assert tick(20, position=106.0) == ("seek", 106.0)
    # The next song loads on its own; when the house stops, the device stops too.
    with Session(house.engine) as db:
        db.get(QueueState, 1).current_id = house.ids[1]
        db.commit()
    assert tick(21, item_id=house.ids[1], position=0.0) == ("load", 0.0, False, False)
    assert tick(22, idle=True) == ("stop", 0)


def test_live_pipes_and_films_are_left_to_the_server(house, monkeypatch):
    from houseos import cinema_cast

    calls = []
    monkeypatch.setattr(settings, "receiver_base_url", "http://192.0.2.17:8991")
    monkeypatch.setattr(cinema_cast, "cast_music", lambda *args: calls.append("load"))
    monkeypatch.setattr(cinema_cast, "cast_control", lambda *args: calls.append(args[1]))
    now = house.ids[0]
    clock = {"status": "observed", "idle": False, "paused": False, "position": 1.0, "item_id": now}
    monkeypatch.setattr(mo, "bridge", lambda command: dict(clock))
    path = settings.runtime_root / "audio" / (now + ".media")
    path.unlink()
    os.mkfifo(path)
    with Session(house.engine) as db:
        db.add(CinemaDevice(id="tv", name="TV", adapter="cast", address="192.0.2.19"))
        mo.save_output_choice(db, cast_device_id="tv")
        db.commit()
    mo.follow_cast()
    assert calls == [] and mo.FOLLOW["item"] == now and mo.FOLLOW["url"] is None
    with Session(house.engine) as db:
        db.get(CinemaDevice, "tv").owner_workflow = "film"
        db.commit()
    mo.follow_cast()
    assert calls == [] and mo.FOLLOW == {}


# ---------- DLNA renderers (Sonos, smart TVs, hi-fi) ----------
SONOS = "http://192.0.2.21:1400"


def fake_renderer(monkeypatch, state):
    """A renderer answering SOAP; records (action, arguments) and follows the transport state."""
    import httpx
    import xml.etree.ElementTree as ET
    from houseos import dlna

    calls = []
    where = SONOS + "/xml/device_description.xml"
    monkeypatch.setattr(dlna, "CONTROLS", {})
    dlna.CONTROLS[where] = {
        "av": SONOS + "/MediaRenderer/AVTransport/Control",
        "rc": SONOS + "/MediaRenderer/RenderingControl/Control",
    }

    def post(url, content, headers, **kwargs):
        service, action = headers["SOAPAction"].strip('"').split("#")
        arguments = {child.tag: child.text for child in ET.fromstring(content).iter() if "}" not in child.tag}
        calls.append((action, arguments))
        assert url == dlna.CONTROLS[where]["rc" if "RenderingControl" in service else "av"]
        if action == "SetAVTransportURI":
            state["TrackURI"] = arguments["CurrentURI"]
        out = {
            "GetTransportInfo": {"CurrentTransportState": "PLAYING"},
            "GetPositionInfo": {"TrackURI": state.get("TrackURI"), "RelTime": state.get("RelTime")},
            "GetVolume": {"CurrentVolume": state.get("CurrentVolume")},
        }.get(action, {})
        body = "".join(f"<{k}>{v}</{k}>" for k, v in out.items())
        reply = (
            '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body>'
            f'<u:{action}Response xmlns:u="{service}">{body}</u:{action}Response></s:Body></s:Envelope>'
        )
        return httpx.Response(200, content=reply.encode(), request=httpx.Request("POST", url))

    monkeypatch.setattr(dlna.httpx, "post", post)
    return calls, where


def test_dlna_follows_the_house_clock_with_an_mp3_copy(house, monkeypatch):
    state = {}
    calls, where = fake_renderer(monkeypatch, state)
    monkeypatch.setattr(settings, "receiver_base_url", "http://192.0.2.17:8991")
    clock = {"status": "observed", "idle": False, "paused": False, "position": 10.0, "item_id": house.ids[0]}
    monkeypatch.setattr(mo, "bridge", lambda command: dict(clock))
    now = [0.0]
    monkeypatch.setattr(mo.time, "monotonic", lambda: now[0])

    def copy(path):  # WebM/Opus is not for every renderer: an MP3 copy is served instead
        target = path.with_suffix(".dlna")
        target.write_bytes(b"ID3" + b"\0" * 60)
        return target

    monkeypatch.setattr(mo, "mp3_copy", copy)
    with Session(house.engine) as db:
        db.add(
            CinemaDevice(
                id="sonos",
                name="Living Room",
                adapter="dlna",
                address="192.0.2.21",
                capabilities={"description_url": where},
            )
        )
        mo.save_output_choice(db, device_id="sonos")
        db.commit()

    def tick(at, **changes):
        now[0] = at
        clock.update(changes)
        calls.clear()
        mo.follow_cast()
        return [
            (action, arguments.get("Target") or arguments.get("DesiredVolume")) for action, arguments in calls
        ]

    assert tick(0) == [
        ("SetAVTransportURI", None),
        ("Play", None),
        ("GetTransportInfo", None),
        ("Seek", "0:00:10"),  # starts where the house is
    ]
    url = mo.FOLLOW["url"]
    assert url == state["TrackURI"] and url.startswith("http://192.0.2.17:8991/receiver/music/")
    # The renderer (seen from its own address) gets the MP3 copy, with the DLNA headers.
    with Session(house.engine) as db:
        grant = mo.output_choice(db)["grant"]
        grant["address"] = "testclient"
        mo.save_output_choice(db, grant=grant)
        db.commit()
    served = house.client.get(url.removeprefix("http://192.0.2.17:8991"))
    assert served.status_code == 200 and served.headers["content-type"] == "audio/mpeg"
    assert served.headers["transferMode.dlna.org"] == "Streaming"
    assert tick(1, paused=True, position=11.0) == [("Pause", None)]
    state["CurrentVolume"] = "30"
    with Session(house.engine) as db:
        db.get(QueueState, 1).volume -= 10
        db.commit()
    assert tick(2) == [("GetVolume", None), ("SetVolume", "20")]
    assert tick(3, position=90.0) == [("Seek", "0:01:30")]  # someone seeked on the house player
    assert tick(4, paused=False) == [("Play", None)]
    assert tick(10, position=96.0) == []  # on time: nothing to do
    state["RelTime"] = "0:02:00"  # every 15 s the renderer is checked; drift above 2 s is fixed
    assert tick(20, position=106.0) == [("GetPositionInfo", None), ("Seek", "0:01:46")]
    state["RelTime"] = "NOT_IMPLEMENTED"  # a renderer that cannot tell is left alone
    assert tick(36, position=122.0) == [("GetPositionInfo", None)]
    with Session(house.engine) as db:
        db.get(QueueState, 1).current_id = house.ids[1]
        db.commit()
    assert tick(37, item_id=house.ids[1], position=0.0)[0] == ("SetAVTransportURI", None)
    assert tick(38, idle=True) == [("Stop", None)]


def test_a_renderer_that_stops_answering_is_looked_up_again(house, monkeypatch):
    import httpx
    from houseos import dlna

    where = SONOS + "/xml/device_description.xml"
    monkeypatch.setattr(dlna, "CONTROLS", {where: {"av": SONOS + "/AVTransport", "rc": None}})

    def refused(*args, **kwargs):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(dlna.httpx, "post", refused)
    with pytest.raises(mo.MediaError):
        dlna.dlna_control(where, "pause", 0)
    assert where not in dlna.CONTROLS  # its port may have changed: found again next time


def test_output_choices_made_before_dlna_still_count(house):
    with Session(house.engine) as db:
        db.add(Integration(name=mo.OUTPUT, config={"cast_device_id": "tv"}))
        db.commit()
        assert mo.output_choice(db)["device_id"] == "tv"
        mo.save_output_choice(db, device_id=None, grant=None)  # "this computer" chosen since
        db.commit()
        assert mo.output_choice(db)["device_id"] is None


def test_the_mp3_copy_is_made_once_and_only_for_the_current_song(tmp_path, monkeypatch):
    runs = []

    def ffmpeg(command, **kwargs):
        runs.append(command)
        (tmp_path / "b.dlna.part").write_bytes(b"ID3")

    (tmp_path / "a.dlna").write_bytes(b"old")
    monkeypatch.setattr(mo.subprocess, "run", ffmpeg)
    assert mo.mp3_copy(tmp_path / "b.media") == tmp_path / "b.dlna"
    assert mo.mp3_copy(tmp_path / "b.media") == tmp_path / "b.dlna"
    assert len(runs) == 1 and "libmp3lame" in runs[0]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["b.dlna"]


# ---------- radio replaces radio; Stop keeps the place ----------
def test_a_new_station_replaces_the_one_on_air_but_songs_still_queue(house, monkeypatch):
    now = house.ids[0]
    with Session(house.engine) as db:
        db.get(QueueItem, now).source_url = "radio:" + str(uuid.uuid4())
        db.commit()
    stopped = []
    from houseos import worker

    monkeypatch.setattr(worker, "fetch", lambda action, **kw: stopped.append((action, kw)))
    song = house.client.post(
        "/music/queue",
        json={"source_url": "https://www.youtube.com/watch?v=zzzzzzzzzzz", "idempotency_key": "song-now"},
    )
    assert song.status_code == 200 and not song.json()["autoplay_requested"]
    station = house.client.post(
        "/music/radio/" + str(uuid.uuid4()) + "/queue", json={"idempotency_key": "radio-now"}
    )
    assert station.status_code == 200 and station.json()["autoplay_requested"]
    with Session(house.engine) as db:
        q, old = db.get(QueueState, 1), db.get(QueueItem, now)
        assert q.current_id == station.json()["item_id"] and q.desired == "playing"
        assert old.status == "completed" and old.metadata_json["ended_reason"] == "replaced_by_station"
        assert db.get(QueueItem, song.json()["item_id"]).status == "pending_metadata"
    assert stopped == [("live_stop", {"item_id": now})]


def test_a_station_still_connecting_is_replaced_too(house, monkeypatch):
    now = house.ids[0]
    with Session(house.engine) as db:
        item = db.get(QueueItem, now)
        item.source_url, item.status = "radio:" + str(uuid.uuid4()), "pending_metadata"
        db.commit()
    from houseos import worker

    monkeypatch.setattr(worker, "fetch", lambda action, **kw: None)
    station = house.client.post(
        "/music/radio/" + str(uuid.uuid4()) + "/queue", json={"idempotency_key": "radio-next"}
    )
    with Session(house.engine) as db:
        assert db.get(QueueState, 1).current_id == station.json()["item_id"]
        assert db.get(QueueItem, now).metadata_json["ended_reason"] == "replaced_by_station"


def test_stop_releases_the_speakers_and_keeps_the_place(house):
    now = house.ids[0]
    with Session(house.engine) as db:
        item = db.get(QueueItem, now)
        item.metadata_json = {**item.metadata_json, "last_position": 42}
        db.commit()
    result = house.client.post(
        "/music/control", json={"action": "stop", "expected_version": 1, "idempotency_key": "stop-now"}
    )
    assert result.status_code == 200
    with Session(house.engine) as db:
        q, item = db.get(QueueState, 1), db.get(QueueItem, now)
        assert (q.desired, q.current_id, item.status) == ("paused", now, "ready")
        assert item.metadata_json["resume_position"] == 42


# ---------- the household LAN ----------
def test_private_lan_addresses_are_accepted_without_a_configured_range(monkeypatch):
    from houseos.cinema_models import DeviceInput
    from houseos.integrations import check_config

    monkeypatch.setattr(settings, "cast_lan_cidr", "")
    check_config("cast", {"host": "192.168.1.20"})
    check_config("cast", {"host": "10.0.0.7"})
    for address in ["127.0.0.1", "169.254.3.4", "8.8.8.8", "224.0.0.1"]:
        with pytest.raises(HTTPException):
            check_config("cast", {"host": address})
    monkeypatch.setattr(settings, "cast_lan_cidr", "192.168.1.0/24")
    with pytest.raises(HTTPException):
        check_config("cast", {"host": "10.0.0.7"})
    assert DeviceInput(name="TV", adapter="cast", address="192.168.1.20").address == "192.168.1.20"


def test_the_listening_socket_never_replaces_the_sound_server_kind(tmp_path, monkeypatch):
    """Regression: `with UnixStreamServer(...) as server` once overwrote the global `server`
    ("pulse"/"alsa"/"none"), so every later answer failed to serialize."""
    from types import SimpleNamespace

    from houseos import audio

    seen = {}

    class Listener:
        def __init__(self, *args):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def serve_forever(self):
            seen["kind"] = audio.server

    monkeypatch.setattr(audio, "detect_server", lambda *a, **k: "none")
    monkeypatch.setattr(audio, "start_player", lambda *a: None)
    monkeypatch.setattr(audio, "outputs", lambda: [{"id": "none"}])
    monkeypatch.setattr(audio.socketserver, "UnixStreamServer", Listener)
    monkeypatch.setattr(audio.os, "chmod", lambda *a: None)
    monkeypatch.setattr(audio, "player", SimpleNamespace(terminate=lambda: None, wait=lambda timeout: None))
    monkeypatch.setattr(audio.settings, "runtime_root", tmp_path)
    monkeypatch.setattr(audio.settings, "audio_socket", tmp_path / "audio.sock")
    monkeypatch.setattr(audio, "MEDIA", tmp_path / "audio")
    audio.main()
    assert seen["kind"] == "none"


def test_speakers_switch_mid_song(monkeypatch):
    """Picking another output never needs the music stopped: same sound server, mpv changes
    device; otherwise the player restarts and the song resumes; a live pipe says why not."""
    from houseos import audio

    state = {
        "idle-active": False,
        "current-ao": "pulse",
        "path": "/a/song.media",
        "time-pos": 42.5,
        "pause": False,
    }
    sent, started = [], []
    monkeypatch.setattr(audio, "server", "pulse")
    monkeypatch.setattr(audio, "default_sink", lambda: "alsa_output.analog")
    monkeypatch.setattr(audio, "start_player", lambda sink: started.append(sink))

    def mpv(command):
        sent.append(command)
        return state.get(command[1]) if command[0] == "get_property" else None

    monkeypatch.setattr(audio, "mpv", mpv)
    monkeypatch.setattr(audio, "live_item", None)
    assert audio.move_to("bluez_output.jbl") is None
    assert ["set_property", "audio-device", "pulse/bluez_output.jbl"] in sent and started == []

    sent.clear()
    assert audio.move_to("none") is None  # to silence: a new player, same song, same place
    assert started == ["none"]
    assert sent[-3:] == [
        ["set_property", "start", "42.5"],
        ["loadfile", "/a/song.media", "replace"],
        ["set_property", "pause", False],
    ]

    monkeypatch.setattr(audio, "live_item", "radio-item")
    state["current-ao"] = "null"
    assert audio.move_to("default")["code"] == "LIVE_OUTPUT_SWITCH"
    assert audio.kind("bluez_output.00_11.1") == "bluetooth" and audio.kind("x.hdmi-stereo") == "hdmi"


def test_a_silent_speaker_says_why_on_listen(house, monkeypatch):
    """A speaker that doesn't answer (or refuses, like a grouped Sonos) is named on Listen
    instead of leaving everyone to listen to silence; choosing again clears it."""
    from houseos import cinema_cast
    from houseos.playback import MediaError

    monkeypatch.setattr(settings, "receiver_base_url", "http://192.0.2.17:8991")

    def offline(*args):
        raise MediaError(
            "TARGET_OFFLINE", "The configured Cast receiver did not respond.", "destination", True
        )

    monkeypatch.setattr(cinema_cast, "cast_music", offline)
    clock = {"status": "observed", "idle": False, "paused": False, "position": 1.0, "item_id": house.ids[0]}
    monkeypatch.setattr(mo, "bridge", lambda command: dict(clock))
    with Session(house.engine) as db:
        db.add(CinemaDevice(id="tv", name="TV", adapter="cast", address="192.0.2.19"))
        mo.save_output_choice(db, device_id="tv")
        db.commit()
    mo.follow_cast()
    with Session(house.engine) as db:
        assert mo.output_choice(db)["problem"] == "TARGET_OFFLINE"
