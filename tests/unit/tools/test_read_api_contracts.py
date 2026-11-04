"""Read API regressions using vendor-shaped IDs and real tool/client boundaries."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
import respx
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from unifi_mcp.clients.network_integration import NetworkIntegrationClient
from unifi_mcp.clients.site_manager import SITE_MANAGER_BASE_URL, SiteManagerClient
from unifi_mcp.tools.network_integration import register_network_integration_tools
from unifi_mcp.tools.site_manager import register_site_manager_tools

SITE = "11111111-2222-3333-4444-555555555555"
SOURCE = "22222222-3333-4444-5555-666666666666"
DESTINATION = "33333333-4444-5555-6666-777777777777"
NETWORK_BASE = "https://192.0.2.1"
SM_PREFIX = f"{SITE_MANAGER_BASE_URL}/v1/"
ORDERING = f"{NETWORK_BASE}/proxy/network/integration/v1/sites/{SITE}/firewall/policies/ordering"


@pytest.fixture
def server():
    srv = FastMCP("read-contract-tests")
    register_site_manager_tools(srv)
    register_network_integration_tools(srv)
    return srv


async def call(server, name, clients, **kwargs: Any):
    tool = await server.get_tool(name)
    ctx = AsyncMock()
    ctx.lifespan_context = SimpleNamespace(clients=clients)
    return await tool.fn(ctx, **kwargs)


@pytest.mark.parametrize("suffix", ["1234", "12345"])
@respx.mock
async def test_listed_composite_host_id_roundtrips_through_host_detail(server, suffix):
    host_id = "A" * 64 + ":" + suffix
    respx.get(f"{SM_PREFIX}hosts").respond(200, json={"data": [{"id": host_id}]})
    detail = respx.get(f"{SM_PREFIX}hosts/{host_id}").respond(200, json={"data": {"id": host_id}})
    client = SiteManagerClient("synthetic-key")
    try:
        listed = await call(server, "unifi_site_manager_list_hosts", {"site_manager": client})
        result = await call(
            server, "unifi_site_manager_get_host", {"site_manager": client}, host_id=listed["data"][0]["id"]
        )
        assert result["data"]["id"] == host_id
        assert detail.calls.last.request.url.raw_path.endswith(("A" * 64 + "%3A" + suffix).encode())
    finally:
        await client.close()


@respx.mock
async def test_filtered_device_tool_selects_only_requested_host(server):
    host_id = "A" * 64 + ":12345"
    other = "B" * 64 + ":67890"

    def devices(request):
        selected = request.url.params.get_list("hostIds[]")
        groups = [{"hostId": host_id, "devices": [{"id": "selected"}]}, {"hostId": other, "devices": [{"id": "other"}]}]
        return httpx.Response(200, json={"data": [g for g in groups if not selected or g["hostId"] in selected]})

    route = respx.get(f"{SM_PREFIX}devices").mock(side_effect=devices)
    client = SiteManagerClient("synthetic-key")
    try:
        result = await call(server, "unifi_site_manager_list_devices", {"site_manager": client}, host_id=host_id)
        assert [g["hostId"] for g in result["data"]] == [host_id]
        assert route.calls.last.request.url.params.get_list("hostIds[]") == [host_id]
        assert "hostId" not in route.calls.last.request.url.params
    finally:
        await client.close()


@pytest.mark.parametrize("name", ["unifi_site_manager_get_host", "unifi_site_manager_list_devices"])
@pytest.mark.parametrize(
    "host_id", ["", "../escape", "a/b", "a?query", "a#fragment", "a%2Fb", "a\n", "a\x00", "a b", "é", "a" * 257]
)
async def test_host_validation_rejects_unsafe_ids_before_client(server, name, host_id):
    client = AsyncMock()
    with pytest.raises(ToolError, match="host_id: invalid id format"):
        await call(server, name, {"site_manager": client}, host_id=host_id)
    client.get_host.assert_not_awaited()
    client.list_devices.assert_not_awaited()


@respx.mock
async def test_firewall_ordering_sends_both_required_zone_queries(server):
    route = respx.get(
        ORDERING, params={"sourceFirewallZoneId": SOURCE, "destinationFirewallZoneId": DESTINATION}
    ).respond(200, json={"orderedFirewallPolicyIds": ["policy-1"]})
    client = NetworkIntegrationClient(NETWORK_BASE, "synthetic-key", site=SITE)
    client._resolved_site = SITE
    try:
        result = await call(
            server,
            "unifi_network_get_firewall_policies_ordering",
            {"network_integration": client},
            source_firewall_zone_id=SOURCE,
            destination_firewall_zone_id=DESTINATION,
        )
        assert result == {"orderedFirewallPolicyIds": ["policy-1"]}
        assert route.calls.last.request.method == "GET"
        assert not route.calls.last.request.content
    finally:
        await client.close()


async def test_firewall_ordering_schema_requires_both_selectors(server):
    tool = await server.get_tool("unifi_network_get_firewall_policies_ordering")
    assert set(tool.parameters["required"]) == {"source_firewall_zone_id", "destination_firewall_zone_id"}
    assert "write" not in tool.tags


@pytest.mark.parametrize("field", ["source_firewall_zone_id", "destination_firewall_zone_id"])
async def test_firewall_ordering_invalid_selector_never_calls_client(server, field):
    client = AsyncMock()
    args = {"source_firewall_zone_id": SOURCE, "destination_firewall_zone_id": DESTINATION, field: "../escape"}
    with pytest.raises(ToolError, match=f"{field}: invalid id format"):
        await call(server, "unifi_network_get_firewall_policies_ordering", {"network_integration": client}, **args)
    client.get_firewall_policies_ordering.assert_not_awaited()
