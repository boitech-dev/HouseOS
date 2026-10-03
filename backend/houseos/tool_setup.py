"""House-setup tools for Nox's admin-only setup mode.

Each tool calls the same service the Control Room screens use; nothing here runs a shell or
Docker command. Changes that need a confirmation return the existing confirmation card."""

import time
from datetime import timedelta
from types import SimpleNamespace
from typing import Literal

from fastapi import HTTPException
from pydantic import Field
from sqlalchemy import select

from .auth import Input, require_admin
from .config import settings
from .control_room import CONTAINER_RESTARTS, SERVICES
from .db import utcnow
from .integrations import AI_PROVIDERS, NAMES
from .languages import NewLanguage
from .models import Integration, Operation

SCAN_WAIT = 10  # seconds devices_find waits for the media relay's scan (about 6 s)
CAST_KINDS = {"tv", "audio", "group", "cast"}
INTEGRATIONS = tuple(sorted(NAMES - {"music", "budgets"}))
DIALOGS = tuple(sorted(set(INTEGRATIONS) - {"cast", *AI_PROVIDERS}))  # AI has its own tab
TABS = (
    "setup",
    "health",
    "house",
    "access",
    "services",
    "speakers",
    "devices",
    "ai",
    "integrations",
    "invites",
    "users",
    "storage",
    "recovery",
)


class Empty(Input):
    pass


class ServiceName(Input):
    name: Literal[tuple(sorted(set(SERVICES) | CONTAINER_RESTARTS))]


class DeviceAdd(Input):
    address: str = Field(min_length=1, max_length=64, description="Address from devices_find.")
    name: str | None = Field(default=None, max_length=100)


class SpeakerChoice(Input):
    output: str | None = Field(default=None, max_length=256, description="A computer output id.")
    cast_device_id: str | None = Field(default=None, max_length=36)


class IntegrationName(Input):
    name: Literal[INTEGRATIONS]


class SettingsScreen(Input):
    tab: Literal[TABS]
    open: Literal[DIALOGS] | None = Field(default=None, description="Integration dialog to open.")


class Origin(Input):
    origin: str = Field(min_length=8, max_length=200)


def browser(db):
    """The checklist and Access ask how the browser reached HouseOS. A tool call has no browser
    request, so a trusted https:// address stands in for "reached over HTTPS"."""
    from .access import ENV_ORIGINS

    row = db.get(Integration, "access")
    origins = ENV_ORIGINS | set((row.config or {}).get("origins", []) if row else [])
    secure = any(origin.startswith("https://") for origin in origins)
    return SimpleNamespace(url=SimpleNamespace(scheme="https" if secure else "http"), headers={})


def checklist(body, actor, db):
    from .house_setup import ESSENTIAL, setup

    result = setup(browser(db), actor, db)
    for step in result["steps"]:
        step["essential"] = step["key"] in ESSENTIAL
    return {
        "status": "completed",
        **result,
        "note": "access is judged from the trusted addresses: done when an https:// one is trusted",
    }


def services_status(body, actor, db):
    from .config import settings
    from .control_room import services
    from .house_setup import SERVICES as PROBED

    rows = services(actor, db)
    if settings.storage_container:  # for `docker compose logs <compose_service>`
        compose = {name: service for name, service, _ in PROBED}
        rows = [{**row, "compose_service": compose.get(row["name"])} for row in rows]
    return {"status": "completed", "docker": settings.storage_container, "services": rows}


def service_restart(body, actor, db):
    from .control_room import Action, prepare

    result = prepare(body.name, Action(), actor, db)
    return {
        **result,
        "label": "Restart a HouseOS service",
        "confirmation_path": "/admin/services/confirmations/" + result["confirmation_id"],
    }


class NewVersion(Input):
    apply: bool = Field(default=False, description="true: prepare the update (a confirmation card)")


def house_update(body, actor, db):
    from .config import settings
    from .house_actions import Request, available, helper_alive, prepare, update_config

    if not settings.storage_container:
        return {"status": "unavailable", "detail": "Not the Docker install: it is updated on the server."}
    found = available()
    if not body.apply or not found:
        return {
            "status": "completed",
            "update_available": bool(found),
            "current": found[0] if found else None,
            "latest": found[1] if found else None,
            "updates_by_itself_at_night": bool(update_config(db).get("auto")),
            "control_room_buttons": helper_alive(),
        }
    result = prepare("update", Request(), actor, db)
    return {
        **result,
        "label": "Update HouseOS",
        "confirmation_path": "/admin/house-actions/confirm/" + result["confirmation_id"],
    }


def devices_find(body, actor, db):
    from .cinema_models import CinemaDevice
    from .discovery import request_scan, scan_result

    if not scan_result(actor, db)["scanner_running"]:
        return {"status": "scanner_off", "detail": "The media relay runs scans; it is not answering."}
    request_scan(actor, db)
    deadline = time.monotonic() + SCAN_WAIT
    while True:
        db.rollback()  # end the transaction so the relay's answer is visible
        found = scan_result(actor, db)
        if not found["scanning"] or time.monotonic() >= deadline:
            break
        time.sleep(1)
    added = set(db.scalars(select(CinemaDevice.address)))
    return {
        "status": "still_scanning" if found["scanning"] else "completed",
        "problem": found["problem"],
        "devices": [
            {
                **{
                    key: device[key] for key in ("kind", "name", "address", "url", "model") if device.get(key)
                },
                "added": device.get("address") in added,
            }
            for device in found["devices"][:30]
        ],
    }


def device_add(body, actor, db):
    from .cinema import create_device
    from .cinema_models import CinemaDevice, DeviceInput
    from .discovery import scan_result

    device = next((d for d in scan_result(actor, db)["devices"] if d.get("address") == body.address), None)
    if not device:
        return {"status": "not_found", "detail": "Not in the latest scan; run devices_find first."}
    if device.get("kind") not in CAST_KINDS:
        return {
            "status": "unsupported",
            "kind": device.get("kind"),
            "supported": "Cast devices only (Chromecast, Google TV, Android TV, Cast speakers)",
            "integration": device.get("kind") if device.get("kind") in INTEGRATIONS else None,
        }
    existing = db.scalar(
        select(CinemaDevice).where(CinemaDevice.adapter == "cast", CinemaDevice.address == body.address)
    )
    if existing:
        return {"status": "completed", "already_added": True, "id": existing.id, "name": existing.name}
    created = create_device(
        DeviceInput(
            name=(body.name or device.get("name") or body.address)[:100],
            adapter="cast",
            address=body.address,
            capabilities={},
        ),
        actor,
        db,
    )
    return {
        "status": "completed",
        "id": created["id"],
        "name": created["name"],
        "card": card("Device added", created["name"], "/control?tab=devices"),
    }


def speakers_list(body, actor, db):
    from .audio_admin import status

    found = status(actor, db)
    return {
        "status": "completed",
        "audio_service": found.get("status", "ok"),
        "sound_server": found.get("sound_server"),
        "outputs": [{"id": o["id"], "name": o.get("name")} for o in found.get("items", [])],
        "selected_output": found.get("selected"),
        "heard_by_someone": found.get("physical_verified"),
        "cast_devices": found["devices"],
        "selected_cast_device_id": found["device_id"],
    }


def speaker_choose(body, actor, db):
    if bool(body.output) == bool(body.cast_device_id):
        raise HTTPException(422, "Choose either a computer output or a Cast device")
    label = "Choose where music plays"
    if body.output:
        from .audio_admin import Prepare, prepare
        from .music import bridge

        result = prepare(Prepare(action="select", sink=body.output), actor, db)
        names = {o["id"]: o.get("name") for o in bridge("outputs").get("items", [])}
        result["preview"] = {
            "name": names.get(body.output, body.output),
            "effect": result["preview"]["effect"],
        }
        return {
            **result,
            "label": label,
            "confirmation_path": "/admin/audio/confirm/" + result["confirmation_id"],
        }
    from .cinema_models import CinemaDevice

    device = db.get(CinemaDevice, body.cast_device_id)
    if not device or device.adapter != "cast":
        raise HTTPException(404, "Choose a Cast device from speakers_list")
    return confirmation(
        actor,
        db,
        "assistant.cast_output",
        {"device_id": device.id},
        label,
        {"name": device.name, "effect": "Music plays on this Cast device; this computer goes quiet"},
    )


def confirmation(
    actor, db, kind, data, label, preview, ttl=timedelta(seconds=120), path="/assistant/confirmations/"
):
    """A card the person taps; assistant.confirm_message carries it out (nothing runs before)."""
    op = Operation(
        actor_id=actor.id,
        kind=kind,
        state="needs_confirmation",
        data=data,
        expires_at=utcnow() + ttl,
    )
    db.add(op)
    db.commit()
    return {
        "status": "needs_confirmation",
        "confirmation_id": op.id,
        "confirmation_path": path + op.id,
        "label": label,
        "preview": preview,
    }


def integration_status(body, actor, db):
    from .integrations import list_integrations

    return {
        "status": "completed",
        "items": [
            {key: row[key] for key in ("name", "enabled", "configured", "has_secret", "status")}
            for row in list_integrations(actor, db)
            if row["name"] in INTEGRATIONS
        ],
    }


def integration_test(body, actor, db):
    from .integrations import test_integration

    result = test_integration(body.name, actor, db)
    for key in ("users", "players"):  # choices for the settings screen; a few are enough here
        if key in result:
            result[key] = result[key][:20]
    return {"status": "completed", "test": result}


def open_settings(body, actor, db):
    tab = "integrations" if body.open else body.tab
    href = "/control?tab=" + tab + ("&open=" + body.open if body.open else "")
    where = " → ".join(
        ["Control Room", "AI" if tab == "ai" else tab.title()]
        + ([body.open.replace("_", " ").title()] if body.open else [])
    )
    return {"status": "completed", "href": href, "card": card("Open settings", where, href)}


def access_list(body, actor, db):
    from .access import list_access

    found = list_access(browser(db), actor, db)
    return {"status": "completed", "origins": found["origins"], "https_trusted": found["secure"]}


def access_add(body, actor, db):
    """Trusting an address is security-relevant, so the admin confirms it on a card."""
    from .access import normalize

    origin = normalize(body.origin)
    if not origin:
        raise HTTPException(422, "Use a full address such as https://house.example.lan")
    return confirmation(
        actor,
        db,
        "assistant.access_add",
        {"origin": origin},
        "Trust a new address",
        {"name": origin, "effect": "HouseOS will answer and accept sign-ins at this address"},
    )


class ActivityFilter(Input):
    category: Literal["", "music", "films", "games", "nox", "house", "system"] = ""
    problems: bool = Field(default=False, description="Only lines that went wrong.")


def house_activity(body, actor, db):
    """The Logs screen's newest lines, as sentences: what played, what Nox did, what failed."""
    from .activity import activity
    from .assistant_tools import route

    page = route(activity, category=body.category, problems=body.problems, actor=actor, db=db)
    lines = [
        {
            "at": line["at"],
            "category": line["category"],
            "level": line["level"],
            "who": line["who"],
            "said": line["template"].format(**{k: str(v) for k, v in line["values"].items()}),
        }
        for line in page["items"][:40]
    ]
    return {"status": "completed", "lines": lines}


def language_add(body, actor, db):
    from .languages import start

    return {"status": "completed", **start(db, actor, body)}


def ai_status(body, actor, db):
    from .assistant_profiles import profiles
    from .house_setup import ai_ready

    return {"status": "completed", "nox_ready": ai_ready(db), **profiles(actor, db)}


def card(label, detail, href):
    """A result card for the admin's screen (shown, not sent to the model)."""
    return {
        "kind": "result",
        "label": label,
        "domain": "setup",
        "status": "completed",
        "detail": detail,
        "href": href,
    }


class GameLink(Input):
    url: str = Field(min_length=8, max_length=2000, description="The https:// link the admin gave.")
    system: str | None = Field(default=None, max_length=20, description="A console key from games_status.")


class GamesFolder(Input):
    path: str = Field(min_length=2, max_length=500, description="A folder under games_status import_root.")


def games_status(body, actor, db):
    from . import games
    from .games_systems import SYSTEMS
    from .games_tv import tv_status

    present = games.bios_present()
    rows = games.games(db, visible=False)
    return {
        "status": "completed",
        "links_can_download": settings.external_fetch_enabled,
        "consoles": {
            key: {
                "name": s["name"],
                "in_browser": bool(s.get("browser")),
                "on_tv": bool(s.get("tv")),
                "bios": {name: name in present for name in s.get("bios", [])},
            }
            for key, s in SYSTEMS.items()
        },  # fmt: skip
        "games": sum(r.data.get("state", "ready") == "ready" for r in rows),
        "not_ready": [
            {
                "id": r.id,
                "title": r.data.get("title"),
                "state": r.data.get("state"),
                "error": r.data.get("error"),
            }
            for r in rows
            if r.data.get("state", "ready") != "ready"
        ][:10],
        "folders": games.folders(actor, db),
        "tv_play": tv_status(actor, db),
        "note": "a BIOS is uploaded by the admin on the Games set-up screen (games_open setup)",
    }


def game_link_add(body, actor, db):
    from . import games

    identity = games.start_link(db, actor, body.url.strip(), body.system)
    games.background(games.download, identity)
    href = "/games?game=" + identity
    return {"status": "accepted", "id": identity, "note": "downloading; games_status shows when it's ready or why not",
            "card": {**card("Downloading a game", games.link_name(body.url), href), "status": "accepted"}}  # fmt: skip


def games_folder_add(body, actor, db):
    from . import games

    result = games.add_folder(games.Folder(path=body.path), actor, db)
    return {"status": "completed", **result}


class GamesScreen(Input):
    sheet: Literal["setup", "add", "add-link"]


def games_open(body, actor, db):
    href = "/games?sheet=" + body.sheet
    where = {"setup": "Games → Set up", "add": "Games → Add", "add-link": "Games → Add from a link"}[
        body.sheet
    ]
    return {"status": "completed", "href": href, "card": card("Open Games", where, href)}


def admin_only(handler):
    return lambda body, actor, db: handler(body, require_admin(actor), db)


TOOLS = {
    name: (model, description, admin_only(handler))
    for name, model, description, handler in (
        ("setup_checklist", Empty, "The measured setup checklist: what is done, what is next.", checklist),
        ("services_status", Empty, "Whether each HouseOS service answers.", services_status),
        (
            "house_update",
            NewVersion,
            "Whether a new HouseOS version is out; apply=true prepares the update (a confirmation card).",
            house_update,
        ),
        (
            "service_restart",
            ServiceName,
            "Prepare a restart of one HouseOS service; returns a confirmation card.",
            service_restart,
        ),
        (
            "devices_find",
            Empty,
            "Scan the home network for TVs and speakers (about 10 s); says which are already added.",
            devices_find,
        ),
        ("device_add", DeviceAdd, "Add a Cast device found by devices_find.", device_add),
        (
            "speakers_list",
            Empty,
            "Where music can play: this computer's outputs and added Cast devices.",
            speakers_list,
        ),
        (
            "speaker_choose",
            SpeakerChoice,
            "Choose where music plays (one output or one Cast device); returns a confirmation card.",
            speaker_choose,
        ),
        ("integration_status", Empty, "Which connections are set up and hold a key.", integration_status),
        ("integration_test", IntegrationName, "Test one connection (read-only).", integration_test),
        (
            "open_settings",
            SettingsScreen,
            "Show a button to the right Control Room screen, optionally opening one integration's dialog.",
            open_settings,
        ),
        ("access_list", Empty, "The addresses HouseOS may be opened at.", access_list),
        (
            "access_add",
            Origin,
            "Trust one more address, such as https://house.lan:8443; returns a confirmation card.",
            access_add,
        ),
        (
            "games_status",
            Empty,
            "Games: each console's BIOS (present or missing), where it plays, games not ready and why, "
            "the games folders and TV play.",
            games_status,
        ),
        (
            "game_link_add",
            GameLink,
            "Download one game file from an https:// link the admin gives (their own backup, homebrew, "
            "a free game) into the house's games.",
            game_link_add,
        ),
        (
            "games_folder_add",
            GamesFolder,
            "Read a folder of games in place (never copied).",
            games_folder_add,
        ),
        ("games_open", GamesScreen, "Show a button to the Games set-up or add screen.", games_open),
        ("ai_status", Empty, "Nox's AI connections and the model assigned to each assistant.", ai_status),
        (
            "language_add",
            NewLanguage,
            "Translate the whole interface into another language, in the background (a few minutes, "
            "about 30 AI requests). Its progress is GET /api/v1/languages; making it the default is a house-settings change.",
            language_add,
        ),
        (
            "house_activity",
            ActivityFilter,
            "The house's recent activity log (newest first): songs, films, Nox's tool calls, "
            "background chores and errors. Use problems=true to find what went wrong.",
            house_activity,
        ),
    )
}
