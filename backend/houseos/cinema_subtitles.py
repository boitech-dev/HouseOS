"""Bounded complete text sidecars; never read the movie to convert external SRT."""

from pathlib import Path
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
