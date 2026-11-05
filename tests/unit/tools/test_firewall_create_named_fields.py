"""Named firewall creation with explicit controller fields and mocked backend."""

import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

from unifi_mcp._redaction import REDACTED
from unifi_mcp.config import UniFiConfig, UniFiMode
from unifi_mcp.tools.network.firewall import register_firewall_tools

BASE = {"name": "synthetic rule", "ruleset": "LAN_IN", "action": "drop", "enabled": True, "protocol": "all"}
FULL = {
    **BASE,
    "enabled": False,
    "rule_index": 20000,
    "logging": False,
    "state_new": False,
    "state_established": False,
    "state_invalid": False,
    "state_related": False,
    "icmp_typename": "",
    "ipsec": "",
    "src_address": "192.0.2.0/24",
    "dst_address": "192.0.2.0/24",
    "src_firewallgroup_ids": [],
    "dst_firewallgroup_ids": [],
}


@pytest.fixture
async def create_tool():
    server = FastMCP(name="offline firewall creation fixture")
    register_firewall_tools(server)
    tool = await server.get_tool("unifi_network_create_firewall_rule")
    client = AsyncMock()
    client.create_firewall_rule.return_value = {"ok": True}
    ctx = AsyncMock()
    ctx.lifespan_context = SimpleNamespace(
        config=UniFiConfig(_env_file=None, unifi_mode=UniFiMode.READWRITE), clients={"network": client}
    )
    return server, tool, ctx, client


async def test_full_recorded_field_set_maps_exactly(create_tool):
    _, tool, ctx, client = create_tool
    assert await tool.fn(ctx, **FULL) == {"ok": True}
    client.create_firewall_rule.assert_awaited_once_with(FULL)


async def test_prior_scalar_defaults_preserved_without_invented_controller_fields(create_tool):
    _, tool, ctx, client = create_tool
    await tool.fn(ctx, name=BASE["name"], ruleset=BASE["ruleset"])
    client.create_firewall_rule.assert_awaited_once_with(BASE)


@pytest.mark.parametrize(("field", "value"), [*FULL.items(), ("rule_index", 0)])
async def test_each_named_field_is_explicit_and_independent(create_tool, field, value):
    _, tool, ctx, client = create_tool
    values = {"name": BASE["name"], "ruleset": BASE["ruleset"], field: value}
    await tool.fn(ctx, **values)
    client.create_firewall_rule.assert_awaited_once_with({**BASE, field: value})


async def test_optional_none_omits(create_tool):
    _, tool, ctx, client = create_tool
    await tool.fn(ctx, name=BASE["name"], ruleset=BASE["ruleset"], logging=None, rule_index=None)
    client.create_firewall_rule.assert_awaited_once_with(BASE)


@pytest.mark.parametrize("field", BASE)
async def test_required_core_values_cannot_be_null(create_tool, field):
    _, tool, ctx, client = create_tool
    with pytest.raises(ToolError, match="cannot be null"):
        await tool.fn(ctx, **{**BASE, field: None})
    client.create_firewall_rule.assert_not_awaited()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("data", {}),
        ("data", FULL),
        ("permissions", "synthetic"),
        ("unknown", "synthetic"),
    ],
)
async def test_raw_and_unnamed_arguments_removed(create_tool, field, value):
    _, tool, ctx, client = create_tool
    with pytest.raises(ToolError) as caught:
        await tool.fn(ctx, **BASE, **{field: value})
    assert isinstance(caught.value.__cause__, TypeError)
    client.create_firewall_rule.assert_not_awaited()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", {}),
        ("enabled", 1),
        ("rule_index", True),
        ("rule_index", 1.5),
        ("logging", "false"),
        ("state_new", []),
        ("src_firewallgroup_ids", ["../group"]),
        ("dst_firewallgroup_ids", [1]),
    ],
)
async def test_shared_runtime_validation_is_used(create_tool, field, value):
    _, tool, ctx, client = create_tool
    with pytest.raises(ToolError):
        await tool.fn(ctx, **{**BASE, field: value})
    client.create_firewall_rule.assert_not_awaited()


async def test_runtime_readonly_gate(create_tool):
    _, tool, ctx, client = create_tool
    ctx.lifespan_context.config = UniFiConfig(_env_file=None, unifi_mode=UniFiMode.READONLY)
    with pytest.raises(ToolError, match="read-only mode"):
        await tool.fn(ctx, **BASE)
    client.create_firewall_rule.assert_not_awaited()


async def test_response_redaction(create_tool):
    _, tool, ctx, client = create_tool
    client.create_firewall_rule.return_value = {"radius_secret": "response-placeholder"}
    assert await tool.fn(ctx, **BASE) == {"radius_secret": REDACTED}


async def test_post_builder_dangerous_key_defense_retained(create_tool, monkeypatch):
    _, tool, ctx, client = create_tool
    module = importlib.import_module("unifi_mcp.tools.network.firewall")
    monkeypatch.setattr(module, "build_named_arg_body", lambda **_kwargs: {"radius_secret": "synthetic"})
    with pytest.raises(ToolError, match="radius_secret"):
        await tool.fn(ctx, **BASE)
    client.create_firewall_rule.assert_not_awaited()


async def test_real_tools_list_schema(create_tool):
    server, tool, _, _ = create_tool
    async with Client(server) as client:
        tools = {item.name: item for item in await client.list_tools()}
    schema = tools[tool.name].input_schema
    properties = schema["properties"]
    assert set(properties) == set(FULL)
    assert schema["required"] == ["name", "ruleset"]
    assert properties["action"]["default"] == "drop"
    assert properties["enabled"]["default"] is True
    assert properties["protocol"]["default"] == "all"
    assert all(properties[field]["default"] is None for field in set(FULL) - set(BASE))
    assert all(properties[field].get("description") for field in FULL)
    assert tool.annotations.read_only_hint is False
    assert tool.annotations.destructive_hint is False
    assert "write" in tool.tags


async def test_readonly_registration_hides_create(create_tool):
    server, _, _, _ = create_tool
    server.disable(tags={"write"})
    assert not any(tool.name == "unifi_network_create_firewall_rule" for tool in await server.list_tools())
