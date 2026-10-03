"""Setup checklist and service health come from measurements, and read as such."""

import socketserver
import threading
from datetime import timedelta

import pytest

from houseos import radio
from houseos.config import settings
from houseos.db import utcnow
from houseos.models import Integration
from test_core import admin


def test_a_fresh_container_lists_honest_steps(client, quiet):
    c, db = client
    admin(client)
    body = c.get("/api/v1/admin/setup").json()
    states = {s["key"]: s["state"] for s in body["steps"]}
    assert body["container"] is True
    assert states["house"] == "todo" and states["ai"] == "todo" and states["invite"] == "todo"
    assert states["access"] == "todo"  # the test client speaks plain HTTP
    assert states["speakers"] == "unavailable" and states["sources"] == "unavailable"
    assert states["films"] == "unavailable" and states["voice"] == "optional"
    assert body["done"] == 0 and body["needed"] == 6


def test_services_are_measured_and_restart_through_compose(client, quiet):
    c, db = client
    admin(client)
    db.add(Integration(name="worker_heartbeat", config={"observed_at": utcnow().isoformat() + "Z"}))
    old = (utcnow() - timedelta(minutes=10)).isoformat() + "Z"
    db.add(Integration(name="maintenance_heartbeat", config={"observed_at": old}))
    db.commit()

    class Fetch(socketserver.StreamRequestHandler):
        def handle(self):
            self.rfile.readline()
            self.wfile.write(b'{"status": "ok"}\n')

    server = socketserver.UnixStreamServer(str(quiet / "fetch.sock"), Fetch)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        rows = {r["name"]: r for r in c.get("/api/v1/admin/services").json()}
    finally:
        server.shutdown()
        server.server_close()
    assert rows["api"]["status"] == "ok" and rows["worker"]["status"] == "ok"
    assert rows["maintenance"]["status"] == "down" and rows["fetch"]["status"] == "ok"
    assert rows["audio"]["status"] == "off" and rows["voice"]["status"] == "off"
    assert rows["worker"]["restartable"] and not rows["upload"]["restartable"]


def test_radio_never_reaches_the_house_network(monkeypatch):
    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda host, *a, **k: [(2, 1, 6, "", ("192.168.1.1" if host == "evil.example" else "8.8.8.8", 0))],
    )
    assert radio.require_public("https://stream.example/radio") == "https://stream.example/radio"
    with pytest.raises(ValueError):
        radio.require_public("http://evil.example/stream")


def test_health_points_to_its_settings_and_accepts_a_manual_it_works(client):
    import time

    c, db = client
    admin(client)
    db.add(Integration(name="jellyfin", config={}, enabled=True))
    db.commit()

    def jellyfin():
        return next(x for x in c.get("/api/v1/admin/health").json()["checks"] if x["component"] == "jellyfin")

    assert jellyfin()["status"] == "configured_unverified" and jellyfin()["tab"] == "integrations"
    assert c.post("/api/v1/admin/health/jellyfin/confirm").status_code == 200
    assert jellyfin()["status"] == "confirmed" and jellyfin()["confirmed_by"] == "Test Admin"
    time.sleep(0.01)
    db.get(Integration, "jellyfin").config = {"base_url": "http://jellyfin.lan:8096"}
    db.commit()  # changing the connection needs a new check
    assert jellyfin()["status"] == "configured_unverified"
    assert c.post("/api/v1/admin/health/nonsense/confirm").status_code == 404


def test_find_devices_round_trip_through_the_relay(client, monkeypatch):
    from contextlib import nullcontext

    from houseos import discovery

    c, db = client
    admin(client)
    assert c.post("/api/v1/admin/devices/discover").json() == {"status": "scanning"}
    assert c.get("/api/v1/admin/devices/discover").json()["scanning"] is True
    tv = {"name": "Living room", "model": "Google TV", "maker": "", "address": "192.0.2.21", "kind": "tv"}
    monkeypatch.setattr(discovery, "scan", lambda: [tv])
    monkeypatch.setattr(discovery, "SessionLocal", lambda: nullcontext(db))
    discovery.answer_request()
    found = c.get("/api/v1/admin/devices/discover").json()
    assert found["scanning"] is False and found["devices"] == [tv]


def test_docker_services_restart_from_the_app(client, quiet, monkeypatch):
    monkeypatch.setattr(settings, "runtime_root", quiet)
    c, db = client
    admin(client)
    prepared = c.post("/api/v1/admin/services/worker/prepare-restart", json={}).json()
    assert c.post("/api/v1/admin/services/confirmations/" + prepared["confirmation_id"]).status_code == 200
    from houseos.config import settings as live

    assert (live.runtime_root / "run" / "restart" / "worker").exists()
    assert c.post("/api/v1/admin/services/upload/prepare-restart", json={}).status_code == 409
