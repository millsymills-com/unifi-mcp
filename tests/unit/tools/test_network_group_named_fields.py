"""Named network/group update contracts; all clients are mocks.

Exact base 0b4097b61437970008706e7a97f52d415d57dec2: 27 failed, two passed,
two builder-injection controls deselected because the base lacks that import.
"""

import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

from unifi_mcp._redaction import REDACTED
from unifi_mcp.config import UniFiConfig, UniFiMode
from unifi_mcp.tools.network.firewall import register_firewall_tools
from unifi_mcp.tools.network.networks import register_network_config_tools

CASES = [
    (
        register_network_config_tools,
        "unifi_network_update_network",
        "network_id",
        "update_network",
        {
            "name": "fixture network",
            "purpose": "corporate",
            "ip_subnet": "192.0.2.1/24",
            "vlan": 100,
            "vlan_enabled": True,
            "dhcpd_enabled": False,
        },
        {
            "name": "string",
            "purpose": "string",
            "ip_subnet": "string",
            "vlan": "integer",
            "vlan_enabled": "boolean",
            "dhcpd_enabled": "boolean",
        },
    ),
    (
        register_firewall_tools,
        "unifi_network_update_firewall_group",
        "group_id",
        "update_firewall_group",
        {"name": "fixture group", "group_type": "address-group", "group_members": ["192.0.2.0/24"]},
        {"name": "string", "group_type": "string", "group_members": "array"},
    ),
]


@pytest.fixture(params=CASES, ids=["network", "firewall-group"])
async def update_tool(request):
    register, name, id_field, method, named, types = request.param
    server = FastMCP(name="offline named-field fixture")
    register(server)
    tool = await server.get_tool(name)
    client = AsyncMock()
    getattr(client, method).return_value = {"ok": True}
    ctx = AsyncMock()
    ctx.lifespan_context = SimpleNamespace(
        config=UniFiConfig(_env_file=None, unifi_mode=UniFiMode.READWRITE),
        clients={"network": client},
    )
    return server, tool, ctx, getattr(client, method), id_field, named, types


async def test_named_fields_build_exact_payload(update_tool):
    _, tool, ctx, client, id_field, named, _ = update_tool
    assert await tool.fn(ctx, **{id_field: "fixture-1"}, **named) == {"ok": True}
    client.assert_awaited_once_with("fixture-1", named)


async def test_each_field_updates_alone_with_none_omitted(update_tool):
    _, tool, ctx, client, id_field, named, _ = update_tool
    for key, value in named.items():
        client.reset_mock()
        values = dict.fromkeys(named)
        values[key] = value
        await tool.fn(ctx, **{id_field: "fixture-1"}, **values)
        client.assert_awaited_once_with("fixture-1", {key: value})


async def test_empty_and_all_null_updates_refuse_before_client(update_tool):
    _, tool, ctx, client, id_field, named, _ = update_tool
    for values in ({}, dict.fromkeys(named)):
        with pytest.raises(ToolError, match="at least one field"):
            await tool.fn(ctx, **{id_field: "fixture-1"}, **values)
    client.assert_not_awaited()


@pytest.mark.parametrize("data", [{}, {"name": "raw"}, {"radius_secret": "synthetic"}])
async def test_raw_data_is_no_longer_a_call_argument(update_tool, data):
    _, tool, ctx, client, id_field, _, _ = update_tool
    with pytest.raises(ToolError) as caught:
        await tool.fn(ctx, **{id_field: "fixture-1"}, data=data)
    assert isinstance(caught.value.__cause__, TypeError)
    assert "unexpected keyword argument 'data'" in str(caught.value.__cause__)
    client.assert_not_awaited()


async def test_runtime_readonly_gate_remains(update_tool):
    _, tool, ctx, client, id_field, named, _ = update_tool
    ctx.lifespan_context.config = UniFiConfig(_env_file=None, unifi_mode=UniFiMode.READONLY)
    with pytest.raises(ToolError, match="read-only mode"):
        await tool.fn(ctx, **{id_field: "fixture-1"}, **named)
    client.assert_not_awaited()


async def test_response_redaction_remains(update_tool):
    _, tool, ctx, client, id_field, named, _ = update_tool
    client.return_value = {"ok": True, "radius_secret": "synthetic-private-response"}
    assert await tool.fn(ctx, **{id_field: "fixture-1"}, **named) == {"ok": True, "radius_secret": REDACTED}
    client.assert_awaited_once_with("fixture-1", named)


async def test_tools_list_exposes_only_id_and_named_typed_fields(update_tool):
    server, tool, _, _, id_field, named, types = update_tool
    async with Client(server) as client:
        tools = {item.name: item for item in await client.list_tools()}
    schema = tools[tool.name].input_schema
    assert set(schema["properties"]) == {id_field, *named}
    assert schema["required"] == [id_field]
    for field, expected_type in types.items():
        spec = schema["properties"][field]
        assert spec["default"] is None
        variants = spec["anyOf"]
        assert {item["type"] for item in variants} == {expected_type, "null"}
        if expected_type == "array":
            assert next(item for item in variants if item["type"] == "array")["items"] == {"type": "string"}


@pytest.mark.parametrize(("field", "value"), [("dhcpd_enabled", False), ("vlan_enabled", False), ("vlan", 0)])
async def test_network_false_and_zero_are_explicit_updates(field, value):
    server = FastMCP(name="offline false-value fixture")
    register_network_config_tools(server)
    tool = await server.get_tool("unifi_network_update_network")
    client = AsyncMock()
    ctx = AsyncMock()
    ctx.lifespan_context = SimpleNamespace(
        config=UniFiConfig(_env_file=None, unifi_mode=UniFiMode.READWRITE), clients={"network": client}
    )
    await tool.fn(ctx, network_id="fixture-1", **{field: value})
    client.update_network.assert_awaited_once_with("fixture-1", {field: value})


@pytest.mark.parametrize("members", [[], ["192.0.2.0/24"], ["80", "443"]])
async def test_group_members_preserve_explicit_empty_and_nonempty_lists(members):
    server = FastMCP(name="offline group fixture")
    register_firewall_tools(server)
    tool = await server.get_tool("unifi_network_update_firewall_group")
    client = AsyncMock()
    ctx = AsyncMock()
    ctx.lifespan_context = SimpleNamespace(
        config=UniFiConfig(_env_file=None, unifi_mode=UniFiMode.READWRITE), clients={"network": client}
    )
    await tool.fn(ctx, group_id="fixture-1", group_members=members)
    client.update_firewall_group.assert_awaited_once_with("fixture-1", {"group_members": members})


@pytest.mark.parametrize("members", [{}, "80", [80], [{"nested": "value"}], ["80", False]])
async def test_nonstring_members_refuse_before_client(members):
    server = FastMCP(name="offline malformed group fixture")
    register_firewall_tools(server)
    tool = await server.get_tool("unifi_network_update_firewall_group")
    client = AsyncMock()
    ctx = AsyncMock()
    ctx.lifespan_context = SimpleNamespace(
        config=UniFiConfig(_env_file=None, unifi_mode=UniFiMode.READWRITE), clients={"network": client}
    )
    with pytest.raises(ToolError, match="group_members must be a list of strings"):
        await tool.fn(ctx, group_id="fixture-1", group_members=members)
    client.update_firewall_group.assert_not_awaited()


@pytest.mark.parametrize("case", CASES, ids=["network", "firewall-group"])
async def test_dangerous_key_guard_checks_constructed_body(case, monkeypatch):
    register, name, id_field, method, _, _ = case
    module = importlib.import_module(register.__module__)
    monkeypatch.setattr(module, "build_named_arg_body", lambda **_: {"radius_secret": "synthetic"})
    server = FastMCP(name="offline corrupt-builder fixture")
    register(server)
    tool = await server.get_tool(name)
    client = AsyncMock()
    ctx = AsyncMock()
    ctx.lifespan_context = SimpleNamespace(
        config=UniFiConfig(_env_file=None, unifi_mode=UniFiMode.READWRITE), clients={"network": client}
    )
    with pytest.raises(ToolError, match="radius_secret"):
        await tool.fn(ctx, **{id_field: "fixture-1"}, name="fixture")
    getattr(client, method).assert_not_awaited()
