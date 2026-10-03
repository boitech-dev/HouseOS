"""Trusted addresses: parsed strictly, adopted by the first admin, explained when refused."""

from contextlib import nullcontext

import pytest

from houseos import access
from houseos.config import settings


def test_normalize_origins():
    assert access.normalize(" https://House.LAN:443/ ") == "https://house.lan"
    assert access.normalize("http://192.0.2.12:8990") == "http://192.0.2.12:8990"
    assert access.normalize("http://[::1]:80") == "http://[::1]"
    for bad in ("house.lan", "ftp://x", "https://u:p@x", "https://x/path", "https://x?q", ""):
        assert access.normalize(bad) is None


@pytest.fixture
def house(client, monkeypatch):
    c, db = client
    monkeypatch.setattr(access, "SessionLocal", lambda: nullcontext(db))
    monkeypatch.setitem(access._cache, "open", True)
    access.forget()
    yield c, db
    access.forget()
    access._cache["open"] = True


def test_first_admin_adopts_the_proxy_address_then_strangers_are_refused(house):
    c, db = house
    proxy = {"Origin": "https://house.example.net", "Host": "house.example.net"}
    # Before any account, any name may show the setup page.
    assert c.get("/api/v1/auth/status", headers={"Host": "house.example.net"}).status_code == 200
    response = c.post(
        "/api/v1/auth/bootstrap",
        headers=proxy,
        json={
            "name": "Owner",
            "username": "owner",
            "password": "test-only-password-very-long",
            "setup_token": settings.bootstrap_token,
        },
    )
    assert response.status_code == 200, response.text
    access.forget()
    csrf = {"X-CSRF-Token": response.json()["csrf_token"]}
    assert c.put("/api/v1/preferences", json={}, headers=proxy | csrf).status_code == 200
    listed = c.get("/api/v1/admin/access", headers=proxy).json()
    assert {"origin": "https://house.example.net", "source": "house"} in listed["origins"]

    refused = c.put("/api/v1/preferences", json={}, headers={"Origin": "https://evil.example"} | csrf)
    assert refused.status_code == 403
    assert "Control Room → Access" in refused.json()["detail"]
    page = c.get("/", headers={"Host": "evil.example"})
    assert page.status_code == 400 and "Almost there" in page.text


def test_admin_adds_and_removes_an_address(house):
    c, db = house
    from test_core import admin

    admin((c, db))
    assert c.post("/api/v1/admin/access", json={"origin": "not an address"}).status_code == 422
    assert c.post("/api/v1/admin/access", json={"origin": "https://Phone.lan:443"}).json() == {
        "origin": "https://phone.lan"
    }
    access.forget()
    assert c.get("/api/v1/auth/me", headers={"Host": "phone.lan"}).status_code == 200
    assert c.delete("/api/v1/admin/access", params={"origin": "https://phone.lan"}).status_code == 200
    access.forget()
    assert c.get("/api/v1/auth/me", headers={"Host": "phone.lan"}).status_code == 400


def test_the_address_announced_on_the_wifi_is_trusted_by_itself(house):
    c, db = house
    from houseos.discovery import ANNOUNCED
    from houseos.models import Integration
    from test_core import admin

    admin((c, db))
    wifi = {"Origin": "https://houseos.local:8443", "Host": "houseos.local:8443"}
    access.forget()
    assert c.get("/api/v1/auth/me", headers=wifi).status_code == 400
    db.add(Integration(name=ANNOUNCED, config={"origin": "https://houseos.local:8443"}))
    db.commit()
    access.forget()
    assert c.get("/api/v1/auth/me", headers=wifi).status_code == 200
    listed = c.get("/api/v1/admin/access").json()["origins"]
    assert {"origin": "https://houseos.local:8443", "source": "wifi"} in listed
    kept = c.delete("/api/v1/admin/access", params={"origin": "https://houseos.local:8443"})
    assert kept.status_code == 409 and "HOUSEOS_MDNS_NAME" in kept.json()["detail"]


def test_the_https_door_gets_certificates_only_for_trusted_names(house):
    c, db = house
    from test_core import admin

    ask = lambda name: c.get("/api/v1/access/tls-ask", params={"domain": name}, headers={"Host": "api:8990"})
    assert ask("anything.example").status_code == 200  # before the first account
    admin((c, db))
    assert c.post("/api/v1/admin/access", json={"origin": "https://phone.lan:8443"}).status_code == 200
    access.forget()
    assert ask("phone.lan").status_code == 200  # asked as api:8990, after setup
    assert ask("evil.example").status_code == 403
