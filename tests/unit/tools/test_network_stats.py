"""Tests for Network stats MCP tools (read-only)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
import respx
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from unifi_mcp.clients.network import NetworkClient
from unifi_mcp.errors import (
    UniFiAuthError,
    UniFiBadRequestError,
    UniFiNotFoundError,
    UniFiServerError,
    UniFiUnsupportedError,
)
from unifi_mcp.tools.network.stats import register_stats_tools

BASE_URL = "https://10.0.0.1:443"
SITE_PREFIX = f"{BASE_URL}/proxy/network/api/s/default"


@pytest.fixture
def network_client() -> NetworkClient:
    return NetworkClient(base_url=BASE_URL, api_key="test-key", site="default", timeout=5, max_retries=1)


@pytest.fixture
def mcp_with_stats() -> FastMCP:
    """FastMCP with the stats tools registered (no client context wired)."""
    server = FastMCP(name="test-stats")
    register_stats_tools(server)
    return server


class TestStatsToolRegistration:
    async def test_all_stats_tools_registered(self, mcp_with_stats):
        tools = await mcp_with_stats.list_tools()
        names = {t.name for t in tools}
        assert names == {
            "unifi_network_get_health",
            "unifi_network_list_events",
            "unifi_network_list_devices",
            "unifi_network_list_devices_basic",
            "unifi_network_list_active_clients",
            "unifi_network_list_configured_clients",
            "unifi_network_list_all_clients",
            "unifi_network_get_dpi_stats",
            "unifi_network_get_sysinfo",
        }

    async def test_stats_tools_have_network_tag(self, mcp_with_stats):
        tools = await mcp_with_stats.list_tools()
        for tool in tools:
            if tool.name.startswith("unifi_network_"):
                assert "network" in tool.tags

    async def test_stats_tools_not_tagged_write(self, mcp_with_stats):
        # Every stats tool is read-only, so none should carry the write tag.
        tools = await mcp_with_stats.list_tools()
        for tool in tools:
            assert "write" not in tool.tags


class TestStatsClientEndpoints:
    """Verify the stats tools call the correct UniFi endpoints via NetworkClient.

    We exercise the client layer directly because the tool layer is a thin
    delegator — proving the tool registers plus the client hits the right URL
    covers the happy path end-to-end.
    """

    @respx.mock
    async def test_get_health_hits_stat_health(self, network_client):
        route = respx.get(f"{SITE_PREFIX}/stat/health").mock(
            return_value=httpx.Response(200, json={"data": [{"subsystem": "wlan"}]})
        )
        result = await network_client.get_health()
        assert result == {"data": [{"subsystem": "wlan"}]}
        assert route.call_count == 1

    @respx.mock
    async def test_list_devices_hits_stat_device(self, network_client):
        respx.get(f"{SITE_PREFIX}/stat/device").mock(return_value=httpx.Response(200, json={"data": []}))
        result = await network_client.list_devices()
        assert result == {"data": []}

    @respx.mock
    async def test_list_events_passes_limit(self, network_client):
        route = respx.get(f"{SITE_PREFIX}/list/alarm").mock(return_value=httpx.Response(200, json={"data": []}))
        await network_client.list_events(limit=25)
        assert route.calls[0].request.url.params["_limit"] == "25"

    @respx.mock
    async def test_get_dpi_stats_passes_type(self, network_client):
        route = respx.get(f"{SITE_PREFIX}/stat/dpi").mock(return_value=httpx.Response(200, json={"data": []}))
        await network_client.get_dpi_stats(dpi_type="by_cat")
        assert route.calls[0].request.url.params["type"] == "by_cat"

    @respx.mock
    async def test_list_all_clients_hits_stat_alluser_with_defaults(self, network_client):
        route = respx.get(f"{SITE_PREFIX}/stat/alluser").mock(return_value=httpx.Response(200, json={"data": []}))
        await network_client.list_all_clients()
        assert route.calls[0].request.url.params["type"] == "all"
        assert route.calls[0].request.url.params["conn"] == "all"

    @respx.mock
    async def test_get_sysinfo_hits_stat_sysinfo(self, network_client):
        payload = {"data": [{"version": "7"}]}
        respx.get(f"{SITE_PREFIX}/stat/sysinfo").mock(return_value=httpx.Response(200, json=payload))
        result = await network_client.get_sysinfo()
        assert result == payload


class TestEventReadCompatibility:
    @pytest.mark.parametrize(
        ("status", "message"),
        [(400, "api.err.InvalidObject"), (404, "api.err.NotFound")],
    )
    @respx.mock
    async def test_unsupported_controller_reports_capability_error(self, network_client, status, message):
        route = respx.get(f"{SITE_PREFIX}/list/alarm").mock(
            return_value=httpx.Response(status, json={"meta": {"rc": "error", "msg": message}})
        )
        with pytest.raises(UniFiUnsupportedError, match="Network event reads are unavailable") as caught:
            await network_client.list_events(limit=3)
        assert caught.value.status_code == status
        assert isinstance(caught.value.__cause__, (UniFiBadRequestError, UniFiNotFoundError))
        assert route.call_count == 1  # No retries or fallback to a different resource.

    @pytest.mark.parametrize(
        ("status", "message", "error_type"),
        [
            (400, "api.err.InvalidValue", UniFiBadRequestError),
            (401, "api.err.LoginRequired", UniFiAuthError),
            (403, "api.err.NoPermission", UniFiAuthError),
            (500, "api.err.InternalServerError", UniFiServerError),
        ],
    )
    @respx.mock
    async def test_other_errors_keep_their_classification(self, network_client, status, message, error_type):
        respx.get(f"{SITE_PREFIX}/list/alarm").mock(
            return_value=httpx.Response(status, json={"meta": {"rc": "error", "msg": message}})
        )
        with pytest.raises(error_type) as caught:
            await network_client.list_events()
        assert caught.value.status_code == status

    @pytest.mark.parametrize("status", [400, 404])
    @respx.mock
    async def test_unsupported_error_reaches_tool_caller(self, mcp_with_stats, network_client, status):
        message = "api.err.InvalidObject" if status == 400 else "api.err.NotFound"
        respx.get(f"{SITE_PREFIX}/list/alarm").mock(
            return_value=httpx.Response(status, json={"meta": {"rc": "error", "msg": message}})
        )
        ctx = AsyncMock()
        ctx.lifespan_context = SimpleNamespace(
            config=SimpleNamespace(unifi_max_list_items=1000), clients={"network": network_client}
        )
        tool = await mcp_with_stats.get_tool("unifi_network_list_events")
        with pytest.raises(ToolError, match=rf"\[HTTP {status}\] Unsupported operation: Network event reads"):
            await tool.fn(ctx, limit=3)
