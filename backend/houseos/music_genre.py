"""Genres and artwork for songs and stations: code and free public data, never a model.

A song's genre comes, first match wins, from:
1. the house's own genres (Control Room → House: a name and the words that mean it);
2. what the source says: SoundCloud's genre, the station's tags, the title's words
   ("opening", "lofi", "OST"…);
3. Deezer's public catalogue (no account, no key): the album's genre, looked up once per song
   by the maintenance service, with its cover for songs that have no artwork.

Each song keeps its evidence (source genre, tags, Deezer's genres) in its history record, so a
genre the house adds later applies to everything already played, without looking anything up
again. The families are ordered specific before broad ("synthpop" is electro before pop)."""

import re
import time
import unicodedata

FAMILIES = [
    (
        "anime",
        [
            "anime",
            "anisong",
            "anison",
            "amv",
            "opening",
            "openings",
            "ending theme",
            "full ending",
            "tv size",
            "vocaloid",
            "hatsune miku",
            r"re:(?<!\w)(op|ed)\s?\d{1,2}(?!\d)",  # "One Piece OP 7", "ED3"
        ],
    ),
    (
        "soundtrack",
        [
            "soundtrack",
            "ost",
            "bande originale",
            "score",
            "film music",
            "films/games",
            "video game",
            "video game music",
            "game music",
            "vgm",
        ],
    ),
    ("metal", ["metal", "metalcore", "deathcore", "djent", "thrash"]),
    ("lo-fi", ["lofi", "lo-fi", "chillhop", "study beats"]),
    ("house / techno", ["techno", "deep house", "tech house", "house music", "trance", "minimal"]),
    (
        "electro",
        [
            "electro",
            "edm",
            "dubstep",
            "drum and bass",
            "dnb",
            "synthwave",
            "synthpop",
            "trap edm",
            "dance",
            "electronic",
        ],
    ),
    ("rap / hip-hop", ["rap", "hip hop", "hip-hop", "hiphop", "drill", "trap", "grime", "french rap"]),
    ("r&b / soul", ["r&b", "rnb", "soul", "funk", "neo soul", "motown", "soul & funk"]),
    ("jazz", ["jazz", "bossa", "swing", "bebop", "blues"]),
    (
        "classical",
        ["classical", "classique", "symphony", "concerto", "sonata", "orchestra", "piano solo", "opera"],
    ),
    ("reggae", ["reggae", "dancehall", "dub", "ska"]),
    ("j-pop / k-pop", ["j-pop", "jpop", "k-pop", "kpop", "j-rock", "city pop", "asian music"]),
    ("rock", ["rock", "punk", "grunge", "indie rock", "alternative", "emo"]),
    ("chanson", ["chanson", "variété", "variete", "french pop", "chanson française", "variété française"]),
    (
        "latin",
        [
            "reggaeton",
            "latin",
            "latin music",
            "salsa",
            "bachata",
            "cumbia",
            "brazilian",
            "samba",
            "baile funk",
        ],
    ),
    (
        "world",
        [
            "african music",
            "afrobeat",
            "afrobeats",
            "afro",
            "indian music",
            "bollywood",
            "world music",
            "celtic",
            "traditional",
            "arabic music",
            "raï",
            "rai",
            "flamenco",
        ],
    ),
    ("kids", ["kids", "children", "comptine", "comptines", "nursery rhyme"]),
    ("folk", ["folk", "acoustic", "country", "bluegrass"]),
    ("ambient", ["ambient", "meditation", "sleep music", "relaxing"]),
    ("talk / news", ["talk", "news", "news talk", "information", "podcast", "sport", "sports"]),
    ("pop", ["pop", "hits", "charts", "top 40", "oldies", r"re:(19)?[5-9]0s"]),
]
NAMES = [family for family, _ in FAMILIES]


def pattern(words):
    """Whole words or phrases; an entry starting with "re:" is a small regular expression."""
    parts = [w[3:] if w.startswith("re:") else r"(?<!\w)" + re.escape(w) + r"(?!\w)" for w in words]
    return re.compile("|".join(parts))


WORD = {family: pattern(words) for family, words in FAMILIES}
# Everyday words that name a genre only in a genre field or a tag: in a song's title they are
# just words ("Sultans Of Swing", "Rock Your Body", "Soul Man", "Trap Queen").
TITLE_NOISE = {
    "swing", "soul", "rock", "dance", "trap", "blues", "funk", "talk", "sport", "sports", "score",
    "opera", "emo", "afro", "rai", "raï", "dub", "ska", "minimal", "traditional", "acoustic",
    "country", "folk", "drill", "electro", "house music", "news", "children", "kids",
}  # fmt: skip


def custom_families(extra):
    """The house's own genres, [{"name", "words"}], as (name, compiled words)."""
    found = []
    for genre in extra or ():
        words = [w.casefold().strip().removeprefix("re:") for w in genre.get("words") or [] if w.strip()]
        if genre.get("name") and words:
            found.append((str(genre["name"]), pattern(words)))
    return found


def genre_of(meta: dict, extra=()) -> str:
    """The family for what a source says: its genre, then Deezer's, then tags, then the title
    (and uploader). A genre the house added wins wherever its words appear."""
    texts = [str(meta.get("genre") or "")]
    texts += [str(g) for g in (meta.get("genres") or [])[:5]]
    texts += [str(t) for t in (meta.get("tags") or [])[:30]]
    titles = [str(meta.get("title") or "").casefold(), str(meta.get("uploader") or "").casefold()]
    texts = [text.casefold() for text in texts if text]
    ours = [(family, WORD[family]) for family in NAMES]
    for families in (custom_families(extra), ours):
        for text in texts:
            for family, words in families:
                if words.search(text):
                    return family
        # In a title the house's own words count; ours only when not an everyday word.
        for text in titles:
            for family, words in families:
                if any(families is not ours or m.group(0) not in TITLE_NOISE for m in words.finditer(text)):
                    return family
    return "other"


# ---------- artist and title from what YouTube and SoundCloud show ----------
NOISE = re.compile(r"\s*[\(\[][^\)\]]*[\)\]]")  # (Official Video), [Lyrics], (feat. X)…
# The same without brackets, at the end: "Effy VIDEOCLIP", "X - Y Video Oficial", "Clip officiel".
TAIL = re.compile(
    r"\s+(official\s+(music\s+)?video|video\s*clip|videoclip|video\s+oficial|clip\s+officiel|lyrics?|audio)$",
    re.I,
)
INVISIBLE = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060\ufeff]")
FEAT = re.compile(r"\s+(ft\.?|feat\.?|featuring|prod\.?)\s.*$", re.I)


def clean(text):
    text = NOISE.sub("", INVISIBLE.sub("", str(text or "")))
    text = re.split(r" \| | // |//", text)[0]
    return TAIL.sub("", FEAT.sub("", text)).strip(" -–—\"'")


CHANNEL = re.compile(r"(\s*-\s*topic|\s*vevo|\s*official|\s*music|\s*tv|\s*records|\s*channel)$", re.I)


def channel_artist(uploader):
    """The artist behind a channel name: "EminemMusic", "X - Topic", "XVEVO" → the name."""
    name = str(uploader or "").strip()
    while (shorter := CHANNEL.sub("", name)) != name and shorter:
        name = shorter
    return name


def artist_and_track(title, uploader="", artist=""):
    """("Artist", "Track") from "Artist - Track", else the channel name ("X - Topic")."""
    title = clean(title)
    for dash in (" - ", " – ", " — "):
        if dash in title:
            left, right = title.split(dash, 1)
            return clean(left), clean(right)
    return clean(artist or channel_artist(uploader)), title


def fold(text):
    """Lowercase words without accents or punctuation: "Beyoncé – Halo!" → "beyonce halo"."""
    text = unicodedata.normalize("NFKD", str(text or "").casefold())
    return " ".join(re.findall(r"\w+", "".join(c for c in text if not unicodedata.combining(c))))


def same(a, b):
    """Loosely the same name: most of the shorter one's words are in the other."""
    a, b = set(fold(a).split()), set(fold(b).split())
    small = min(a, b, key=len)
    return bool(small) and len(a & b) >= max(1, round(len(small) * 0.6))


# ---------- Deezer's public catalogue ----------
DEEZER = "https://api.deezer.com"


def deezer(title, uploader="", artist="", client=None):
    """{"genres": [...], "cover": url} for a song, {} when Deezer has no match; network errors
    raise (the caller tries again later). Two small requests; Deezer allows 50 per 5 s."""
    import httpx

    name, track = artist_and_track(title, uploader, artist)
    if not track:
        return {}
    http = client or httpx.Client(timeout=6, headers={"Accept-Language": "en"})
    channel = clean(artist or channel_artist(uploader))

    def fits(hit):
        """The same song: its title and artist, either way round ("Title - Artist" exists),
        or the channel's own artist when the title named none."""
        got_title, got_artist = hit.get("title", ""), (hit.get("artist") or {}).get("name", "")
        return (
            same(got_title, track) and (not name or same(got_artist, name) or same(got_artist, channel))
        ) or (name and same(got_title, name) and same(got_artist, track))

    try:
        queries = [f'artist:"{name}" track:"{track}"', f"{name} {track}", track] if name else [track]
        for query in dict.fromkeys(queries):
            response = http.get(DEEZER + "/search", params={"q": query, "limit": 8})
            response.raise_for_status()
            for hit in (response.json().get("data") or [])[:8]:
                hit_artist = (hit.get("artist") or {}).get("name", "")
                if not fits(hit):
                    continue
                album = http.get(DEEZER + "/album/" + str(int(hit["album"]["id"])))
                album.raise_for_status()
                genres = [str(g.get("name"))[:40] for g in (album.json().get("genres") or {}).get("data", [])]
                cover = str((hit.get("album") or {}).get("cover_medium") or "")
                return {
                    "genres": genres[:5],
                    "cover": cover if cover.startswith("https://") and len(cover) < 500 else None,
                    "artist": hit_artist[:200],
                }
            time.sleep(0.1)
        # No such song on Deezer (a live take, a remix, a fan upload): the artist's own genre.
        for query in dict.fromkeys(f'artist:"{artist}"' for artist in (name, channel) if artist):
            response = http.get(DEEZER + "/search", params={"q": query, "limit": 8})
            response.raise_for_status()
            for hit in (response.json().get("data") or [])[:8]:
                hit_artist = (hit.get("artist") or {}).get("name", "")
                if not (same(hit_artist, name) or same(hit_artist, channel)):
                    continue
                album = http.get(DEEZER + "/album/" + str(int(hit["album"]["id"])))
                album.raise_for_status()
                genres = [str(g.get("name"))[:40] for g in (album.json().get("genres") or {}).get("data", [])]
                if genres:
                    return {
                        "genres": genres[:5],
                        "cover": None,
                        "artist": hit_artist[:200],
                        "by_artist": True,
                    }
            time.sleep(0.1)
        return {}
    finally:
        if client is None:
            http.close()


def youtube_thumbnail(url):
    """YouTube's own still for a video, from its address alone."""
    match = re.search(r"(?:v=|youtu\.be/|/shorts/)([A-Za-z0-9_-]{11})", url or "")
    return f"https://i.ytimg.com/vi/{match.group(1)}/hqdefault.jpg" if match else None


if __name__ == "__main__":
    assert genre_of({"genre": "Deep House"}) == "house / techno"
    assert genre_of({"tags": ["synthpop", "80s"]}) == "electro"
    assert genre_of({"title": "Charles Aznavour - Hier encore (Audio Officiel)"}) == "other"
    assert genre_of({"tags": ["chanson française"]}) == "chanson"
    assert genre_of({"title": "lofi hip hop radio - beats to relax"}) == "lo-fi"
    assert genre_of({"genre": "Hip-hop & Rap"}) == "rap / hip-hop"
    assert genre_of({"title": "Jujutsu Kaisen - Opening 2 | Full"}) == "anime"
    assert genre_of({"genres": ["Rap/Hip Hop", "French Rap"]}) == "rap / hip-hop"
    assert genre_of({"genres": ["Films/Games"]}) == "soundtrack"
    assert genre_of({"title": "Aimer - Zankyosanka"}, [{"name": "Anime", "words": ["aimer"]}]) == "Anime"
    assert artist_and_track("La Femme - Pasadena (Official Audio)") == ("La Femme", "Pasadena")
    assert artist_and_track("Séquelles", "So La Lune - Topic") == ("So La Lune", "Séquelles")
    assert artist_and_track("Superman", "EminemMusic") == ("Eminem", "Superman")
    assert artist_and_track("JuL - Toto et Ninetta // Clip officiel // 2018") == ("JuL", "Toto et Ninetta")
    assert genre_of({"title": "One Piece OP 7 - Crazy Rainbow"}) == "anime"
    assert genre_of({"title": "Nocturne Op. 9 No. 2"}) == "other"
    assert genre_of({"title": "90s90s Sommerhits"}) == "pop" and genre_of({"tags": ["news"]}) == "talk / news"
    assert same("Laylow", "LAYLOW") and not same("Pacifique", "So La Lune")
    # Everyday words in a title are not a genre; the same word in a tag still is.
    assert genre_of({"title": "Mark Knopfler - Sultans Of Swing"}) == "other"
    assert genre_of({"title": "Rock Your Body"}) == "other" and genre_of({"tags": ["swing"]}) == "jazz"
    assert artist_and_track("Yung Beef - Effy (Prod.Steve Lean) VIDEOCLIP") == ("Yung Beef", "Effy")
    assert artist_and_track("Velly Joonas \u200e- Stopp, Seisku Aeg!") == (
        "Velly Joonas",
        "Stopp, Seisku Aeg!",
    )
    assert youtube_thumbnail("https://www.youtube.com/watch?v=dQw4w9WgXcQ").endswith(
        "/dQw4w9WgXcQ/hqdefault.jpg"
    )
    print("ok")
