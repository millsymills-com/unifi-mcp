"""Tests for Network firewall MCP tools (4 read + 6 write)."""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from fastmcp import FastMCP

from unifi_mcp.clients.network import NetworkClient
from unifi_mcp.tools.network.firewall import register_firewall_tools

BASE_URL = "https://10.0.0.1:443"
SITE_PREFIX = f"{BASE_URL}/proxy/network/api/s/default"

READ_TOOL_NAMES = {
    "unifi_network_list_firewall_rules",
    "unifi_network_get_firewall_rule",
    "unifi_network_list_firewall_groups",
    "unifi_network_get_firewall_group",
}
WRITE_TOOL_NAMES = {
    "unifi_network_create_firewall_rule",
    "unifi_network_update_firewall_rule",
    "unifi_network_delete_firewall_rule",
    "unifi_network_create_firewall_group",
    "unifi_network_update_firewall_group",
    "unifi_network_delete_firewall_group",
}


@pytest.fixture
def network_client() -> NetworkClient:
    return NetworkClient(base_url=BASE_URL, api_key="test-key", site="default", timeout=5, max_retries=1)


@pytest.fixture
def mcp_with_firewall() -> FastMCP:
    server = FastMCP(name="test-firewall")
    register_firewall_tools(server)
    return server


class TestFirewallRegistration:
    async def test_all_tools_registered(self, mcp_with_firewall):
        tools = await mcp_with_firewall.list_tools()
        assert {t.name for t in tools} == READ_TOOL_NAMES | WRITE_TOOL_NAMES

    @pytest.mark.parametrize(
        "destructive_tool",
        ["unifi_network_delete_firewall_rule", "unifi_network_delete_firewall_group"],
    )
    async def test_delete_tools_marked_destructive(self, mcp_with_firewall, destructive_tool):
        tools = await mcp_with_firewall.list_tools()
        tool = next(t for t in tools if t.name == destructive_tool)
        assert tool.annotations.destructive_hint is True


class TestFirewallClientEndpoints:
    @respx.mock
    async def test_list_firewall_rules(self, network_client):
        respx.get(f"{SITE_PREFIX}/rest/firewallrule").mock(return_value=httpx.Response(200, json={"data": []}))
        assert await network_client.list_firewall_rules() == {"data": []}

    @respx.mock
    async def test_get_firewall_rule(self, network_client):
        respx.get(f"{SITE_PREFIX}/rest/firewallrule/r-1").mock(return_value=httpx.Response(200, json={"data": []}))
        assert await network_client.get_firewall_rule("r-1") == {"data": []}

    @respx.mock
    async def test_list_firewall_groups(self, network_client):
        respx.get(f"{SITE_PREFIX}/rest/firewallgroup").mock(return_value=httpx.Response(200, json={"data": []}))
        assert await network_client.list_firewall_groups() == {"data": []}

    @respx.mock
    async def test_get_firewall_group(self, network_client):
        respx.get(f"{SITE_PREFIX}/rest/firewallgroup/g-1").mock(return_value=httpx.Response(200, json={"data": []}))
        assert await network_client.get_firewall_group("g-1") == {"data": []}

    @respx.mock
    async def test_create_firewall_rule(self, network_client):
        route = respx.post(f"{SITE_PREFIX}/rest/firewallrule").mock(return_value=httpx.Response(200, json={}))
        await network_client.create_firewall_rule({"name": "block-bad-ip", "action": "drop"})
        assert b"block-bad-ip" in route.calls[0].request.content

    @respx.mock
    async def test_update_firewall_rule(self, network_client):
        route = respx.put(f"{SITE_PREFIX}/rest/firewallrule/r-1").mock(return_value=httpx.Response(200, json={}))
        await network_client.update_firewall_rule("r-1", {"enabled": False})
        assert json.loads(route.calls[0].request.content) == {"enabled": False}

    @respx.mock
    async def test_delete_firewall_rule(self, network_client):
        route = respx.delete(f"{SITE_PREFIX}/rest/firewallrule/r-1").mock(return_value=httpx.Response(204))
        assert await network_client.delete_firewall_rule("r-1") == {}
        assert route.call_count == 1

    @respx.mock
    async def test_create_firewall_group(self, network_client):
        route = respx.post(f"{SITE_PREFIX}/rest/firewallgroup").mock(return_value=httpx.Response(200, json={}))
        await network_client.create_firewall_group({"name": "bad-ips", "group_type": "address-group"})
        assert b"bad-ips" in route.calls[0].request.content

    @respx.mock
    async def test_delete_firewall_group(self, network_client):
        route = respx.delete(f"{SITE_PREFIX}/rest/firewallgroup/g-1").mock(return_value=httpx.Response(204))
        assert await network_client.delete_firewall_group("g-1") == {}
        assert route.call_count == 1


class TestFirewallCreateNamedFields:
    """The fields recorded for #90 are available without a raw payload."""

    async def test_named_fields_forward_complete_payload(self):
        """A complete controller fixture maps exactly to its named tool fields."""
        from dataclasses import dataclass, field
        from typing import Any
        from unittest.mock import AsyncMock

        from fastmcp import FastMCP

        from unifi_mcp.config import UniFiConfig, UniFiMode
        from unifi_mcp.tools.network.firewall import register_firewall_tools

        @dataclass
        class _FakeLifespan:
            config: UniFiConfig
            clients: dict[str, Any] = field(default_factory=dict)

        server = FastMCP(name="fw-test")
        register_firewall_tools(server)

        client = AsyncMock()
        client.create_firewall_rule.return_value = {"ok": True}

        config = UniFiConfig(
            _env_file=None,
            unifi_mode=UniFiMode.READWRITE,
            unifi_network_api="k",
            unifi_protect_api=None,
            unifi_site_manager_api=None,
        )
        ctx = AsyncMock()
        ctx.lifespan_context = _FakeLifespan(config=config, clients={"network": client})

        tool = await server.get_tool("unifi_network_create_firewall_rule")
        full_payload = {
            "name": "from-data",
            "ruleset": "LAN_IN",
            "rule_index": 2000,
            "action": "accept",
            "enabled": True,
            "protocol": "tcp",
            "state_new": True,
            "state_established": False,
            "state_invalid": False,
            "state_related": False,
            "logging": False,
            "ipsec": "",
            "src_firewallgroup_ids": [],
            "dst_firewallgroup_ids": [],
        }
        result = await tool.fn(ctx, **full_payload)
        assert result == {"ok": True}
        (forwarded,), _ = client.create_firewall_rule.call_args
        assert forwarded == full_payload

    async def test_original_scalar_defaults_are_preserved(self):
        """Original scalar calls still compose their prior body and defaults.
        Controller-required extra fields remain the caller's responsibility.
        """
        from dataclasses import dataclass, field
        from typing import Any
        from unittest.mock import AsyncMock

        from fastmcp import FastMCP

        from unifi_mcp.config import UniFiConfig, UniFiMode
        from unifi_mcp.tools.network.firewall import register_firewall_tools

        @dataclass
        class _FakeLifespan:
            config: UniFiConfig
            clients: dict[str, Any] = field(default_factory=dict)

        server = FastMCP(name="fw-test")
        register_firewall_tools(server)

        client = AsyncMock()
        client.create_firewall_rule.return_value = {}
        config = UniFiConfig(
            _env_file=None,
            unifi_mode=UniFiMode.READWRITE,
            unifi_network_api="k",
            unifi_protect_api=None,
            unifi_site_manager_api=None,
        )
        ctx = AsyncMock()
        ctx.lifespan_context = _FakeLifespan(config=config, clients={"network": client})

        tool = await server.get_tool("unifi_network_create_firewall_rule")
        await tool.fn(
            ctx,
            name="from-scalars",
            ruleset="WAN_IN",
            src_address="10.0.0.0/8",
        )
        (forwarded,), _ = client.create_firewall_rule.call_args
        assert forwarded["name"] == "from-scalars"
        assert forwarded["ruleset"] == "WAN_IN"
        assert forwarded["src_address"] == "10.0.0.0/8"
        assert forwarded["action"] == "drop"  # default
        assert forwarded["enabled"] is True  # default
        assert "dst_address" not in forwarded  # unset → absent

    async def test_dst_address_included_when_provided(self):
        """The scalar path appends ``dst_address`` only when it's supplied."""
        from dataclasses import dataclass, field
        from typing import Any
        from unittest.mock import AsyncMock

        from fastmcp import FastMCP

        from unifi_mcp.config import UniFiConfig, UniFiMode
        from unifi_mcp.tools.network.firewall import register_firewall_tools

        @dataclass
        class _FakeLifespan:
            config: UniFiConfig
            clients: dict[str, Any] = field(default_factory=dict)

        server = FastMCP(name="fw-test")
        register_firewall_tools(server)

        client = AsyncMock()
        client.create_firewall_rule.return_value = {}
        config = UniFiConfig(
            _env_file=None,
            unifi_mode=UniFiMode.READWRITE,
            unifi_network_api="k",
            unifi_protect_api=None,
            unifi_site_manager_api=None,
        )
        ctx = AsyncMock()
        ctx.lifespan_context = _FakeLifespan(config=config, clients={"network": client})

        tool = await server.get_tool("unifi_network_create_firewall_rule")
        await tool.fn(
            ctx,
            name="from-scalars",
            ruleset="WAN_OUT",
            dst_address="8.8.8.8/32",
        )
        (forwarded,), _ = client.create_firewall_rule.call_args
        assert forwarded["dst_address"] == "8.8.8.8/32"
