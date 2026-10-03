"""Tonight's suggestion: rank sources instead of rejecting them on taste.

Order of what matters: debrid-cached or local, at most the screen's resolution, then
something the viewer can follow (audio or subtitles in one of their languages, worth far more
than 4K), original-language audio, then resolution and size. Hard limits (the screen cannot
play it) still reject."""

import re

from .playback import MediaError, compatibility, language, resolution

# Release-name hints, read before a source is inspected.
MULTI = re.compile(r"(?i)(?<![a-z])(multi|dual|vostfr|subfrench|vost|subbed|vo)(?![a-z])")
FRENCH_DUB = re.compile(r"(?i)(?<![a-z])(truefrench|vff|vfq|vf2|french)(?![a-z])")
# Releases a TV rarely plays: dual-layer Dolby Vision remuxes (profile 7) and 50 GB+ files.
DV_REMUX = re.compile(
    r"(?is)(?=.*(?<![a-z])remux(?![a-z]))(?=.*(?<![a-z])(dv|dovi|dolby.?vision|p7)(?![a-z]))"
)
# 4K over 1080p is worth more than a MULTI/Dual name (15): otherwise a 1080p MULTI release
# was always probed before every plain 2160p one, and a 4K screen never got 4K.
RESOLUTION = {2160: 40, 1080: 20, 720: 5}
NOT_FOLLOWED = "no audio or subtitles in your languages"
# Only when the viewer asked for subtitles every time ("always_subtitles"): a version without
# them in their languages ranks below a smaller one with them.
NO_SUBTITLES = "no subtitles in your languages"


def understood(request):
    """The viewer's languages, most comfortable first. Without a saved list: the subtitle and
    audio languages they chose, then English."""
    chosen = request.get("languages") or [
        request.get("subtitle_language"),
        request.get("audio_language"),
        "en",
    ]
    return list(dict.fromkeys(language(code) for code in chosen if code))


def subtitle_order(audio_language, languages=("fr", "en"), preferred=None, always=False):
    """Subtitles in the viewer's languages (their chosen subtitle language first); none when the
    sound is already in their first language, unless they always want subtitles."""
    if audio_language == languages[0] and not always:
        return []
    return list(dict.fromkeys([language(preferred), *languages] if preferred else languages))


def provisional_score(source, maximum=2160):
    """Score from the provider's claims only (before the 16 MB probe)."""
    release = str(source.get("release") or "")
    height = source.get("height_claim") or 0
    score = 100 if source.get("rd_cached") or source.get("layer") == "LOCAL" else 0
    score += RESOLUTION.get(height, 0) if height <= maximum else -200
    if MULTI.search(release):
        score += 15
    elif FRENCH_DUB.search(release):
        score -= 25
    if DV_REMUX.search(release):
        score -= 40
    if (source.get("size") or 0) > 50e9:
        score -= 15
    return score - (source.get("provider_order") or 0) * 0.1


def rank_provisional(sources, maximum=2160, count=3):
    """The sources worth probing first, best first; never ones that already failed."""
    usable = [s for s in sources if not s.get("inspection") and not s.get("error") and s.get("info_hash")]
    return sorted(usable, key=lambda s: -provisional_score(s, maximum))[:count]


def original_language(media):
    """The default audio track, else the first, is the original in almost every release."""
    tracks = media.get("audio") or []
    chosen = next((t for t in tracks if t.get("default")), tracks[0] if tracks else None)
    return language(chosen.get("language")) if chosen and chosen.get("language") else None


def best_plan(media, capabilities, request, original=None):
    """The most fitting plan for this source, and why. Raises MediaError only on hard limits."""
    original = original or original_language(media)
    languages = understood(request)
    always = bool(request.get("always_subtitles"))
    # Track choices are ours to make; drop the resident's per-track picks from a previous title.
    # Subtitles are tried below, one language at a time: a file without them is not rejected.
    base = {
        k: v
        for k, v in request.items()
        if k not in {"audio_track", "subtitle_track", "audio_language", "subtitle_language", "quality"}
    } | {"subtitles_on": False}
    audio_options = [(original, 40, "original audio")] if original else []
    audio_options += [(code, 10, "your audio language") for code in languages if code != original]
    audio_options.append((None, -40 if original else 0, "the only audio"))
    fallback, last = None, None
    for audio_language, audio_points, audio_reason in audio_options:
        try:
            plan = compatibility(media, capabilities, {**base, "audio_language": audio_language})
        except MediaError as exc:
            if exc.code in {"AUDIO_INCOMPATIBLE"}:
                last = exc
                continue
            raise
        score, reasons = audio_points, [audio_reason]
        spoken = language(plan["audio"].get("language")) or original
        order = subtitle_order(spoken, languages, request.get("subtitle_language"), always)
        for subtitle_language in order:
            try:
                with_subtitles = compatibility(
                    media,
                    capabilities,
                    {
                        **base,
                        "audio_track": plan["audio"]["id"],
                        "subtitle_language": subtitle_language,
                        "subtitles_on": True,
                    },
                )
            except MediaError:
                continue
            if with_subtitles["subtitle_mode"] == "burn":
                continue  # a burn-in is never the quiet default
            plan = with_subtitles
            score += 45 if subtitle_language == order[0] else 25
            reasons.append(f"{subtitle_language} subtitles in the file")
            break
        else:
            if spoken not in languages:
                # 4K means nothing if nobody in the room follows it: try a dub they understand.
                fallback = fallback or (plan, score - 80, [*reasons, NOT_FOLLOWED])
                continue
            if always:
                score -= 60
                reasons.append(NO_SUBTITLES)
            elif subtitle_order(spoken, languages):
                reasons.append("no subtitles in the file")
        break
    else:
        if not fallback:
            raise last or MediaError("AUDIO_INCOMPATIBLE", "No playable audio track.")
        plan, score, reasons = fallback
    score += RESOLUTION.get(resolution(plan["video"]), 0)
    if plan["mode"] == "audio_convert":
        score -= 5
    return plan, score, reasons


def consensus_language(sources):
    """The original language: the one in the most releases (the original soundtrack is in
    nearly all of them, each dub only in some: a Polish MULTi release lists Polish first, yet
    English is in every release). Ties go to the most first tracks, then to non-French
    (dubs are usually French here)."""
    present, first = {}, {}
    for source in sources:
        tracks = [language(t.get("language")) for t in (source.get("inspection") or {}).get("audio", [])]
        spoken = list(dict.fromkeys(code for code in tracks if code not in {None, "und", "mul", "zxx"}))
        for code in spoken:
            present[code] = present.get(code, 0) + 1
        # A MULTI release's first non-French track, else its first: the old single vote.
        vote = next((code for code in spoken if code != "fr"), spoken[0] if spoken else None)
        if vote:
            first[vote] = first.get(vote, 0) + 1
    if not present:
        return None
    return max(present, key=lambda code: (present[code], first.get(code, 0), code != "fr"))


def rank_inspected(sources, capabilities, request, original=None):
    """Inspected sources ranked best first as (source, plan, score, reasons); rejects noted."""
    original = original or consensus_language(sources)
    ranked = []
    for source in sources:
        if not source.get("inspection") or source.get("error"):
            continue
        try:
            plan, score, reasons = best_plan(source["inspection"], capabilities, request, original)
        except MediaError as exc:
            source["rejection"] = exc.public()
            continue
        if source.get("rd_cached") or source.get("layer") in {"LOCAL", "RD_CLOUD"}:
            score += 100
        ranked.append((source, plan, score - (source.get("size") or 0) / 1e12, reasons))
    return sorted(ranked, key=lambda entry: -entry[2])
