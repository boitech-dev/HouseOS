"""Nox's TV remote: "press OK on the TV", "go back", "volume up on the living room TV", "turn the
TV off". Only the remote's allowlisted buttons; the TV is found by name like smart-home devices."""

from __future__ import annotations

from pydantic import Field

from . import screen_tv, tv_remote
from .auth import Input
from .tool_home import score, words
from .tool_setup import confirmation


class TvRemote(Input):
    key: tv_remote.Key = Field(
        description="DPAD_CENTER is OK/select; BACK, HOME, arrows, VOLUME_UP/DOWN, VOLUME_MUTE, "
        "MEDIA_PLAY_PAUSE, VOLUME_SET (with level); POWER (toggles on/off) and INPUT (with input) "
        "return a confirmation card"
    )
    tv: str | None = Field(
        default=None,
        max_length=120,
        description="the TV's or Chromecast's name; omit to use the TV itself when there is one",
    )
    input: str | None = Field(default=None, max_length=80, description="for INPUT: an exact input label")
    times: int = Field(default=1, ge=1, le=10, description="presses, e.g. 3 for 'down three times'")
    level: int | None = Field(default=None, ge=0, le=100, description="for VOLUME_SET: the exact volume")


def tv_remote_press(body, actor, db):
    tv_remote.allowed(actor)
    devices = {d.id: d for d in tv_remote.tvs(db)}
    if not devices:
        return {"status": "failed", "detail": "No TV has been added yet (Control Room → Devices)."}
    # Each screen may have two remotes: the TV itself (Home Assistant) and the Chromecast/DLNA
    # device. Names pick one; otherwise the remotes that have this button, the TV first.
    every = tv_remote.describe(db, list(devices.values()))
    remotes = every
    if body.tv:
        query = words(body.tv)
        ranked = sorted(((score(query, r["name"]), r) for r in remotes), key=lambda pair: -pair[0])
        remotes = [r for value, r in ranked if value == ranked[0][0] and value >= 0.5]
    able = [r for r in remotes if tv_remote.supports(r["capabilities"], body.key)]
    if len(able) > 1 and not body.tv:
        tvs = [r for r in able if r["target"] == "tv"]
        able = tvs if len(tvs) == 1 else able
    if len(able) != 1:
        return {
            "status": "needs_clarification",
            "message": "No TV remote has that name or button; ask which one."
            if not able
            else "Ask the resident which TV or Chromecast.",
            "matches": [r["name"] for r in (able or remotes or every)][:8],
        }
    remote = able[0]
    if body.key in {"POWER", "INPUT"}:  # may cut what someone watches: a card, as tv_control asks
        if body.key == "INPUT" and body.input not in remote["inputs"]:
            return {"status": "needs_clarification", "inputs": remote["inputs"][:12]}
        on = remote["state"].get("on")
        action = "input" if body.key == "INPUT" else {True: "power_off", False: "power_on"}.get(on, "power")
        return confirmation(
            actor,
            db,
            "assistant.tv_remote",
            {"device_id": remote["id"], "key": body.key, "value": body.input, "target": remote["target"]},
            "TV remote",
            {"destination": remote["name"], "action": action, "value": body.input, "may_interrupt": True},
        )
    times = body.times if body.key != "VOLUME_SET" else 1
    result = tv_remote.call(
        tv_remote.press, db, devices[remote["id"]], body.key, body.level, times, remote["target"]
    )
    return {**result, "tv": remote["name"], "times": times}


def tv_film_input(body, actor, db):
    tv_remote.allowed(actor)
    # Only the TVs Home Assistant controls have inputs; no probing of every screen for this.
    mapped = [
        (d, ha) for d in tv_remote.tvs(db) if (ha := tv_remote.home_assistant(db, d)) and ha.get("inputs")
    ]
    if not mapped:
        return {"status": "failed", "detail": "No TV linked through Home Assistant reports its inputs."}
    if len(mapped) > 1:
        return {
            "status": "needs_clarification",
            "message": "Several TVs are linked; set it on the TV's remote card.",
        }
    device, ha = mapped[0]
    if body.input and body.input not in ha["inputs"]:
        return {"status": "needs_clarification", "inputs": ha["inputs"][:12]}
    tv_remote.set_film_input(device.id, body, actor, db)
    return {
        "status": "saved",
        "tv": ha.get("display_name") or device.name,
        "film_input": body.input or "never switch",
    }


class TvShowVideo(Input):
    url: str = Field(min_length=10, max_length=2000, description="the YouTube link to show")


def tv_show_video(body, actor, db):
    tv_remote.allowed(actor)
    video = screen_tv.youtube(body.url)
    if not video:
        return {"status": "failed", "detail": "Only YouTube video links can be shown on the TV this way."}
    if not screen_tv.helper_up():
        return {"status": "failed", "detail": "The computer isn't ready (its desktop helper isn't running)."}
    # It may turn the TV on and replace what is on it: a card, as the remote's power button asks.
    return confirmation(
        actor,
        db,
        "assistant.tv_screen",
        {"url": video["url"]},
        "Show on the TV",
        {"destination": "TV", "action": "show", "value": video["url"], "may_interrupt": True},
    )


TOOLS = {
    "tv_show_video": (
        TvShowVideo,
        "Show a YouTube video on the TV, full screen, through the house computer's screen (the TV is "
        "turned on and switched to it). A confirmation card; the result says it was sent, not that "
        "it plays.",
        tv_show_video,
    ),
    "tv_film_input": (
        tv_remote.FilmInput,
        "Remember which TV input films switch to (where the Chromecast is plugged in): the TV is "
        "turned on and put on that input when a film starts.",
        tv_film_input,
    ),
    "tv_remote": (
        TvRemote,
        "Press a button on a TV's remote: arrows, OK, back, home, volume, mute, play/pause, power, input. "
        "Sent at once, except power and input (a confirmation card); the result says it was sent, "
        "not what the screen shows.",
        tv_remote_press,
    ),
}
