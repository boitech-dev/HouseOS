"""Incremental Cast packaging. Only the parent broker can access the exact source."""

from __future__ import annotations
import shutil
import json
from fractions import Fraction
from statistics import median
from datetime import timedelta
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from sqlalchemy.orm import Session
from .config import settings
from .db import utcnow
from .playback import MEDIA_ENV, MediaError
from .cinema_stream_input import input_broker, streaming_media_command

ACTIVE = set()


def supported(source, plan):
    return (
        not source.get("jellyfin_item")
        and plan.get("video_copied")
        and plan["video"]["codec"] in {"h264", "hevc"}
        and plan.get("subtitle_mode") in {"off", "webvtt"}
    )


def ffmpeg_args(directory, plan):
    args = [
        "ffmpeg",
        "-nostdin",
        "-v",
        "error",
        "-n",
        "-protocol_whitelist",
        "http,tcp,file",
        "-format_whitelist",
        "mov,matroska,webm,mpegts,avi,mpeg",
        "-noaccurate_seek",
        "-ss",
        str(max(0, plan.get("position", 0))),
        "-i",
        "INPUT",
    ]
    external = plan.get("_external_subtitle_path")
    if external:
        args += [
            "-protocol_whitelist",
            "file",
            "-format_whitelist",
            "webvtt",
            "-ss",
            str(max(0, plan.get("position", 0))),
            "-i",
            external,
        ]
    args += ["-map", f"0:{plan['video']['index']}", "-map", f"0:{plan['audio']['id']}", "-c:v", "copy"]
    if plan["video"]["codec"] == "hevc":
        args += ["-tag:v", "hvc1"]
    args += ["-c:a", plan["output_audio_codec"] if plan.get("audio_conversion") else "copy", "-threads", "2"]
    if plan.get("audio_conversion"):
        args += ["-ac", str(plan["output_channels"]), "-b:a", "192k"]
        if "_audio_start_pts" in plan:
            args += ["-af", f"aresample=48000:async=1:first_pts={plan['_audio_start_pts']}"]
    if plan.get("subtitle_mode") == "webvtt":
        args += ["-map", "1:0" if external else f"0:{plan['subtitle']['id']}", "-c:s", "webvtt"]
    else:
        args += ["-sn"]
    return args + [
        "-max_interleave_delta",
        "1000000",
        "-f",
        "hls",
        "-hls_time",
        "4",
        "-hls_list_size",
        "0",
        "-hls_playlist_type",
        "event",
        "-hls_segment_type",
        "fmp4",
        "-hls_segment_options",
        "use_editlist=0",
        "-master_pl_name",
        "av_master.m3u8",
        "-hls_flags",
        "temp_file+independent_segments",
        str(directory / "video.m3u8"),
    ]


def ready(directory, plan):
    # A published playlist alone is insufficient: its complete first fragments must exist.
    def playlist_ready(name):
        try:
            text = (directory / name).read_text()
            if "#EXTINF:" not in text:
                return False
            import re

            resources = [
                line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")
            ]
            resources += re.findall(r'#EXT-X-MAP:URI="([^"]+)"', text)
            return bool(resources) and all(
                Path(item).name == item
                and (directory / item).is_file()
                and (directory / item).stat().st_size > 0
                for item in resources
            )
        except OSError:
            return False

    return playlist_ready("video.m3u8") and (
        plan.get("subtitle_mode") != "webvtt" or playlist_ready("video_vtt.m3u8")
    )


def packaged_codecs(directory):
    """RFC 6381 identifiers from the actual fMP4 initialization segment."""
    from .playback import media_command
    import re

    init = directory / "init.mp4"
    if init.stat().st_size > 4_000_000:
        raise ValueError("Oversized initialization segment")
    args = [
        "ffprobe",
        "-v",
        "error",
        "-protocol_whitelist",
        "file",
        "-show_entries",
        "stream=codec_name,codec_tag_string,extradata",
        "-show_data",
        "-of",
        "json",
        str(init),
    ]
    result = subprocess.run(
        media_command(args, init, directory), capture_output=True, check=True, timeout=5, env=MEDIA_ENV
    )
    codecs = []
    for stream in json.loads(result.stdout)["streams"]:
        data = bytes.fromhex(
            "".join(
                line.split(": ", 1)[1].split("  ", 1)[0].replace(" ", "")
                for line in stream.get("extradata", "").splitlines()
                if re.match(r"^[0-9a-f]{8}: ", line)
            )
        )
        name = stream["codec_name"]
        if name == "hevc" and len(data) >= 13:
            compatibility = int(f"{int.from_bytes(data[2:6]):032b}"[::-1], 2)
            constraints = data[6:12].rstrip(b"\0")
            codecs.append(
                f"{stream['codec_tag_string']}.{' ABC'[data[1] >> 6].strip()}{data[1] & 31}.{compatibility:X}.{'H' if data[1] & 32 else 'L'}{data[12]}"
                + "".join(f".{b:02X}" for b in constraints)
            )
        elif name == "aac" and data:
            codecs.append(f"mp4a.40.{data[0] >> 3}")
        elif name in {"mp3", "opus", "flac"}:
            codecs.append({"mp3": "mp4a.6B", "opus": "opus", "flac": "fLaC"}[name])
        else:
            raise ValueError("Unsupported codec declaration")
    return ",".join(codecs)


def write_master(directory, plan, size):
    lines = ["#EXTM3U", "#EXT-X-VERSION:7"]
    subtitle = plan.get("subtitle_mode") == "webvtt"
    if subtitle:
        lang = str(plan["subtitle"].get("language") or "und")
        if not lang.isalpha():
            lang = "und"
        lines.append(
            f'#EXT-X-MEDIA:TYPE=SUBTITLES,GROUP-ID="subs",NAME="Subtitles",DEFAULT=YES,AUTOSELECT=YES,LANGUAGE="{lang}",URI="video_vtt.m3u8"'
        )
    # Let the muxer declare the actual packaged codecs/profile; guessing HEVC as
    # H.264 makes adaptive receivers fail before they can expose subtitle tracks.
    try:
        variant = next(
            line
            for line in (directory / "av_master.m3u8").read_text().splitlines()
            if line.startswith("#EXT-X-STREAM-INF:")
        )
        if "CODECS=" not in variant:
            variant += ',CODECS="' + packaged_codecs(directory) + '"'
    except (OSError, StopIteration, ValueError, KeyError, subprocess.SubprocessError):
        raise MediaError(
            "PREPARATION_FAILED", "The stream codec manifest is not ready.", "prepare", True
        ) from None
    import re

    # Copied video often has no bitrate metadata; FFmpeg then reports audio only.
    bandwidth = max(1000000, int(size * 8 / max(1, plan.get("duration") or 1) * 1.3))
    variant = re.sub(r"(?<!-)BANDWIDTH=\d+", "BANDWIDTH=" + str(bandwidth), variant)
    variant = re.sub(r",AVERAGE-BANDWIDTH=\d+", "", variant)
    lines += [variant + (',SUBTITLES="subs"' if subtitle else ""), "video.m3u8"]
    (directory / "master.m3u8").write_text("\n".join(lines) + "\n")


def timeline_packets(socket_path, output, args):
    result = subprocess.run(
        streaming_media_command(args, socket_path, output), capture_output=True, env=MEDIA_ENV, timeout=15
    )
    try:
        if result.returncode or len(result.stdout) > 100000:
            raise ValueError()
        lines = result.stdout.decode().splitlines()
        timebase = Fraction(next(line.split(":", 1)[1].strip() for line in lines if line.startswith("#tb ")))
        return [
            (parts[-1].strip(), float(int(parts[2]) * timebase), float(int(parts[1]) * timebase))
            for line in lines
            if line and not line.startswith("#")
            for parts in [line.split(",")]
        ]
    except (ValueError, StopIteration, IndexError, UnicodeError):
        raise MediaError(
            "STREAM_TIMELINE_UNVERIFIED", "The seek timeline could not be verified.", "prepare"
        ) from None


def prepare_timeline(socket_path, output, plan):
    original = timeline_packets(
        socket_path,
        output,
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-copyts",
            "-ss",
            str(plan.get("position", 0)),
            "-protocol_whitelist",
            "http,tcp",
            "-format_whitelist",
            "mov,matroska,webm,mpegts,avi,mpeg",
            "-i",
            "INPUT",
            "-map",
            f"0:{plan['video']['index']}",
            "-c:v",
            "copy",
            "-frames:v",
            "16",
            "-f",
            "framehash",
            "pipe:1",
        ],
    )
    if not original:
        raise MediaError("STREAM_TIMELINE_UNVERIFIED", "No video timestamp was available.", "prepare")
    # Supply silence before the first video decode timestamp. Both tracks then
    # share a real fMP4 origin, including B-frame and AAC encoder preroll; no
    # receiver-specific edit-list compensation or guessed audio delay is needed.
    start = min(packet[2] for packet in original) - plan.get("position", 0) - 0.05
    if not -31 <= start <= 0:
        raise MediaError(
            "STREAM_TIMELINE_UNVERIFIED", "The source has an unsupported preroll timeline.", "prepare"
        )
    return {**plan, "_audio_start_pts": round(start * 48000)}, original


def position_offset(socket_path, output, plan, original=None):
    """Map identical copied packets after the initial B-frame boundary."""
    if original is None:
        _, original = prepare_timeline(socket_path, output, plan)
    # Pin the first fragment: a fast-growing EVENT playlist can otherwise start
    # ffprobe at its live edge, changing the inferred offset as it downloads.
    first = output / "timeline.m3u8"
    first.write_text(
        '#EXTM3U\n#EXT-X-VERSION:7\n#EXT-X-TARGETDURATION:60\n#EXT-X-MAP:URI="init.mp4"\n#EXTINF:60,\nvideo0.m4s\n#EXT-X-ENDLIST\n'
    )
    try:
        prepared = timeline_packets(
            socket_path,
            output,
            [
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-copyts",
                "-protocol_whitelist",
                "file,crypto,data",
                "-i",
                str(first),
                "-map",
                "0:v:0",
                "-c:v",
                "copy",
                "-frames:v",
                "16",
                "-f",
                "framehash",
                "pipe:1",
            ],
        )
    finally:
        first.unlink(missing_ok=True)
    offsets = [a[1] - b[1] for a, b in zip(original[8:], prepared[8:]) if a[0] == b[0]]
    if len(offsets) < 4 or max(offsets) - min(offsets) > 0.005:
        raise MediaError(
            "STREAM_TIMELINE_UNVERIFIED", "The copied stream timeline did not match the source.", "prepare"
        )
    offset = median(offsets)
    if not -1 <= offset <= plan.get("position", 0) or plan.get("position", 0) - offset > 30:
        raise MediaError(
            "STREAM_TIMELINE_UNVERIFIED", "This release has an unsupported seek boundary.", "prepare"
        )
    return offset


def retained_seek_buffer(workflow, directory):
    previous = workflow.data.get("_seek_previous") or {}
    path = previous.get("prepared", {}).get("path")
    return bool(path and Path(path).parent.parent == directory)


def cleanup_stream_directory(bind, workflow_id, directory):
    from .cinema import CinemaWorkflow

    with Session(bind) as fresh:
        current = fresh.get(CinemaWorkflow, workflow_id)
        retain = bool(
            current
            and current.state in {"preparing", "command_sent", "playing_observed", "paused"}
            and retained_seek_buffer(current, directory)
        )
    if not retain:
        shutil.rmtree(directory, ignore_errors=True)


def start(db, row, device, source, plan, job):
    from .cinema import (
        CinemaWorkflow,
        CinemaPreparation,
        authorize_workflow,
        inspect_destination,
        save_workflow,
    )
    from .cinema_adapters import public_stream
    from .cinema_sources import resolve_media
    from .cinema_cast import execute_cast

    bind = db.get_bind()
    workflow_id = row.id
    job_id = job.id
    url, size = resolve_media(db, source)
    size = size or source["size"]
    if size != source["size"]:
        raise MediaError("PLAN_STALE", "Source size changed after preview.", "prepare")
    if (
        not size
        or size > 80 * 1024**3
        or shutil.disk_usage(settings.runtime_root).free < int(size * 1.3) + 20 * 1024**3
    ):
        raise MediaError(
            "RESOURCE_LIMIT", "Temporary streaming media cannot fit within the disk budget.", "prepare"
        )
    directory = Path(settings.runtime_root) / "cinema" / row.id / job.id
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    output = directory / "ready"
    output.mkdir(mode=0o700)
    if (plan.get("subtitle") or {}).get("external"):
        from .cinema_subtitles import normalize_external

        plan = {**plan, "_external_subtitle_path": normalize_external(db, row, source, plan, output)}
    row.data = {**row.data, "_stream_job_id": job_id}
    db.commit()
    ACTIVE.add(job_id)
    check_lock = threading.Lock()
    last_check = [0.0, False]

    def check_authorized():
        with Session(bind) as fresh:
            current = fresh.get(CinemaWorkflow, workflow_id)
            if (
                not current
                or current.data.get("_stream_job_id") != job_id
                or current.state not in {"preparing", "command_sent", "playing_observed", "paused"}
            ):
                return True
            try:
                authorize_workflow(fresh, current)
            except MediaError:
                return True
            return False

    def cancelled():
        with check_lock:
            if time.monotonic() - last_check[0] >= 1:
                last_check[:] = [time.monotonic(), check_authorized()]
            return last_check[1]

    broker = input_broker(
        directory, lambda byte_range, head: public_stream(url, byte_range, head=head), cancelled=cancelled
    )
    errors = tempfile.TemporaryFile()
    process = None
    try:
        socket_path = broker.__enter__()
        plan, original = prepare_timeline(socket_path, output, plan)
        process = subprocess.Popen(
            streaming_media_command(ffmpeg_args(output, plan), socket_path, output),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=errors,
            env=MEDIA_ENV,
        )
        started = time.monotonic()
        while not ready(output, plan):
            if cancelled():
                raise MediaError("PREPARATION_CANCELLED", "Streaming preparation was cancelled.", "prepare")
            if process.poll() is not None or time.monotonic() - started > 60:
                raise MediaError(
                    "STREAM_PREPARATION_FAILED",
                    "The first playable buffer could not be prepared. Try another release.",
                    "prepare",
                    True,
                )
            time.sleep(0.15)
        offset = position_offset(socket_path, output, plan, original)
        write_master(output, plan, size)
        db.rollback()
        db.expire_all()
        row = db.get(CinemaWorkflow, workflow_id)
        if check_authorized():
            raise MediaError("PREPARATION_CANCELLED", "Streaming preparation was cancelled.", "prepare")
        observation = inspect_destination(db, device)
        old = row.data["_destination_observation"]
        if observation.get("item_id") != old.get("item_id") or (
            not row.data.get("_seek_previous") and observation.get("session_id") != old.get("session_id")
        ):
            raise MediaError("PLAN_STALE", "The destination changed during buffering.", "prepare")
        if check_authorized():
            raise MediaError("PREPARATION_CANCELLED", "Streaming preparation was cancelled.", "prepare")
        row.data = {
            **row.data,
            "_prepared": {
                "path": str(output / "master.m3u8"),
                "streaming": True,
                "timeline_version": 2,
                "position_offset": offset,
                "subtitle_path": None,
            },
        }
        db.commit()
        execute_cast(db, row, device, source, plan)
        previous = row.data.get("_seek_previous")
        if previous:
            from .cinema import CinemaRelay
            from sqlalchemy import select

            old_path = previous["prepared"]["path"]
            for grant in db.scalars(
                select(CinemaRelay).where(CinemaRelay.workflow_id == row.id, CinemaRelay.path == old_path)
            ):
                db.delete(grant)
            old_directory = Path(old_path).parent.parent
            row.data = {**row.data, "_seek_previous": None}
            db.commit()
            if (
                old_directory.parent == Path(settings.runtime_root) / "cinema" / row.id
                and old_directory != directory
            ):
                shutil.rmtree(old_directory, ignore_errors=True)
        save_workflow(
            db,
            row,
            "command_sent",
            {
                "error": None,
                "_observation_deadline": (utcnow() + timedelta(seconds=45)).isoformat(),
                "observation": {"state": "command_sent", "physical_verification": "unverified"},
            },
        )
    except BaseException as exc:
        if process and process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        broker.__exit__(None, None, None)
        errors.close()
        shutil.rmtree(directory, ignore_errors=True)
        ACTIVE.discard(job_id)
        if isinstance(exc, (OSError, subprocess.TimeoutExpired)):
            raise MediaError(
                "STREAM_PREPARATION_FAILED",
                "Streaming preparation could not finish its bounded startup checks.",
                "prepare",
                True,
            ) from None
        raise

    def monitor():
        failure = None
        try:
            while process.poll() is None:
                if cancelled():
                    break
                if (
                    time.monotonic() - started > max(1800, plan.get("duration") or 0) + 600
                    or errors.tell() > 1_000_000
                    or shutil.disk_usage(directory).free < 20 * 1024**3
                    or sum(p.stat().st_size for p in output.iterdir() if p.is_file())
                    > int(size * 1.3) + 16 * 1024**2
                ):
                    failure = MediaError(
                        "STREAM_RESOURCE_LIMIT",
                        "Streaming preparation exceeded its resource budget.",
                        "prepare",
                    )
                    break
                time.sleep(1)
            if process.poll() not in {None, 0} and not cancelled():
                failure = MediaError(
                    "STREAM_INTERRUPTED",
                    "The source or conversion stopped before completion.",
                    "prepare",
                    True,
                )
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            broker.__exit__(None, None, None)
            errors.close()
            with Session(bind) as fresh:
                job = fresh.get(CinemaPreparation, job_id)
                current = fresh.get(CinemaWorkflow, workflow_id)
                job.state = "failed" if failure else "done"
                job.finished_at = utcnow()
                if (
                    failure
                    and current
                    and current.data.get("_stream_job_id") == job_id
                    and current.state in {"preparing", "command_sent", "playing_observed", "paused"}
                ):
                    save_workflow(fresh, current, "recovery_required", {"error": failure.public()})
                fresh.commit()
            if failure or check_authorized():
                cleanup_stream_directory(bind, workflow_id, directory)
            ACTIVE.discard(job_id)

    threading.Thread(target=monitor, name="cinema-stream-" + job_id, daemon=True).start()
    return True
