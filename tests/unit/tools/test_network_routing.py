"""Tests for Network static-route MCP tools (2 read + 3 write)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest
import respx
from fastmcp import FastMCP

from unifi_mcp.clients.network import NetworkClient
from unifi_mcp.tools.network.routing import register_routing_tools

BASE_URL = "https://10.0.0.1:443"
SITE_PREFIX = f"{BASE_URL}/proxy/network/api/s/default"

ALL_TOOLS = {
    "unifi_network_list_routes",
    "unifi_network_get_route",
    "unifi_network_create_route",
    "unifi_network_update_route",
    "unifi_network_delete_route",
}


@pytest.fixture
def network_client() -> NetworkClient:
    return NetworkClient(base_url=BASE_URL, api_key="test-key", site="default", timeout=5, max_retries=1)


@pytest.fixture
def mcp_with_routing() -> FastMCP:
    server = FastMCP(name="test-routing")
    register_routing_tools(server)
    return server


class TestRoutingRegistration:
    async def test_all_tools_registered(self, mcp_with_routing):
        tools = await mcp_with_routing.list_tools()
        assert {t.name for t in tools} == ALL_TOOLS

    async def test_delete_marked_destructive(self, mcp_with_routing):
        tools = await mcp_with_routing.list_tools()
        tool = next(t for t in tools if t.name == "unifi_network_delete_route")
        assert tool.annotations.destructive_hint is True


class TestRoutingClientEndpoints:
    @respx.mock
    async def test_list_routes(self, network_client):
        respx.get(f"{SITE_PREFIX}/rest/routing").mock(return_value=httpx.Response(200, json={"data": []}))
        assert await network_client.list_routes() == {"data": []}

    @respx.mock
    async def test_get_route(self, network_client):
        respx.get(f"{SITE_PREFIX}/rest/routing/r-1").mock(return_value=httpx.Response(200, json={"data": []}))
        assert await network_client.get_route("r-1") == {"data": []}

    @respx.mock
    async def test_create_route(self, network_client):
        route = respx.post(f"{SITE_PREFIX}/rest/routing").mock(return_value=httpx.Response(200, json={}))
        await network_client.create_route({"name": "to-10", "gateway_ip": "10.0.0.254"})
        assert b"to-10" in route.calls[0].request.content

    @respx.mock
    async def test_update_route(self, network_client):
        route = respx.put(f"{SITE_PREFIX}/rest/routing/r-1").mock(return_value=httpx.Response(200, json={}))
        await network_client.update_route("r-1", {"enabled": False})
        assert b"enabled" in route.calls[0].request.content

    @respx.mock
    async def test_delete_route(self, network_client):
        route = respx.delete(f"{SITE_PREFIX}/rest/routing/r-1").mock(return_value=httpx.Response(204))
        assert await network_client.delete_route("r-1") == {}
        assert route.call_count == 1


class TestCreateRoutePayloadShape:
    """Pin the controller-accepted payload shape for unifi_network_create_route.

    Live-verified against UCK-Ultra (Network 9.x) on 2026-05-19 — the
    controller rejects flat keys (``network``, ``gateway_ip``) with
    ``api.err.InvalidPayload`` and requires ``type=static-route`` plus
    ``static-route_*`` prefixed sub-fields. See issue #257.
    """

    async def _invoke_create_route(self, **kwargs):
        from dataclasses import dataclass, field
        from typing import Any

        from unifi_mcp.config import UniFiConfig, UniFiMode

        @dataclass
        class _FakeLifespan:
            config: UniFiConfig
            clients: dict[str, Any] = field(default_factory=dict)

        server = FastMCP(name="route-test")
        register_routing_tools(server)

        client = AsyncMock()
        client.create_route.return_value = {"data": [{"_id": "r-1"}]}

        config = UniFiConfig(
            _env_file=None,
            unifi_mode=UniFiMode.READWRITE,
            unifi_network_api="k",
            unifi_protect_api=None,
            unifi_site_manager_api=None,
        )
        ctx = AsyncMock()
        ctx.lifespan_context = _FakeLifespan(config=config, clients={"network": client})

        tool = await server.get_tool("unifi_network_create_route")
        await tool.fn(ctx, **kwargs)
        (forwarded,), _ = client.create_route.call_args
        return forwarded

    async def test_nexthop_route_payload(self):
        sent = await self._invoke_create_route(
            name="to-10",
            network="10.0.0.0/24",
            gateway_ip="192.168.1.1",
        )
        assert sent["type"] == "static-route"
        assert sent["name"] == "to-10"
        assert sent["static-route_type"] == "nexthop-route"
        assert sent["static-route_network"] == "10.0.0.0/24"
        assert sent["static-route_nexthop"] == "192.168.1.1"
        assert sent["static-route_distance"] == 1
        assert "network" not in sent
        assert "gateway_ip" not in sent

    async def test_interface_route_payload(self):
        sent = await self._invoke_create_route(
            name="via-eth1",
            network="10.0.0.0/24",
            route_type="interface-route",
            interface="eth1",
        )
        assert sent["static-route_type"] == "interface-route"
        assert sent["static-route_interface"] == "eth1"
        assert "static-route_nexthop" not in sent
        assert "interface" not in sent
