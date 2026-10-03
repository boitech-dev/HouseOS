"""Nox's prompts and the trimmed tool schemas providers see."""

import json

from houseos import assistant_prompt as prompt, assistant_tools as t, claude_bridge, codex_bridge


def objects(node):
    if isinstance(node, dict):
        if node.get("type") == "object":
            yield node
        for child in node.values():
            yield from objects(child)
    elif isinstance(node, list):
        for child in node:
            yield from objects(child)


def test_trimmed_schemas_keep_required_fields_enums_and_descriptions():
    registry = t.tool_registry("general")
    schemas = {s["name"]: s["parameters"] for s in t.tool_schemas(registry)}
    remote = schemas["tv_remote"]
    assert remote["required"] == ["key"] and "VOLUME_SET" in remote["properties"]["key"]["enum"]
    assert remote["properties"]["tv"]["type"] == "string" and "description" in remote["properties"]["tv"]
    grocery = schemas["household_create"]["$defs"]["GroceryData"]
    assert grocery["required"] == ["label"] and "purchased" in grocery["properties"]
    text = json.dumps(schemas)
    assert '"title": "' not in text and '"default"' not in text  # a field named title stays
    assert '{"type": "null"}' not in json.dumps(schemas["tv_remote"])
    # OpenAI's strict mode still gets every property required, nullable when optional.
    for name, parameters in schemas.items():
        for node in objects(t.strict_schema(parameters)):
            assert node["additionalProperties"] is False, name
            assert node["required"] == list(node.get("properties", {})), name


def test_bridges_share_one_suffix_that_distrusts_tool_results():
    assert "untrusted data" in prompt.BRIDGE_SUFFIX and "You are" not in prompt.BRIDGE_SUFFIX
    assert claude_bridge.BRIDGE_SUFFIX is codex_bridge.BRIDGE_SUFFIX is prompt.BRIDGE_SUFFIX


def test_setup_policy_names_real_commands_and_tools():
    setup = prompt.system_prompt("setup")
    for word in ("./houseos.sh setup-code", "./houseos.sh gpu on", "house_activity", "language_add"):
        assert word in setup
    assert "house_api_propose" in setup and "192.168" not in setup and "cannot run Docker" not in setup


def test_routing_home_and_watch():
    assert "home_control" in prompt.system_prompt("home")
    assert prompt.initial_context("Watch the kids until six") is None
    assert prompt.initial_context("Watch a film tonight") == "cinema"
    assert prompt.initial_context("Hisense input 1") == "tv"
