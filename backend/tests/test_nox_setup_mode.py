"""Nox setup mode: admins only, its own model, prompt and tools; tools reuse admin services.
Provider rounds are fixtures: no model is called and no service is restarted."""

import pytest
from fastapi import HTTPException

from houseos import assistant as a, assistant_profiles as profiles, tool_api, tool_code, tool_setup
from houseos.auth import RESIDENT, Actor
from houseos.cinema_models import CinemaDevice
from houseos.config import settings
from houseos.db import new_id
from houseos.models import Integration, Operation, Usage, User
from test_assistant_profiles import seed

SETUP_TOOL_NAMES = (
    set(tool_setup.TOOLS) | set(tool_api.TOOLS) | set(tool_code.TOOLS) | {"diagnostics_get_health"}
)


def resident(db):
    user = User(
        id=new_id(),
        username="Carol",
        name="Carol",
        role="resident",
        permissions=list(RESIDENT),
        password_hash="-",
    )
    db.add(user)
    db.commit()
    return Actor(user.id, "Carol", "resident", RESIDENT)


def fake_provider(monkeypatch, rounds, seen=None):
    """Each provider round returns the next (reply, calls); the request is recorded in `seen`."""
    monkeypatch.setattr(a, "integration_config", lambda d, p: {"api_key": "fixture", "model": "small"})

    def reserve(db, who, provider, cfg, messages, schemas):
        if seen is not None:
            seen.update(policy=cfg["_policy"], model=cfg["model"], tools={s["name"] for s in schemas})
        row = Usage(user_id=who.id, provider=provider, model=cfg["model"], reserved_microusd=1)
        db.add(row)
        db.commit()
        return row.id

    replies = iter(rounds)

    def provider_round(provider, cfg, messages, schemas):
        reply, calls = next(replies)
        wire = {
            "role": "assistant",
            "content": reply,
            "tool_calls": [
                {"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": "{}"}}
                for c in calls
            ],
        }
        return reply, calls, wire, {"input_tokens": 1, "output_tokens": 1}

    monkeypatch.setattr(a, "reserve", reserve)
    monkeypatch.setattr(a, "provider_round", provider_round)


def chat(actor, db, message="Help me set up the house", **fields):
    return a.chat(a.Chat(message=message, purpose="setup", idempotency_key=new_id(), **fields), actor, db)


def test_setup_mode_is_refused_to_residents(setup):
    db, _ = setup
    seed(db)
    carol = resident(db)
    for attempt in (
        lambda: chat(carol, db),
        lambda: a.create_conversation(a.NewConversation(title="Setup", purpose="setup"), carol, db),
        lambda: a.status(carol, db, purpose="setup"),
    ):
        with pytest.raises(HTTPException) as refused:
            attempt()
        assert refused.value.status_code == 403
    assert a.status(carol, db, purpose="general")["purpose"] == "general"


def test_setup_model_assignment_falls_back_then_is_its_own(setup):
    db, (alice, _) = setup
    seed(db)
    assert profiles.assignment(db, "setup")["model"] == "small"  # first working connection
    profiles.save("setup", profiles.Assignment(provider="openrouter", model="large"), alice, db)
    assert profiles.assignment(db, "setup")["model"] == "large"
    assert profiles.assignment(db, "general")["model"] == "small"
    assert [row["purpose"] for row in profiles.profiles(alice, db)["items"]] == [
        "general",
        "personal_space",
        "setup",
        "themes",
    ]


def test_setup_conversation_uses_its_model_prompt_and_tools(setup, quiet, monkeypatch):
    db, (alice, _) = setup
    seed(db)
    profiles.save("setup", profiles.Assignment(provider="openrouter", model="large"), alice, db)
    seen = {}
    fake_provider(monkeypatch, [("Let's start with the checklist.", [])], seen)
    result = chat(alice, db)
    assert result["reply"] == "Let's start with the checklist."
    assert seen["model"] == "large" and seen["policy"] == a.system_prompt("setup")
    assert "setup_checklist" in seen["policy"] and "Nox has no shell" in seen["policy"]
    assert seen["tools"] == SETUP_TOOL_NAMES  # no switch_context: the mode keeps its tools
    assert len(a.conversations(alice, db, purpose="setup")) == 1
    assert a.conversations(alice, db, purpose="general") == []
    with pytest.raises(HTTPException) as moved:
        a.chat(
            a.Chat(message="play music", conversation_id=result["conversation_id"], idempotency_key=new_id()),
            alice,
            db,
        )
    assert moved.value.status_code == 409


def test_setup_bundle_is_admin_tools_only():
    tools = a.tool_registry("setup")
    assert set(tools) == SETUP_TOOL_NAMES
    assert "switch_context" in a.tool_registry("general")
    assert not SETUP_TOOL_NAMES & set(a.tool_registry("general"))


@pytest.mark.parametrize("name", sorted(tool_setup.TOOLS))
def test_every_setup_tool_checks_the_admin_role(setup, name):
    db, _ = setup
    carol = resident(db)
    with pytest.raises(HTTPException) as refused:
        tool_setup.TOOLS[name][2](None, carol, db)
    assert refused.value.status_code == 403


def test_devices_find_waits_for_the_scan_row(setup, monkeypatch):
    db, (alice, _) = setup
    import houseos.music_outputs as outputs

    monkeypatch.setattr(outputs, "relay_base_url", lambda db=None: "http://relay")
    waits = []

    def relay_answers(seconds):  # the relay writes its answer while Nox waits
        waits.append(seconds)
        row = db.get(Integration, "device_discovery")
        row.config = {
            **row.config,
            "scanned_for": row.config["requested_at"],
            "devices": [
                {"kind": "tv", "name": "Living room TV", "address": "192.168.1.20"},
                {"kind": "airplay", "name": "Kitchen", "address": "192.0.2.19"},
                {"kind": "home_assistant", "name": "Home", "url": "http://192.0.2.13:8123"},
            ],
            "problem": None,
        }
        db.commit()

    monkeypatch.setattr(tool_setup.time, "sleep", relay_answers)
    tools = tool_setup.TOOLS
    found = tools["devices_find"][2](None, alice, db)
    assert waits == [1] and found["status"] == "completed"
    assert found["devices"][0] == {
        "kind": "tv",
        "name": "Living room TV",
        "address": "192.168.1.20",
        "added": False,
    }
    assert found["devices"][2]["url"] == "http://192.0.2.13:8123"

    added = tools["device_add"][2](tool_setup.DeviceAdd(address="192.168.1.20"), alice, db)
    assert added["status"] == "completed" and added["card"]["href"] == "/control?tab=devices"
    assert db.query(CinemaDevice).one().adapter == "cast"
    again = tools["device_add"][2](tool_setup.DeviceAdd(address="192.168.1.20"), alice, db)
    assert again["already_added"] and db.query(CinemaDevice).count() == 1
    other = tools["device_add"][2](tool_setup.DeviceAdd(address="192.0.2.19"), alice, db)
    assert other["status"] == "unsupported" and other["kind"] == "airplay"

    monkeypatch.setattr(tool_setup, "SCAN_WAIT", 0)
    monkeypatch.setattr(tool_setup.time, "sleep", lambda seconds: pytest.fail("no wait past the deadline"))
    assert tools["devices_find"][2](None, alice, db)["status"] == "still_scanning"


def test_devices_find_says_when_no_scanner_runs(setup, monkeypatch):
    db, (alice, _) = setup
    import houseos.music_outputs as outputs

    monkeypatch.setattr(outputs, "relay_base_url", lambda db=None: "")
    assert tool_setup.TOOLS["devices_find"][2](None, alice, db)["status"] == "scanner_off"
    assert db.get(Integration, "device_discovery") is None  # no request left waiting


def test_service_restart_becomes_a_confirmation_card(setup, monkeypatch, tmp_path):
    db, (alice, _) = setup
    seed(db)
    monkeypatch.setattr(settings, "storage_container", True)
    monkeypatch.setattr(settings, "runtime_root", tmp_path)
    call = {"id": "c1", "name": "service_restart", "args": {"name": "worker"}}
    fake_provider(monkeypatch, [("", [call])])
    result = chat(alice, db, message="The worker is down, restart it")
    card = result["cards"][0]
    operation = db.get(Operation, card["confirmation_id"])
    assert result["status"] == "needs_confirmation"
    assert card["confirmation_path"] == "/admin/services/confirmations/" + operation.id
    assert card["label"] == "Restart a HouseOS service" and card["preview"]["service"] == "worker"
    assert operation.kind == "service.restart" and operation.state == "needs_confirmation"
    assert not (tmp_path / "run" / "restart").exists()  # nothing restarts before the tap


def test_cast_speaker_choice_is_confirmed_by_the_admin(setup, monkeypatch):
    db, (alice, _) = setup
    import houseos.audio_admin as audio_admin

    monkeypatch.setattr(audio_admin, "bridge", lambda *a, **k: {"status": "configured"})
    device = CinemaDevice(id=new_id(), name="Kitchen speaker", adapter="cast", address="192.0.2.21")
    db.add(device)
    db.commit()
    choice = tool_setup.SpeakerChoice(cast_device_id=device.id)
    prepared = tool_setup.TOOLS["speaker_choose"][2](choice, alice, db)
    assert prepared["status"] == "needs_confirmation"
    assert prepared["confirmation_path"] == "/assistant/confirmations/" + prepared["confirmation_id"]
    assert prepared["preview"]["name"] == "Kitchen speaker"
    assert a.confirm_message(prepared["confirmation_id"], alice, db) == {
        "status": "configured",
        "device_id": device.id,
    }
    with pytest.raises(HTTPException):  # consumed
        a.confirm_message(prepared["confirmation_id"], alice, db)
    listed = tool_setup.TOOLS["speakers_list"][2](None, alice, db)
    assert listed["selected_cast_device_id"] == device.id
    assert {"id": device.id, "name": "Kitchen speaker", "adapter": "cast"} in listed["cast_devices"]


def test_open_settings_links_to_the_integration_dialog(setup):
    db, (alice, _) = setup
    opened = tool_setup.TOOLS["open_settings"][2](
        tool_setup.SettingsScreen(tab="integrations", open="jellyfin"), alice, db
    )
    assert opened["href"] == "/control?tab=integrations&open=jellyfin"
    assert opened["card"]["domain"] == "setup" and opened["card"]["href"] == opened["href"]
    assert opened["card"]["detail"] == "Control Room → Integrations → Jellyfin"
    ai = tool_setup.TOOLS["open_settings"][2](tool_setup.SettingsScreen(tab="ai"), alice, db)
    assert ai["href"] == "/control?tab=ai"
    with pytest.raises(ValueError):  # AI keys have their own tab, not an integration dialog
        tool_setup.SettingsScreen(tab="integrations", open="openrouter")


def test_invitations_are_made_on_screen_never_in_chat():
    # An invitation link is a sign-up credential: Nox opens the Invitations screen instead.
    assert "invite_create" not in tool_setup.TOOLS


def test_checklist_reads_a_trusted_https_address_as_secure(setup, quiet):
    db, (alice, _) = setup
    checklist = tool_setup.TOOLS["setup_checklist"][2]
    steps = {s["key"]: s for s in checklist(None, alice, db)["steps"]}
    assert steps["access"]["state"] == "todo" and steps["access"]["essential"]
    db.add(Integration(name="access", enabled=True, config={"origins": ["https://house.lan:8443"]}))
    db.commit()
    steps = {s["key"]: s for s in checklist(None, alice, db)["steps"]}
    assert steps["access"]["state"] == "done"


def test_services_status_names_the_compose_service(setup, quiet):
    db, (alice, _) = setup
    found = tool_setup.TOOLS["services_status"][2](None, alice, db)
    rows = {row["name"]: row for row in found["services"]}
    assert found["docker"] and rows["media"]["compose_service"] == "relay"
    assert rows["worker"]["status"] == "off"  # measured: no heartbeat yet


def test_setup_mode_knows_games(setup, monkeypatch):
    from houseos import games

    db, (alice, _) = setup
    tools = tool_setup.TOOLS
    status = tools["games_status"][2](None, alice, db)
    assert status["consoles"]["ps2"]["bios"] == {"pcsx2/bios/scph39001.bin": False}
    assert not status["consoles"]["ps2"]["in_browser"] and status["consoles"]["ps2"]["on_tv"]
    with pytest.raises(HTTPException) as refused:  # the loop turns it into {status, code, detail}
        tools["game_link_add"][2](tool_setup.GameLink(url="http://example.com/a.iso"), alice, db)
    assert refused.value.detail["code"] == "GAME_LINK_INVALID"
    started = []
    monkeypatch.setattr(games, "download", started.append)
    added = tools["game_link_add"][2](
        tool_setup.GameLink(url="https://example.com/games/My%20Game.iso", system="ps2"), alice, db
    )
    assert added["status"] == "accepted" and added["card"]["href"] == "/games?game=" + added["id"]
    assert added["card"]["status"] == "accepted"
    row = games.game_row(db, added["id"])
    assert (row.data["title"], row.data["state"], row.data["system"]) == ("My Game.iso", "downloading", "ps2")
    opened = tools["games_open"][2](tool_setup.GamesScreen(sheet="setup"), alice, db)
    assert opened["href"] == "/games?sheet=setup"
