from datetime import datetime, timedelta
from types import SimpleNamespace
import base64

import pytest
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric.ec import generate_private_key, SECP256R1
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from fastapi import HTTPException
from sqlalchemy import select

from houseos import notifications as n
from houseos.config import settings
from houseos.db import new_id, utcnow
from houseos.household import HouseholdNotification


def subscription():
    key = (
        generate_private_key(SECP256R1())
        .public_key()
        .public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    )
    encode = lambda data: base64.urlsafe_b64encode(data).decode().rstrip("=")
    return n.SubscriptionInput(
        endpoint="https://fcm.googleapis.com/fcm/send/test-fixture-not-real",
        keys={"p256dh": encode(key), "auth": encode(b"a" * 16)},
    )


def test_push_endpoint_and_quiet_hours():
    for url in [
        "http://fcm.googleapis.com/x",
        "https://fcm.googleapis.com.evil.test/x",
        "https://127.0.0.1/x",
        "https://fcm.googleapis.com:8443/x",
        "https://a@fcm.googleapis.com/x",
    ]:
        with pytest.raises(HTTPException):
            n.validate_endpoint(url)
    n.validate_subscription(subscription())
    # Paris 23:30 during winter and summer, plus an ordinary morning; UTC without a zone.
    paris = {"timezone": "Europe/Paris"}
    assert n.quiet_now(paris, datetime(2026, 1, 1, 22, 30))
    assert n.quiet_now(paris, datetime(2026, 7, 1, 21, 30))
    assert not n.quiet_now(paris, datetime(2026, 7, 1, 9, 30))
    assert n.quiet_now({}, datetime(2026, 7, 1, 23, 30)) and not n.quiet_now({}, datetime(2026, 7, 1, 21, 30))


def test_push_privacy_and_acceptance_not_read(domain, monkeypatch):
    db, (alice, bob, _) = domain
    monkeypatch.setattr(settings, "encryption_key", Fernet.generate_key().decode())
    monkeypatch.setattr(n, "configured", lambda: True)
    monkeypatch.setattr(n, "quiet_now", lambda prefs, now: False)
    created = n.subscribe(subscription(), alice, db)
    stored = db.get(n.PushSubscription, created["id"])
    assert "fcm.googleapis.com" not in stored.encrypted_payload
    with pytest.raises(HTTPException):
        n.subscribe(subscription(), bob, db)
    note = HouseholdNotification(
        id=new_id(),
        user_id=alice.id,
        record_id=new_id(),
        category="message",
        dedupe_key=new_id(),
        created_at=utcnow() + timedelta(microseconds=10),
    )
    db.add(note)
    db.commit()
    sent = []
    monkeypatch.setattr(
        n, "send_push", lambda sub, payload: sent.append(payload) or SimpleNamespace(status_code=201)
    )
    result = n.deliver_pending(db)
    assert result["accepted"] == 1
    assert sent[0]["body"] == "New house message"
    assert note.read_at is None
    assert db.scalar(select(n.PushDelivery)).state == "provider_accepted"
    assert n.deliver_pending(db)["accepted"] == 0
    n.unsubscribe(created["id"], alice, db)
    assert not stored.active


def test_webpush_crypto_and_pinned_transport_without_network(monkeypatch, tmp_path):
    from cryptography.hazmat.primitives.serialization import PrivateFormat, NoEncryption
    import requests

    key = generate_private_key(SECP256R1())
    keyfile = tmp_path / "vapid-test.pem"
    keyfile.write_bytes(key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()))
    keyfile.chmod(0o600)
    monkeypatch.setattr(settings, "vapid_private_key", str(keyfile))
    monkeypatch.setattr(settings, "vapid_subject", "mailto:test@example.invalid")
    calls = []

    class Transport:
        def post(self, url, data, headers, **kw):
            calls.append((url, data, headers))
            result = requests.Response()
            result.status_code = 201
            result._content = b""
            return result

    monkeypatch.setattr(n, "PinnedPushSession", Transport)
    assert (
        n.send_push(subscription().model_dump(exclude_none=True), {"body": "New house message"}).status_code
        == 201
    )
    assert b"New house message" not in calls[0][1]
    assert calls[0][2]["content-encoding"] == "aes128gcm"


def test_push_dns_private_address_rejected(monkeypatch):
    monkeypatch.setattr(n.socket, "getaddrinfo", lambda *args, **kw: [(2, 1, 6, "", ("127.0.0.1", 443))])
    with pytest.raises(ValueError):
        n.PinnedPushSession().post("https://fcm.googleapis.com/fcm/send/fixture", b"encrypted", {})
