import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from houseos.db import Base, utcnow
from houseos.models import User, SessionToken
from houseos.cinema import CinemaTitle, CinemaDevice, CinemaWorkflow, CinemaRelay
from houseos.cinema_delivery import local_stream, revocable_chunks, grant_authorized


class DeliveryTests(unittest.TestCase):
    def test_exact_local_ranges_head_and_subtitle_mime_source_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "fixture"
            path.write_bytes(b"0123456789")
            status, headers, chunks = local_stream(path, "bytes=2-5")
            self.assertEqual(status, 206)
            self.assertEqual(headers["Content-Range"], "bytes 2-5/10")
            self.assertEqual(b"".join(chunks), b"2345")
            self.assertEqual(b"".join(local_stream(path, "bytes=-3")[2]), b"789")
            self.assertEqual(local_stream(path, "bytes=10-")[0], 416)
            status, headers, chunks = local_stream(path, head=True)
            self.assertEqual(headers["Content-Length"], "10")
            self.assertEqual(b"".join(chunks), b"")

    def test_inflight_revocation_stops_and_closes_upstream(self):
        closed = []

        def source():
            try:
                yield b"a" * 1024**2
                yield b"forbidden-after-revocation"
            finally:
                closed.append(True)

        with patch("houseos.cinema_delivery.grant_authorized", side_effect=[True, False]) as auth:
            output = b"".join(revocable_chunks(source(), object(), "opaque-grant-hash"))
        self.assertEqual(len(output), 1024**2)
        self.assertEqual(closed, [True])
        self.assertEqual(auth.call_count, 2)

    def test_actual_grant_requires_active_session_owner_and_destination(self):
        engine = create_engine("sqlite://", poolclass=StaticPool)
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            db.add(User(id="user", name="User", username="user", password_hash="fixture", role="resident"))
            db.add(
                SessionToken(
                    token_hash="session",
                    user_id="user",
                    csrf_token="fixture",
                    expires_at=utcnow() + timedelta(hours=1),
                )
            )
            db.add(CinemaTitle(id="title", canonical_id="fixture", title="Fixture", kind="movie"))
            db.add(
                CinemaDevice(
                    id="device",
                    name="Fixture",
                    adapter="cast",
                    address="192.0.2.17",
                    owner_workflow="workflow",
                )
            )
            db.add(
                CinemaWorkflow(
                    id="workflow",
                    owner_id="user",
                    media_id="title",
                    device_id="device",
                    idempotency_key="fixture-key",
                    state="playing_observed",
                    data={"_authorization_session": "session"},
                )
            )
            db.add(
                CinemaRelay(
                    token_hash="grant",
                    workflow_id="workflow",
                    device_address="192.0.2.17",
                    path="",
                    mime="video/mp4",
                    expires_at=utcnow() + timedelta(hours=1),
                )
            )
            db.commit()
            self.assertTrue(grant_authorized(engine, "grant"))
            db.delete(db.get(SessionToken, "session"))
            db.commit()
            self.assertFalse(grant_authorized(engine, "grant"))
        engine.dispose()

    def test_rd_renewal_is_same_file_once_and_does_not_add_select_or_play(self):
        from cryptography.fernet import Fernet
        from houseos.config import settings
        from houseos.cinema_delivery import refresh_rd_relay
        from houseos.playback import MediaError

        engine = create_engine("sqlite://", poolclass=StaticPool)
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            db.add(User(id="user", name="User", username="user", password_hash="fixture", role="resident"))
            db.add(CinemaTitle(id="title", canonical_id="fixture", title="Fixture", kind="movie"))
            db.add(
                CinemaDevice(
                    id="device",
                    name="Fixture",
                    adapter="cast",
                    address="192.0.2.17",
                    owner_workflow="workflow",
                )
            )
            db.add(
                CinemaWorkflow(
                    id="workflow",
                    owner_id="user",
                    media_id="title",
                    device_id="device",
                    idempotency_key="fixture-key",
                    state="playing_observed",
                    data={
                        "_selected_source": "source",
                        "_sources": [
                            {
                                "id": "source",
                                "torrent_id": "existing-torrent",
                                "file_id": "7",
                                "info_hash": "a" * 40,
                                "size": 100,
                            }
                        ],
                        "checkpoint": {"position": 45},
                    },
                )
            )
            db.add(
                CinemaRelay(
                    token_hash="grant",
                    workflow_id="workflow",
                    device_address="192.0.2.17",
                    path="",
                    mime="video/mp4",
                    expires_at=utcnow() + timedelta(hours=1),
                )
            )
            db.commit()
        with (
            patch.object(settings, "encryption_key", Fernet.generate_key().decode()),
            patch("houseos.integrations.integration_config", return_value={}),
            patch("houseos.cinema_sources.RealDebrid") as rd,
        ):
            rd.return_value.info.return_value = {"hash": "a" * 40}
            rd.return_value.resolve.return_value = ("https://example.org/new-private-stream", 100)
            self.assertEqual(refresh_rd_relay(engine, "grant"), "https://example.org/new-private-stream")
            rd.return_value.resolve.assert_called_once_with("existing-torrent", "7")
            rd.return_value.add.assert_not_called()
            rd.return_value.select.assert_not_called()
            with self.assertRaisesRegex(MediaError, "SOURCE_EXPIRED"):
                refresh_rd_relay(engine, "grant")
            self.assertEqual(rd.return_value.resolve.call_count, 1)
            with Session(engine) as db:
                row = db.get(CinemaWorkflow, "workflow")
                self.assertEqual(row.data["checkpoint"]["position"], 45)
                self.assertEqual(row.state, "playing_observed")
                row.data = {**row.data, "_relay_refresh_attempts": 0}
                db.commit()

            def revoked(*args):
                with Session(engine) as db:
                    db.get(User, "user").active = False
                    db.commit()
                return "https://example.org/must-not-publish", 100

            rd.return_value.resolve.side_effect = revoked
            with self.assertRaisesRegex(MediaError, "PERMISSION_REVOKED"):
                refresh_rd_relay(engine, "grant")
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
