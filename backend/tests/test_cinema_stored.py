"""Watch loads rows side by side: a title saved twice at once must not fail the loser."""

from sqlalchemy.exc import IntegrityError, OperationalError

from houseos import cinema


class FakeSession:
    def __init__(self):
        self.commits = self.rollbacks = 0

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def test_stored_retries_after_a_duplicate_or_deadlock(monkeypatch):
    errors = [
        IntegrityError("insert", {}, Exception("dup")),
        OperationalError("insert", {}, Exception("deadlock")),
    ]

    def once(db, rows):
        if errors:
            raise errors.pop(0)
        return ["saved"]

    monkeypatch.setattr(cinema, "stored_once", once)
    monkeypatch.setattr(cinema.time, "sleep", lambda s: None)
    db = FakeSession()
    assert cinema.stored(db, []) == ["saved"]
    assert (db.rollbacks, db.commits) == (2, 1)


def test_rows_asking_at_once_load_the_index_once(monkeypatch, tmp_path):
    import threading
    import time

    from houseos import cinema_explore

    loads = []

    def slow_films():
        loads.append(1)
        time.sleep(0.2)
        return [{"kind": "movie", "title": "Heat"}, {"kind": "series", "title": "Arcane"}]

    monkeypatch.setattr(cinema_explore, "films", slow_films)
    monkeypatch.setattr(cinema_explore, "stamp", lambda kind: ("fixture", 1))
    monkeypatch.setattr(cinema_explore, "_loaded", {})
    rows = []
    threads = [threading.Thread(target=lambda: rows.append(cinema_explore.index("movie"))) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(loads) == 1 and all(r is rows[0] for r in rows) and rows[0][0]["title"] == "Heat"
