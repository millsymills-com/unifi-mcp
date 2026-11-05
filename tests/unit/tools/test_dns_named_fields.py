"""Offline named DNS policy contracts; no controller is contacted."""

from types import SimpleNamespace
from typing import get_args
from unittest.mock import AsyncMock

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

from unifi_mcp._redaction import REDACTED
from unifi_mcp.config import UniFiConfig, UniFiMode
from unifi_mcp.tools.network_integration._dns_policy import DnsPolicyType
from unifi_mcp.tools.network_integration.dns import register_dns_tools

VARIANTS = {
    "A_RECORD": {"ipv4_address": "192.0.2.10", "ttl_seconds": 0},
    "AAAA_RECORD": {"ipv6_address": "2001:db8::1", "ttl_seconds": 86400},
    "CNAME_RECORD": {"target_domain": "target.example.test", "ttl_seconds": 604800},
    "MX_RECORD": {"mail_server_domain": "mail.example.test", "priority": 0},
    "TXT_RECORD": {"text": 'a quoted "value"'},
    "SRV_RECORD": {
        "server_domain": "server.example.test",
        "service": "_ldap",
        "protocol": "_tcp",
        "port": 0,
        "priority": 0,
        "weight": 65535,
    },
    "FORWARD_DOMAIN": {"ip_address": "2001:db8::53"},
}
EXPECTED_NAMES = {
    "ipv4_address": "ipv4Address",
    "ipv6_address": "ipv6Address",
    "target_domain": "targetDomain",
    "mail_server_domain": "mailServerDomain",
    "server_domain": "serverDomain",
    "ip_address": "ipAddress",
    "ttl_seconds": "ttlSeconds",
}


@pytest.fixture(params=["create", "update"])
async def dns_tool(request):
    server = FastMCP(name="offline DNS policy fixture")
    register_dns_tools(server)
    operation = request.param
    tool = await server.get_tool(f"unifi_network_{operation}_dns_policy")
    client = AsyncMock()
    method = getattr(client, f"{operation}_dns_policy")
    method.return_value = {"ok": True}
    ctx = AsyncMock()
    ctx.lifespan_context = SimpleNamespace(
        config=UniFiConfig(_env_file=None, unifi_mode=UniFiMode.READWRITE),
        clients={"network_integration": client},
    )
    ids = {"dns_policy_id": "policy-1"} if operation == "update" else {}
    return server, tool, ctx, method, ids


@pytest.mark.parametrize("policy_type", VARIANTS)
async def test_exact_variant_payload(dns_tool, policy_type):
    _, tool, ctx, method, ids = dns_tool
    fields = VARIANTS[policy_type]
    await tool.fn(ctx, **ids, policy_type=policy_type, enabled=False, domain="example.test", **fields)
    expected = {"type": policy_type, "enabled": False, "domain": "example.test"}
    expected.update({EXPECTED_NAMES.get(key, key): value for key, value in fields.items()})
    method.assert_awaited_once_with(*ids.values(), expected)


@pytest.mark.parametrize(
    ("policy_type", "missing"), [(kind, name) for kind, fields in VARIANTS.items() for name in fields]
)
async def test_every_required_variant_field_is_required(dns_tool, policy_type, missing):
    _, tool, ctx, method, ids = dns_tool
    fields = {key: value for key, value in VARIANTS[policy_type].items() if key != missing}
    with pytest.raises(ToolError, match="exactly the fields required"):
        await tool.fn(ctx, **ids, policy_type=policy_type, enabled=True, domain="example.test", **fields)
    method.assert_not_awaited()


@pytest.mark.parametrize("policy_type", VARIANTS)
async def test_other_variant_fields_are_refused(dns_tool, policy_type):
    _, tool, ctx, method, ids = dns_tool
    fields = {**VARIANTS[policy_type]}
    extra = "priority" if "priority" not in fields else "ttl_seconds"
    fields[extra] = 1
    with pytest.raises(ToolError, match="exactly the fields required"):
        await tool.fn(ctx, **ids, policy_type=policy_type, enabled=True, domain="example.test", **fields)
    method.assert_not_awaited()


@pytest.mark.parametrize(
    ("policy_type", "field", "value"),
    [
        ("A_RECORD", "ttl_seconds", -1),
        ("A_RECORD", "ttl_seconds", 86401),
        ("AAAA_RECORD", "ttl_seconds", 86401),
        ("CNAME_RECORD", "ttl_seconds", 604801),
        ("MX_RECORD", "priority", -1),
        ("MX_RECORD", "priority", 65536),
        ("SRV_RECORD", "port", 65536),
        ("SRV_RECORD", "weight", -1),
        ("TXT_RECORD", "text", ""),
        ("TXT_RECORD", "text", "x" * 1025),
        ("CNAME_RECORD", "target_domain", "x" * 128),
    ],
)
async def test_declared_bounds_refuse_before_client(dns_tool, policy_type, field, value):
    _, tool, ctx, method, ids = dns_tool
    fields = {**VARIANTS[policy_type], field: value}
    with pytest.raises(ToolError):
        await tool.fn(ctx, **ids, policy_type=policy_type, enabled=True, domain="example.test", **fields)
    method.assert_not_awaited()


@pytest.mark.parametrize(("field", "value"), [("data", {}), ("permissions", "synthetic")])
async def test_raw_or_unnamed_arguments_removed(dns_tool, field, value):
    _, tool, ctx, method, ids = dns_tool
    with pytest.raises(ToolError) as caught:
        await tool.fn(
            ctx,
            **ids,
            policy_type="TXT_RECORD",
            enabled=True,
            domain="example.test",
            text="synthetic",
            **{field: value},
        )
    assert isinstance(caught.value.__cause__, TypeError)
    method.assert_not_awaited()


async def test_mode_gate_precedes_client(dns_tool):
    _, tool, ctx, method, ids = dns_tool
    ctx.lifespan_context.config = UniFiConfig(_env_file=None, unifi_mode=UniFiMode.READONLY)
    with pytest.raises(ToolError, match="read-only mode"):
        await tool.fn(ctx, **ids, policy_type="TXT_RECORD", enabled=True, domain="example.test", text="synthetic")
    method.assert_not_awaited()


async def test_response_redaction(dns_tool):
    _, tool, ctx, method, ids = dns_tool
    method.return_value = {"radius_secret": "response-placeholder"}
    result = await tool.fn(ctx, **ids, policy_type="TXT_RECORD", enabled=True, domain="example.test", text="synthetic")
    assert result == {"radius_secret": REDACTED}


async def test_real_tools_list_schema(dns_tool):
    server, tool, _, _, ids = dns_tool
    async with Client(server) as client:
        tools = {item.name: item for item in await client.list_tools()}
    schema = tools[tool.name].input_schema
    properties = schema["properties"]
    assert "data" not in properties
    assert "ctx" not in properties
    assert properties["policy_type"]["enum"] == list(get_args(DnsPolicyType))
    assert set(schema["required"]) == {"policy_type", "enabled", "domain", *ids}
    assert all(
        properties[name].get("description") for name in ["policy_type", "enabled", "domain", "ttl_seconds", "text"]
    )
    assert tool.annotations.read_only_hint is False
    assert tool.annotations.destructive_hint is False
    assert "write" in tool.tags


async def test_readonly_registration_hides_both_writes(dns_tool):
    server, _, _, _, _ = dns_tool
    server.disable(tags={"write"})
    assert not any("write" in tool.tags for tool in await server.list_tools())
