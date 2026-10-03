"""One interface: the page served, and a stored interface choice (`ui`) leaves stored data."""

import pytest

from houseos import house_settings, music
from houseos.config import settings
from houseos.models import Integration
from test_core import admin


@pytest.fixture
def dist(tmp_path, monkeypatch):
    new = tmp_path / "frontend"
    (new / "assets").mkdir(parents=True)
    (new / "art").mkdir()
    (new / "index.html").write_text('<div id="root">new</div>')
    (new / "sw.js").write_text("// new")
    (new / "assets/app-1.js").write_text("new code")
    monkeypatch.setattr(settings, "frontend_dist", new)
    return new


def test_one_page_whatever_the_old_cookie_says(client, dist):
    c, _ = client
    c.cookies.set("houseos-ui", "legacy")
    assert "new" in c.get("/listen").text and c.get("/sw.js").text == "// new"
    assert "new" in c.get("/?ui=legacy").text
    assert c.get("/assets/app-1.js").text == "new code"
    for missing in ("/assets/gone.js", "/assets-legacy/app-2.js", "/art/gone.png"):
        assert c.get(missing).status_code == 404  # never the page, which a cache would keep as code


def test_the_retired_ui_setting_leaves_the_stored_house_settings(client):
    import importlib.util
    from pathlib import Path

    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    _, db = client
    row = db.get(Integration, "house_settings") or Integration(name="house_settings", enabled=True)
    row.config = {**(row.config or {}), "ui": "legacy", "name": "Old House"}
    db.add(row)
    db.commit()
    path = Path(__file__).parents[1] / "migrations/versions/0008_house_settings_without_ui.py"
    spec = importlib.util.spec_from_file_location("house_settings_without_ui", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    for _ in range(2):  # safe to run twice
        with db.bind.connect() as connection, Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            connection.commit()
    db.expire_all()
    assert "ui" not in db.get(Integration, "house_settings").config
    assert house_settings.get_house_settings(db)["name"] == "Old House"


def test_a_form_that_sends_part_of_the_settings_keeps_the_rest(client, monkeypatch):
    c, db = client
    admin(client)
    calls = []
    monkeypatch.setattr(
        music, "bridge", lambda command, **kw: calls.append(command) or {"status": "configured"}
    )
    full = house_settings.HouseSettings(music_volume_cap=40, theme="base").model_dump()
    assert c.put("/api/v1/admin/house-settings", json=full).status_code == 200
    assert calls == ["volume_cap"]
    # A form sends only what it shows; the rest keeps its value.
    older = {key: value for key, value in full.items() if key != "theme"} | {"name": "Other House"}
    assert c.put("/api/v1/admin/house-settings", json=older).status_code == 200
    assert c.put("/api/v1/admin/house-settings", json={"motion": "still"}).status_code == 200
    saved = db.get(Integration, "house_settings").config
    assert (saved["theme"], saved["name"], saved["music_volume_cap"], saved["motion"]) == (
        "base",
        "Other House",
        40,
        "still",
    )
    assert calls == ["volume_cap"]  # unsent settings are not "changed" back to their defaults
