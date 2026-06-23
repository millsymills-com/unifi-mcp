"""Tool-layer tests for the Phase 1 Site Manager read tools (#406).

Covers the six new read tools: host detail, ISP metrics (get + pure-query
POST), and the SD-WAN early-access trio. Exercises the tool layer directly via
``tool.fn`` so the metric_type allowlist, ``validate_id`` gates, redaction wrap,
and the 404 → ``ToolError`` error funnel are asserted, not just the client.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
import respx
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from unifi_mcp.clients.site_manager import SITE_MANAGER_BASE_URL, SiteManagerClient
from unifi_mcp.tools.site_manager import register_site_manager_tools

API_PREFIX = f"{SITE_MANAGER_BASE_URL}/v1/"
EA_PREFIX = f"{SITE_MANAGER_BASE_URL}/ea/"


@dataclass
class _FakeLifespan:
    clients: dict[str, Any] = field(default_factory=dict)


@pytest.fixture
def sm_client():
    return SiteManagerClient(api_key="test-key", timeout=5, max_retries=1)


@pytest.fixture
def server():
    srv = FastMCP(name="test-server")
    register_site_manager_tools(srv)
    return srv


@pytest.fixture
def ctx(sm_client):
    fake = AsyncMock()
    fake.lifespan_context = _FakeLifespan(clients={"site_manager": sm_client})
    return fake


async def _fn(server, name):
    tool = await server.get_tool(name)
    return tool.fn


class TestNewToolsRegistered:
    async def test_all_six_present_and_read_only(self, server):
        tools = await server.list_tools()
        names = {t.name for t in tools}
        expected = {
            "unifi_site_manager_get_host",
            "unifi_site_manager_get_isp_metrics",
            "unifi_site_manager_query_isp_metrics",
            "unifi_site_manager_list_sdwan_configs",
            "unifi_site_manager_get_sdwan_config",
            "unifi_site_manager_get_sdwan_config_status",
        }
        assert expected <= names
        for tool in tools:
            if tool.name in expected:
                assert "write" not in tool.tags
                assert "site_manager" in tool.tags


class TestGetHost:
    @respx.mock
    async def test_returns_redacted_response(self, server, ctx):
        respx.get(f"{API_PREFIX}hosts/host-1").mock(
            return_value=httpx.Response(200, json={"data": {"id": "host-1", "apiKey": "supersecret-token-value"}})
        )
        fn = await _fn(server, "unifi_site_manager_get_host")
        result = await fn(ctx, host_id="host-1")
        assert result["data"]["id"] == "host-1"
        assert result["data"]["apiKey"] != "supersecret-token-value"

    async def test_invalid_host_id_rejected_before_http(self, server, ctx):
        fn = await _fn(server, "unifi_site_manager_get_host")
        with pytest.raises(ToolError):
            await fn(ctx, host_id="../escape")

    @respx.mock
    async def test_404_becomes_tool_error(self, server, ctx):
        respx.get(f"{API_PREFIX}hosts/missing").mock(return_value=httpx.Response(404, json={"message": "nope"}))
        fn = await _fn(server, "unifi_site_manager_get_host")
        with pytest.raises(ToolError):
            await fn(ctx, host_id="missing")


class TestGetIspMetrics:
    @respx.mock
    async def test_valid_metric_type(self, server, ctx):
        respx.get(f"{API_PREFIX}isp-metrics/5m").mock(return_value=httpx.Response(200, json={"data": []}))
        fn = await _fn(server, "unifi_site_manager_get_isp_metrics")
        result = await fn(ctx, metric_type="5m")
        assert result == {"data": []}

    async def test_rejects_metric_type_not_in_allowlist(self, server, ctx):
        fn = await _fn(server, "unifi_site_manager_get_isp_metrics")
        with pytest.raises(ToolError):
            await fn(ctx, metric_type="1d")

    async def test_rejects_id_shaped_but_invalid_metric_type(self, server, ctx):
        # "5m" passes a generic id regex; an arbitrary id-shaped value must
        # still be rejected by the explicit allowlist before any HTTP call.
        fn = await _fn(server, "unifi_site_manager_get_isp_metrics")
        with pytest.raises(ToolError):
            await fn(ctx, metric_type="hourly")


class TestQueryIspMetrics:
    @respx.mock
    async def test_pure_query_posts_body(self, server, ctx):
        route = respx.post(f"{API_PREFIX}isp-metrics/1h/query").mock(
            return_value=httpx.Response(200, json={"data": [{"x": 1}]})
        )
        fn = await _fn(server, "unifi_site_manager_query_isp_metrics")
        result = await fn(ctx, metric_type="1h", sites=[{"hostId": "h-1"}])
        assert route.called
        assert result == {"data": [{"x": 1}]}

    async def test_rejects_bad_metric_type(self, server, ctx):
        fn = await _fn(server, "unifi_site_manager_query_isp_metrics")
        with pytest.raises(ToolError):
            await fn(ctx, metric_type="bogus", sites=[])


class TestSdwanTools:
    @respx.mock
    async def test_list_redacts_psk(self, server, ctx):
        respx.get(f"{EA_PREFIX}sd-wan-configs").mock(
            return_value=httpx.Response(200, json={"data": [{"id": "c1", "wpaPsk": "leak-this-key"}]})
        )
        fn = await _fn(server, "unifi_site_manager_list_sdwan_configs")
        result = await fn(ctx)
        assert result["data"][0]["wpaPsk"] != "leak-this-key"

    @respx.mock
    async def test_get_config(self, server, ctx):
        respx.get(f"{EA_PREFIX}sd-wan-configs/c1").mock(return_value=httpx.Response(200, json={"data": {"id": "c1"}}))
        fn = await _fn(server, "unifi_site_manager_get_sdwan_config")
        result = await fn(ctx, config_id="c1")
        assert result["data"]["id"] == "c1"

    @respx.mock
    async def test_get_config_status(self, server, ctx):
        respx.get(f"{EA_PREFIX}sd-wan-configs/c1/status").mock(
            return_value=httpx.Response(200, json={"data": {"state": "DEPLOYED"}})
        )
        fn = await _fn(server, "unifi_site_manager_get_sdwan_config_status")
        result = await fn(ctx, config_id="c1")
        assert result["data"]["state"] == "DEPLOYED"

    async def test_invalid_config_id_rejected(self, server, ctx):
        fn = await _fn(server, "unifi_site_manager_get_sdwan_config")
        with pytest.raises(ToolError):
            await fn(ctx, config_id="bad/id")

    @respx.mock
    async def test_get_config_404_becomes_tool_error(self, server, ctx):
        respx.get(f"{EA_PREFIX}sd-wan-configs/missing").mock(return_value=httpx.Response(404, json={"message": "nope"}))
        fn = await _fn(server, "unifi_site_manager_get_sdwan_config")
        with pytest.raises(ToolError):
            await fn(ctx, config_id="missing")
