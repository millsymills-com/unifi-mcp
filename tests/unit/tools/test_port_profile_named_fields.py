"""Port-profile named-field contracts; every client operation is mocked."""

import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

from unifi_mcp._redaction import REDACTED
from unifi_mcp.config import UniFiConfig, UniFiMode
from unifi_mcp.tools.network.port_profiles import register_port_profile_tools

FIELDS = {"name": "fixture profile", "poe_mode": "off", "forward": "native", "native_networkconf_id": "vlan-1"}


@pytest.fixture(params=["create", "update"])
async def profile_tool(request):
    operation = request.param
    server = FastMCP(name="offline port-profile fixture")
    register_port_profile_tools(server)
    tool = await server.get_tool(f"unifi_network_{operation}_port_profile")
    client = AsyncMock()
    method = getattr(client, f"{operation}_port_profile")
    method.return_value = {"ok": True}
    ctx = AsyncMock()
    ctx.lifespan_context = SimpleNamespace(
        config=UniFiConfig(_env_file=None, unifi_mode=UniFiMode.READWRITE), clients={"network": client}
    )
    ids = {"profile_id": "profile-1"} if operation == "update" else {}
    return server, tool, ctx, method, ids


async def test_named_payload_matches_existing_fixture(profile_tool):
    _, tool, ctx, method, ids = profile_tool
    assert await tool.fn(ctx, **ids, **FIELDS) == {"ok": True}
    method.assert_awaited_once_with(*ids.values(), FIELDS)


@pytest.mark.parametrize("data", [{}, {"poe_mode": "off"}, {"radius_secret": "synthetic"}])
async def test_raw_data_argument_removed(profile_tool, data):
    _, tool, ctx, method, ids = profile_tool
    with pytest.raises(ToolError) as caught:
        await tool.fn(ctx, **ids, **FIELDS, data=data)
    assert isinstance(caught.value.__cause__, TypeError)
    assert "unexpected keyword argument 'data'" in str(caught.value.__cause__)
    method.assert_not_awaited()


async def test_readonly_refuses_before_client(profile_tool):
    _, tool, ctx, method, ids = profile_tool
    ctx.lifespan_context.config = UniFiConfig(_env_file=None, unifi_mode=UniFiMode.READONLY)
    with pytest.raises(ToolError, match="read-only mode"):
        await tool.fn(ctx, **ids, **FIELDS)
    method.assert_not_awaited()


async def test_response_redacted(profile_tool):
    _, tool, ctx, method, ids = profile_tool
    method.return_value = {"radius_secret": "synthetic-private-response"}
    assert await tool.fn(ctx, **ids, **FIELDS) == {"radius_secret": REDACTED}


async def test_tools_list_named_types_and_required_fields(profile_tool):
    server, tool, _, _, ids = profile_tool
    async with Client(server) as client:
        tools = {item.name: item for item in await client.list_tools()}
    schema = tools[tool.name].input_schema
    assert set(schema["properties"]) == {*ids, *FIELDS}
    assert set(schema["required"]) == (set(ids) if ids else {"name", "poe_mode", "forward"})
    for name in FIELDS:
        spec = schema["properties"][name]
        if ids or name == "native_networkconf_id":
            assert spec["default"] is None
            assert {item["type"] for item in spec["anyOf"]} == {"string", "null"}
        else:
            assert spec["type"] == "string"


@pytest.mark.parametrize("invalid_id", ["../escape", "", "has/slash", "has space"])
async def test_network_id_validated_before_client(profile_tool, invalid_id):
    _, tool, ctx, method, ids = profile_tool
    values = {**FIELDS, "native_networkconf_id": invalid_id}
    with pytest.raises(ToolError, match="native_networkconf_id"):
        await tool.fn(ctx, **ids, **values)
    method.assert_not_awaited()


async def test_dangerous_key_guard_checks_constructed_body(profile_tool, monkeypatch):
    _, tool, ctx, method, ids = profile_tool
    module = importlib.import_module("unifi_mcp.tools.network.port_profiles")
    monkeypatch.setattr(module, "build_named_arg_body", lambda **_kwargs: {"radius_secret": "synthetic"})
    with pytest.raises(ToolError, match="radius_secret"):
        await tool.fn(ctx, **ids, **FIELDS)
    method.assert_not_awaited()


async def test_create_omits_optional_none_and_requires_native_id():
    server = FastMCP(name="offline create fixture")
    register_port_profile_tools(server)
    tool = await server.get_tool("unifi_network_create_port_profile")
    ctx = AsyncMock()
    client = AsyncMock()
    ctx.lifespan_context = SimpleNamespace(
        config=UniFiConfig(_env_file=None, unifi_mode=UniFiMode.READWRITE), clients={"network": client}
    )
    values = {"name": "fixture", "poe_mode": "off", "forward": "all"}
    await tool.fn(ctx, **values, native_networkconf_id=None)
    client.create_port_profile.assert_awaited_once_with(values)
    client.reset_mock()
    with pytest.raises(ToolError, match="native_networkconf_id is required"):
        await tool.fn(ctx, **{**values, "forward": "native"})
    client.create_port_profile.assert_not_awaited()


async def test_update_each_field_alone_and_empty_refusal():
    server = FastMCP(name="offline update fixture")
    register_port_profile_tools(server)
    tool = await server.get_tool("unifi_network_update_port_profile")
    ctx = AsyncMock()
    client = AsyncMock()
    ctx.lifespan_context = SimpleNamespace(
        config=UniFiConfig(_env_file=None, unifi_mode=UniFiMode.READWRITE), clients={"network": client}
    )
    for key, value in FIELDS.items():
        client.reset_mock()
        await tool.fn(ctx, profile_id="profile-1", **{**dict.fromkeys(FIELDS), key: value})
        client.update_port_profile.assert_awaited_once_with("profile-1", {key: value})
    client.reset_mock()
    for values in ({}, dict.fromkeys(FIELDS)):
        with pytest.raises(ToolError, match="at least one field"):
            await tool.fn(ctx, profile_id="profile-1", **values)
    client.update_port_profile.assert_not_awaited()
