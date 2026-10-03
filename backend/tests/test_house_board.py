"""The House board's lists (to do / done / recurring, to buy / bought) and conversations."""

from houseos import household
from houseos.auth import Actor, RESIDENT
from houseos.db import new_id
from houseos.models import User
from test_core import admin


def add(c, kind, data):
    response = c.post("/api/v1/household/" + kind, json={"data": data, "idempotency_key": new_id()})
    assert response.status_code == 201, response.text
    return response.json()


def ids(c, url):
    return [r["id"] for r in c.get(url).json()["items"]]


def test_tasks_move_to_done_and_back_groceries_to_bought(client):
    c, db = client
    admin(client)
    later = add(c, "tasks", {"title": "Later", "due_date": "2026-12-01"})
    soon = add(c, "tasks", {"title": "Soon", "due_date": "2026-10-01"})
    add(c, "tasks", {"title": "Bins", "due_date": "2026-10-01", "recurrence": "weekly"})
    assert ids(c, "/api/v1/household/tasks?state=open")[:2] == [soon["id"], later["id"]]
    assert len(ids(c, "/api/v1/household/tasks?state=recurring")) == 1
    done = c.post(
        f"/api/v1/household/tasks/{soon['id']}/action",
        json={"version": soon["version"], "action": "complete"},
    ).json()
    assert soon["id"] not in ids(c, "/api/v1/household/tasks?state=open")
    assert ids(c, "/api/v1/household/tasks?state=done") == [soon["id"]]
    reopened = c.post(
        f"/api/v1/household/tasks/{soon['id']}/action", json={"version": done["version"], "action": "reopen"}
    ).json()
    assert reopened["data"]["status"] == "open" and reopened["data"]["completed_at"] is None
    # A repeating task's copy due next month waits out of To do; this week's shows.
    from datetime import date, timedelta
    from houseos.models import Record

    me = db.query(User).first()
    for days, title in ((30, "Far copy"), (2, "Near copy")):
        due = (date.today() + timedelta(days=days)).isoformat()
        data = {"title": title, "status": "open", "template_id": "t1", "due_date": due}
        db.add(Record(kind="household.tasks", owner_id=me.id, visibility="house", data=data))
    db.commit()
    titles = [r["data"]["title"] for r in c.get("/api/v1/household/tasks?state=open").json()["items"]]
    assert "Near copy" in titles and "Far copy" not in titles
    milk = add(c, "groceries", {"label": "Milk"})
    c.patch(
        f"/api/v1/household/groceries/{milk['id']}",
        json={"version": milk["version"], "data": {"purchased": True}},
    )
    assert ids(c, "/api/v1/household/groceries?state=bought") == [milk["id"]]
    assert ids(c, "/api/v1/household/groceries?state=open") == []


def test_calendar_occurrences_say_who_owns_them(client):
    c, db = client
    me = admin(client)
    add(c, "calendar", {"title": "Dinner", "all_day": True, "start": "2026-10-02", "end": "2026-10-03"})
    item = c.get("/api/v1/household/calendar/agenda?start=2026-10-01&end=2026-10-03").json()["items"][0]
    assert item["owner_id"] == me["id"] and item["visibility"] == "house"


def test_conversations_group_by_people_and_page_back(client):
    c, db = client
    me = admin(client)
    iris = User(
        id=new_id(),
        name="Iris",
        username="iris",
        password_hash="x",
        role="resident",
        permissions=list(RESIDENT),
    )
    milo = User(
        id=new_id(),
        name="Milo",
        username="milo",
        password_hash="x",
        role="resident",
        permissions=list(RESIDENT),
    )
    db.add_all([iris, milo])
    db.commit()
    for n in range(3):
        add(c, "messages", {"body": f"hi {n}", "recipient_ids": [iris.id]})
    add(c, "messages", {"body": "group", "recipient_ids": [iris.id, milo.id]})
    household.create_record(
        db,
        Actor(iris.id, "Iris", "resident", frozenset(RESIDENT)),
        "messages",
        household.CreateRecord(data={"body": "reply", "recipient_ids": [me["id"]]}, idempotency_key=new_id()),
    )
    # One message per minute, in the order written (the database keeps whole seconds).
    from datetime import datetime, timedelta
    from houseos.models import Record

    rows = db.query(Record).filter(Record.kind == "household.messages").all()
    order = ["hi 0", "hi 1", "hi 2", "group", "reply"]
    for row in rows:
        row.created_at = datetime(2026, 10, 1) + timedelta(minutes=order.index(row.data["body"]))
    db.commit()
    talks = c.get("/api/v1/household/conversations").json()["items"]
    assert [len(t["people"]) for t in talks] == [2, 3]  # latest exchange first
    pair = talks[0]
    assert pair["count"] == 4 and pair["unread"] == 1 and pair["last"]["data"]["body"] == "reply"
    first = c.get(f"/api/v1/household/conversations/{pair['key']}?limit=3").json()
    assert [m["data"]["body"] for m in first["items"]] == ["reply", "hi 2", "hi 1"]
    rest = c.get(
        f"/api/v1/household/conversations/{pair['key']}?limit=3&before={first['next_before']}"
    ).json()
    assert [m["data"]["body"] for m in rest["items"]] == ["hi 0"] and rest["next_before"] is None
    assert c.get("/api/v1/household/conversations").json()["items"][0]["unread"] == 0


def test_library_sorts_and_filters_by_genre_person_and_type(client):
    from houseos.cinema_models import CinemaTitle
    from houseos.models import Record
    from houseos.music import history_key

    c, db = client
    me = admin(client)
    iris = User(id=new_id(), name="Iris", username="iris", password_hash="x", role="resident")
    db.add(iris)
    db.commit()
    songs = {
        "rock": "https://www.youtube.com/watch?v=aaaaaaaaaaa",
        "jazz": "https://www.youtube.com/watch?v=bbbbbbbbbbb",
    }
    from houseos.music_downloads import identity

    for genre, url in songs.items():
        download = {"state": "ready", "source_url": url, "title": genre.title() + " song"}
        db.add(
            Record(
                id=identity(url), kind="music.download", owner_id=me["id"], visibility="house", data=download
            )
        )
        history = {"source_url": url, "genre": genre, "plays": 3 if genre == "jazz" else 1}
        db.add(
            Record(
                id=history_key(url), kind="music.history", owner_id=me["id"], visibility="house", data=history
            )
        )
    db.add(
        Record(
            kind="music.play", owner_id=iris.id, visibility="house", data={"key": history_key(songs["jazz"])}
        )
    )
    anime = CinemaTitle(
        canonical_id="mal:1", title="Cowboy Bebop", kind="series", data={"year": 1998, "genres": ["Sci-Fi"]}
    )
    film = CinemaTitle(
        canonical_id="tt1", title="Heat", kind="movie", data={"year": 1995, "genres": ["Crime"]}
    )
    db.add_all([anime, film])
    db.flush()
    for title in (anime, film):
        db.add(
            Record(
                kind="cinema.local_media",
                owner_id=me["id"],
                visibility="house",
                data={"state": "ready", "media_id": title.id},
            )
        )
    db.commit()
    music = c.get("/api/v1/files/library?kind=music&sort=title").json()
    assert [i["title"] for i in music["items"]] == ["Jazz song", "Rock song"]
    assert c.get(f"/api/v1/files/library?kind=music&by={iris.id}").json()["total"] == 1
    assert [i["title"] for i in c.get("/api/v1/files/library?kind=music&genre=jazz").json()["items"]] == [
        "Jazz song"
    ]
    assert c.get("/api/v1/files/library?kind=music&sort=plays").json()["items"][0]["plays"] == 3
    films = c.get("/api/v1/files/library?kind=movies&sort=year").json()
    assert [(i["title"], i["type"]) for i in films["items"]] == [("Cowboy Bebop", "anime"), ("Heat", "film")]
    assert films["facets"]["types"] == {"anime": 1, "film": 1}
    assert c.get("/api/v1/files/library?kind=movies&genre=Crime").json()["items"][0]["title"] == "Heat"


def test_kept_songs_and_saved_films_can_be_deleted_by_whoever_kept_them(client, tmp_path, monkeypatch):
    import pytest
    from fastapi import HTTPException
    from houseos import storage_admin
    from houseos.config import settings
    from houseos.models import Record

    c, db = client
    me = admin(client)
    iris = User(id=new_id(), name="Iris", username="iris", password_hash="x", role="resident")
    db.add(iris)
    monkeypatch.setattr(settings, "data_root", tmp_path)
    monkeypatch.setattr(storage_admin, "storage_check", lambda: {"status": "healthy"})
    (tmp_path / "music-downloads").mkdir()
    (tmp_path / "media/movies").mkdir(parents=True)
    song = Record(id=new_id(), kind="music.download", owner_id=me["id"], visibility="house", data={})
    song.data = {"state": "ready", "title": "Song", "path": f"music-downloads/{song.id}.media"}
    (tmp_path / "music-downloads" / (song.id + ".media")).write_bytes(b"audio")
    film_path = tmp_path / "media/movies/Heat-1.mkv"
    film_path.write_bytes(b"video")
    film = Record(
        kind="cinema.local_media",
        owner_id=iris.id,
        visibility="house",
        data={"state": "ready", "_path": str(film_path)},
    )
    db.add_all([song, film])
    db.commit()
    listed = c.get("/api/v1/files/library?kind=music").json()["items"]
    assert listed[0]["can_delete"] and listed[0]["version"] == 1
    assert c.delete(f"/api/v1/files/library/music/{song.id}?version=1").json() == {"status": "completed"}
    assert not (tmp_path / "music-downloads" / (song.id + ".media")).exists()
    assert c.get("/api/v1/files/library?kind=music").json()["total"] == 0
    resident = Actor(new_id(), "Theo", "resident", RESIDENT)
    with pytest.raises(HTTPException) as refused:
        storage_admin.delete_kept("movies", film.id, 1, resident, db)
    assert refused.value.status_code == 403 and film_path.exists()
    assert c.delete(f"/api/v1/files/library/movies/{film.id}?version=1").status_code == 200  # an admin may
    assert not film_path.exists()


def test_a_queued_song_is_deleted_from_the_house_and_the_playing_one_plays_on(client, tmp_path, monkeypatch):
    from houseos import storage_admin, worker
    from houseos.config import settings
    from houseos.models import Record
    from houseos.music import QueueItem, QueueState
    from houseos.music_downloads import identity

    c, db = client
    me = admin(client)
    monkeypatch.setattr(settings, "data_root", tmp_path)
    monkeypatch.setattr(storage_admin, "storage_check", lambda: {"status": "healthy"})
    monkeypatch.setattr(worker, "fetch", lambda *a, **k: {"status": "completed"})
    monkeypatch.setattr("houseos.music.bridge", lambda *a, **k: {"status": "unavailable"})
    (tmp_path / "music-downloads").mkdir()
    urls = ["https://www.youtube.com/watch?v=aaaaaaaaaaa", "https://www.youtube.com/watch?v=bbbbbbbbbbb"]
    songs = []
    for url in urls:
        key = identity(url)
        (tmp_path / "music-downloads" / (key + ".media")).write_bytes(b"audio")
        path = f"music-downloads/{key}.media"
        db.add(
            Record(
                id=key,
                kind="music.download",
                owner_id=me["id"],
                visibility="house",
                data={"state": "ready", "path": path},
            )
        )
        songs.append(
            QueueItem(id=new_id(), source_url=url, owner_id=me["id"], title=url[-3:], position=len(songs) + 1)
        )
    playing, waiting = songs
    playing.status, waiting.status = "playing", "ready"
    db.add_all(songs)
    db.get(QueueState, 1).current_id = playing.id
    db.commit()
    kept = {row["id"]: row["kept_by"] for row in c.get("/api/v1/music").json()["items"]}
    assert kept == {playing.id: me["id"], waiting.id: me["id"]}
    assert c.delete(f"/api/v1/music/queue/{playing.id}/kept").json()["left_queue"] is False
    assert c.delete(f"/api/v1/music/queue/{waiting.id}/kept").json()["left_queue"] is True
    assert not list((tmp_path / "music-downloads").iterdir())
    db.expire_all()
    assert (db.get(QueueItem, playing.id).status, db.get(QueueItem, waiting.id).status) == (
        "playing",
        "removed",
    )
    assert c.delete(f"/api/v1/music/queue/{playing.id}/kept").status_code == 404  # already gone
