"""Subtitles for a version that has none in the viewer's language, as Stremio finds them: the public
OpenSubtitles add-on (no account), asked with this exact file's fingerprint.

In sync or not at all: a subtitle made for this very file (its fingerprint matched) comes first,
then one from the same source at the same frame rate (a different frame rate drifts), and any
pick must end near the end of the film (another cut or speed is refused, not shown off time)."""

import re
import struct

from .cinema_adapters import public_fetch, public_stream
from .playback import MediaError, language

ADDON = "https://opensubtitles-v3.strem.io/subtitles"
BLOCK = 64 * 1024
# The add-on speaks ISO 639-2 (eng, fre, pob); HouseOS keeps two letters.
LANGUAGE_CODES = {"en": {"eng"}, "fr": {"fre", "fra"}, "pt": {"por", "pob"}, "es": {"spa", "spl"}}


def head_and_tail(url, size):
    if url.startswith("local:"):
        from .cinema import saved_path

        with open(saved_path(url.removeprefix("local:")), "rb") as film:
            head = film.read(BLOCK)
            film.seek(max(0, size - BLOCK))
            return head, film.read(BLOCK)
    parts = []
    for byte_range in (f"bytes=0-{BLOCK - 1}", f"bytes={max(0, size - BLOCK)}-{size - 1}"):
        _, _, chunks = public_stream(url, byte_range)
        parts.append(b"".join(chunks)[:BLOCK])
    return parts[0], parts[1]


def fingerprint(head, tail, size):
    """OpenSubtitles' file hash: the size plus the 64-bit words of the first and last 64 KB."""
    total = size
    for block in (head, tail):
        block = block[: len(block) - len(block) % 8]
        total += sum(struct.unpack(f"<{len(block) // 8}q", block))
    return f"{total & 0xFFFFFFFFFFFFFFFF:016x}"


def candidates(imdb, kind, season, episode, file_hash, size):
    path = f"{imdb}:{season}:{episode}" if kind != "movie" and season is not None else imdb
    extra = f"/videoHash={file_hash}&videoSize={size}" if file_hash else ""
    content, _ = public_fetch(f"{ADDON}/{'movie' if kind == 'movie' else 'series'}/{path}{extra}.json")
    import json

    items = json.loads(content).get("subtitles", [])
    return [
        item for item in items if isinstance(item, dict) and str(item.get("url", "")).startswith("https://")
    ]


def ranked(items, wanted, fps, release):
    """In sync first: the file's own (fingerprint), then the same frame rate and source."""
    codes = LANGUAGE_CODES.get(wanted, {wanted})
    words = {w for w in re.split(r"[^a-z0-9]+", release.lower()) if len(w) > 2}
    source = next(
        (s for s in ("bluray", "web", "hdtv", "dvd") if s in release.lower().replace("-", "")), None
    )
    out = []
    for item in items:
        if str(item.get("lang")) not in codes and language(item.get("lang")) != wanted:
            continue
        exact = item.get("m") == "h"
        rate = item.get("fpsMilli")
        if not exact and fps and rate and abs(rate / 1000 - fps) > 0.05:
            continue  # another frame rate: it would drift further out of sync as the film goes
        name = str(item.get("movieReleaseName") or item.get("subtitleFileName") or "").lower()
        same_source = bool(source and source in name.replace("-", ""))
        shared = len(words & {w for w in re.split(r"[^a-z0-9]+", name) if len(w) > 2})
        out.append(((exact, same_source, shared), item))
    return [item for _, item in sorted(out, key=lambda pair: pair[0], reverse=True)]


def last_cue_end(text):
    ends = re.findall(r"-->\s*(\d+):(\d\d):(\d\d)[,.](\d+)", text)
    if not ends:
        return None
    h, m, s, _ = ends[-1]
    return int(h) * 3600 + int(m) * 60 + int(s)


def find(url, size, imdb, kind, season, episode, wanted, fps, release, duration):
    """The best subtitle for this exact file, as (text, item), or None. Never raises for the film:
    no subtitles is a quiet outcome."""
    try:
        file_hash = fingerprint(*head_and_tail(url, size), size) if size else None
        items = candidates(imdb, kind, season, episode, file_hash, size)
    except (MediaError, OSError, ValueError):
        return None
    for item in ranked(items, wanted, fps, release)[:4]:
        try:
            content, _ = public_fetch(item["url"], limit=5 * 1024**2)
        except MediaError:
            continue
        text = content.decode("utf-8", "replace")
        end = last_cue_end(text)
        # It must end near the end of the film: another cut, or another speed, is not shown.
        if end and duration and 0.75 * duration <= end <= duration + 60:
            return text, item
    return None
