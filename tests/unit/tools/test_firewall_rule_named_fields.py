"""Offline firewall update allowlist; all controller operations are mocked."""

import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

from unifi_mcp._redaction import REDACTED
from unifi_mcp.config import UniFiConfig, UniFiMode
from unifi_mcp.tools.network.firewall import register_firewall_tools

FIELDS = {
    "name": "synthetic rule",
    "ruleset": "LAN_IN",
    "rule_index": 20000,
    "action": "drop",
    "protocol": "all",
    "src_address": "192.0.2.0/24",
    "dst_address": "192.0.2.0/24",
    "enabled": False,
    "logging": False,
    "state_new": False,
    "state_established": False,
    "state_invalid": False,
    "state_related": False,
    "icmp_typename": "",
    "ipsec": "",
    "src_firewallgroup_ids": [],
    "dst_firewallgroup_ids": [],
}


@pytest.fixture
async def rule_tool():
    server = FastMCP(name="offline firewall update fixture")
    register_firewall_tools(server)
    tool = await server.get_tool("unifi_network_update_firewall_rule")
    client = AsyncMock()
    client.update_firewall_rule.return_value = {"ok": True}
    ctx = AsyncMock()
    ctx.lifespan_context = SimpleNamespace(
        config=UniFiConfig(_env_file=None, unifi_mode=UniFiMode.READWRITE), clients={"network": client}
    )
    return server, tool, ctx, client


async def test_complete_existing_fixture_fields_are_forwarded(rule_tool):
    _, tool, ctx, client = rule_tool
    assert await tool.fn(ctx, "rule-1", **FIELDS) == {"ok": True}
    client.update_firewall_rule.assert_awaited_once_with("rule-1", FIELDS)


@pytest.mark.parametrize(("name", "value"), [*FIELDS.items(), ("rule_index", 0)])
async def test_each_field_updates_independently_without_invented_defaults(rule_tool, name, value):
    _, tool, ctx, client = rule_tool
    await tool.fn(ctx, "rule-1", **{name: value})
    client.update_firewall_rule.assert_awaited_once_with("rule-1", {name: value})


async def test_none_omits_field(rule_tool):
    _, tool, ctx, client = rule_tool
    await tool.fn(ctx, "rule-1", enabled=False, action=None, rule_index=None)
    client.update_firewall_rule.assert_awaited_once_with("rule-1", {"enabled": False})


@pytest.mark.parametrize("fields", [{}, {"enabled": None}, {"src_firewallgroup_ids": None}])
async def test_empty_update_refuses(rule_tool, fields):
    _, tool, ctx, client = rule_tool
    with pytest.raises(ToolError, match="at least one field"):
        await tool.fn(ctx, "rule-1", **fields)
    client.update_firewall_rule.assert_not_awaited()


@pytest.mark.parametrize(
    "fields", [{"data": {}}, {"data": {"enabled": False}}, {"radius_secret": "synthetic"}, {"unknown": "synthetic"}]
)
async def test_raw_or_unnamed_input_refuses(rule_tool, fields):
    _, tool, ctx, client = rule_tool
    with pytest.raises(ToolError) as caught:
        await tool.fn(ctx, "rule-1", enabled=False, **fields)
    assert isinstance(caught.value.__cause__, TypeError)
    client.update_firewall_rule.assert_not_awaited()


@pytest.mark.parametrize("name", ["src_firewallgroup_ids", "dst_firewallgroup_ids"])
@pytest.mark.parametrize("value", ["group-1", [1], ["../group"], {}, [None]])
async def test_invalid_group_ids_refuse_before_client(rule_tool, name, value):
    _, tool, ctx, client = rule_tool
    with pytest.raises(ToolError):
        await tool.fn(ctx, "rule-1", **{name: value})
    client.update_firewall_rule.assert_not_awaited()


async def test_nonempty_group_ids_preserved(rule_tool):
    _, tool, ctx, client = rule_tool
    values = {"src_firewallgroup_ids": ["g-1", "g-2"], "dst_firewallgroup_ids": ["g-3"]}
    await tool.fn(ctx, "rule-1", **values)
    client.update_firewall_rule.assert_awaited_once_with("rule-1", values)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("name", {}),
        ("ruleset", []),
        ("action", 1),
        ("enabled", 1),
        ("logging", "false"),
        ("state_new", 0),
        ("state_established", "true"),
        ("state_invalid", []),
        ("state_related", {}),
        ("rule_index", True),
        ("rule_index", 1.5),
        ("protocol", False),
        ("src_address", {}),
        ("icmp_typename", []),
    ],
)
async def test_direct_handler_type_validation(rule_tool, name, value):
    _, tool, ctx, client = rule_tool
    with pytest.raises(ToolError):
        await tool.fn(ctx, "rule-1", **{name: value})
    client.update_firewall_rule.assert_not_awaited()


async def test_invalid_rule_id_refuses_before_client(rule_tool):
    _, tool, ctx, client = rule_tool
    with pytest.raises(ToolError, match="rule_id: invalid"):
        await tool.fn(ctx, "../rule", enabled=False)
    client.update_firewall_rule.assert_not_awaited()


async def test_runtime_readonly_gate(rule_tool):
    _, tool, ctx, client = rule_tool
    ctx.lifespan_context.config = UniFiConfig(_env_file=None, unifi_mode=UniFiMode.READONLY)
    with pytest.raises(ToolError, match="read-only mode"):
        await tool.fn(ctx, "rule-1", enabled=False)
    client.update_firewall_rule.assert_not_awaited()


async def test_response_redaction(rule_tool):
    _, tool, ctx, client = rule_tool
    client.update_firewall_rule.return_value = {"radius_secret": "response-placeholder"}
    assert await tool.fn(ctx, "rule-1", enabled=False) == {"radius_secret": REDACTED}


async def test_dangerous_key_defense_retained_after_body_build(rule_tool, monkeypatch):
    _, tool, ctx, client = rule_tool
    module = importlib.import_module("unifi_mcp.tools.network.firewall")
    monkeypatch.setattr(module, "build_named_arg_body", lambda **_kwargs: {"radius_secret": "synthetic"})
    with pytest.raises(ToolError, match="radius_secret"):
        await tool.fn(ctx, "rule-1", enabled=False)
    client.update_firewall_rule.assert_not_awaited()


async def test_real_tools_list_schema(rule_tool):
    server, tool, _, _ = rule_tool
    async with Client(server) as client:
        tools = {item.name: item for item in await client.list_tools()}
    schema = tools[tool.name].input_schema
    properties = schema["properties"]
    assert set(properties) == {"rule_id", *FIELDS}
    assert schema["required"] == ["rule_id"]
    assert all(properties[name].get("description") for name in properties)
    for name in FIELDS:
        assert properties[name]["default"] is None
    assert tool.annotations.read_only_hint is False
    assert tool.annotations.destructive_hint is False
    assert "write" in tool.tags


async def test_readonly_registration_hides_update(rule_tool):
    server, _, _, _ = rule_tool
    server.disable(tags={"write"})
    assert not any(tool.name == "unifi_network_update_firewall_rule" for tool in await server.list_tools())
