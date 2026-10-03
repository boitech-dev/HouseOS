from houseos import assistant_tools as t

"""Physical TV controls are not the same capability as native movie playback."""
from unittest.mock import patch
from houseos.assistant import assistant_devices, initial_context
from houseos.auth import Actor, RESIDENT


def test_tv_list_identifies_linked_hisense_and_supplies_inputs_without_native_playback():
    config = {
        "enabled": True,
        "device_id": "media_player.vidaa_tv",
        "receiver_id": "cast-one",
        "token": "fixture",
    }
    playback = {
        "items": [
            {
                "id": "cast-one",
                "name": "Chromecast with Google TV",
                "adapter": "cast",
                "version": 5,
                "state": "active",
                "capabilities": {
                    "set_input": True,
                    "volume_absolute": True,
                    "power_on": True,
                    "power_off": True,
                },
            }
        ],
        "setup_required": [{"name": "Hisense TV", "reason": "Native playback not configured"}],
    }
    state = {
        "display_name": "Vidaa TV",
        "state": "on",
        "input": "HDMI2",
        "inputs": ["HDMI1", "HDMI2", "Netflix"],
        "volume": 0.1,
        "observed_at": "fixture",
    }
    with (
        patch("houseos.cinema.devices", return_value=playback),
        patch("houseos.assistant_tools.integration_config", return_value=config),
        patch("houseos.cinema_tv.tv_state", return_value=state),
    ):
        result = assistant_devices(Actor("a", "Alice", "resident", RESIDENT), None, tv=True)
    tv = result["items"][0]
    assert tv["name"] == "Hisense TV" and tv["id"] == "cast-one"
    assert "TV" in tv["aliases"] and "Hisense" in tv["aliases"]
    assert tv["controls"] == ["power_on", "power_off", "volume", "input"]
    assert tv["input"] == "HDMI2" and tv["inputs"] == ["HDMI1", "HDMI2"]
    assert "setup_required" not in result
    assert tv["volume"] == 0.1


def test_compact_tv_names_route_to_tv_tools():
    for message in ("mets HDMI1", "change la télé sur HDMI 1", "Hisense input 1", "TV volume 5"):
        assert initial_context(message) == "tv"


def test_tv_request_has_target_on_first_round_and_does_not_start_movie_followup(domain, monkeypatch):
    from houseos import assistant as a
    from houseos.db import new_id
    from test_security import stub_provider_setup

    db, (actor, _, _) = domain
    stub_provider_setup(monkeypatch)
    target = {
        "items": [
            {
                "id": "tv-one",
                "name": "Hisense TV",
                "version": 5,
                "input": "HDMI2",
                "inputs": ["HDMI1", "HDMI2"],
            }
        ]
    }
    monkeypatch.setattr(a, "assistant_devices", lambda *args, **kwargs: target)
    calls = []

    def handler(body, *_):
        calls.append(body.model_dump())
        return {
            "status": "needs_confirmation",
            "confirmation_id": new_id(),
            "preview": {"summary": "Switch Hisense TV to HDMI1."},
        }

    monkeypatch.setattr(a, "tool_registry", lambda _: {"tv_control": (t.TVControl, "Fixture TV", handler)})
    rounds = []

    def provider(_, cfg, messages, schemas):
        rounds.append(1)
        # Live TV state rides in the turn's note, never the cached system prompt.
        assert "Hisense TV" in str(messages) and "HDMI1" in str(messages)
        assert "Hisense TV" not in cfg["_resident_context"]
        if len(rounds) == 1:
            return (
                "",
                [
                    {
                        "id": "input",
                        "name": "tv_control",
                        "args": {"device_id": "tv-one", "version": 5, "action": "input", "value": "HDMI1"},
                    }
                ],
                [],
                {"input_tokens": 1, "output_tokens": 1},
            )
        return "Passer la TV sur HDMI1 ?", [], [], {"input_tokens": 1, "output_tokens": 1}

    monkeypatch.setattr(a, "provider_round", provider)
    result = a.chat(a.Chat(message="mets la télé sur HDMI1", idempotency_key=new_id()), actor, db)
    assert len(calls) == 1 and calls[0]["value"] == "HDMI1"
    assert not any(card.get("continuation_path") for card in result["cards"])
