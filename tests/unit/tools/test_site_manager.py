"""Tests for Site Manager MCP tools."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
import respx
from fastmcp import FastMCP

from unifi_mcp.clients.site_manager import SITE_MANAGER_BASE_URL, SiteManagerClient
from unifi_mcp.errors import UniFiAuthError
from unifi_mcp.tools.site_manager.discovery import register_site_manager_tools

API_PREFIX = f"{SITE_MANAGER_BASE_URL}/v1/"
FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent / "fixtures"


@pytest.fixture
def fixtures():
    with (FIXTURES_DIR / "site_manager_responses.json").open() as f:
        return json.load(f)


@pytest.fixture
def sm_client():
    return SiteManagerClient(api_key="test-key", timeout=5, max_retries=1)


@dataclass
class FakeLifespanContext:
    clients: dict[str, Any] = field(default_factory=dict)


@pytest.fixture
def mcp_server(sm_client):
    """Create a FastMCP server with site manager tools registered."""
    server = FastMCP(name="test-server")
    register_site_manager_tools(server)
    return server


@pytest.fixture
def fake_ctx(sm_client):
    """Create a fake context with the site manager client."""
    ctx = AsyncMock()
    ctx.lifespan_context = FakeLifespanContext(clients={"site_manager": sm_client})
    return ctx


class TestSiteManagerListHosts:
    @respx.mock
    async def test_list_hosts_returns_hosts(self, fake_ctx, fixtures):
        respx.get(f"{API_PREFIX}hosts").mock(return_value=httpx.Response(200, json=fixtures["list_hosts"]))
        # Call the tool function directly through the client
        client = fake_ctx.lifespan_context.clients["site_manager"]
        result = await client.list_hosts()
        assert result == fixtures["list_hosts"]
        assert len(result["data"]) == 1
        assert result["data"][0]["id"] == "host-1"
        assert result["data"][0]["name"] == "UDR Ultra"


class TestSiteManagerListSites:
    @respx.mock
    async def test_list_sites_returns_sites(self, fake_ctx, fixtures):
        respx.get(f"{API_PREFIX}sites").mock(return_value=httpx.Response(200, json=fixtures["list_sites"]))
        client = fake_ctx.lifespan_context.clients["site_manager"]
        result = await client.list_sites()
        assert result == fixtures["list_sites"]
        assert len(result["data"]) == 1
        assert result["data"][0]["id"] == "site-1"
        assert result["data"][0]["name"] == "Default"


class TestSiteManagerListDevices:
    @respx.mock
    async def test_list_devices_returns_devices(self, fake_ctx, fixtures):
        respx.get(f"{API_PREFIX}devices").mock(return_value=httpx.Response(200, json=fixtures["list_devices"]))
        client = fake_ctx.lifespan_context.clients["site_manager"]
        result = await client.list_devices()
        assert result == fixtures["list_devices"]
        assert len(result["data"]) == 1
        assert result["data"][0]["id"] == "dev-1"
        assert result["data"][0]["mac"] == "aa:bb:cc:dd:ee:ff"

    @respx.mock
    async def test_list_devices_with_host_id_filter(self, fake_ctx, fixtures):
        route = respx.get(f"{API_PREFIX}devices").mock(return_value=httpx.Response(200, json=fixtures["list_devices"]))
        client = fake_ctx.lifespan_context.clients["site_manager"]
        result = await client.list_devices(host_id="host-1")
        assert result == fixtures["list_devices"]
        assert route.calls[0].request.url.params["hostIds[]"] == "host-1"


class TestSiteManagerAuthError:
    @respx.mock
    async def test_auth_error_returns_proper_error(self, fake_ctx):
        respx.get(f"{API_PREFIX}hosts").mock(return_value=httpx.Response(401, text="Unauthorized"))
        client = fake_ctx.lifespan_context.clients["site_manager"]
        with pytest.raises(UniFiAuthError, match="401"):
            await client.list_hosts()


class TestToolRegistration:
    async def test_tools_are_registered(self, mcp_server):
        """Verify all three site manager tools are registered."""
        tools = await mcp_server.list_tools()
        tool_names = {t.name for t in tools}
        assert "unifi_site_manager_list_hosts" in tool_names
        assert "unifi_site_manager_list_sites" in tool_names
        assert "unifi_site_manager_list_devices" in tool_names

    async def test_tools_have_site_manager_tag(self, mcp_server):
        """Verify tools are tagged with site_manager."""
        tools = await mcp_server.list_tools()
        for tool in tools:
            if tool.name.startswith("unifi_site_manager_"):
                assert "site_manager" in tool.tags
