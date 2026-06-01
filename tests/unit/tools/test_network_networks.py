"""Tests for Network VLAN/subnet MCP tools (2 read + 3 write)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
import respx
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from unifi_mcp.clients.network import NetworkClient
from unifi_mcp.config import UniFiConfig, UniFiMode
from unifi_mcp.tools.network.networks import register_network_config_tools

BASE_URL = "https://10.0.0.1:443"
SITE_PREFIX = f"{BASE_URL}/proxy/network/api/s/default"

READ_TOOL_NAMES = {"unifi_network_list_networks", "unifi_network_get_network"}
WRITE_TOOL_NAMES = {"unifi_network_create_network", "unifi_network_update_network", "unifi_network_delete_network"}


@pytest.fixture
def network_client() -> NetworkClient:
    return NetworkClient(base_url=BASE_URL, api_key="test-key", site="default", timeout=5, max_retries=1)


@pytest.fixture
def mcp_with_networks() -> FastMCP:
    server = FastMCP(name="test-networks")
    register_network_config_tools(server)
    return server


class TestNetworkConfigRegistration:
    async def test_all_tools_registered(self, mcp_with_networks):
        tools = await mcp_with_networks.list_tools()
        assert {t.name for t in tools} == READ_TOOL_NAMES | WRITE_TOOL_NAMES

    async def test_delete_network_marked_destructive(self, mcp_with_networks):
        tools = await mcp_with_networks.list_tools()
        tool = next(t for t in tools if t.name == "unifi_network_delete_network")
        assert tool.annotations.destructiveHint is True


class TestNetworkConfigClientEndpoints:
    @respx.mock
    async def test_list_networks(self, network_client):
        respx.get(f"{SITE_PREFIX}/rest/networkconf").mock(return_value=httpx.Response(200, json={"data": []}))
        assert await network_client.list_networks() == {"data": []}

    @respx.mock
    async def test_get_network(self, network_client):
        respx.get(f"{SITE_PREFIX}/rest/networkconf/n-1").mock(return_value=httpx.Response(200, json={"data": []}))
        assert await network_client.get_network("n-1") == {"data": []}

    @respx.mock
    async def test_create_network(self, network_client):
        route = respx.post(f"{SITE_PREFIX}/rest/networkconf").mock(return_value=httpx.Response(200, json={}))
        await network_client.create_network({"name": "guest", "vlan": 100})
        body = route.calls[0].request.content
        assert b"guest" in body
        assert b"100" in body

    @respx.mock
    async def test_update_network(self, network_client):
        route = respx.put(f"{SITE_PREFIX}/rest/networkconf/n-1").mock(return_value=httpx.Response(200, json={}))
        await network_client.update_network("n-1", {"enabled": False})
        assert b"enabled" in route.calls[0].request.content

    @respx.mock
    async def test_delete_network(self, network_client):
        route = respx.delete(f"{SITE_PREFIX}/rest/networkconf/n-1").mock(return_value=httpx.Response(204))
        assert await network_client.delete_network("n-1") == {}
        assert route.call_count == 1


@dataclass
class _FakeLifespan:
    config: UniFiConfig
    clients: dict[str, Any] = field(default_factory=dict)


def _ctx(mode: UniFiMode, **clients: Any) -> AsyncMock:
    config = UniFiConfig(
        _env_file=None,
        unifi_mode=mode,
        unifi_network_api="k",
        unifi_protect_api=None,
        unifi_site_manager_api=None,
    )
    ctx = AsyncMock()
    ctx.lifespan_context = _FakeLifespan(config=config, clients=clients)
    return ctx


class TestCreateNetworkHandler:
    """Drive create_network through the handler to cover its optional-arg branches."""

    async def test_readonly_blocks_create(self, mcp_with_networks):
        client = AsyncMock()
        ctx = _ctx(UniFiMode.READONLY, network=client)
        tool = await mcp_with_networks.get_tool("unifi_network_create_network")
        with pytest.raises(ToolError, match="read-only mode"):
            await tool.fn(ctx, name="guest")
        client.create_network.assert_not_awaited()

    async def test_subnet_and_vlan_included_when_provided(self, mcp_with_networks):
        client = AsyncMock()
        client.create_network.return_value = {"ok": True}
        ctx = _ctx(UniFiMode.READWRITE, network=client)
        tool = await mcp_with_networks.get_tool("unifi_network_create_network")
        result = await tool.fn(ctx, name="guest", subnet="192.168.2.0/24", vlan=100)
        assert result == {"ok": True}
        (forwarded,), _ = client.create_network.call_args
        assert forwarded["subnet"] == "192.168.2.0/24"
        assert forwarded["vlan"] == 100

    async def test_subnet_and_vlan_absent_when_omitted(self, mcp_with_networks):
        client = AsyncMock()
        client.create_network.return_value = {}
        ctx = _ctx(UniFiMode.READWRITE, network=client)
        tool = await mcp_with_networks.get_tool("unifi_network_create_network")
        await tool.fn(ctx, name="guest")
        (forwarded,), _ = client.create_network.call_args
        assert "subnet" not in forwarded
        assert "vlan" not in forwarded
