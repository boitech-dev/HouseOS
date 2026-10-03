import unittest
from datetime import timedelta
from unittest.mock import patch
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from houseos.db import Base, utcnow
from houseos.models import User, Job
from houseos.auth import Actor
from houseos.cinema import Discover
from houseos.cinema_jobs import enqueue_discovery, get_operation, process_one_operation


class CinemaJobTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine, expire_on_commit=False)
        self.db.add(
            User(
                id="resident",
                username="resident",
                name="Resident",
                password_hash="unused",
                role="resident",
                permissions=[],
            )
        )
        self.db.commit()
        self.actor = Actor("resident", "Resident", "resident", frozenset({"cinema.use"}))
        self.body = Discover(media_id="title", device_id="device", idempotency_key="discovery-idempotency")

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_enqueue_is_immediate_idempotent_and_owner_scoped(self):
        with patch("houseos.cinema_jobs.discover") as provider:
            first = enqueue_discovery(self.body, self.actor, self.db)
            second = enqueue_discovery(self.body, self.actor, self.db)
            self.assertEqual(first, second)
            provider.assert_not_called()
        other = Actor("other", "Other", "resident", frozenset({"cinema.use"}))
        with self.assertRaisesRegex(Exception, "404"):
            get_operation(first["operation_id"], other, self.db)

    def test_worker_persists_compact_result(self):
        accepted = enqueue_discovery(self.body, self.actor, self.db)
        with patch(
            "houseos.cinema_jobs.discover", return_value={"id": "workflow", "state": "awaiting_choice"}
        ) as provider:
            self.assertTrue(process_one_operation(self.db))
            self.assertFalse(process_one_operation(self.db))
            self.assertEqual(provider.call_count, 1)
        result = get_operation(accepted["operation_id"], self.actor, self.db)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["workflow_id"], "workflow")

    def test_revoked_actor_never_calls_provider(self):
        accepted = enqueue_discovery(self.body, self.actor, self.db)
        self.db.get(User, "resident").active = False
        self.db.commit()
        with patch("houseos.cinema_jobs.discover") as provider:
            process_one_operation(self.db)
            provider.assert_not_called()
        self.assertEqual(
            get_operation(accepted["operation_id"], self.actor, self.db)["error"]["code"],
            "PERMISSION_REVOKED",
        )

    def test_interrupted_remote_work_does_not_replay(self):
        accepted = enqueue_discovery(self.body, self.actor, self.db)
        job = self.db.scalar(select(Job))
        job.state, job.lease_until = "running", utcnow() - timedelta(seconds=1)
        self.db.commit()
        with patch("houseos.cinema_jobs.discover") as provider:
            process_one_operation(self.db)
            provider.assert_not_called()
        self.assertEqual(get_operation(accepted["operation_id"], self.actor, self.db)["status"], "unverified")


if __name__ == "__main__":
    unittest.main()
