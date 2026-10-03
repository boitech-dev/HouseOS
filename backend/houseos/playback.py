"""Deterministic media inspection and planning. Never controls a device."""

from __future__ import annotations
import json
import re
import subprocess
from pathlib import Path


class MediaError(Exception):
    def __init__(self, code: str, message: str, stage: str = "preflight", retryable: bool = False):
        self.code, self.message, self.stage, self.retryable = code, message, stage, retryable
        super().__init__(code)

    def public(self):
        return dict(code=self.code, message=self.message, stage=self.stage, retryable=self.retryable)


LANGUAGES = {
    "eng": "en",
    "fra": "fr",
    "fre": "fr",
    "spa": "es",
    "deu": "de",
    "ger": "de",
    "ita": "it",
    "jpn": "ja",
    "por": "pt",
    # ISO 639-2 names in release files, so a viewer's two-letter choice matches them.
    **dict(
        pair.split(":")
        for pair in (
            "pol:pl rus:ru ukr:uk cze:cs ces:cs dut:nl nld:nl swe:sv nor:no nob:no dan:da fin:fi "
            "gre:el ell:el hun:hu rum:ro ron:ro tur:tr ara:ar heb:he hin:hi kor:ko chi:zh zho:zh "
            "tha:th vie:vi ind:id may:ms msa:ms per:fa fas:fa bul:bg hrv:hr slo:sk slk:sk slv:sl "
            "est:et lav:lv lit:lt ice:is isl:is alb:sq sqi:sq cat:ca srp:sr tam:ta tel:te"
        ).split()
    ),
    "und": None,
}
TEXT_SUBS = {"subrip", "srt", "webvtt", "mov_text", "ass", "ssa", "text"}
MEDIA_ENV = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "HOME": "/nonexistent"}
CONTAINER_FORMATS = "mov,matroska,webm,mpegts,avi,mpeg"
VIDEO_SUFFIXES = {".mkv", ".mp4", ".m4v", ".avi", ".ts", ".webm", ".mov"}


def media_command(args: list[str], source: Path, output_directory: Path | None = None) -> list[str]:
    """Expose one input and one owned output directory, with no network or host home."""
    input_path = str(source.resolve())
    command = [
        "bwrap",
        "--unshare-all",
        "--die-with-parent",
        "--new-session",
        "--cap-drop",
        "ALL",
        "--ro-bind",
        "/usr",
        "/usr",
        "--symlink",
        "usr/lib",
        "/lib",
        "--symlink",
        "usr/lib64",
        "/lib64",
        "--ro-bind",
        "/etc/fonts",
        "/etc/fonts",
        "--ro-bind",
        "/etc/ld.so.cache",
        "/etc/ld.so.cache",
        "--dev",
        "/dev",
        "--dir",
        "/proc",
        "--tmpfs",
        "/tmp",
        "--dir",
        "/input",
        "--ro-bind",
        input_path,
        "/input/media.bin",
    ]
    output_path = str(output_directory.resolve()) if output_directory else None
    if output_path:
        command += ["--bind", output_path, "/output"]
    rewritten = [
        arg.replace(input_path, "/input/media.bin").replace(output_path, "/output")
        if output_path
        else arg.replace(input_path, "/input/media.bin")
        for arg in args
    ]
    return command + rewritten


def language(value):
    return LANGUAGES.get(str(value).lower(), str(value).lower() if value else None)


def inspect_probe(raw: dict) -> dict:
    streams = raw.get("streams", [])
    video = next(
        (
            s
            for s in streams
            if s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic")
        ),
        None,
    )
    if not video:
        raise MediaError("MEDIA_PROBE_FAILED", "No video stream was found.", "probe")
    side_data = video.get("side_data_list", [])
    dv = next((s for s in side_data if "DOVI" in s.get("side_data_type", "")), None)
    transfer = video.get("color_transfer")
    hdr = (
        "dolby_vision"
        if dv
        else "hdr10"
        if transfer == "smpte2084"
        else "hlg"
        if transfer == "arib-std-b67"
        else "sdr"
    )

    def track(s):
        tags, disposition = s.get("tags", {}), s.get("disposition", {})
        return {
            "id": str(s["index"]),
            "codec": s.get("codec_name"),
            "language": language(tags.get("language")),
            "title": str(tags.get("title") or "")[:160],
            "channels": s.get("channels"),
            "default": bool(disposition.get("default")),
            "forced": bool(disposition.get("forced")),
            "sdh": bool(disposition.get("hearing_impaired")),
            "commentary": bool(disposition.get("comment")),
        }

    try:
        duration = float(raw.get("format", {}).get("duration") or video.get("duration") or 0)
    except (ValueError, TypeError):
        duration = 0
    from fractions import Fraction

    try:
        frame_rate = round(float(Fraction(str(video.get("avg_frame_rate") or "0"))), 4) or None
    except (ValueError, ZeroDivisionError):
        frame_rate = None
    return {
        "video_stream_count": sum(
            s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic")
            for s in streams
        ),
        "video": {
            "index": video["index"],
            "codec": video.get("codec_name"),
            "profile": video.get("profile"),
            "level": video.get("level"),
            "width": video.get("width"),
            "height": video.get("height"),
            "pixel_format": video.get("pix_fmt"),
            "frame_rate": frame_rate,
            "hdr": hdr,
            "dv_profile": dv.get("dv_profile") if dv else None,
            "dv_compatibility_id": dv.get("dv_bl_signal_compatibility_id") if dv else None,
        },
        "audio": [track(s) for s in streams if s.get("codec_type") == "audio"],
        "subtitles": [track(s) for s in streams if s.get("codec_type") == "subtitle"],
        "duration": duration,
        "container": raw.get("format", {}).get("format_name", ""),
        "bit_rate": raw.get("format", {}).get("bit_rate"),
        "evidence": "ffprobe",
    }


def probe_file(path: Path, *, timeout: int = 20) -> dict:
    """Only a local, regular file. The demuxer cannot fetch network/child protocols."""
    if not path.is_file() or path.is_symlink():
        raise MediaError("MEDIA_PROBE_FAILED", "The prepared media file is unavailable.", "probe")
    try:
        result = subprocess.run(
            media_command(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-protocol_whitelist",
                    "file",
                    "-format_whitelist",
                    CONTAINER_FORMATS,
                    "-probesize",
                    "16000000",
                    "-analyzeduration",
                    "10000000",
                    "-show_streams",
                    "-show_format",
                    "-of",
                    "json",
                    str(path.resolve()),
                ],
                path,
            ),
            capture_output=True,
            timeout=timeout,
            env=MEDIA_ENV,
        )
        if result.returncode or len(result.stdout) > 2_000_000:
            raise ValueError()
        return inspect_probe(json.loads(result.stdout))
    except (subprocess.TimeoutExpired, ValueError, OSError):
        raise MediaError(
            "MEDIA_PROBE_FAILED", "Media inspection failed within its bounded probe budget.", "probe", True
        ) from None


def effective_request(saved: dict, current: dict) -> dict:
    return {
        "subtitles_on": False,
        "autoplay": False,
        **saved,
        **{k: v for k, v in current.items() if v is not None},
    }


def choose_track(tracks, requested_id, requested_language, *, subtitles=False, enabled=True):
    if subtitles and not enabled:
        return None
    if requested_id is not None:
        matches = [t for t in tracks if t["id"] == str(requested_id)]
    elif requested_language:
        matches = [t for t in tracks if t.get("language") == language(requested_language)]
    else:
        matches = tracks
    if not matches:
        raise MediaError(
            "SUBTITLE_UNAVAILABLE" if subtitles else "AUDIO_INCOMPATIBLE",
            "The requested subtitle track is unavailable."
            if subtitles
            else "The requested audio track is unavailable.",
        )
    # Forced-only subtitles (signs, foreign lines) are never the quiet default.
    return sorted(
        matches,
        key=lambda t: (
            subtitles and requested_id is None and bool(t.get("forced")),
            not t.get("default"),
            bool(t.get("commentary")),
            t["id"],
        ),
    )[0]


def resolution(video):
    """2160, 1080 or 720, else the height. Widescreen films are cropped (1920×800, 3840×1600),
    so the width decides when it is known; a 720×576 DVD stays below 720p."""
    height = video.get("height") or 0
    size = max(height, (video.get("width") or 0) * 9 // 16)
    return 2160 if size >= 2000 else 1080 if size >= 1000 else 720 if size >= 700 else height


def compatibility(media: dict, capabilities: dict, request: dict) -> dict:
    """No optimistic support: unknown video/HDR/capability evidence stops planning."""
    if not capabilities.get("inspected_at"):
        raise MediaError("TARGET_UNVERIFIED", "Inspect this destination before preparing playback.")
    video = media["video"]
    height = resolution(video)
    desired = request.get("quality")
    if desired in {"4k", "2160p"} and height < 2160 or desired == "1080p" and height < 1080:
        raise MediaError("QUALITY_MISMATCH", "This source does not meet the requested resolution.")
    maximum = request.get("maximum_resolution")
    if maximum and height > int(maximum):
        raise MediaError("QUALITY_MISMATCH", "This source exceeds the current request resolution limit.")
    if request.get("hdr") == "require" and video.get("hdr") == "sdr":
        raise MediaError("VIDEO_MODE_UNSUPPORTED", "The request requires HDR; this source is SDR.")
    if request.get("hdr") == "avoid" and video.get("hdr") != "sdr":
        raise MediaError("VIDEO_MODE_UNSUPPORTED", "The request asks for SDR; this source is HDR.")
    if video.get("codec") not in capabilities.get("video_codecs", []) or height > capabilities.get(
        "maximum_resolution", 0
    ):
        raise MediaError(
            "VIDEO_MODE_UNSUPPORTED",
            "The destination cannot preserve this video codec/resolution. Choose a compatible source.",
        )
    if video.get("hdr") not in capabilities.get("hdr_modes", []):
        raise MediaError(
            "VIDEO_MODE_UNSUPPORTED", "This destination has no verified support for the source HDR mode."
        )
    if video.get("hdr") == "dolby_vision" and video.get("dv_profile") not in capabilities.get(
        "dv_profiles", []
    ):
        raise MediaError(
            "VIDEO_MODE_UNSUPPORTED", "The exact Dolby Vision profile is not supported by this destination."
        )
    limits = capabilities.get("video_profiles", {}).get(video.get("codec"), {})
    if limits.get("profiles") and video.get("profile") not in limits["profiles"]:
        raise MediaError("VIDEO_MODE_UNSUPPORTED", "The video codec profile is not supported.")
    if limits.get("maximum_level") and (not video.get("level") or video["level"] > limits["maximum_level"]):
        raise MediaError("VIDEO_MODE_UNSUPPORTED", "The video codec level exceeds destination capability.")
    if limits.get("maximum_frame_rate") and (
        not video.get("frame_rate") or video["frame_rate"] > limits["maximum_frame_rate"]
    ):
        raise MediaError(
            "VIDEO_MODE_UNSUPPORTED", "The source frame rate exceeds the verified destination limit."
        )
    if limits.get("pixel_formats") and video.get("pixel_format") not in limits["pixel_formats"]:
        raise MediaError(
            "VIDEO_MODE_UNSUPPORTED",
            "The source bit depth/chroma format is not verified on this destination.",
        )
    audio = choose_track(media["audio"], request.get("audio_track"), request.get("audio_language"))
    subtitle_tracks = media["subtitles"]
    if request.get("subtitle_track") is None:
        # Prefer a usable text track in the requested language over bitmap burn-in.
        compatible = [
            t
            for t in subtitle_tracks
            if (
                not request.get("subtitle_language")
                or t.get("language") == language(request["subtitle_language"])
            )
            and (
                t["codec"] in capabilities.get("embedded_subtitle_codecs", [])
                or t["codec"] in TEXT_SUBS
                and capabilities.get("external_webvtt")
            )
        ]
        if compatible:
            subtitle_tracks = compatible
    subtitle = choose_track(
        subtitle_tracks,
        request.get("subtitle_track"),
        request.get("subtitle_language"),
        subtitles=True,
        enabled=request.get("subtitles_on", False),
    )
    audio_conversion = audio["codec"] not in capabilities.get("audio_codecs", []) or (
        audio.get("channels") or 2
    ) > capabilities.get("max_audio_channels", 2)
    warnings = []
    if audio_conversion:
        if "aac" not in capabilities.get("audio_codecs", []):
            raise MediaError("AUDIO_INCOMPATIBLE", "No supported audio conversion target is available.")
        warnings.append("Audio conversion required; video will be copied unchanged.")
    subtitle_mode = "off"
    if subtitle:
        if subtitle["codec"] in capabilities.get("embedded_subtitle_codecs", []):
            subtitle_mode = "embedded"
        elif subtitle["codec"] in TEXT_SUBS and capabilities.get("external_webvtt"):
            subtitle_mode = "webvtt"
            if subtitle["codec"] in {"ass", "ssa"}:
                warnings.append("WebVTT conversion loses ASS/SSA positioning and styling.")
        elif (
            request.get("allow_video_transcode")
            and video.get("hdr") == "sdr"
            and height <= 1080
            and "h264" in capabilities.get("video_codecs", [])
        ):
            subtitle_mode = "burn"
            warnings.append(
                "Subtitle burn-in re-encodes SDR video to H.264, cannot be switched off during this stream, and uses the single video preparation slot."
            )
        else:
            raise MediaError(
                "SUBTITLE_BURN_REQUIRED",
                "This subtitle requires video burn-in. Choose a compatible text track or explicitly approve a different video plan.",
            )
    container_supported = (
        any(c in capabilities.get("containers", []) for c in media["container"].split(","))
        and media.get("video_stream_count", 1) == 1
    )
    mode = (
        "video_convert"
        if subtitle_mode == "burn"
        else "audio_convert"
        if audio_conversion
        else "direct"
        if container_supported
        else "remux"
    )
    return {
        "video": video,
        "audio": audio,
        "subtitle": subtitle,
        "subtitle_mode": subtitle_mode,
        "mode": mode,
        "output_audio_codec": "aac" if audio_conversion else audio["codec"],
        "audio_conversion": audio_conversion,
        "output_channels": min(audio.get("channels") or 2, capabilities.get("max_audio_channels", 2)),
        "warnings": warnings,
        "duration": media["duration"],
        "video_copied": subtitle_mode != "burn",
        "verification": {
            "physical_video": "unverified",
            "physical_audio": "unverified",
            "physical_subtitles": "unverified",
        },
    }


def exact_episode_file(files: list[dict], season: int, episode: int) -> dict:
    matches = []
    for file in files:
        path = str(file.get("path", ""))
        if Path(path).suffix.lower() not in VIDEO_SUFFIXES or re.search(
            r"(?<![A-Za-z0-9])(sample|trailer|extra|featurette)(?![A-Za-z0-9])", path, re.I
        ):
            continue
        name = Path(path).name
        found = re.findall(r"(?i)(?<!\w)S(\d{1,2})[ ._-]*E(\d{1,3})(?!\d)", name)
        if not found:
            found = re.findall(r"(?i)(?<!\d)(\d{1,2})x(\d{1,3})(?!\d)", name)
        # Double/ranged episodes require a canonical chapter map; never guess a start offset.
        multi = re.search(
            r"(?i)E\d{1,3}[ ._+/\-]*E\d|E\d{1,3}[-+]\d|\d+x\d+[-+]\d|\d+x\d+[ ._+-]*\d+x\d+", name
        )
        if not multi and len(found) == 1 and tuple(map(int, found[0])) == (season, episode):
            matches.append(file)
    if len(matches) != 1:
        raise MediaError(
            "EPISODE_AMBIGUOUS",
            "The exact episode cannot be uniquely mapped to a file. Playback was not started.",
            "identify",
        )
    return matches[0]


def select_candidate(candidates: list[dict], choice: str) -> dict:
    normalized = choice.strip().lower()
    if normalized.isdigit():
        index = int(normalized) - 1
        if 0 <= index < len(candidates):
            return candidates[index]
        raise MediaError("CHOICE_AMBIGUOUS", "That source number is not in this choice set.", "select")
    exact = [c for c in candidates if c["id"] == choice]
    if exact:
        return exact[0]
    matches = candidates
    used = False
    for token, height in [("4k", 2160), ("2160p", 2160), ("1080p", 1080), ("720p", 720)]:
        if token in normalized:
            matches = [c for c in matches if c.get("height") == height]
            used = True
    if "smaller" in normalized and matches:
        smallest = min(c.get("size") or float("inf") for c in matches)
        matches = [c for c in matches if (c.get("size") or float("inf")) == smallest]
        used = True
    if used and len(matches) == 1:
        return matches[0]
    raise MediaError(
        "CHOICE_AMBIGUOUS",
        "Choose one source number; the description does not uniquely identify a source.",
        "select",
    )


def prepare_local(source: Path, directory: Path, plan: dict, *, timeout: int = 120, cancelled=None) -> dict:
    """Fixed argv, selected tracks, video copy, bounded conversion. No network demuxing."""
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    output = directory / "media.mp4"
    args = [
        "ffmpeg",
        "-nostdin",
        "-v",
        "error",
        "-n",
        "-protocol_whitelist",
        "file",
        "-format_whitelist",
        CONTAINER_FORMATS,
        "-i",
        str(source.resolve()),
    ]
    burn = plan.get("subtitle_mode") == "burn"
    if burn and plan["subtitle"]["codec"] not in TEXT_SUBS:
        args += [
            "-filter_complex",
            f"[0:{plan['video']['index']}][0:{plan['subtitle']['id']}]overlay[v]",
            "-map",
            "[v]",
        ]
    else:
        args += ["-map", f"0:{plan['video']['index']}"]
    args += ["-map", f"0:{plan['audio']['id']}"]
    if burn:
        if plan["subtitle"]["codec"] in TEXT_SUBS:
            subtitle_number = (
                None
                if plan.get("_external_subtitle_path")
                else [t["id"] for t in probe_file(source)["subtitles"]].index(plan["subtitle"]["id"])
            )
            # HouseOS preparation inputs have generated names, never client-supplied paths.
            if any(c in str(source.resolve()) for c in ["'", ":", "\\"]):
                raise MediaError(
                    "PREPARATION_FAILED",
                    "The generated media path is unsafe for subtitle conversion.",
                    "prepare",
                )
            args += [
                "-vf",
                f"subtitles=filename='{plan['_external_subtitle_path']}'"
                if plan.get("_external_subtitle_path")
                else f"subtitles=filename='{source.resolve()}':si={subtitle_number}",
            ]
        args += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18"]
    else:
        args += ["-c:v", "copy"]
    convert_audio = plan.get("audio_conversion", plan["mode"] == "audio_convert")
    args += ["-c:a", plan["output_audio_codec"] if convert_audio else "copy", "-threads", "2", "-sn"]
    if convert_audio:
        args += ["-ac", str(plan["output_channels"]), "-b:a", "192k"]
    args += ["-movflags", "+faststart", "-fs", str(80 * 1024**3), str(output)]
    try:
        run_media_command(media_command(args, source, directory), timeout=timeout, cancelled=cancelled)
        subtitle_path = None
        if plan.get("subtitle_mode") == "webvtt":
            subtitle_path = (
                Path(plan["_external_subtitle_path"])
                if plan.get("_external_subtitle_path")
                else directory / "subtitle.vtt"
            )
            if not plan.get("_external_subtitle_path"):
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
                            CONTAINER_FORMATS,
                            "-i",
                            str(source.resolve()),
                            "-map",
                            f"0:{plan['subtitle']['id']}",
                            "-c:s",
                            "webvtt",
                            str(subtitle_path),
                        ],
                        source,
                        directory,
                    ),
                    capture_output=True,
                    timeout=30,
                    check=True,
                    env=MEDIA_ENV,
                )
        inspected = probe_file(output)
        if plan.get("duration") and abs(inspected["duration"] - plan["duration"]) > max(
            3, plan["duration"] * 0.01
        ):
            raise MediaError(
                "PREPARATION_INCOMPLETE",
                "Prepared media duration does not match the selected source.",
                "prepare",
            )
        return {
            "path": str(output),
            "subtitle_path": str(subtitle_path) if subtitle_path else None,
            "inspection": inspected,
        }
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, OSError):
        raise MediaError(
            "PREPARATION_FAILED", "Media preparation failed or exceeded its time budget.", "prepare", True
        ) from None


def run_media_command(args, *, timeout, cancelled=None):
    """Bound subprocess time/error output; a revoked preparation is terminated promptly."""
    import tempfile
    import time

    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=errors, env=MEDIA_ENV)
        started = time.monotonic()
        try:
            while process.poll() is None:
                if cancelled and cancelled():
                    raise MediaError(
                        "PREPARATION_CANCELLED",
                        "The preparation was cancelled or its authorization changed.",
                        "prepare",
                    )
                if time.monotonic() - started > timeout or errors.tell() > 1_000_000:
                    raise subprocess.TimeoutExpired(args[0], timeout)
                time.sleep(0.1)
            if process.returncode:
                raise subprocess.CalledProcessError(process.returncode, args[0])
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)


def map_library_tracks(actual: dict, declared: dict):
    """Jellyfin may renumber streams when it inserts sidecars; prove a unique mapping."""
    import copy

    mapped = copy.deepcopy(actual)
    physical = {str(declared["video"]["index"]): str(actual["video"]["index"])}
    mapped["video"]["index"] = declared["video"]["index"]
    keys = ("codec", "language", "title", "channels", "default", "forced", "sdh", "commentary")
    for kind in ("audio", "subtitles"):
        expected = [track for track in declared[kind] if not track.get("external_jellyfin")]
        available = list(actual[kind])
        if len(expected) != len(available):
            raise MediaError("PLAN_STALE", "Library media tracks differ from the approved source.", "prepare")
        converted = []
        for track in expected:
            matches = [
                candidate
                for candidate in available
                if all(candidate.get(key) == track.get(key) for key in keys)
            ]
            if len(matches) != 1:
                raise MediaError(
                    "TRACK_MAPPING_AMBIGUOUS",
                    "The library track cannot be uniquely matched to the media file. Choose another release or use the native Jellyfin player.",
                    "prepare",
                )
            candidate = matches[0]
            available.remove(candidate)
            physical[track["id"]] = candidate["id"]
            converted.append({**candidate, "id": track["id"]})
        mapped[kind] = converted
    return mapped, physical
