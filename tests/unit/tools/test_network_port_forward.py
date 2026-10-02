"""Tests for Network port forwarding MCP tools (2 read + 3 write)."""

from __future__ import annotations

import httpx
import pytest
import respx
from fastmcp import FastMCP

from unifi_mcp.clients.network import NetworkClient
from unifi_mcp.tools.network.port_forward import register_port_forward_tools

BASE_URL = "https://10.0.0.1:443"
SITE_PREFIX = f"{BASE_URL}/proxy/network/api/s/default"

ALL_TOOLS = {
    "unifi_network_list_port_forwards",
    "unifi_network_get_port_forward",
    "unifi_network_create_port_forward",
    "unifi_network_update_port_forward",
    "unifi_network_delete_port_forward",
}


@pytest.fixture
def network_client() -> NetworkClient:
    return NetworkClient(base_url=BASE_URL, api_key="test-key", site="default", timeout=5, max_retries=1)


@pytest.fixture
def mcp_with_pf() -> FastMCP:
    server = FastMCP(name="test-pf")
    register_port_forward_tools(server)
    return server


class TestPortForwardRegistration:
    async def test_all_tools_registered(self, mcp_with_pf):
        tools = await mcp_with_pf.list_tools()
        assert {t.name for t in tools} == ALL_TOOLS

    async def test_delete_marked_destructive(self, mcp_with_pf):
        tools = await mcp_with_pf.list_tools()
        tool = next(t for t in tools if t.name == "unifi_network_delete_port_forward")
        assert tool.annotations.destructive_hint is True


class TestPortForwardClientEndpoints:
    @respx.mock
    async def test_list_port_forwards(self, network_client):
        respx.get(f"{SITE_PREFIX}/rest/portforward").mock(return_value=httpx.Response(200, json={"data": []}))
        assert await network_client.list_port_forwards() == {"data": []}

    @respx.mock
    async def test_get_port_forward(self, network_client):
        respx.get(f"{SITE_PREFIX}/rest/portforward/pf-1").mock(return_value=httpx.Response(200, json={"data": []}))
        assert await network_client.get_port_forward("pf-1") == {"data": []}

    @respx.mock
    async def test_create_port_forward(self, network_client):
        route = respx.post(f"{SITE_PREFIX}/rest/portforward").mock(return_value=httpx.Response(200, json={}))
        await network_client.create_port_forward({"name": "ssh", "dst_port": "22"})
        assert b"ssh" in route.calls[0].request.content

    @respx.mock
    async def test_update_port_forward(self, network_client):
        route = respx.put(f"{SITE_PREFIX}/rest/portforward/pf-1").mock(return_value=httpx.Response(200, json={}))
        await network_client.update_port_forward("pf-1", {"enabled": False})
        assert b"enabled" in route.calls[0].request.content

    @respx.mock
    async def test_delete_port_forward(self, network_client):
        route = respx.delete(f"{SITE_PREFIX}/rest/portforward/pf-1").mock(return_value=httpx.Response(204))
        assert await network_client.delete_port_forward("pf-1") == {}
        assert route.call_count == 1
