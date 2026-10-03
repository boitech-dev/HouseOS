"""Web videos for Watch: read a link, download the video for the TV, remove it later.
Runs inside the fetcher: public internet only, no secrets. Files live in DIR, named by the
house's own id for the video: <id>.<ext> (the video), <id>.info.json (what the link said)."""

import json
import os
import re
import shutil
import subprocess
import time
from urllib.parse import urlsplit
from uuid import UUID

from .config import settings

DIR = settings.runtime_root / "audio" / "web-video"
# Up to 1080p, H.264 and AAC first (every TV plays them as they are), then anything.
FORMAT = (
    "bv*[vcodec^=avc1][height<=1080]+ba[acodec^=mp4a]/b[vcodec^=avc1][height<=1080]"
    "/bv*[height<=1080]+ba/b[height<=1080]/bv*+ba/b"
)
MAX_BYTES = 6 * 1024**3
MAX_SECONDS = 4 * 3600
VIDEO = {".mp4", ".webm", ".mkv", ".mov", ".m4v", ".ts"}


def link(value):
    """Only a plain web address (the fetcher's egress rules refuse private hosts anyway)."""
    value = str(value or "")
    parts = urlsplit(value)
    if (
        parts.scheme not in {"http", "https"}
        or not parts.hostname
        or parts.username
        or parts.password
        or len(value) > 2000
    ):
        raise ValueError("WEB_VIDEO_LINK_INVALID")
    return value


def files(identity):
    return [p for p in DIR.glob(identity + ".*") if p.is_file() and not p.is_symlink()]


def stream_dir(identity):
    """A video played while it downloads lives in its own folder, as HLS pieces (web_stream)."""
    return DIR / identity


def remove(identity, keep=()):
    for path in files(identity):
        if path.name not in keep:
            path.unlink(missing_ok=True)
    folder = stream_dir(identity)
    if folder.is_dir() and not folder.is_symlink():
        shutil.rmtree(folder, ignore_errors=True)


def expected(info):
    parts = info.get("requested_formats") or [info]
    sizes = [part.get("filesize") or part.get("filesize_approx") for part in parts]
    return int(sum(sizes)) if sizes and all(sizes) else None


def startup():
    """No transfer survives a restart: drop partial pieces, keep finished videos."""
    DIR.mkdir(exist_ok=True)
    for path in DIR.iterdir():
        identity = path.name.split(".", 1)[0]
        try:
            UUID(identity)
        except ValueError:
            continue
        if path.is_dir() and not path.is_symlink():
            if not complete_stream(path):  # its download was cut: it can't play to the end
                shutil.rmtree(path, ignore_errors=True)
            continue
        finished = path.name == identity + path.suffix and path.suffix in VIDEO | {".jpg"}
        if not finished:
            path.unlink(missing_ok=True)


def complete_stream(folder):
    try:
        return "#EXT-X-ENDLIST" in (folder / "video.m3u8").read_text()
    except OSError:
        return False


def streamable(info):
    """Picture and sound the TV plays as they are (H.264, AAC), each readable from the start as it
    arrives (YouTube's DASH files, HLS): then the video plays while it downloads."""
    parts = info.get("requested_formats") or [info]
    video = [p for p in parts if (p.get("vcodec") or "none") != "none"]
    audio = [p for p in parts if (p.get("acodec") or "none") != "none"]
    return (
        len(video) == 1
        and len(audio) == 1
        and str(video[0].get("vcodec")).startswith(("avc1", "h264"))
        and str(audio[0].get("acodec")).startswith(("mp4a", "aac"))
        and all(p.get("protocol") in {"https", "m3u8_native"} for p in parts)
        # A plain single MP4 keeps its index at the end: it can't be read as it arrives.
        and (len(parts) == 2 or parts[0].get("protocol") == "m3u8_native")
    )


def execute(data, base):
    from .fetcher import bounded_process, thumbnail_of

    DIR.mkdir(exist_ok=True)
    identity = str(UUID(data["item_id"]))
    ticket = DIR / (identity + ".info.json")
    cancelled = DIR / (identity + ".cancelled")
    if data["action"] == "web_remove":  # also stops its download, if one runs
        folder = stream_dir(identity)
        running = any(p.suffix in {".part", ".ytdl"} for p in files(identity)) or (
            folder.is_dir() and not complete_stream(folder)
        )
        if running:  # its download loop sees this, stops and clears it
            cancelled.touch(mode=0o600)
        remove(identity, keep={cancelled.name})
        return {"status": "completed"}
    url = link(data.get("source_url"))
    if data["action"] == "web_info":
        raw = bounded_process(
            base + ["-f", FORMAT, "--dump-single-json", "--skip-download", "--", url], 60, 30_000_000
        )
        info = json.loads(raw)
        if info.get("_type") == "playlist":
            raise ValueError("WEB_VIDEO_PLAYLIST")
        if info.get("is_live") or info.get("live_status") in {"is_live", "is_upcoming"}:
            raise ValueError("WEB_VIDEO_LIVE")
        duration = info.get("duration")
        if duration and duration > MAX_SECONDS:
            raise ValueError("WEB_VIDEO_TOO_LONG")
        size = expected(info)
        if size and size > MAX_BYTES:
            raise ValueError("WEB_VIDEO_TOO_BIG")
        ticket.write_bytes(raw)
        os.chmod(ticket, 0o640)
        return {
            "status": "completed",
            "streamable": streamable(info),
            "title": " ".join(str(info.get("title") or "").split())[:300],
            "site": str(info.get("extractor_key") or "")[:60],
            "uploader": str(info.get("uploader") or info.get("channel") or "")[:200],
            "duration": duration if isinstance(duration, (int, float)) else None,
            "bytes": size,
            "height": info.get("height") if isinstance(info.get("height"), int) else None,
            "thumbnail": thumbnail_of(info),
        }
    if data["action"] == "web_stream":
        return stream(identity, base, ticket, cancelled, data.get("bytes"))
    # web_video: the download itself, one at a time (its own lane, not the songs').
    cancelled.unlink(missing_ok=True)
    if shutil.disk_usage(DIR).free < (data.get("bytes") or 2 * 1024**3) + 10 * 1024**3:
        raise ValueError("WEB_VIDEO_NO_SPACE")
    args = base + [
        "-f",
        FORMAT,
        "--merge-output-format",
        "mp4",
        "--max-filesize",
        "6G",
        "--retries",
        "5",
        "--fragment-retries",
        "5",
        "--concurrent-fragments",
        "4",
        "-o",
        str(DIR / (identity + ".%(ext)s")),
    ]
    complete = None
    try:
        for attempt in range(2):
            # The link read a moment ago, or the page again when its video addresses expired.
            source = ["--load-info-json", str(ticket)] if ticket.is_file() and not attempt else ["--", url]
            try:
                bounded_process(
                    args + source,
                    3600,
                    65536,
                    cancelled=cancelled.exists,
                    file_limit=MAX_BYTES + 512 * 1024**2,
                )
                break
            except ValueError as error:
                if str(error) != "SOURCE_URL_EXPIRED" or attempt:
                    raise
        if cancelled.exists():
            raise ValueError("DOWNLOAD_CANCELLED")
        video = next(
            (p for p in files(identity) if p.suffix in VIDEO and p.name == identity + p.suffix), None
        )
        if not video:  # yt-dlp skips a file over --max-filesize without failing
            raise ValueError("WEB_VIDEO_TOO_BIG")
        os.chmod(video, 0o640)
        complete = video
        return {"status": "completed", "file": video.name, "bytes": video.stat().st_size}
    finally:
        # Finished: the video (and its picture) stay; the pieces go. Failed: everything goes.
        remove(identity, keep={complete.name, identity + ".jpg"} if complete else ())
        cancelled.unlink(missing_ok=True)


def partial_bytes(identity):
    """How much of a video is downloaded so far (its growing pieces), for the progress bar."""
    folder = stream_dir(identity)
    total = sum(p.stat().st_size for p in folder.iterdir() if p.is_file()) if folder.is_dir() else 0
    for path in files(identity):
        if re.search(r"\.(part|ytdl)$|\.f\d+\.\w+$", path.name) or path.suffix in VIDEO:
            try:
                total += path.stat().st_size
            except FileNotFoundError:
                pass
    return total


def stream(identity, base, ticket, cancelled, expected_bytes):
    """Download picture and sound at full speed (yt-dlp, in chunks: one long request is throttled
    to playback speed) into two pipes, and cut them into HLS pieces as they come (ffmpeg, copied,
    not converted). The TV starts on the first pieces; the finished folder is the kept copy."""
    info = json.loads(ticket.read_bytes()) if ticket.is_file() else None
    if not info or not streamable(info):
        raise ValueError("WEB_VIDEO_NOT_STREAMABLE")
    cancelled.unlink(missing_ok=True)
    if shutil.disk_usage(DIR).free < (expected_bytes or 2 * 1024**3) + 10 * 1024**3:
        raise ValueError("WEB_VIDEO_NO_SPACE")
    folder = stream_dir(identity)
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(mode=0o770)

    def limits():
        import resource

        resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_BYTES, MAX_BYTES))

    parts = info.get("requested_formats") or [info]
    loader = [x for x in base if x != "--no-playlist"] + ["--load-info-json", str(ticket), "-o", "-"]
    producers = [
        subprocess.Popen(
            loader + ["-f", part["format_id"]],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            preexec_fn=limits,
        )
        for part in parts
    ]
    pipes = [p.stdout.fileno() for p in producers]
    args = ["ffmpeg", "-nostdin", "-v", "error", "-n", "-protocol_whitelist", "pipe"]
    for fd in pipes:
        args += ["-i", f"pipe:{fd}"]
    args += [
        "-map",
        "0:v:0",
        "-map",
        f"{len(pipes) - 1}:a:0",
        "-c",
        "copy",
        "-max_interleave_delta",
        "1000000",
    ]
    args += ["-f", "hls", "-hls_time", "4", "-hls_list_size", "0", "-hls_playlist_type", "event"]
    args += ["-hls_segment_type", "fmp4", "-hls_segment_options", "use_editlist=0"]
    args += ["-master_pl_name", "av_master.m3u8", "-hls_flags", "temp_file+independent_segments"]
    muxer = subprocess.Popen(
        args + [str(folder / "video.m3u8")],
        pass_fds=pipes,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        start_new_session=True,
        preexec_fn=limits,
    )
    for p in producers:
        p.stdout.close()
    deadline = time.monotonic() + 3600
    try:
        while muxer.poll() is None:
            if cancelled.exists():
                raise ValueError("DOWNLOAD_CANCELLED")
            if time.monotonic() > deadline:
                raise ValueError("SOURCE_TIMEOUT")
            time.sleep(0.5)
        failed = muxer.returncode != 0 or any(p.wait(timeout=30) != 0 for p in producers)
        if failed or not complete_stream(folder):
            tail = (muxer.stderr.read() or b"")[-300:].decode(errors="replace")
            print(
                "web stream failed:", re.sub(r"https?://\S+", "<url>", tail).replace("\n", " | "), flush=True
            )
            raise ValueError("WEB_VIDEO_NOT_STREAMABLE")
        size = sum(p.stat().st_size for p in folder.iterdir() if p.is_file())
        return {"status": "completed", "stream": identity, "bytes": size}
    except BaseException:
        for process in (muxer, *producers):
            if process.poll() is None:
                os.killpg(process.pid, 9)
                process.wait()
        shutil.rmtree(folder, ignore_errors=True)
        raise
    finally:
        ticket.unlink(missing_ok=True)
        cancelled.unlink(missing_ok=True)
