import contextlib
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
import wave
from types import SimpleNamespace
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from houseos.auth import Actor, require_actor
from houseos.db import Base, get_db
from houseos.models import User, Job
from houseos.files import FileEntry
from houseos.music import router, QueueState, QueueItem
from houseos.music_library import stage_local_audio, authorized_vote_job


class MusicLibraryTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
        )
        Base.metadata.create_all(self.engine)
        with Session(self.engine) as db:
            for identity in ["one", "two", "three"]:
                db.add(
                    User(
                        id=identity, name=identity, username=identity, password_hash="unused", role="resident"
                    )
                )
            db.add(QueueState(id=1))
            db.add(
                QueueItem(
                    id="track",
                    owner_id="one",
                    source_url="https://www.youtube.com/watch?v=abcdefghijk",
                    title="Synthetic",
                    position=1,
                    status="playing",
                )
            )
            db.commit()
        self.actor = Actor("one", "One", "resident", frozenset({"music.read", "music.queue", "files.read"}))
        self.app = FastAPI()
        self.app.include_router(router)
        self.app.dependency_overrides[require_actor] = lambda: self.actor

        def session():
            with Session(self.engine, expire_on_commit=False) as db:
                yield db

        self.app.dependency_overrides[get_db] = session
        self.client = TestClient(self.app)

    def test_named_playlists_are_private_and_import_is_previewed(self):
        made = self.client.post("/music/library/playlists", json={"name": "Evening", "item_ids": ["track"]})
        self.assertEqual(made.status_code, 200)
        identity = made.json()["id"]
        preview = self.client.post("/music/library/playlists/" + identity + "/preview")
        self.assertEqual(preview.json()["status"], "needs_confirmation")
        self.actor = Actor("two", "Two", "resident", self.actor.permissions)
        self.assertEqual(self.client.get("/music/library/playlists").json()["items"], [])
        self.assertEqual(
            self.client.post("/music/library/playlists/" + identity + "/preview").status_code, 404
        )

    def test_a_linked_playlist_is_kept_as_a_house_playlist_page_by_page(self):
        from houseos import music, worker

        songs = [
            {"source_url": f"https://www.youtube.com/watch?v={i:011d}", "title": f"Song {i}"}
            for i in range(50)
        ]
        with patch.object(
            worker,
            "fetch",
            return_value={
                "status": "completed",
                "items": songs,
                "total": 70,
                "title": "Road trip",
                "unavailable": 2,
            },
        ):
            made = self.client.post(
                "/music/library/playlists/import",
                json={"url": "https://www.youtube.com/playlist?list=PLabcdefghij"},
            ).json()
        self.assertEqual(
            (made["name"], len(made["items"]), made["total"], made["unavailable"]), ("Road trip", 50, 70, 2)
        )
        with Session(self.engine) as db:
            job = db.scalar(select(Job).where(Job.kind == "music.playlist_import"))
            self.assertEqual((job.payload["playlist_id"], job.payload["start"]), (made["id"], 51))
            identity, generation, payload = job.id, job.generation, job.payload
            job.state = "running"
            db.commit()
        more = [
            {"source_url": f"https://www.youtube.com/watch?v={i:011d}", "title": f"Song {i}"}
            for i in range(45, 70)
        ]
        with (
            patch.object(worker, "fetch", return_value={"status": "completed", "items": more}),
            patch("houseos.db.SessionLocal", lambda: Session(self.engine, expire_on_commit=False)),
        ):
            music.import_playlist_page(identity, generation, payload)
        detail = self.client.get("/music/library/playlists/" + made["id"]).json()
        self.assertEqual(len(detail["items"]), 70)  # 50, then the 20 new ones; repeats once
        self.assertFalse(detail["items"][0]["at_home"])
        with Session(self.engine) as db:
            self.assertEqual(db.scalars(select(QueueItem)).all().__len__(), 1)  # nothing was queued

    def test_a_removed_song_leaves_the_queue_and_its_other_version_takes_its_place(self):
        from houseos import worker

        gone = "https://www.youtube.com/watch?v=gonegonegon"
        other = "https://www.youtube.com/watch?v=othervideo1"
        lists = "/music/library/playlists"
        playlist = self.client.post(lists, json={"name": "Mix", "source_urls": [gone]}).json()
        with Session(self.engine) as db:
            db.add(
                QueueItem(
                    id="lost",
                    owner_id="one",
                    source_url=gone,
                    title="Old hit",
                    position=2,
                    metadata_json={"playlist_id": playlist["id"]},
                )
            )
            db.add(
                Job(
                    id="meta",
                    logical_key="metadata:lost",
                    kind="music.metadata",
                    actor_id="one",
                    payload={"item_id": "lost"},
                    state="running",
                    generation=1,
                )
            )
            db.commit()
        with (
            patch.object(worker, "SessionLocal", lambda: Session(self.engine, expire_on_commit=False)),
            patch.object(worker, "job_authorized", lambda *a: True),
            patch.object(worker, "cached_music", lambda *a: None),
            patch.object(worker, "fetch", return_value={"status": "failed", "code": "SOURCE_REMOVED"}),
        ):
            worker.run_job(("meta", 1, "music.metadata", {"item_id": "lost"}))
        with Session(self.engine) as db:
            self.assertEqual(db.get(QueueItem, "lost").status, "removed")  # out of the queue
        notice = self.client.get("/music/unavailable").json()["items"]
        self.assertEqual([(n["title"], n["playlist_id"]) for n in notice], [("Old hit", playlist["id"])])
        with patch("houseos.music.activate_added", lambda *a: False):
            self.client.post(
                "/music/unavailable/" + notice[0]["id"] + "/replace",
                json={"source_url": other, "idempotency_key": "replace-1"},
            )
        songs = self.client.get(lists + "/" + playlist["id"]).json()["items"]
        self.assertEqual([song["source_url"] for song in songs], [other])
        self.assertEqual(self.client.get("/music/unavailable").json()["items"], [])
        # A song imported with no name (YouTube gave none): it leaves quietly, nothing to search by.
        with Session(self.engine) as db:
            db.add(QueueItem(id="nameless", owner_id="one", source_url=gone + "x", title="None", position=3))
            db.add(Job(id="meta2", logical_key="metadata:nameless", kind="music.metadata", actor_id="one",
                       payload={"item_id": "nameless"}, state="running", generation=1))  # fmt: skip
            db.commit()
        with (
            patch.object(worker, "SessionLocal", lambda: Session(self.engine, expire_on_commit=False)),
            patch.object(worker, "job_authorized", lambda *a: True),
            patch.object(worker, "cached_music", lambda *a: None),
            patch.object(worker, "fetch", return_value={"status": "failed", "code": "SOURCE_REMOVED"}),
        ):
            worker.run_job(("meta2", 1, "music.metadata", {"item_id": "nameless"}))
        with Session(self.engine) as db:
            self.assertEqual(db.get(QueueItem, "nameless").status, "removed")
        self.assertEqual(self.client.get("/music/unavailable").json()["items"], [])

    def test_playlists_are_made_edited_and_queued_together(self):
        a, b = "https://www.youtube.com/watch?v=aaaaaaaaaaa", "https://youtu.be/bbbbbbbbbbb"
        base = "/music/library/playlists"
        empty = self.client.post(base, json={"name": " Night "}).json()
        self.assertEqual((empty["name"], empty["items"]), ("Night", []))
        self.assertEqual(
            self.client.post(base, json={"name": "x", "source_urls": ["radio:x"]}).status_code, 422
        )
        songs = self.client.post(base, json={"name": "Day", "item_ids": ["track"], "source_urls": [a, b, a]})
        day = songs.json()
        self.assertEqual(
            [s["source_url"] for s in day["items"]],
            ["https://www.youtube.com/watch?v=abcdefghijk", a, "https://www.youtube.com/watch?v=bbbbbbbbbbb"],
        )
        self.assertEqual(day["items"][0]["title"], "Synthetic")
        # add once, twice is harmless; reorder and remove in one edit; rename; stale version refused
        added = self.client.post(base + "/" + empty["id"] + "/songs", json={"source_url": a}).json()
        self.assertTrue(added["added"])
        again = self.client.post(base + "/" + empty["id"] + "/songs", json={"source_url": a}).json()
        self.assertFalse(again["added"])
        edit = self.client.patch(
            base + "/" + day["id"],
            json={"expected_version": 1, "name": "Dawn", "source_urls": [day["items"][2]["source_url"], a]},
        ).json()
        self.assertEqual((edit["name"], edit["version"], len(edit["items"])), ("Dawn", 2, 2))
        self.assertEqual(
            self.client.patch(base + "/" + day["id"], json={"expected_version": 1}).status_code, 409
        )
        detail = self.client.get(base + "/" + day["id"]).json()
        self.assertEqual(detail["items"][1]["source_url"], a)
        # both playlists, reviewed first, each song once; confirming queues the new ones
        with Session(self.engine) as db:
            state = db.get(QueueState, 1)
            state.current_id, state.desired = "track", "playing"
            db.commit()
        review = self.client.post(base + "/queue", json={"ids": [day["id"], empty["id"]]}).json()
        self.assertEqual(
            (review["status"], review["total"], review["names"]), ("needs_confirmation", 2, ["Dawn", "Night"])
        )
        done = self.client.post("/music/playlists/" + review["confirmation_id"] + "/confirm").json()
        self.assertEqual((done["status"], done["added"]), ("completed", 2))
        # private: another resident can neither see, edit, add to nor queue them
        self.actor = Actor("two", "Two", "resident", self.actor.permissions)
        self.assertEqual(self.client.get(base + "/" + day["id"]).status_code, 404)
        self.assertEqual(
            self.client.patch(base + "/" + day["id"], json={"expected_version": 2}).status_code, 404
        )
        self.assertEqual(
            self.client.post(base + "/" + day["id"] + "/songs", json={"source_url": a}).status_code, 404
        )
        self.assertEqual(self.client.post(base + "/queue", json={"ids": [day["id"]]}).status_code, 404)
        self.assertEqual(self.client.delete(base + "/" + day["id"]).status_code, 404)

    def test_guest_votes_need_three_distinct_valid_users(self):
        with Session(self.engine) as db:
            db.get(QueueState, 1).current_id = "track"
            db.commit()
        for identity in ["one", "one", "two", "three"]:
            self.actor = Actor(identity, identity, "guest", frozenset({"music.queue"}))
            result = self.client.post("/music/queue/track/skip-vote", json={"expected_version": 1})
            self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["votes"], 3)
        self.assertEqual(result.json()["status"], "accepted")
        with Session(self.engine) as db:
            jobs = db.scalars(select(Job)).all()
            self.assertEqual(len(jobs), 1)
            self.assertTrue(authorized_vote_job(db, jobs[0]))
            db.get(User, "two").active = False
            db.commit()
            self.assertFalse(authorized_vote_job(db, jobs[0]))

    def test_local_audio_confirmation_and_actual_sandbox_staging(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            blob = root / "blob"
            with wave.open(str(blob), "wb") as stream:
                stream.setnchannels(1)
                stream.setsampwidth(2)
                stream.setframerate(8000)
                stream.writeframes(b"\0\0" * 8000)
            with Session(self.engine) as db:
                db.add(
                    FileEntry(
                        id="blob",
                        owner_id="one",
                        name="Synthetic.wav",
                        mime="audio/wav",
                        scope="personal",
                        size=blob.stat().st_size,
                        checksum=hashlib.sha256(blob.read_bytes()).hexdigest(),
                    )
                )
                db.commit()
            preview = self.client.post(
                "/music/local/preview", json={"file_id": "blob", "idempotency_key": "local-preview-one"}
            )
            self.assertEqual(preview.status_code, 200)
            self.assertIn("shared household speakers", preview.json()["preview"]["effect"])
            confirmation = preview.json()["confirmation_id"]
            added = self.client.post("/music/local/" + confirmation + "/confirm")
            self.assertEqual(added.status_code, 200)
            self.assertEqual(self.client.post("/music/local/" + confirmation + "/confirm").status_code, 409)
            item_id = added.json()["item_id"]
            with Session(self.engine) as db:
                db.get(QueueItem, item_id).status = "resolving"
                db.commit()

            @contextlib.contextmanager
            def directory(_):
                fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    yield fd
                finally:
                    os.close(fd)

            with (
                patch("houseos.music_library.settings", SimpleNamespace(runtime_root=root)),
                patch("houseos.music_library.SessionLocal", lambda: Session(self.engine)),
                patch("houseos.files.subdir_fd", directory),
            ):
                self.assertEqual(stage_local_audio(item_id), {"status": "completed"})
                self.assertTrue((root / "audio" / (item_id + ".media")).read_bytes().startswith(b"fLaC"))
                with Session(self.engine) as db:
                    db.get(FileEntry, "blob").version += 1
                    db.commit()
                self.assertEqual(stage_local_audio(item_id)["code"], "LOCAL_AUDIO_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
