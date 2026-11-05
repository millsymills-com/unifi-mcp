"""Named WLAN update contracts with mocked controller operations only."""

import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

from unifi_mcp._redaction import REDACTED
from unifi_mcp.config import UniFiConfig, UniFiMode
from unifi_mcp.tools.network.wlan import register_wlan_tools

FIELDS = {
    "name": "fixture SSID",
    "security": "wpapsk",
    "wpa_mode": "wpa2",
    "x_passphrase": "synthetic-fixture-password",
    "enabled": False,
    "networkconf_id": "net-1",
    "is_guest": False,
    "l2_isolation": False,
    "wpa_enc": "ccmp",
    "wlan_band": "both",
    "wlan_bands": ["2g", "5g"],
    "ap_group_ids": ["ap-1"],
    "usergroup_id": "group-1",
}


@pytest.fixture
async def wlan_tool():
    server = FastMCP(name="offline WLAN update fixture")
    register_wlan_tools(server)
    tool = await server.get_tool("unifi_network_update_wlan")
    backend = AsyncMock()
    backend.update_wlan.return_value = {"ok": True}
    ctx = AsyncMock()
    ctx.lifespan_context = SimpleNamespace(
        config=UniFiConfig(_env_file=None, unifi_mode=UniFiMode.READWRITE), clients={"network": backend}
    )
    return server, tool, ctx, backend


async def test_named_fields_build_exact_body(wlan_tool):
    _, tool, ctx, backend = wlan_tool
    assert await tool.fn(ctx, wlan_id="wlan-1", **FIELDS) == {"ok": True}
    backend.update_wlan.assert_awaited_once_with("wlan-1", FIELDS)
    backend.list_wlans.assert_not_awaited()
    backend.list_networks.assert_not_awaited()


@pytest.mark.parametrize("field", FIELDS)
async def test_each_field_alone_omits_none_without_resolving_site_ids(wlan_tool, field):
    _, tool, ctx, backend = wlan_tool
    await tool.fn(ctx, wlan_id="wlan-1", **{**dict.fromkeys(FIELDS), field: FIELDS[field]})
    backend.update_wlan.assert_awaited_once_with("wlan-1", {field: FIELDS[field]})
    backend.list_wlans.assert_not_awaited()
    backend.list_networks.assert_not_awaited()


@pytest.mark.parametrize("values", [{}, dict.fromkeys(FIELDS)])
async def test_empty_updates_refuse_before_client(wlan_tool, values):
    _, tool, ctx, backend = wlan_tool
    with pytest.raises(ToolError, match="at least one field"):
        await tool.fn(ctx, wlan_id="wlan-1", **values)
    backend.update_wlan.assert_not_awaited()


@pytest.mark.parametrize("data", [{}, {"name": "raw"}, {"radius_secret": "synthetic"}])
async def test_raw_data_removed(wlan_tool, data):
    _, tool, ctx, backend = wlan_tool
    with pytest.raises(ToolError) as caught:
        await tool.fn(ctx, wlan_id="wlan-1", data=data)
    assert isinstance(caught.value.__cause__, TypeError)
    assert "unexpected keyword argument 'data'" in str(caught.value.__cause__)
    backend.update_wlan.assert_not_awaited()


@pytest.mark.parametrize("field", ["wlan_id", "networkconf_id", "usergroup_id", "ap_group_ids"])
@pytest.mark.parametrize("invalid", ["../escape", "has/slash", ""])
async def test_all_provided_ids_validated(wlan_tool, field, invalid):
    _, tool, ctx, backend = wlan_tool
    args = {"wlan_id": "wlan-1", "name": "fixture", field: [invalid] if field == "ap_group_ids" else invalid}
    with pytest.raises(ToolError, match=field):
        await tool.fn(ctx, **args)
    backend.update_wlan.assert_not_awaited()


@pytest.mark.parametrize("field", ["ap_group_ids", "wlan_bands"])
@pytest.mark.parametrize("invalid", ["scalar", {"radius_secret": "synthetic"}, [1], [{"name": "nested"}]])
async def test_list_shape_validated_even_for_direct_calls(wlan_tool, field, invalid):
    _, tool, ctx, backend = wlan_tool
    with pytest.raises(ToolError, match="list of strings"):
        await tool.fn(ctx, wlan_id="wlan-1", **{field: invalid})
    backend.update_wlan.assert_not_awaited()


@pytest.mark.parametrize("field", ["name", "x_passphrase", "ap_group_ids", "wlan_bands"])
async def test_explicit_empty_values_preserved(wlan_tool, field):
    _, tool, ctx, backend = wlan_tool
    value = [] if field.endswith("ids") or field == "wlan_bands" else ""
    await tool.fn(ctx, wlan_id="wlan-1", **{field: value})
    backend.update_wlan.assert_awaited_once_with("wlan-1", {field: value})


async def test_runtime_readonly_gate_remains(wlan_tool):
    _, tool, ctx, backend = wlan_tool
    ctx.lifespan_context.config = UniFiConfig(_env_file=None, unifi_mode=UniFiMode.READONLY)
    with pytest.raises(ToolError, match="read-only mode"):
        await tool.fn(ctx, wlan_id="wlan-1", name="fixture")
    backend.update_wlan.assert_not_awaited()


async def test_response_redacts_echoed_password(wlan_tool):
    _, tool, ctx, backend = wlan_tool
    backend.update_wlan.return_value = {"x_passphrase": "synthetic-echo", "name": "fixture"}
    assert await tool.fn(ctx, wlan_id="wlan-1", x_passphrase="synthetic-fixture-password") == {
        "x_passphrase": REDACTED,
        "name": "fixture",
    }


async def test_dangerous_key_guard_checks_constructed_body(wlan_tool, monkeypatch):
    _, tool, ctx, backend = wlan_tool
    module = importlib.import_module("unifi_mcp.tools.network.wlan")
    monkeypatch.setattr(module, "build_named_arg_body", lambda **_kwargs: {"radius_secret": "synthetic"})
    with pytest.raises(ToolError, match="radius_secret"):
        await tool.fn(ctx, wlan_id="wlan-1", name="fixture")
    backend.update_wlan.assert_not_awaited()


async def test_tools_list_exposes_only_id_and_named_types(wlan_tool):
    server, tool, _, _ = wlan_tool
    async with Client(server) as client:
        tools = {item.name: item for item in await client.list_tools()}
    schema = tools[tool.name].input_schema
    assert set(schema["properties"]) == {"wlan_id", *FIELDS}
    assert schema["required"] == ["wlan_id"]
    for name, value in FIELDS.items():
        spec = schema["properties"][name]
        kind = "boolean" if isinstance(value, bool) else "array" if isinstance(value, list) else "string"
        assert spec["default"] is None
        assert {item["type"] for item in spec["anyOf"]} == {kind, "null"}
        if kind == "array":
            assert next(item for item in spec["anyOf"] if item["type"] == "array")["items"] == {"type": "string"}


@pytest.mark.parametrize(
    ("name", "description", "default"),
    [
        ("unifi_network_create_wlan", "Wi-Fi password (required for wpapsk).", ""),
        ("unifi_network_update_wlan", "Wi-Fi PSK.", None),
    ],
)
async def test_wireless_credential_guidance_remains_in_parameter_metadata(name, description, default):
    server = FastMCP(name="offline WLAN parameter guidance")
    register_wlan_tools(server)
    async with Client(server) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}
    parameter = tools[name].input_schema["properties"]["x_passphrase"]
    assert parameter["description"] == description
    assert parameter["default"] == default
