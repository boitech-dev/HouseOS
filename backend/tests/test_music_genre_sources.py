"""Where a song's genre comes from: Deezer's for the song, else its artist's, MusicBrainz's when
only the artist's is known (finer) or Deezer has none. Network answers are faked here."""

from types import SimpleNamespace

from houseos import music_genre
from houseos.music_catalog import evidence_for
from houseos.music_genre import genre_of


class FakeHttp:
    """Answers by address; records what was asked."""

    def __init__(self, deezer_album_genres, deezer_artist_genres, musicbrainz_tags):
        self.asked = []
        self.album, self.artist, self.tags = deezer_album_genres, deezer_artist_genres, musicbrainz_tags

    def get(self, url, params=None, headers=None):
        self.asked.append(url)
        if "musicbrainz" in url:
            body = {"artists": [{"name": "Arat Kilo", "score": 100, "tags": self.tags}]}
        elif "/search" in url and "track:" in (params or {}).get("q", ""):
            body = {"data": [{"title": "Dia Barani", "artist": {"name": "Arat Kilo"}, "album": {"id": 1}}]}
        elif "/search" in url:
            body = {"data": [{"title": "Other song", "artist": {"name": "Arat Kilo"}, "album": {"id": 2}}]}
        else:
            genres = self.album if url.endswith("/1") else self.artist
            body = {"genres": {"data": [{"name": g} for g in genres]}}
        return SimpleNamespace(json=lambda: body, raise_for_status=lambda: None)


def look(http):
    return evidence_for(None, "https://www.youtube.com/watch?v=x", None, True, http, {
        "title": "Dia Barani", "uploader": "Arat Kilo",
    })  # fmt: skip


def test_the_song_s_own_genre_comes_first(monkeypatch):
    monkeypatch.setattr(music_genre.time, "sleep", lambda s: None)
    http = FakeHttp(["Jazz"], ["Pop"], [{"name": "ethio-jazz", "count": 1}])
    found = look(http)
    assert genre_of(found, ()) == "jazz" and not any("musicbrainz" in u for u in http.asked)


def test_an_album_without_genre_uses_the_artist_and_musicbrainz_is_finer(monkeypatch):
    monkeypatch.setattr(music_genre.time, "sleep", lambda s: None)
    # Deezer: the song's album has no genre, the artist's other album says "Pop";
    # MusicBrainz's community says ethio-jazz: that one is kept.
    http = FakeHttp([], ["Pop"], [{"name": "jazz", "count": 1}, {"name": "ethio-jazz", "count": 2}])
    found = look(http)
    assert found["genres"] == ["ethio-jazz", "jazz"] and genre_of(found, ()) == "jazz"
    # MusicBrainz doesn't know the artist: Deezer's artist genre stays.
    found = look(FakeHttp([], ["Pop"], []))
    assert found["genres"] == ["Pop"]
    # Nobody knows: no genre (the song stays "other", never a guess).
    assert not look(FakeHttp([], [], [])).get("genres")


def test_musicbrainz_busy_keeps_deezer_s_artist_genre_and_nothing_known_is_asked_again(monkeypatch):
    import httpx
    import pytest

    monkeypatch.setattr(music_genre.time, "sleep", lambda s: None)

    class Busy(FakeHttp):
        def get(self, url, params=None, headers=None):
            if "musicbrainz" in url:
                raise httpx.ConnectError("busy")
            return super().get(url, params, headers)

    assert look(Busy([], ["Pop"], []))["genres"] == ["Pop"]  # Deezer's artist genre stands
    with pytest.raises(httpx.HTTPError):  # nothing known: the lookup is tried again later
        look(Busy([], [], []))
