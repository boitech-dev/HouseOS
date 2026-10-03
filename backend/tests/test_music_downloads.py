from contextlib import contextmanager
import pytest
from types import SimpleNamespace
from uuid import uuid4
import os

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from houseos.db import Base
from houseos.models import User, Record
from houseos.music import QueueItem, QueueState
from houseos import music_downloads as downloads, worker

URL = "https://www.youtube.com/watch?v=abcdefghijk"


def test_durable_deduplicated_library_replay_and_storage_failure(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///" + str(tmp_path / "test.db"))
    Base.metadata.create_all(engine)
    storage, runtime = tmp_path / "storage", tmp_path / "runtime"
    storage.mkdir()
    runtime.mkdir()
    (runtime / "audio").mkdir()
    config = SimpleNamespace(runtime_root=runtime, data_root=storage, media_quota_bytes=200 * 1024**3)
    monkeypatch.setattr(downloads, "settings", config)
    monkeypatch.setattr(downloads, "SessionLocal", lambda: Session(engine, expire_on_commit=False))
    monkeypatch.setattr(downloads.files, "lock_quota", lambda db: None)
    monkeypatch.setattr(downloads.files, "media_usage", lambda *args, **kwargs: (0, 0))

    @contextmanager
    def root_fd(**kwargs):
        fd = os.open(storage, os.O_RDONLY | os.O_DIRECTORY)
        try:
            yield fd
        finally:
            os.close(fd)

    monkeypatch.setattr(downloads.files, "root_fd", root_fd)
    one, two, replay = [str(uuid4()) for _ in range(3)]
    with Session(engine) as db:
        db.add(User(id="resident", username="resident", name="Resident", password_hash="unused"))
        for number, item in enumerate((one, two, replay)):
            db.add(
                QueueItem(
                    id=item,
                    source_url=URL,
                    owner_id="resident",
                    title="Exact song",
                    position=number,
                    metadata_json={"duration": 60},
                )
            )
        db.commit()
    for item in (one, two):
        (runtime / "audio" / (item + ".media")).write_bytes(b"test audio")
    assert downloads.retain(URL, one)["retained"]
    assert downloads.retain(URL, two)["retained"]
    assert len(list((storage / "music-downloads").glob("*.media"))) == 1
    with Session(engine) as db:
        assert len(list(db.scalars(select(Record).where(Record.kind == downloads.KIND)))) == 1
        assert downloads.restore(db, URL, replay)["retained"]
    assert (runtime / "audio" / (replay + ".media")).read_bytes() == b"test audio"
    another = str(uuid4())
    with Session(engine) as db:
        assert downloads.restore(db, URL, another)["retained"]
    assert (runtime / "audio" / (replay + ".media")).stat().st_ino == (
        runtime / "audio" / (another + ".media")
    ).stat().st_ino
    assert (runtime / "audio" / (one + ".media")).stat().st_ino != (
        runtime / "audio" / (replay + ".media")
    ).stat().st_ino
    assert (runtime / "audio" / (one + ".media")).read_bytes() == b"test audio"
    # Quota failure preserves playable cache and never creates a falsely ready download.
    config.media_quota_bytes = 1
    extra, extra_url = str(uuid4()), "https://www.youtube.com/watch?v=zzzzzzzzzzz"
    with Session(engine) as db:
        db.add(QueueItem(id=extra, source_url=extra_url, owner_id="resident", title="Other song", position=5))
        db.commit()
    (runtime / "audio" / (extra + ".media")).write_bytes(b"other audio")
    assert downloads.retain(extra_url, extra)["retention_error"] == "MUSIC_LIBRARY_FULL"
    assert (runtime / "audio" / (extra + ".media")).read_bytes() == b"other audio"
    config.media_quota_bytes = 200 * 1024**3
    # Restart/replay does not depend on any queue-history record or resolver memory.
    with Session(engine) as db:
        db.query(QueueItem).delete()
        db.commit()
        assert downloads.restore(db, URL, str(uuid4()))["title"] == "Exact song"
    with Session(engine) as db:
        assert downloads.restore(db, "https://www.youtube.com/watch?v=zzzzzzzzzzz", str(uuid4())) is None
    (storage / "music-downloads" / (downloads.identity(URL) + ".media")).unlink()
    with Session(engine) as db:
        assert downloads.restore(db, URL, str(uuid4())) is None
        assert db.get(Record, downloads.identity(URL)).data["state"] == "missing"
    engine.dispose()


def test_whole_queue_downloads_in_order_without_progressive_mode(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///" + str(tmp_path / "prefetch.db"))
    Base.metadata.create_all(engine)
    monkeypatch.setattr(worker, "SessionLocal", lambda: Session(engine, expire_on_commit=False))
    monkeypatch.setattr(worker, "item_authorized", lambda *args: True)
    calls = []
    monkeypatch.setattr(
        worker,
        "prepare_audio",
        lambda source, identity: calls.append(identity) or {"status": "completed", "retained": True},
    )
    with Session(engine) as db:
        db.add(User(id="resident", username="resident", name="Resident", password_hash="unused"))
        db.add(QueueState(id=1, current_id="0", desired="playing"))
        for i in range(4):
            db.add(
                QueueItem(
                    id=str(i),
                    owner_id="resident",
                    source_url=URL,
                    position=i,
                    status="playing" if i == 0 else "ready",
                    metadata_json={},
                )
            )
        db.commit()
    worker.prefetch_next()
    worker.prefetch_next()
    worker.prefetch_next()
    assert calls == ["1", "2", "3"]
    with Session(engine) as db:
        db.get(QueueItem, "1").metadata_json = {}
        db.commit()
    monkeypatch.setattr(
        worker,
        "prepare_audio",
        lambda source, identity: calls.append(identity) or {"status": "failed", "code": "SOURCE_UNAVAILABLE"},
    )
    worker.prefetch_next()
    worker.prefetch_next()
    assert calls == ["1", "2", "3", "1"]  # a failed prefetch must not hammer the provider
    engine.dispose()


def test_preload_follows_the_house_and_a_house_keeping_nothing_deletes_played_songs(tmp_path, monkeypatch):
    from houseos.models import Integration

    engine = create_engine("sqlite:///" + str(tmp_path / "preload.db"))
    Base.metadata.create_all(engine)
    monkeypatch.setattr(worker, "SessionLocal", lambda: Session(engine, expire_on_commit=False))
    monkeypatch.setattr(worker, "item_authorized", lambda *args: True)
    calls, pruned = [], []
    monkeypatch.setattr(
        worker, "prepare_audio", lambda source, identity: calls.append(identity) or {"status": "completed"}
    )
    monkeypatch.setattr(worker, "fetch", lambda action, **kw: pruned.append(kw) or {"status": "completed"})
    with Session(engine) as db:
        db.add(User(id="resident", username="resident", name="Resident", password_hash="unused"))
        db.add(QueueState(id=1, current_id="0", desired="playing"))
        db.add(Integration(name="house_settings", config={"music_preload": 1, "music_keep_downloads": False}))
        for i in range(4):
            db.add(
                QueueItem(
                    id=str(i),
                    owner_id="resident",
                    source_url=URL,
                    position=i,
                    status="playing" if i == 0 else "ready",
                    metadata_json={},
                )
            )
        db.commit()
    for _ in range(3):
        worker.prefetch_next()
    assert calls == ["1"]  # one song ahead, as the house chose
    assert pruned == [{"pins": ["0", "1"], "keep_none": True}]  # everything else is deleted
    engine.dispose()


def test_songs_far_ahead_download_one_at_a_time_with_a_pause(tmp_path, monkeypatch):
    from houseos.models import Integration

    engine = create_engine("sqlite:///" + str(tmp_path / "pace.db"))
    Base.metadata.create_all(engine)
    monkeypatch.setattr(worker, "SessionLocal", lambda: Session(engine, expire_on_commit=False))
    monkeypatch.setattr(worker, "item_authorized", lambda *args: True)
    monkeypatch.setattr(worker, "last_download", [0.0])
    calls = []

    def download(source, identity):  # a fresh download, as _prepare_audio notes it
        calls.append(identity)
        worker.last_download[0] = worker.time.monotonic()
        return {"status": "completed"}

    monkeypatch.setattr(worker, "prepare_audio", download)
    with Session(engine) as db:
        db.add(User(id="resident", username="resident", name="Resident", password_hash="unused"))
        db.add(QueueState(id=1, current_id="0", desired="playing"))
        db.add(Integration(name="house_settings", config={"music_preload": 0}))  # the whole queue
        for i in range(6):
            db.add(QueueItem(id=str(i), owner_id="resident", source_url=URL, position=i,
                             status="playing" if i == 0 else "ready", metadata_json={}))  # fmt: skip
        db.commit()
    for _ in range(6):
        worker.prefetch_next()
    assert calls == ["1", "2", "3"]  # the next three at once; the fourth waits its turn
    worker.last_download[0] -= worker.FAR_PACE
    worker.prefetch_next()
    worker.prefetch_next()
    assert calls == ["1", "2", "3", "4"]
    engine.dispose()


def test_a_youtube_bot_check_is_tried_again_on_the_other_network(monkeypatch):
    from houseos import fetcher

    monkeypatch.setattr(fetcher, "ROUTE", {"flag": None, "until": 0.0})
    seen = []

    def execute(data):
        seen.append(fetcher.ROUTE["flag"])
        if fetcher.ROUTE["flag"] != "--force-ipv4":
            raise ValueError("YOUTUBE_SIGN_IN_REQUIRED")
        return {"status": "completed"}

    monkeypatch.setattr(fetcher, "execute", execute)
    request = {"action": "metadata", "source_url": "https://www.youtube.com/watch?v=aaaaaaaaaaa"}
    assert fetcher.run(request) == {"status": "completed"} and seen == [None, "--force-ipv4"]
    fetcher.ROUTE["flag"] = "--force-ipv6"  # that network refused too, within the 12 h: no flapping
    with pytest.raises(ValueError):
        fetcher.run(request)
    with pytest.raises(ValueError):  # SoundCloud is never rerouted
        fetcher.run({"action": "metadata", "source_url": "https://soundcloud.com/a/b"})
