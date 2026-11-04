"""Keep legacy config IDs distinct from official Integration network UUIDs."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
import respx
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from unifi_mcp.clients.network_integration import NetworkIntegrationClient
from unifi_mcp.config import UniFiConfig
from unifi_mcp.tools.network.networks import register_network_config_tools
from unifi_mcp.tools.network_integration.networks import register_networks_tools

BASE = "https://192.0.2.1"
SITE = "11111111-2222-3333-4444-555555555555"
NETWORK = "22222222-3333-4444-5555-666666666666"
PREFIX = f"{BASE}/proxy/network/integration/v1/sites/{SITE}/"
LEGACY = "0123456789abcdef01234567"


@pytest.fixture
def server():
    s = FastMCP("network-id-contract")
    register_network_config_tools(s)
    register_networks_tools(s)
    return s


def context(**clients):
    c = AsyncMock()
    c.lifespan_context = SimpleNamespace(clients=clients, config=UniFiConfig(_env_file=None))
    return c


async def call(server, name, ctx, **kwargs: Any):
    tool = await server.get_tool(name)
    return await tool.fn(ctx, **kwargs)


async def test_default_keeps_legacy_response_and_does_not_call_integration(server):
    legacy = AsyncMock()
    integration = AsyncMock()
    legacy.list_networks.return_value = {"data": [{"_id": LEGACY}]}
    result = await call(server, "unifi_network_list_networks", context(network=legacy, network_integration=integration))
    assert result == {"data": [{"_id": LEGACY}]}
    legacy.list_networks.assert_awaited_once_with()
    integration.list_networks.assert_not_awaited()


@respx.mock
async def test_integration_discovery_ids_roundtrip_to_references(server):
    page = {"data": [{"id": NETWORK, "name": "synthetic"}], "offset": 3, "limit": 10, "count": 1, "totalCount": 4}
    inventory = respx.get(PREFIX + "networks", params={"offset": 3, "limit": 10}).respond(200, json=page)
    references = respx.get(PREFIX + f"networks/{NETWORK}/references").respond(200, json={"data": []})
    c = NetworkIntegrationClient(BASE, "synthetic", site=SITE)
    c._resolved_site = SITE
    try:
        ctx = context(network=AsyncMock(), network_integration=c)
        result = await call(server, "unifi_network_list_networks", ctx, api_surface="integration", offset=3, limit=10)
        assert result == page
        assert await call(server, "unifi_network_get_network_references", ctx, network_id=result["data"][0]["id"]) == {
            "data": []
        }
        assert inventory.calls.last.request.method == references.calls.last.request.method == "GET"
        assert not inventory.calls.last.request.content
        assert not references.calls.last.request.content
    finally:
        await c.close()


async def test_unavailable_integration_does_not_fallback_or_guess_ids(server):
    legacy = AsyncMock()
    with pytest.raises(ToolError, match="unavailable; no legacy-ID fallback"):
        await call(server, "unifi_network_list_networks", context(network=legacy), api_surface="integration")
    legacy.list_networks.assert_not_awaited()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"api_surface": "legacy", "offset": 1},
        {"api_surface": "legacy", "limit": 10},
        {"api_surface": "integration", "limit": 0},
        {"api_surface": "integration", "limit": 1001},
        {"api_surface": "integration", "offset": -1},
    ],
)
async def test_invalid_pagination_never_contacts_either_backend(server, kwargs):
    legacy = AsyncMock()
    integration = AsyncMock()
    with pytest.raises(ToolError):
        await call(
            server, "unifi_network_list_networks", context(network=legacy, network_integration=integration), **kwargs
        )
    legacy.list_networks.assert_not_awaited()
    integration.list_networks.assert_not_awaited()


@pytest.mark.parametrize("network_id", [LEGACY, "net-1", "2" * 32, "{" + NETWORK + "}", "urn:uuid:" + NETWORK])
async def test_non_integration_ids_rejected_before_client(server, network_id):
    c = AsyncMock()
    with pytest.raises(ToolError, match=r"network_id: (expected an Integration network UUID|invalid id format)"):
        await call(
            server, "unifi_network_get_network_references", context(network_integration=c), network_id=network_id
        )
    c.get_network_references.assert_not_awaited()


@respx.mock
async def test_modern_uuid_http500_remains_upstream_server_error(server):
    route = respx.get(PREFIX + f"networks/{NETWORK}/references").respond(500, json={"message": "synthetic failure"})
    c = NetworkIntegrationClient(BASE, "synthetic", site=SITE, max_retries=1)
    c._resolved_site = SITE
    try:
        with pytest.raises(ToolError, match=r"\[HTTP 500\] UniFi server error"):
            await call(
                server, "unifi_network_get_network_references", context(network_integration=c), network_id=NETWORK
            )
        assert route.call_count == 1
    finally:
        await c.close()


async def test_discovery_schema_exposes_explicit_surface_enum_without_new_tool(server):
    tool = await server.get_tool("unifi_network_list_networks")
    assert tool.parameters["properties"]["api_surface"]["enum"] == ["legacy", "integration"]
    assert tool.parameters["properties"]["api_surface"]["default"] == "legacy"
    assert "write" not in tool.tags
