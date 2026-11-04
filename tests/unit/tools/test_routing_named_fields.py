"""Route/forward update schemas expose only named fields; all clients are mocks."""

import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from unifi_mcp.config import UniFiConfig, UniFiMode
from unifi_mcp.tools.network.port_forward import register_port_forward_tools
from unifi_mcp.tools.network.routing import register_routing_tools

CASES = [
    (
        register_routing_tools,
        "unifi_network_update_route",
        "route_id",
        "update_route",
        {
            "name": "fixture route",
            "network": "198.51.100.0/24",
            "route_type": "nexthop-route",
            "gateway_ip": "192.0.2.1",
            "interface": "eth1",
            "enabled": False,
        },
        {
            "name": "fixture route",
            "static-route_network": "198.51.100.0/24",
            "static-route_type": "nexthop-route",
            "static-route_nexthop": "192.0.2.1",
            "static-route_interface": "eth1",
            "enabled": False,
        },
    ),
    (
        register_port_forward_tools,
        "unifi_network_update_port_forward",
        "port_forward_id",
        "update_port_forward",
        {
            "name": "fixture forward",
            "dst_port": "8080",
            "fwd": "192.0.2.2",
            "fwd_port": "80",
            "proto": "tcp",
            "enabled": False,
        },
        {
            "name": "fixture forward",
            "dst_port": "8080",
            "fwd": "192.0.2.2",
            "fwd_port": "80",
            "proto": "tcp",
            "enabled": False,
        },
    ),
]


@pytest.fixture(params=CASES, ids=["route", "port-forward"])
async def update_tool(request):
    register, name, id_field, method, named, expected = request.param
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
    return tool, ctx, getattr(client, method), id_field, named, expected


async def test_all_named_fields_build_exact_body(update_tool):
    tool, ctx, client, id_field, named, expected = update_tool
    assert await tool.fn(ctx, **{id_field: "fixture-1"}, **named) == {"ok": True}
    client.assert_awaited_once_with("fixture-1", expected)


async def test_each_field_updates_alone_and_none_is_omitted(update_tool):
    tool, ctx, client, id_field, named, expected = update_tool
    for key, value in named.items():
        client.reset_mock()
        values = dict.fromkeys(named)
        values[key] = value
        await tool.fn(ctx, **{id_field: "fixture-1"}, **values)
        controller_key = list(expected)[list(named).index(key)]
        client.assert_awaited_once_with("fixture-1", {controller_key: expected[controller_key]})


@pytest.mark.parametrize("values", [{}, {"enabled": None}])
async def test_empty_update_refuses_before_client(update_tool, values):
    tool, ctx, client, id_field, _, _ = update_tool
    with pytest.raises(ToolError, match="at least one field"):
        await tool.fn(ctx, **{id_field: "fixture-1"}, **values)
    client.assert_not_awaited()


@pytest.mark.parametrize("data", [{"enabled": False}, {"radius_secret": "synthetic"}])
async def test_raw_data_is_no_longer_a_call_argument(update_tool, data):
    tool, ctx, client, id_field, _, _ = update_tool
    with pytest.raises(ToolError, match="Unexpected internal error") as caught:
        await tool.fn(ctx, **{id_field: "fixture-1"}, data=data)
    assert isinstance(caught.value.__cause__, TypeError)
    assert "unexpected keyword argument 'data'" in str(caught.value.__cause__)
    client.assert_not_awaited()


async def test_readonly_runtime_gate_remains(update_tool):
    tool, ctx, client, id_field, _, _ = update_tool
    ctx.lifespan_context.config = UniFiConfig(_env_file=None, unifi_mode=UniFiMode.READONLY)
    with pytest.raises(ToolError, match="read-only mode"):
        await tool.fn(ctx, **{id_field: "fixture-1"}, enabled=False)
    client.assert_not_awaited()


async def test_schema_contains_only_id_and_named_scalars(update_tool):
    tool, _, _, id_field, named, _ = update_tool
    schema = tool.parameters
    assert set(schema["properties"]) == {id_field, *named}
    assert schema["required"] == [id_field]
    for field in named:
        assert schema["properties"][field]["default"] is None
        types = {item["type"] for item in schema["properties"][field]["anyOf"]}
        assert types == ({"boolean", "null"} if field == "enabled" else {"string", "null"})


@pytest.mark.parametrize("case", CASES, ids=["route", "port-forward"])
async def test_dangerous_key_guard_still_checks_the_built_body(case, monkeypatch):
    register, name, id_field, method, _, _ = case
    module = importlib.import_module(register.__module__)
    # Deliberately corrupt the builder output: the downstream denylist remains
    # defense in depth even if a future field-map edit introduces a denied key.
    monkeypatch.setattr(module, "build_named_arg_body", lambda **_: {"radius_secret": "synthetic"})
    server = FastMCP(name="offline corrupt-builder fixture")
    register(server)
    tool = await server.get_tool(name)
    client = AsyncMock()
    ctx = AsyncMock()
    ctx.lifespan_context = SimpleNamespace(
        config=UniFiConfig(_env_file=None, unifi_mode=UniFiMode.READWRITE),
        clients={"network": client},
    )

    with pytest.raises(ToolError, match="radius_secret"):
        await tool.fn(ctx, **{id_field: "fixture-1"}, enabled=False)
    getattr(client, method).assert_not_awaited()
