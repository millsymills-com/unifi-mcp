"""Offline ACL union mapping and guards, without controller connections."""

import importlib
from itertools import product
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

from unifi_mcp._redaction import REDACTED
from unifi_mcp.config import UniFiConfig, UniFiMode
from unifi_mcp.tools.network_integration.acl import register_acl_tools

ID1 = "00000000-0000-4000-8000-000000000001"
ID2 = "00000000-0000-4000-8000-000000000002"
MAC = "02:00:00:00:00:01"
BASE = {"rule_type": "IPV4", "enabled": False, "name": "synthetic ACL", "action": "BLOCK"}
WIRE = {"type": "IPV4", "enabled": False, "name": "synthetic ACL", "action": "BLOCK"}
V4 = [
    ({}, None),
    (
        {"ip_addresses_or_subnets": ["192.0.2.0/24"]},
        {"type": "IP_ADDRESSES_OR_SUBNETS", "ipAddressesOrSubnets": ["192.0.2.0/24"]},
    ),
    ({"network_ids": [ID1]}, {"type": "NETWORKS", "networkIds": [ID1]}),
    ({"ports": [1, 65535]}, {"type": "PORTS", "portFilter": [1, 65535]}),
    (
        {"ip_addresses_or_subnets": ["192.0.2.1"], "ports": [443]},
        {"type": "IP_ADDRESSES_OR_SUBNETS", "ipAddressesOrSubnets": ["192.0.2.1"], "portFilter": [443]},
    ),
    ({"network_ids": [ID1, ID2], "ports": [80]}, {"type": "NETWORKS", "networkIds": [ID1, ID2], "portFilter": [80]}),
]
L2 = [
    ({}, None),
    ({"mac_addresses": [MAC]}, {"type": "MAC_ADDRESSES", "macAddresses": [MAC]}),
    (
        {"mac_addresses": [MAC], "mac_prefix_length": 1},
        {"type": "MAC_ADDRESSES", "macAddresses": [MAC], "prefixLength": 1},
    ),
    (
        {"mac_addresses": [MAC], "mac_prefix_length": 48},
        {"type": "MAC_ADDRESSES", "macAddresses": [MAC], "prefixLength": 48},
    ),
]
LIST_FIELDS = ["protocol_filter", "enforcing_device_ids"] + [
    f"{side}_{suffix}"
    for side in ("source", "destination")
    for suffix in ("ip_addresses_or_subnets", "network_ids", "ports", "mac_addresses")
]


@pytest.fixture(params=["create", "update"])
async def acl_tool(request):
    server = FastMCP(name="offline ACL fixture")
    register_acl_tools(server)
    operation = request.param
    tool = await server.get_tool(f"unifi_network_{operation}_acl_rule")
    backend = AsyncMock()
    method = getattr(backend, f"{operation}_acl_rule")
    method.return_value = {"ok": True}
    ctx = AsyncMock()
    ctx.lifespan_context = SimpleNamespace(
        config=UniFiConfig(_env_file=None, unifi_mode=UniFiMode.READWRITE), clients={"network_integration": backend}
    )
    ids = {"acl_rule_id": ID2} if operation == "update" else {}
    return server, tool, ctx, backend, method, ids


@pytest.mark.parametrize(("source", "destination"), list(product(V4, repeat=2)))
async def test_all_ipv4_filter_shapes_map_exactly(acl_tool, source, destination):
    _, tool, ctx, backend, method, ids = acl_tool
    fields = {**BASE, "description": "", "protocol_filter": ["TCP", "UDP"], "enforcing_device_ids": [ID1]}
    expected = {
        **WIRE,
        "description": "",
        "protocolFilter": ["TCP", "UDP"],
        "enforcingDeviceFilter": {"type": "DEVICES", "deviceIds": [ID1]},
    }
    for side, (values, output) in [("source", source), ("destination", destination)]:
        fields.update({f"{side}_{key}": value for key, value in values.items()})
        if output is not None:
            expected[side + "Filter"] = output
    assert await tool.fn(ctx, **ids, **fields) == {"ok": True}
    method.assert_awaited_once_with(*ids.values(), expected)
    assert len(backend.mock_calls) == 1


@pytest.mark.parametrize(("source", "destination"), list(product(L2, repeat=2)))
async def test_all_mac_filter_shapes_map_exactly(acl_tool, source, destination):
    _, tool, ctx, _, method, ids = acl_tool
    fields = {**BASE, "rule_type": "MAC", "network_id": ID1}
    expected = {**WIRE, "type": "MAC", "networkIdFilter": ID1}
    for side, (values, output) in [("source", source), ("destination", destination)]:
        fields.update({f"{side}_{key}": value for key, value in values.items()})
        if output is not None:
            expected[side + "Filter"] = output
    await tool.fn(ctx, **ids, **fields)
    method.assert_awaited_once_with(*ids.values(), expected)


async def test_omitted_filters_are_not_read_or_merged(acl_tool):
    _, tool, ctx, backend, method, ids = acl_tool
    await tool.fn(ctx, **ids, **BASE)
    method.assert_awaited_once_with(*ids.values(), WIRE)
    assert len(backend.mock_calls) == 1


@pytest.mark.parametrize("side", ["source", "destination"])
@pytest.mark.parametrize("suffix", ["ip_addresses_or_subnets", "network_ids", "ports"])
async def test_ip_selectors_forbidden_on_mac(acl_tool, side, suffix):
    _, tool, ctx, _, method, ids = acl_tool
    value = {"ip_addresses_or_subnets": ["192.0.2.1"], "network_ids": [ID1], "ports": [80]}[suffix]
    with pytest.raises(ToolError):
        await tool.fn(ctx, **ids, **{**BASE, "rule_type": "MAC", "network_id": ID1, f"{side}_{suffix}": value})
    method.assert_not_awaited()


@pytest.mark.parametrize("side", ["source", "destination"])
async def test_mac_selectors_forbidden_on_ipv4(acl_tool, side):
    _, tool, ctx, _, method, ids = acl_tool
    with pytest.raises(ToolError):
        await tool.fn(ctx, **ids, **BASE, **{f"{side}_mac_addresses": [MAC]})
    method.assert_not_awaited()


@pytest.mark.parametrize("side", ["source", "destination"])
async def test_ip_and_network_selectors_cannot_mix(acl_tool, side):
    _, tool, ctx, _, method, ids = acl_tool
    with pytest.raises(ToolError, match="choose IP"):
        await tool.fn(
            ctx, **ids, **BASE, **{f"{side}_network_ids": [ID1], f"{side}_ip_addresses_or_subnets": ["192.0.2.1"]}
        )
    method.assert_not_awaited()


@pytest.mark.parametrize(
    "fields",
    [{"rule_type": "MAC"}, {"network_id": ID1}, {"rule_type": "MAC", "network_id": ID1, "protocol_filter": ["TCP"]}],
)
async def test_root_variant_requirements(acl_tool, fields):
    _, tool, ctx, _, method, ids = acl_tool
    with pytest.raises(ToolError):
        await tool.fn(ctx, **ids, **{**BASE, **fields})
    method.assert_not_awaited()


@pytest.mark.parametrize("field", LIST_FIELDS)
@pytest.mark.parametrize("value", [[], "not-a-list", [None], [{}]])
async def test_nonempty_typed_lists_required(acl_tool, field, value):
    _, tool, ctx, _, method, ids = acl_tool
    fields = {**BASE, field: value}
    if field.endswith("_mac_addresses"):
        fields.update(rule_type="MAC", network_id=ID1)
    with pytest.raises(ToolError):
        await tool.fn(ctx, **ids, **fields)
    method.assert_not_awaited()


@pytest.mark.parametrize("field", ["source_ports", "destination_ports"])
@pytest.mark.parametrize("value", [0, -1, 65536, True, 1.5, "80"])
async def test_port_item_bounds_and_types(acl_tool, field, value):
    _, tool, ctx, _, method, ids = acl_tool
    with pytest.raises(ToolError):
        await tool.fn(ctx, **ids, **BASE, **{field: [value]})
    method.assert_not_awaited()


@pytest.mark.parametrize("side", ["source", "destination"])
@pytest.mark.parametrize("value", [0, 49, True, 1.5])
async def test_mac_prefix_bounds(acl_tool, side, value):
    _, tool, ctx, _, method, ids = acl_tool
    with pytest.raises(ToolError):
        await tool.fn(
            ctx,
            **ids,
            **{
                **BASE,
                "rule_type": "MAC",
                "network_id": ID1,
                f"{side}_mac_addresses": [MAC],
                f"{side}_mac_prefix_length": value,
            },
        )
    method.assert_not_awaited()


@pytest.mark.parametrize("side", ["source", "destination"])
async def test_mac_prefix_requires_addresses(acl_tool, side):
    _, tool, ctx, _, method, ids = acl_tool
    with pytest.raises(ToolError, match="requires MAC addresses"):
        await tool.fn(ctx, **ids, **{**BASE, "rule_type": "MAC", "network_id": ID1, f"{side}_mac_prefix_length": 24})
    method.assert_not_awaited()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("protocol_filter", ["TCP", "TCP"]),
        ("protocol_filter", ["SCTP"]),
        ("source_ports", [80, 80]),
        ("destination_ports", [80, 80]),
        ("source_network_ids", [ID1, ID1]),
        ("destination_network_ids", [ID1, ID1]),
        ("enforcing_device_ids", [ID1, ID1]),
        ("enforcing_device_ids", ["../device"]),
    ],
)
async def test_unique_lists_and_protocol_membership(acl_tool, field, value):
    _, tool, ctx, _, method, ids = acl_tool
    with pytest.raises(ToolError):
        await tool.fn(ctx, **ids, **BASE, **{field: value})
    method.assert_not_awaited()


@pytest.mark.parametrize(
    "fields",
    [
        {"rule_type": "other"},
        {"action": "ACCEPT"},
        {"enabled": 1},
        {"name": ""},
        {"description": {}},
        {"rule_type": "MAC", "network_id": "../net"},
        {"rule_type": "MAC", "network_id": ID1, "source_mac_addresses": ["invalid"]},
    ],
)
async def test_invalid_base_and_identifiers(acl_tool, fields):
    _, tool, ctx, _, method, ids = acl_tool
    with pytest.raises(ToolError):
        await tool.fn(ctx, **ids, **{**BASE, **fields})
    method.assert_not_awaited()


@pytest.mark.parametrize(("field", "value"), [("data", {}), ("index", 0), ("sourceFilter", {}), ("roles", ["admin"])])
async def test_raw_or_unnamed_arguments_removed(acl_tool, field, value):
    _, tool, ctx, _, method, ids = acl_tool
    with pytest.raises(ToolError) as caught:
        await tool.fn(ctx, **ids, **BASE, **{field: value})
    assert isinstance(caught.value.__cause__, TypeError)
    method.assert_not_awaited()


async def test_runtime_readonly_gate(acl_tool):
    _, tool, ctx, _, method, ids = acl_tool
    ctx.lifespan_context.config = UniFiConfig(_env_file=None, unifi_mode=UniFiMode.READONLY)
    with pytest.raises(ToolError, match="read-only mode"):
        await tool.fn(ctx, **ids, **BASE)
    method.assert_not_awaited()


async def test_response_redaction(acl_tool):
    _, tool, ctx, _, method, ids = acl_tool
    method.return_value = {"radius_secret": "response-placeholder"}
    assert await tool.fn(ctx, **ids, **BASE) == {"radius_secret": REDACTED}


async def test_dangerous_key_defense_retained(acl_tool, monkeypatch):
    _, tool, ctx, _, method, ids = acl_tool
    module = importlib.import_module("unifi_mcp.tools.network_integration._acl_rule")
    monkeypatch.setattr(module, "build_named_arg_body", lambda **_kwargs: {"radius_secret": "synthetic"})
    with pytest.raises(ToolError, match="radius_secret"):
        await tool.fn(ctx, **ids, **BASE)
    method.assert_not_awaited()


async def test_real_tools_list_schema(acl_tool):
    server, tool, _, _, _, ids = acl_tool
    async with Client(server) as client:
        tools = {item.name: item for item in await client.list_tools()}
    schema = tools[tool.name].input_schema
    properties = schema["properties"]
    assert "data" not in properties
    assert "index" not in properties
    assert "ctx" not in properties
    assert properties["rule_type"]["enum"] == ["IPV4", "MAC"]
    assert properties["action"]["enum"] == ["ALLOW", "BLOCK"]
    assert properties["protocol_filter"]["anyOf"][0]["items"]["enum"] == ["TCP", "UDP"]
    assert set(schema["required"]) == {"rule_type", "enabled", "name", "action", *ids}
    assert all(properties[name].get("description") for name in properties)
    assert tool.annotations.read_only_hint is False
    assert tool.annotations.destructive_hint is False
    assert "write" in tool.tags


async def test_readonly_registration_hides_writes(acl_tool):
    server, _, _, _, _, _ = acl_tool
    server.disable(tags={"write"})
    assert not any("write" in tool.tags for tool in await server.list_tools())


@pytest.mark.parametrize("rule_type", ["IPV4", "MAC"])
async def test_address_lists_preserve_duplicates_allowed_by_schema(acl_tool, rule_type):
    _, tool, ctx, _, method, ids = acl_tool
    fields = {**BASE, "rule_type": rule_type}
    if rule_type == "MAC":
        fields.update(network_id=ID1, source_mac_addresses=[MAC, MAC])
        output = {
            **WIRE,
            "type": "MAC",
            "networkIdFilter": ID1,
            "sourceFilter": {"type": "MAC_ADDRESSES", "macAddresses": [MAC, MAC]},
        }
    else:
        fields["source_ip_addresses_or_subnets"] = ["192.0.2.1", "192.0.2.1"]
        output = {
            **WIRE,
            "sourceFilter": {"type": "IP_ADDRESSES_OR_SUBNETS", "ipAddressesOrSubnets": ["192.0.2.1", "192.0.2.1"]},
        }
    await tool.fn(ctx, **ids, **fields)
    method.assert_awaited_once_with(*ids.values(), output)
