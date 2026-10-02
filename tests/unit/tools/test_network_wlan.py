"""Tests for Network WLAN MCP tools (2 read + 3 write)."""

from __future__ import annotations

import httpx
import pytest
import respx
from fastmcp import FastMCP

from unifi_mcp.clients.network import NetworkClient
from unifi_mcp.config import UniFiConfig, UniFiMode
from unifi_mcp.server import create_server
from unifi_mcp.tools.network.wlan import register_wlan_tools

BASE_URL = "https://10.0.0.1:443"
SITE_PREFIX = f"{BASE_URL}/proxy/network/api/s/default"

READ_TOOL_NAMES = {"unifi_network_list_wlans", "unifi_network_get_wlan"}
WRITE_TOOL_NAMES = {"unifi_network_create_wlan", "unifi_network_update_wlan", "unifi_network_delete_wlan"}


@pytest.fixture
def network_client() -> NetworkClient:
    return NetworkClient(base_url=BASE_URL, api_key="test-key", site="default", timeout=5, max_retries=1)


@pytest.fixture
def mcp_with_wlan() -> FastMCP:
    server = FastMCP(name="test-wlan")
    register_wlan_tools(server)
    return server


def _full_config(mode: UniFiMode) -> UniFiConfig:
    return UniFiConfig(
        _env_file=None,
        unifi_mode=mode,
        unifi_network_api="test-net",
        unifi_protect_api=None,
        unifi_site_manager_api=None,
    )


class TestWlanToolRegistration:
    async def test_all_wlan_tools_registered(self, mcp_with_wlan):
        tools = await mcp_with_wlan.list_tools()
        assert {t.name for t in tools} == READ_TOOL_NAMES | WRITE_TOOL_NAMES

    async def test_delete_wlan_marked_destructive(self, mcp_with_wlan):
        # Deleting a WLAN drops every client on that SSID — must flag destructive.
        tools = await mcp_with_wlan.list_tools()
        tool = next(t for t in tools if t.name == "unifi_network_delete_wlan")
        assert tool.annotations.destructive_hint is True


class TestWlanModeGating:
    async def test_readonly_hides_wlan_write_tools(self):
        server = create_server(_full_config(UniFiMode.READONLY))
        names = {t.name for t in await server.list_tools()}
        for w in WRITE_TOOL_NAMES:
            assert w not in names
        for r in READ_TOOL_NAMES:
            assert r in names


class TestWlanClientEndpoints:
    @respx.mock
    async def test_list_wlans_hits_rest_wlanconf(self, network_client):
        respx.get(f"{SITE_PREFIX}/rest/wlanconf").mock(return_value=httpx.Response(200, json={"data": []}))
        result = await network_client.list_wlans()
        assert result == {"data": []}

    @respx.mock
    async def test_get_wlan_hits_rest_wlanconf_id(self, network_client):
        payload = {"data": [{"_id": "w-1"}]}
        respx.get(f"{SITE_PREFIX}/rest/wlanconf/w-1").mock(return_value=httpx.Response(200, json=payload))
        result = await network_client.get_wlan("w-1")
        assert result == payload

    @respx.mock
    async def test_create_wlan_posts_body(self, network_client):
        route = respx.post(f"{SITE_PREFIX}/rest/wlanconf").mock(return_value=httpx.Response(200, json={"data": []}))
        await network_client.create_wlan({"name": "Guest", "security": "wpapsk", "x_passphrase": "pw"})
        body = route.calls[0].request.content
        assert b"Guest" in body
        assert b"wpapsk" in body

    @respx.mock
    async def test_update_wlan_puts_to_id(self, network_client):
        route = respx.put(f"{SITE_PREFIX}/rest/wlanconf/w-1").mock(return_value=httpx.Response(200, json={}))
        await network_client.update_wlan("w-1", {"enabled": False})
        assert route.calls[0].request.content == b'{"enabled":false}' or b"enabled" in route.calls[0].request.content

    @respx.mock
    async def test_delete_wlan_deletes_to_id(self, network_client):
        route = respx.delete(f"{SITE_PREFIX}/rest/wlanconf/w-1").mock(return_value=httpx.Response(204))
        result = await network_client.delete_wlan("w-1")
        assert result == {}
        assert route.call_count == 1
