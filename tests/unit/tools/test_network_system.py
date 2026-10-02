"""Tests for Network system/command MCP tools (1 read + 8 write)."""

from __future__ import annotations

import httpx
import pytest
import respx
from fastmcp import FastMCP

from unifi_mcp.clients.network import NetworkClient
from unifi_mcp.tools.network.system import register_system_tools

BASE_URL = "https://10.0.0.1:443"
SITE_PREFIX = f"{BASE_URL}/proxy/network/api/s/default"

READ_TOOL_NAMES = {"unifi_network_get_settings"}
WRITE_TOOL_NAMES = {
    "unifi_network_update_settings",
    "unifi_network_run_speedtest",
    "unifi_network_create_backup",
    "unifi_network_upgrade_device",
    "unifi_network_power_cycle_port",
    "unifi_network_unauthorize_guest",
    "unifi_network_reset_dpi",
}


@pytest.fixture
def network_client() -> NetworkClient:
    return NetworkClient(base_url=BASE_URL, api_key="test-key", site="default", timeout=5, max_retries=1)


@pytest.fixture
def mcp_with_system() -> FastMCP:
    server = FastMCP(name="test-system")
    register_system_tools(server)
    return server


class TestSystemToolRegistration:
    async def test_all_tools_registered(self, mcp_with_system):
        tools = await mcp_with_system.list_tools()
        assert {t.name for t in tools} == READ_TOOL_NAMES | WRITE_TOOL_NAMES

    @pytest.mark.parametrize(
        "tool_name",
        [
            # Destructive per #49/#50.
            "unifi_network_upgrade_device",
            "unifi_network_power_cycle_port",
            # reset-dpi discards state.
            "unifi_network_reset_dpi",
        ],
    )
    async def test_destructive_writes_flagged(self, mcp_with_system, tool_name):
        tools = await mcp_with_system.list_tools()
        tool = next(t for t in tools if t.name == tool_name)
        assert tool.annotations.destructive_hint is True


class TestSystemCommandEndpoints:
    @respx.mock
    async def test_get_settings(self, network_client):
        respx.get(f"{SITE_PREFIX}/rest/setting").mock(return_value=httpx.Response(200, json={"data": []}))
        assert await network_client.get_settings() == {"data": []}

    @respx.mock
    async def test_run_speedtest_posts_cmd_devmgr(self, network_client):
        route = respx.post(f"{SITE_PREFIX}/cmd/devmgr").mock(return_value=httpx.Response(200, json={}))
        await network_client.run_speedtest()
        assert b"speedtest" in route.calls[0].request.content

    @respx.mock
    async def test_create_backup_posts_cmd_backup(self, network_client):
        route = respx.post(f"{SITE_PREFIX}/cmd/backup").mock(return_value=httpx.Response(200, json={}))
        await network_client.create_backup()
        assert b"backup" in route.calls[0].request.content

    @respx.mock
    async def test_upgrade_device_posts_cmd_devmgr(self, network_client):
        route = respx.post(f"{SITE_PREFIX}/cmd/devmgr").mock(return_value=httpx.Response(200, json={}))
        await network_client.upgrade_device("aa:bb:cc:dd:ee:ff")
        body = route.calls[0].request.content
        assert b"upgrade" in body
        assert b"aa:bb:cc:dd:ee:ff" in body

    @respx.mock
    async def test_power_cycle_port_posts_port_idx(self, network_client):
        route = respx.post(f"{SITE_PREFIX}/cmd/devmgr").mock(return_value=httpx.Response(200, json={}))
        await network_client.power_cycle_port("aa:bb:cc:dd:ee:ff", 5)
        body = route.calls[0].request.content
        assert b"power-cycle" in body
        assert b'"port_idx":5' in body

    @respx.mock
    async def test_reset_dpi(self, network_client):
        route = respx.post(f"{SITE_PREFIX}/cmd/stat").mock(return_value=httpx.Response(200, json={}))
        await network_client.reset_dpi()
        assert b"reset-dpi" in route.calls[0].request.content

    @respx.mock
    async def test_update_settings_dispatches_per_section(self, network_client):
        route = respx.put(f"{SITE_PREFIX}/rest/setting/ntp").mock(return_value=httpx.Response(200, json={}))
        await network_client.update_settings({"ntp": {"ntp_server_1": "0.example.com"}})
        assert route.call_count == 1
