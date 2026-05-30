"""Tests for Protect NVR MCP tools (1 read)."""

from __future__ import annotations

import httpx
import pytest
import respx
from fastmcp import FastMCP

from unifi_mcp.clients.protect import ProtectClient
from unifi_mcp.config import UniFiConfig, UniFiMode
from unifi_mcp.server import create_server
from unifi_mcp.tools.protect.nvr import register_nvr_tools

BASE_URL = "https://10.0.0.1:443"
PROTECT_PREFIX = f"{BASE_URL}/proxy/protect/integration/v1"

READ_TOOL_NAMES = {"unifi_protect_get_nvr"}


@pytest.fixture
def protect_client_local() -> ProtectClient:
    return ProtectClient(base_url=BASE_URL, api_key="test-key", timeout=5, max_retries=1)


@pytest.fixture
def mcp_with_nvr() -> FastMCP:
    server = FastMCP(name="test-nvr")
    register_nvr_tools(server)
    return server


def _full_config(mode: UniFiMode) -> UniFiConfig:
    return UniFiConfig(
        _env_file=None,
        unifi_mode=mode,
        unifi_network_api="test-net",
        unifi_protect_api="test-prot",
        unifi_site_manager_api=None,
    )


class TestNvrRegistration:
    async def test_all_tools_registered(self, mcp_with_nvr):
        tools = await mcp_with_nvr.list_tools()
        assert {t.name for t in tools} == READ_TOOL_NAMES

    async def test_readonly_exposes_get_nvr(self):
        server = create_server(_full_config(UniFiMode.READONLY))
        names = {t.name for t in await server.list_tools()}
        assert "unifi_protect_get_nvr" in names


class TestNvrClientEndpoints:
    @respx.mock
    async def test_get_nvr(self, protect_client_local):
        respx.get(f"{PROTECT_PREFIX}/nvrs").mock(return_value=httpx.Response(200, json={"name": "nvr-1"}))
        assert await protect_client_local.get_nvr() == {"name": "nvr-1"}
