"""Bounded complete text sidecars; never read the movie to convert external SRT."""

from pathlib import Path
import re
import subprocess
from .integrations import integration_config
from .playback import MEDIA_ENV, MediaError, media_command


def normalize_external(db, row, source, plan, directory):
    from .cinema import CinemaSubtitle
    from .cinema_adapters import Jellyfin, OpenSubtitles

    subtitle = plan["subtitle"]
    if subtitle.get("external_jellyfin"):
        content = Jellyfin(integration_config(db, "jellyfin")).subtitle(
            source["jellyfin_item"], source["jellyfin_source"], subtitle["id"]
        )
    else:
        selected = db.get(CinemaSubtitle, subtitle["id"])
        if not selected or selected.owner_id != row.owner_id:
            raise MediaError("SUBTITLE_UNAVAILABLE", "The selected subtitle is unavailable.", "prepare")
        content = (
            selected.data["uploaded_vtt"].encode("utf-8")
            if selected.data.get("uploaded_vtt")
            else selected.data["text"].encode("utf-8")  # found for this file (cinema_community_subs)
            if selected.data.get("text")
            else OpenSubtitles(integration_config(db, "opensubtitles")).download(selected.data["file_id"])
        )
    return normalize_text(content, directory)


def normalize_text(content, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    source, output = directory / "external.srt", directory / "subtitle.vtt"
    if not content or len(content) > 5 * 1024**2:
        raise MediaError(
            "SUBTITLE_UNAVAILABLE", "The subtitle is empty or exceeds the text size limit.", "prepare"
        )
    try:
        source.write_bytes(content)
        subprocess.run(
            media_command(
                [
                    "ffmpeg",
                    "-nostdin",
                    "-v",
                    "error",
                    "-n",
                    "-protocol_whitelist",
                    "file",
                    "-format_whitelist",
                    "srt,ass,webvtt",
                    "-i",
                    str(source),
                    "-c:s",
                    "webvtt",
                    str(output),
                ],
                source,
                directory,
            ),
            capture_output=True,
            check=True,
            timeout=20,
            env=MEDIA_ENV,
        )
        if not output.read_bytes().startswith(b"WEBVTT"):
            raise ValueError("invalid normalized subtitle")
        return str(output)
    except (subprocess.SubprocessError, OSError, ValueError):
        output.unlink(missing_ok=True)
        raise MediaError(
            "SUBTITLE_UNAVAILABLE",
            "The subtitle could not be prepared. Choose another subtitle.",
            "prepare",
            True,
        ) from None
    finally:
        source.unlink(missing_ok=True)


TIMING = re.compile(r"^((?:\d+:)?\d{2}:\d{2}\.\d{3})\s+-->\s+((?:\d+:)?\d{2}:\d{2}\.\d{3})(.*)$")


def seconds(text):
    *hours, minutes, rest = text.split(":")
    return int(hours[0] if hours else 0) * 3600 + int(minutes) * 60 + float(rest)


def stamp(value):
    millis = round(value * 1000)
    return f"{millis // 3600000:02}:{millis // 60000 % 60:02}:{millis // 1000 % 60:02}.{millis % 1000:03}"


def shift_vtt(text, offset):
    """WebVTT cues moved by `offset` seconds (positive: later). A cue that would end before the
    start is dropped, one that would start before it starts at 0. Headers and notes stay."""
    blocks = []
    for block in text.replace("\r\n", "\n").split("\n\n"):
        lines = block.split("\n")
        at = next((i for i, line in enumerate(lines) if TIMING.match(line)), None)
        if at is not None:
            start, end, settings = TIMING.match(lines[at]).groups()
            start, end = seconds(start) + offset, seconds(end) + offset
            if end <= 0:
                continue
            lines[at] = stamp(max(0.0, start)) + " --> " + stamp(end) + settings
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)
