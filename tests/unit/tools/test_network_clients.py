"""Tests for Network client MCP tools (1 read + 4 write)."""

from __future__ import annotations

import httpx
import pytest
import respx
from fastmcp import FastMCP

from unifi_mcp.clients.network import NetworkClient
from unifi_mcp.config import UniFiConfig, UniFiMode
from unifi_mcp.server import create_server
from unifi_mcp.tools.network.clients import register_client_tools

BASE_URL = "https://10.0.0.1:443"
SITE_PREFIX = f"{BASE_URL}/proxy/network/api/s/default"

READ_TOOL_NAMES = {"unifi_network_get_client"}
WRITE_TOOL_NAMES = {
    "unifi_network_block_client",
    "unifi_network_unblock_client",
    "unifi_network_kick_client",
    "unifi_network_authorize_guest",
}


@pytest.fixture
def network_client() -> NetworkClient:
    return NetworkClient(base_url=BASE_URL, api_key="test-key", site="default", timeout=5, max_retries=1)


@pytest.fixture
def mcp_with_clients() -> FastMCP:
    server = FastMCP(name="test-clients")
    register_client_tools(server)
    return server


def _full_config(mode: UniFiMode) -> UniFiConfig:
    return UniFiConfig(
        _env_file=None,
        unifi_mode=mode,
        unifi_network_api="test-net",
        unifi_protect_api=None,
        unifi_site_manager_api=None,
    )


class TestClientToolRegistration:
    async def test_all_client_tools_registered(self, mcp_with_clients):
        tools = await mcp_with_clients.list_tools()
        assert {t.name for t in tools} == READ_TOOL_NAMES | WRITE_TOOL_NAMES

    async def test_write_tools_carry_write_tag(self, mcp_with_clients):
        tools = await mcp_with_clients.list_tools()
        for tool in tools:
            if tool.name in WRITE_TOOL_NAMES:
                assert "write" in tool.tags
            else:
                assert "write" not in tool.tags

    async def test_block_client_marked_destructive(self, mcp_with_clients):
        # Blocking a client is a real disruption — should carry destructiveHint.
        tools = await mcp_with_clients.list_tools()
        tool = next(t for t in tools if t.name == "unifi_network_block_client")
        assert tool.annotations.destructive_hint is True


class TestClientModeGating:
    async def test_readonly_hides_client_write_tools(self):
        server = create_server(_full_config(UniFiMode.READONLY))
        names = {t.name for t in await server.list_tools()}
        for w in WRITE_TOOL_NAMES:
            assert w not in names
        assert "unifi_network_get_client" in names

    async def test_readwrite_exposes_client_write_tools(self):
        server = create_server(_full_config(UniFiMode.READWRITE))
        names = {t.name for t in await server.list_tools()}
        for t in READ_TOOL_NAMES | WRITE_TOOL_NAMES:
            assert t in names


class TestClientCommandEndpoints:
    @pytest.mark.parametrize(
        ("method_name", "expected_cmd", "needs_precheck"),
        [
            # block/unblock now pre-check the MAC against the client list (#96).
            ("block_client", b"block-sta", True),
            ("unblock_client", b"unblock-sta", True),
            # kick_client relies on the controller's own validation.
            ("kick_client", b"kick-sta", False),
        ],
    )
    @respx.mock
    async def test_client_command(self, network_client, method_name, expected_cmd, needs_precheck):
        mac = "aa:bb:cc:dd:ee:ff"
        if needs_precheck:
            respx.get(f"{SITE_PREFIX}/stat/alluser").mock(
                return_value=httpx.Response(200, json={"data": [{"mac": mac}]}),
            )
        route = respx.post(f"{SITE_PREFIX}/cmd/stamgr").mock(
            return_value=httpx.Response(200, json={"meta": {"rc": "ok"}}),
        )
        await getattr(network_client, method_name)(mac)
        body = route.calls[0].request.content
        assert expected_cmd in body
        assert mac.encode() in body

    @respx.mock
    async def test_authorize_guest_passes_minutes(self, network_client):
        mac = "aa:bb:cc:dd:ee:ff"
        respx.get(f"{SITE_PREFIX}/stat/alluser").mock(
            return_value=httpx.Response(200, json={"data": [{"mac": mac, "is_guest": True}]}),
        )
        route = respx.post(f"{SITE_PREFIX}/cmd/stamgr").mock(return_value=httpx.Response(200, json={}))
        await network_client.authorize_guest(mac, minutes=120)
        body = route.calls[0].request.content
        assert b"authorize-guest" in body
        assert b"120" in body
