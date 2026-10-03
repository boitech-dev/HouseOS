"""Cinema preparation worker: one lane that spools, probes and hands prepared media to
the receiver. Runs only in the cinema-worker service, never from a browser request.

Receiver, integration and authorization helpers are called through the cinema module so
there is a single definition of each."""

from __future__ import annotations
import copy
import hashlib
from datetime import timedelta
from pathlib import Path
from sqlalchemy import select
from . import cinema
from .auth import account_usable
from .cinema import save_workflow
from .cinema_models import CinemaDevice, CinemaPreparation, CinemaTitle, CinemaWorkflow
from .config import settings
from .db import utcnow
from .playback import MediaError, compatibility, probe_file


def process_one_preparation(db):
    """Durable worker entrypoint; single preparation at a time. Never called by a browser."""
    from .models import User
    from .playback import prepare_local
    from .cinema_adapters import public_stream
    from .cinema_cast import execute_cast
    import shutil
    import time

    active = db.scalar(select(CinemaPreparation).where(CinemaPreparation.state == "running"))
    if active:
        from .cinema_progressive import ACTIVE

        existing = db.get(CinemaWorkflow, active.workflow_id)
        if existing and existing.data.get("_stream_job_id") == active.id and active.id not in ACTIVE:
            active.state = "failed"
            active.finished_at = utcnow()
            save_workflow(
                db,
                existing,
                "recovery_required",
                {
                    "error": MediaError(
                        "STREAM_INTERRUPTED",
                        "Streaming preparation was interrupted. Start a fresh playback request.",
                        "prepare",
                        True,
                    ).public()
                },
            )
            return False
        # The single preparation lane is idle whenever this runs, so a running row that is
        # not a live progressive stream was orphaned by a restart or an unexpected error.
        # A crashed worker never resumes a physical command automatically.
        if active.id not in ACTIVE:
            active.state, active.finished_at = "failed", utcnow()
            if existing and existing.state == "preparing" and existing.version == active.workflow_version:
                save_workflow(
                    db,
                    existing,
                    "recovery_required",
                    {
                        "error": MediaError(
                            "PREPARATION_INTERRUPTED",
                            "Media preparation was interrupted. Create a new playback preview.",
                            "prepare",
                        ).public()
                    },
                )
            else:
                db.commit()
        return False
    job = db.scalar(
        select(CinemaPreparation)
        .where(CinemaPreparation.state == "queued")
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if not job:
        db.rollback()
        return False
    job.state, job.started_at = "running", utcnow()
    db.commit()
    row = db.get(CinemaWorkflow, job.workflow_id)
    directory = None
    try:
        user = db.get(User, job.owner_id)
        cinema.authorize_workflow(db, row)
        if (
            not account_usable(user)
            or user.role not in {"admin", "resident"}
            and "cinema.use" not in user.permissions
        ):
            raise MediaError("PERMISSION_REVOKED", "Playback authorization is no longer valid.", "prepare")
        if not row or row.version != job.workflow_version or row.state != "preparing":
            raise MediaError("PLAN_STALE", "The preparation was cancelled or superseded.", "prepare")
        if row.data.get("_kind") == "save_local":
            download_local(db, row, job, user)
            return True
        device = db.get(CinemaDevice, row.device_id)
        if device.owner_workflow != row.id:
            raise MediaError(
                "DESTINATION_OWNERSHIP_LOST", "The destination is now owned by another session.", "prepare"
            )
        source = next(s for s in row.data["_sources"] if s["id"] == row.data["_selected_source"])
        plan = row.data["plan"]
        size = source.get("size")
        if plan.get("preparation_strategy") == "progressive_hls":
            from .cinema_progressive import start

            return start(db, row, device, source, plan, job)
        if plan.get("preparation_strategy") == "external_sidecar":
            from .cinema_subtitles import normalize_external

            directory = Path(settings.runtime_root) / "cinema" / row.id / job.id
            subtitle_path = normalize_external(db, row, source, plan, directory / "ready")
            db.rollback()
            row = db.get(CinemaWorkflow, job.workflow_id)
            device = db.get(CinemaDevice, row.device_id)
            cinema.authorize_workflow(db, row)
            if (
                row.state != "preparing"
                or row.version != job.workflow_version
                or device.owner_workflow != row.id
            ):
                raise MediaError(
                    "PLAN_STALE", "Playback authorization changed during preparation.", "prepare"
                )
            fresh = cinema.inspect_destination(db, device)
            previous = row.data["_destination_observation"]
            if fresh.get("item_id") != previous.get("item_id") or fresh.get("session_id") != previous.get(
                "session_id"
            ):
                raise MediaError(
                    "PLAN_STALE",
                    "Destination playback changed while preparing. Choose Play again.",
                    "prepare",
                )
            row.data = {
                **row.data,
                "_prepared": {"path": "", "subtitle_path": subtitle_path, "sidecar_only": True},
            }
            db.commit()
            execute_cast(db, row, device, source, plan)
            job.state, job.finished_at = "done", utcnow()
            save_workflow(
                db,
                row,
                "command_sent",
                {"observation": {"state": "command_sent", "physical_verification": "unverified"}},
            )
            return True
        if (
            not size
            or size > 80 * 1024**3
            or shutil.disk_usage(settings.runtime_root).free < size * 2.2 + 20 * 1024**3
        ):
            raise MediaError(
                "RESOURCE_LIMIT", "Temporary media preparation cannot fit within the disk budget.", "prepare"
            )
        if source.get("jellyfin_item"):
            jf = cinema.Jellyfin(cinema.integration_config(db, "jellyfin"))
            selected = next(
                (
                    item
                    for item in jf.playback_info(source["jellyfin_item"]).get("MediaSources", [])
                    if item["Id"] == source["jellyfin_source"]
                ),
                None,
            )
            if not selected:
                raise MediaError("SOURCE_EXPIRED", "The exact Jellyfin release is unavailable.", "prepare")
            current_size = selected.get("Size")
            status, headers, chunks = jf.stream(source["jellyfin_item"], source["jellyfin_source"])
        else:
            from .cinema_sources import resolve_media

            url, current_size = resolve_media(db, source)
            status, headers, chunks = public_stream(url)
        if current_size and current_size != size:
            raise MediaError("PLAN_STALE", "The source size changed after preview.", "prepare")
        directory = Path(settings.runtime_root) / "cinema" / row.id / job.id
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        source_path = directory / "source.bin"
        started = time.monotonic()
        total = 0
        last_permission_check = 0

        def cancelled():
            db.rollback()  # start a fresh read view; expire_all alone keeps MariaDB's old snapshot
            current_workflow = db.get(CinemaWorkflow, job.workflow_id)
            current_user = db.get(User, job.owner_id)
            try:
                cinema.authorize_workflow(db, current_workflow)
            except MediaError:
                return True
            return (
                not current_workflow
                or current_workflow.state != "preparing"
                or current_workflow.version != job.workflow_version
                or not current_user
                or not current_user.active
                or bool(current_user.expires_at and current_user.expires_at <= utcnow())
            )

        with source_path.open("xb") as stream:
            for chunk in chunks:
                total += len(chunk)
                if time.monotonic() - last_permission_check > 5:
                    last_permission_check = time.monotonic()
                    if cancelled():
                        raise MediaError(
                            "PREPARATION_CANCELLED",
                            "The preparation was cancelled or authorization changed.",
                            "prepare",
                        )
                if total > size + 4096 or time.monotonic() - started > 1800:
                    raise MediaError(
                        "PROBE_BUDGET_EXCEEDED",
                        "The temporary download exceeded its declared size or time limit.",
                        "prepare",
                    )
                stream.write(chunk)
        if total != size:
            raise MediaError("PREPARATION_INCOMPLETE", "The temporary download is incomplete.", "prepare")
        current_probe = probe_file(source_path)
        track_mapping = None
        if source.get("jellyfin_item"):
            from .playback import map_library_tracks

            current_probe, track_mapping = map_library_tracks(current_probe, source["inspection"])
        if (plan.get("subtitle") or {}).get("external") or (plan.get("subtitle") or {}).get(
            "external_jellyfin"
        ):
            current_probe["subtitles"].append(plan["subtitle"])
        current_plan = compatibility(current_probe, device.capabilities, row.data["request"])
        if any(current_plan[k] != plan[k] for k in ["video", "audio", "subtitle", "mode"]):
            raise MediaError(
                "PLAN_STALE", "Full-file inspection differs from the approved preview.", "prepare"
            )
        preparation_plan = copy.deepcopy(plan)
        if track_mapping:
            preparation_plan["video"]["index"] = int(track_mapping[str(plan["video"]["index"])])
            preparation_plan["audio"]["id"] = track_mapping[plan["audio"]["id"]]
            if (
                plan.get("subtitle")
                and not plan["subtitle"].get("external_jellyfin")
                and not plan["subtitle"].get("external")
            ):
                preparation_plan["subtitle"]["id"] = track_mapping[plan["subtitle"]["id"]]
        external = (plan.get("subtitle") or {}).get("external")
        jellyfin_external = (plan.get("subtitle") or {}).get("external_jellyfin")
        if external or jellyfin_external:
            from .cinema_subtitles import normalize_external

            preparation_plan["_external_subtitle_path"] = normalize_external(
                db, row, source, plan, directory / "ready"
            )
        prepared = prepare_local(
            source_path, directory / "ready", preparation_plan, timeout=1800, cancelled=cancelled
        )
        source_path.unlink(missing_ok=True)
        db.rollback()
        row, device, user = (
            db.get(CinemaWorkflow, job.workflow_id),
            db.get(CinemaDevice, row.device_id),
            db.get(User, job.owner_id),
        )
        if (
            not row
            or row.state != "preparing"
            or row.version != job.workflow_version
            or device.owner_workflow != row.id
            or not user.active
            or user.expires_at
            and user.expires_at <= utcnow()
        ):
            raise MediaError("PLAN_STALE", "Playback authorization changed during preparation.", "prepare")
        fresh = cinema.inspect_destination(db, device)
        previous = row.data["_destination_observation"]
        if fresh.get("item_id") != previous.get("item_id") or fresh.get("session_id") != previous.get(
            "session_id"
        ):
            raise MediaError(
                "PLAN_STALE",
                "Destination playback changed while preparing. A new preview is required.",
                "prepare",
            )
        row.data = {**row.data, "_prepared": prepared}
        db.commit()
        execute_cast(db, row, device, source, plan)
        job.state, job.finished_at = "done", utcnow()
        save_workflow(
            db,
            row,
            "command_sent",
            {"observation": {"state": "command_sent", "physical_verification": "unverified"}},
        )
    except MediaError as exc:
        db.rollback()
        db.expire_all()
        row = db.get(CinemaWorkflow, job.workflow_id)
        job.state, job.finished_at = "failed", utcnow()
        if row and row.state == "preparing" and row.version == job.workflow_version:
            previous = row.data.get("_seek_previous")
            restored = False
            if previous:
                try:
                    current = cinema.inspect_destination(db, db.get(CinemaDevice, row.device_id))
                    if current.get("item_id") == previous["plan"].get("expected_item"):
                        save_workflow(
                            db,
                            row,
                            "command_sent",
                            {
                                "plan": previous["plan"],
                                "_prepared": previous["prepared"],
                                "_stream_job_id": previous.get("job_id"),
                                "_seek_previous": None,
                                "_observation_deadline": (utcnow() + timedelta(seconds=45)).isoformat(),
                                "error": exc.public(),
                            },
                        )
                        restored = True
                except MediaError:
                    pass
            if not restored:
                save_workflow(db, row, "recovery_required", {"_seek_previous": None, "error": exc.public()})
        else:
            db.commit()
    except (OSError, StopIteration):
        job.state, job.finished_at = "failed", utcnow()
        if row:
            save_workflow(
                db,
                row,
                "recovery_required",
                {
                    "error": MediaError(
                        "PREPARATION_FAILED",
                        "The temporary preparation failed. Inspect storage and source health.",
                        "prepare",
                    ).public()
                },
            )
    finally:
        if row and row.data.get("_kind") == "save_local" and job.state != "done":
            from .models import Record

            local_record = db.get(Record, row.data.get("_local_record_id"))
            if local_record:
                local_record.data = {**local_record.data, "state": "failed"}
                db.commit()
        if directory and job.state != "done":
            # Generated job-only scratch files; never a library/user upload root.
            expected = Path(settings.runtime_root).resolve() / "cinema" / job.workflow_id / job.id
            if directory.resolve() == expected and not directory.is_symlink():
                shutil.rmtree(directory, ignore_errors=True)
    return True


def download_progress(db, row, job, total, size, phase):
    # Keep the authorized workflow revision stable; serialize against cancellation.
    db.rollback()
    current = db.scalar(
        select(CinemaWorkflow)
        .where(CinemaWorkflow.id == row.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if current.state != "preparing" or current.version != job.workflow_version:
        raise MediaError("PREPARATION_CANCELLED", "The download was cancelled.", "download")
    current.data = {
        **current.data,
        "download": {"bytes": total, "total": size, "phase": phase, "updated_at": utcnow().isoformat()},
    }
    current.updated_at = utcnow()
    db.commit()


def download_local(db, row, job, user):
    from .files import storage_check
    from .models import Record
    from .auth import user_permissions
    from .cinema_adapters import public_stream
    import os
    import re
    import time
    import shutil

    if "files.shared.write" not in user_permissions(user):
        raise MediaError("PERMISSION_REVOKED", "Shared media storage permission was revoked.", "prepare")
    storage = storage_check()
    source = next(s for s in row.data["_sources"] if s["id"] == row.data["_selected_source"])
    title = db.get(CinemaTitle, row.media_id)
    record = db.get(Record, row.data["_local_record_id"])
    size = source["size"]
    if shutil.disk_usage(settings.data_root).free < size + 20 * 1024**3:
        raise MediaError(
            "RESOURCE_LIMIT", "The storage free-space safety floor would be exceeded.", "download"
        )
    download_progress(db, row, job, 0, size, "resolving")
    from .cinema_sources import resolve_media

    url, actual_size = resolve_media(db, source)
    if actual_size and actual_size != size:
        raise MediaError("PLAN_STALE", "The source size changed after the download preview.", "download")
    root = Path(settings.data_root) / "media" / ("shows" if title.kind == "episode" else "movies")
    directory_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    if os.fstat(directory_fd).st_dev != storage["device"]:
        os.close(directory_fd)
        raise MediaError(
            "STORAGE_UNAVAILABLE", "The library directory is not on the approved storage drive.", "download"
        )
    stage = ".houseos-" + job.id + ".part"
    suffix = ".mkv" if "matroska" in source["inspection"]["container"] else ".mp4"
    name = (re.sub(r"[^A-Za-z0-9 ._-]", "_", title.title)[:100] or "Film") + "-" + job.id + suffix
    record.data = {**record.data, "state": "downloading"}
    db.commit()
    total, started, last_check = 0, time.monotonic(), 0
    checksum = hashlib.sha256()
    try:
        fd = os.open(stage, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o640, dir_fd=directory_fd)
        with os.fdopen(fd, "wb") as out:
            _, _, chunks = public_stream(url)
            for chunk in chunks:
                total += len(chunk)
                if total > size or time.monotonic() - started > 3600:
                    raise MediaError(
                        "RESOURCE_LIMIT",
                        "The download exceeded its size or one-hour time budget.",
                        "download",
                    )
                if time.monotonic() - last_check > 5:
                    last_check = time.monotonic()
                    db.rollback()
                    current = db.get(CinemaWorkflow, row.id)
                    current_user = db.get(type(user), user.id)
                    cinema.authorize_workflow(db, current)
                    if (
                        current.state != "preparing"
                        or current.version != job.workflow_version
                        or not current_user.active
                        or current_user.expires_at
                        and current_user.expires_at <= utcnow()
                        or "files.shared.write" not in user_permissions(current_user)
                    ):
                        raise MediaError(
                            "PREPARATION_CANCELLED",
                            "Download permission changed or the job was cancelled.",
                            "download",
                        )
                    download_progress(db, current, job, total, size, "downloading")
                out.write(chunk)
                checksum.update(chunk)
            out.flush()
            os.fsync(out.fileno())
        if total != size:
            raise MediaError(
                "PREPARATION_INCOMPLETE", "The downloaded file did not match its declared size.", "download"
            )
        download_progress(db, row, job, total, size, "verifying")
        inspected = probe_file(root / stage)
        if abs(inspected["duration"] - source["inspection"]["duration"]) > max(
            3, source["inspection"]["duration"] * 0.01
        ):
            raise MediaError(
                "MEDIA_PROBE_FAILED", "Downloaded media did not match the approved duration.", "download"
            )
        db.rollback()
        row = db.scalar(select(CinemaWorkflow).where(CinemaWorkflow.id == row.id).with_for_update())
        user = db.get(type(user), user.id)
        cinema.authorize_workflow(db, row)
        if (
            row.state != "preparing"
            or row.version != job.workflow_version
            or "files.shared.write" not in user_permissions(user)
        ):
            raise MediaError(
                "PREPARATION_CANCELLED", "Download authorization changed before publication.", "download"
            )
        storage_check()
        os.rename(stage, name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
        os.fsync(directory_fd)
        record.data = {
            **record.data,
            "state": "ready",
            "checksum": checksum.hexdigest(),
            "_path": str(root / name),
            "library_index": "pending_observation",
        }
        job.state, job.finished_at = "done", utcnow()
        save_workflow(
            db,
            row,
            "completed",
            {
                "download": {
                    "bytes": total,
                    "total": size,
                    "phase": "completed",
                    "updated_at": utcnow().isoformat(),
                },
                "preview": {
                    "action": "Saved locally",
                    "bytes": total,
                    "checksum": checksum.hexdigest(),
                    "library_index": "pending_observation",
                },
                "error": None,
            },
        )
    finally:
        try:
            os.unlink(stage, dir_fd=directory_fd)
        except FileNotFoundError:
            pass
        os.close(directory_fd)
