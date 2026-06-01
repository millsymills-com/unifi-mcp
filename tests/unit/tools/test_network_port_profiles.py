"""Tests for switch port-profile MCP tools (2 read + 4 write). See #93."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
import respx
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from unifi_mcp.clients.network import NetworkClient
from unifi_mcp.config import UniFiConfig, UniFiMode
from unifi_mcp.errors import UniFiError, UniFiNotFoundError
from unifi_mcp.server import create_server
from unifi_mcp.tools.network.port_profiles import register_port_profile_tools

BASE_URL = "https://10.0.0.1:443"
SITE_PREFIX = f"{BASE_URL}/proxy/network/api/s/default"

READ_TOOL_NAMES = {"unifi_network_list_port_profiles", "unifi_network_get_port_profile"}
WRITE_TOOL_NAMES = {
    "unifi_network_create_port_profile",
    "unifi_network_update_port_profile",
    "unifi_network_delete_port_profile",
    "unifi_network_assign_port_profile",
}


@dataclass
class _FakeLifespan:
    config: UniFiConfig
    clients: dict[str, Any] = field(default_factory=dict)


def _ctx(config: UniFiConfig, **clients: Any) -> AsyncMock:
    ctx = AsyncMock()
    ctx.lifespan_context = _FakeLifespan(config=config, clients=clients)
    return ctx


def _config(mode: UniFiMode = UniFiMode.READWRITE) -> UniFiConfig:
    return UniFiConfig(
        _env_file=None,
        unifi_mode=mode,
        unifi_network_api="k",
        unifi_protect_api=None,
        unifi_site_manager_api=None,
    )


@pytest.fixture
def network_client() -> NetworkClient:
    return NetworkClient(base_url=BASE_URL, api_key="test-key", site="default", timeout=5, max_retries=1)


@pytest.fixture
def mcp_with_profiles() -> FastMCP:
    server = FastMCP(name="test-profiles")
    register_port_profile_tools(server)
    return server


class TestPortProfileRegistration:
    async def test_all_tools_registered(self, mcp_with_profiles):
        tools = await mcp_with_profiles.list_tools()
        assert {t.name for t in tools} == READ_TOOL_NAMES | WRITE_TOOL_NAMES

    async def test_write_tools_carry_write_tag(self, mcp_with_profiles):
        tools = await mcp_with_profiles.list_tools()
        for tool in tools:
            if tool.name in WRITE_TOOL_NAMES:
                assert "write" in tool.tags
            else:
                assert "write" not in tool.tags

    @pytest.mark.parametrize(
        "destructive_tool",
        ["unifi_network_delete_port_profile", "unifi_network_assign_port_profile"],
    )
    async def test_destructive_flagged(self, mcp_with_profiles, destructive_tool):
        tools = await mcp_with_profiles.list_tools()
        tool = next(t for t in tools if t.name == destructive_tool)
        assert tool.annotations.destructiveHint is True


class TestPortProfileModeGating:
    async def test_readonly_hides_write_tools(self):
        server = create_server(_config(UniFiMode.READONLY))
        names = {t.name for t in await server.list_tools()}
        for w in WRITE_TOOL_NAMES:
            assert w not in names
        assert "unifi_network_list_port_profiles" in names

    async def test_readwrite_exposes_write_tools(self):
        server = create_server(_config(UniFiMode.READWRITE))
        names = {t.name for t in await server.list_tools()}
        for t in READ_TOOL_NAMES | WRITE_TOOL_NAMES:
            assert t in names


class TestPortProfileClientEndpoints:
    @respx.mock
    async def test_list_port_profiles(self, network_client):
        respx.get(f"{SITE_PREFIX}/rest/portconf").mock(return_value=httpx.Response(200, json={"data": []}))
        assert await network_client.list_port_profiles() == {"data": []}

    @respx.mock
    async def test_get_port_profile(self, network_client):
        respx.get(f"{SITE_PREFIX}/rest/portconf/p-1").mock(
            return_value=httpx.Response(200, json={"data": [{"_id": "p-1"}]})
        )
        assert await network_client.get_port_profile("p-1") == {"data": [{"_id": "p-1"}]}

    @respx.mock
    async def test_create_port_profile(self, network_client):
        route = respx.post(f"{SITE_PREFIX}/rest/portconf").mock(return_value=httpx.Response(200, json={}))
        await network_client.create_port_profile({"name": "guest", "poe_mode": "off", "forward": "all"})
        body = route.calls[0].request.content
        assert b"guest" in body
        assert b"poe_mode" in body

    @respx.mock
    async def test_update_port_profile(self, network_client):
        route = respx.put(f"{SITE_PREFIX}/rest/portconf/p-1").mock(return_value=httpx.Response(200, json={}))
        await network_client.update_port_profile("p-1", {"poe_mode": "off"})
        assert b"poe_mode" in route.calls[0].request.content

    @respx.mock
    async def test_delete_port_profile(self, network_client):
        route = respx.delete(f"{SITE_PREFIX}/rest/portconf/p-1").mock(return_value=httpx.Response(204))
        assert await network_client.delete_port_profile("p-1") == {}
        assert route.call_count == 1


class TestAssignPortProfile:
    @respx.mock
    async def test_assign_splices_override(self, network_client):
        mac = "aa:bb:cc:dd:ee:ff"
        device = {
            "_id": "dev-1",
            "mac": mac,
            "port_overrides": [
                {"port_idx": 1, "portconf_id": "p-old"},
                {"port_idx": 2, "portconf_id": "p-keep"},
            ],
        }
        respx.get(f"{SITE_PREFIX}/stat/device").mock(
            return_value=httpx.Response(200, json={"data": [device]}),
        )
        put_route = respx.put(f"{SITE_PREFIX}/rest/device/dev-1").mock(
            return_value=httpx.Response(200, json={}),
        )

        await network_client.assign_port_profile(mac, port_idx=1, profile_id="p-new")

        # PUT body: port_idx=1 replaced, port_idx=2 preserved.
        import json

        body = json.loads(put_route.calls[0].request.content)
        overrides = {entry["port_idx"]: entry["portconf_id"] for entry in body["port_overrides"]}
        assert overrides == {1: "p-new", 2: "p-keep"}

    @respx.mock
    async def test_assign_to_new_port_appends(self, network_client):
        mac = "aa:bb:cc:dd:ee:ff"
        device = {"_id": "dev-1", "mac": mac, "port_overrides": []}
        respx.get(f"{SITE_PREFIX}/stat/device").mock(
            return_value=httpx.Response(200, json={"data": [device]}),
        )
        put_route = respx.put(f"{SITE_PREFIX}/rest/device/dev-1").mock(
            return_value=httpx.Response(200, json={}),
        )
        await network_client.assign_port_profile(mac, port_idx=5, profile_id="p-1")

        import json

        body = json.loads(put_route.calls[0].request.content)
        assert body["port_overrides"] == [{"port_idx": 5, "portconf_id": "p-1"}]

    @respx.mock
    async def test_assign_unknown_mac_raises_not_found(self, network_client):
        respx.get(f"{SITE_PREFIX}/stat/device").mock(return_value=httpx.Response(200, json={"data": []}))
        # PUT must not be reached.
        put_route = respx.put(f"{SITE_PREFIX}/rest/device/anything").mock(
            return_value=httpx.Response(200, json={}),
        )
        with pytest.raises(UniFiNotFoundError, match="aa:bb"):
            await network_client.assign_port_profile("aa:bb:cc:dd:ee:ff", port_idx=1, profile_id="p-1")
        assert put_route.call_count == 0

    @respx.mock
    async def test_assign_missing_device_id_raises_unifi_error(self, network_client):
        mac = "aa:bb:cc:dd:ee:ff"
        device = {"mac": mac, "port_overrides": []}  # no _id
        respx.get(f"{SITE_PREFIX}/stat/device").mock(
            return_value=httpx.Response(200, json={"data": [device]}),
        )
        with pytest.raises(UniFiError, match="no '_id'"):
            await network_client.assign_port_profile(mac, port_idx=1, profile_id="p-1")


class TestAssignHandlerPlumbing:
    """End-to-end through the MCP tool handler — asserts the config gating
    and client plumbing work from the tool surface.
    """

    async def test_readonly_blocks_assign(self):
        server = FastMCP(name="t")
        register_port_profile_tools(server)
        client = AsyncMock()
        ctx = _ctx(_config(UniFiMode.READONLY), network=client)
        tool = await server.get_tool("unifi_network_assign_port_profile")
        with pytest.raises(ToolError, match="read-only mode"):
            await tool.fn(ctx, mac="aa:bb:cc:dd:ee:ff", port_idx=1, profile_id="p-1")
        client.assign_port_profile.assert_not_awaited()

    async def test_readwrite_forwards_args(self):
        server = FastMCP(name="t")
        register_port_profile_tools(server)
        client = AsyncMock()
        client.assign_port_profile.return_value = {"ok": True}
        ctx = _ctx(_config(UniFiMode.READWRITE), network=client)
        tool = await server.get_tool("unifi_network_assign_port_profile")
        result = await tool.fn(ctx, mac="aa:bb:cc:dd:ee:ff", port_idx=7, profile_id="p-7")
        assert result == {"ok": True}
        client.assign_port_profile.assert_awaited_once_with("aa:bb:cc:dd:ee:ff", 7, "p-7")


class TestListPortProfilesHandler:
    """Drive the read tool through the handler so the redact-and-return path runs."""

    async def test_list_redacts_and_returns(self, mcp_with_profiles):
        client = AsyncMock()
        client.list_port_profiles.return_value = {"data": [{"_id": "p-1", "name": "guest", "x_passphrase": "hunter2"}]}
        ctx = _ctx(_config(UniFiMode.READONLY), network=client)
        tool = await mcp_with_profiles.get_tool("unifi_network_list_port_profiles")
        result = await tool.fn(ctx)
        assert result == {"data": [{"_id": "p-1", "name": "guest", "x_passphrase": "***REDACTED***"}]}
        client.list_port_profiles.assert_awaited_once_with()

    async def test_list_client_error_maps_to_tool_error(self, mcp_with_profiles):
        from unifi_mcp.errors import UniFiServerError

        client = AsyncMock()
        client.list_port_profiles.side_effect = UniFiServerError("controller down")
        ctx = _ctx(_config(UniFiMode.READONLY), network=client)
        tool = await mcp_with_profiles.get_tool("unifi_network_list_port_profiles")
        with pytest.raises(ToolError, match="controller down"):
            await tool.fn(ctx)


class TestCreatePortProfileHandler:
    async def test_readonly_blocks_create(self, mcp_with_profiles):
        client = AsyncMock()
        ctx = _ctx(_config(UniFiMode.READONLY), network=client)
        tool = await mcp_with_profiles.get_tool("unifi_network_create_port_profile")
        with pytest.raises(ToolError, match="read-only mode"):
            await tool.fn(ctx, data={"name": "guest", "poe_mode": "off", "forward": "all"})
        client.create_port_profile.assert_not_awaited()

    async def test_readwrite_forwards_payload(self, mcp_with_profiles):
        client = AsyncMock()
        client.create_port_profile.return_value = {"ok": True}
        ctx = _ctx(_config(UniFiMode.READWRITE), network=client)
        tool = await mcp_with_profiles.get_tool("unifi_network_create_port_profile")
        payload = {"name": "guest", "poe_mode": "off", "forward": "all"}
        result = await tool.fn(ctx, data=payload)
        assert result == {"ok": True}
        client.create_port_profile.assert_awaited_once_with(payload)


class TestUpdatePortProfileHandler:
    async def test_readonly_blocks_update(self, mcp_with_profiles):
        client = AsyncMock()
        ctx = _ctx(_config(UniFiMode.READONLY), network=client)
        tool = await mcp_with_profiles.get_tool("unifi_network_update_port_profile")
        with pytest.raises(ToolError, match="read-only mode"):
            await tool.fn(ctx, profile_id="p-1", data={"poe_mode": "off"})
        client.update_port_profile.assert_not_awaited()

    async def test_readwrite_forwards_payload(self, mcp_with_profiles):
        client = AsyncMock()
        client.update_port_profile.return_value = {"ok": True}
        ctx = _ctx(_config(UniFiMode.READWRITE), network=client)
        tool = await mcp_with_profiles.get_tool("unifi_network_update_port_profile")
        result = await tool.fn(ctx, profile_id="p-1", data={"poe_mode": "off"})
        assert result == {"ok": True}
        client.update_port_profile.assert_awaited_once_with("p-1", {"poe_mode": "off"})


class TestDeletePortProfileHandler:
    async def test_readonly_blocks_delete(self, mcp_with_profiles):
        client = AsyncMock()
        ctx = _ctx(_config(UniFiMode.READONLY), network=client)
        tool = await mcp_with_profiles.get_tool("unifi_network_delete_port_profile")
        with pytest.raises(ToolError, match="read-only mode"):
            await tool.fn(ctx, profile_id="p-1")
        client.delete_port_profile.assert_not_awaited()

    async def test_readwrite_forwards_id(self, mcp_with_profiles):
        client = AsyncMock()
        client.delete_port_profile.return_value = {"ok": True}
        ctx = _ctx(_config(UniFiMode.READWRITE), network=client)
        tool = await mcp_with_profiles.get_tool("unifi_network_delete_port_profile")
        result = await tool.fn(ctx, profile_id="p-1")
        assert result == {"ok": True}
        client.delete_port_profile.assert_awaited_once_with("p-1")
