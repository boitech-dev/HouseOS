"""Subtitles found online for a version without any in the viewer's language, in sync or not at all."""

from houseos import cinema_community_subs as subs


def srt(end_seconds):
    h, rest = divmod(end_seconds, 3600)
    m, s = divmod(rest, 60)
    return f"1\n00:00:01,000 --> 00:00:02,000\nHello\n\n2\n{h:02}:{m:02}:{s - 2:02},000 --> {h:02}:{m:02}:{s:02},500\nBye\n"


def test_the_fingerprint_is_opensubtitles_file_hash():
    blank = bytes(64 * 1024)
    assert subs.fingerprint(blank, blank, 131072) == "0000000000020000"  # the size alone
    one = (1).to_bytes(8, "little") + bytes(64 * 1024 - 8)
    assert subs.fingerprint(one, blank, 131072) == "0000000000020001"


def test_subtitles_in_sync_come_first_and_another_frame_rate_never():
    items = [
        {"lang": "eng", "m": "i", "fpsMilli": 29970, "movieReleaseName": "Film.1973.avi", "url": "https://a"},
        {
            "lang": "eng",
            "m": "i",
            "fpsMilli": 24000,
            "movieReleaseName": "Film.1973.720p.WEB",
            "url": "https://b",
        },
        {
            "lang": "eng",
            "m": "i",
            "fpsMilli": 24000,
            "movieReleaseName": "Film.1973.BluRay.x264",
            "url": "https://c",
        },
        {"lang": "eng", "m": "h", "fpsMilli": 25000, "movieReleaseName": "exact", "url": "https://d"},
        {"lang": "ger", "m": "h", "movieReleaseName": "German", "url": "https://e"},
    ]
    picked = [
        i["url"] for i in subs.ranked(items, "en", 23.976, "Film.1973.JAPANESE.1080p.BluRay.x265-VXT.mp4")
    ]
    # made for this file first (its own frame rate is its own), then same source, never 29.97
    assert picked == ["https://d", "https://c", "https://b"]


def test_a_subtitle_that_ends_far_from_the_films_end_is_refused(monkeypatch):
    monkeypatch.setattr(subs, "head_and_tail", lambda url, size: (b"", b""))
    monkeypatch.setattr(
        subs,
        "candidates",
        lambda *a: [
            {
                "lang": "eng",
                "m": "i",
                "fpsMilli": 24000,
                "movieReleaseName": "short cut",
                "url": "https://cut",
            },
            {"lang": "eng", "m": "i", "fpsMilli": 24000, "movieReleaseName": "right", "url": "https://right"},
        ],
    )
    texts = {"https://cut": srt(3000), "https://right": srt(5100)}
    monkeypatch.setattr(subs, "public_fetch", lambda url, limit=0: (texts[url].encode(), {}))
    text, item = subs.find("https://film", 1000, "tt1", "movie", None, None, "en", 23.976, "film", 5177)
    assert item["url"] == "https://right" and "Bye" in text
    texts["https://right"] = srt(3000)
    assert subs.find("https://film", 1000, "tt1", "movie", None, None, "en", 23.976, "film", 5177) is None


def test_no_subtitles_are_fetched_when_the_film_speaks_your_language(monkeypatch):
    from types import SimpleNamespace

    from houseos import cinema

    asked = []
    monkeypatch.setattr(subs, "find", lambda *a: asked.append(a))
    title = SimpleNamespace(canonical_id="tt1", data={})
    db = SimpleNamespace(get=lambda model, identity: title)
    row = SimpleNamespace(media_id="m", data={"request": {"languages": ["en"]}, "_sources": []})
    source = {"id": "s", "inspection": {"audio": [{"id": "1", "language": "en"}]}}
    assert cinema.found_subtitle(db, row, source, None, "1") is None and not asked
