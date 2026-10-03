"""A new language: started by an admin (or Nox), translated in batches, then offered to all."""

import json

from sqlalchemy.orm import Session

from houseos import languages
from houseos.config import settings
from test_core import admin


def test_a_language_is_translated_in_batches_then_offered(client, tmp_path, monkeypatch):
    c, db = client
    admin(client)
    source = {"Hello": "Bonjour", "Playing {title}": "Lecture de {title}", "Groceries": "Courses"}
    (tmp_path / "ui-strings.json").write_text(json.dumps(source))
    monkeypatch.setattr(settings, "frontend_dist", tmp_path)
    monkeypatch.setattr(languages, "SessionLocal", lambda: Session(db.get_bind(), expire_on_commit=False))
    monkeypatch.setattr(languages, "BATCH_CHARACTERS", 20)  # one string per batch here
    monkeypatch.setattr(languages.time, "sleep", lambda _: None)
    asked = []

    def fake_ask(session, row, texts, pairs):
        asked.append(texts)
        # A lost placeholder keeps the English sentence (checked in ask); here: all translated.
        return {text: "PL " + text for text in texts}

    monkeypatch.setattr(languages, "ask", fake_ask)
    started = c.post("/api/v1/admin/languages", json={"code": "pl", "name": "Polski"})
    assert started.status_code == 200 and started.json()["state"] == "translating"
    assert c.patch("/api/v1/account/profile", json={"language": "pl"}).status_code == 422  # not ready
    languages.work("pl")
    assert len(asked) == 3
    listed = {x["code"]: x for x in c.get("/api/v1/languages").json()["items"]}
    assert listed["pl"]["state"] == "ready" and listed["pl"]["done"] == 3
    assert c.get("/api/v1/languages/pl/strings").json()["Playing {title}"] == "PL Playing {title}"
    assert c.patch("/api/v1/account/profile", json={"language": "pl"}).json()["language"] == "pl"


def test_placeholders_must_survive_the_translation():
    answer = 'Sure!\n```json\n{"1": "Odtwarzanie", "2": "Cześć"}\n```'
    assert languages.read_answer(answer, ["Playing {title}", "Hello"]) == {"Hello": "Cześć"}
