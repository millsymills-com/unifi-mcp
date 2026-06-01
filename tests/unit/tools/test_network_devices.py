"""Tests for Network device MCP tools (1 read + 5 write)."""

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
from unifi_mcp.server import create_server
from unifi_mcp.tools.network.devices import register_device_tools


@dataclass
class _FakeLifespan:
    config: UniFiConfig
    clients: dict[str, Any] = field(default_factory=dict)


def _ctx(config: UniFiConfig, **clients: Any) -> AsyncMock:
    ctx = AsyncMock()
    ctx.lifespan_context = _FakeLifespan(config=config, clients=clients)
    return ctx


BASE_URL = "https://10.0.0.1:443"
SITE_PREFIX = f"{BASE_URL}/proxy/network/api/s/default"

WRITE_TOOL_NAMES = {
    "unifi_network_restart_device",
    "unifi_network_adopt_device",
    "unifi_network_locate_device",
    "unifi_network_unlocate_device",
    "unifi_network_provision_device",
    "unifi_network_forget_device",
}
READ_TOOL_NAMES = {"unifi_network_get_device"}


@pytest.fixture
def network_client() -> NetworkClient:
    return NetworkClient(base_url=BASE_URL, api_key="test-key", site="default", timeout=5, max_retries=1)


@pytest.fixture
def mcp_with_devices() -> FastMCP:
    server = FastMCP(name="test-devices")
    register_device_tools(server)
    return server


def _full_config(mode: UniFiMode) -> UniFiConfig:
    return UniFiConfig(
        _env_file=None,
        unifi_mode=mode,
        unifi_network_api="test-net",
        unifi_protect_api=None,
        unifi_site_manager_api=None,
    )


class TestDeviceToolRegistration:
    async def test_all_device_tools_registered(self, mcp_with_devices):
        tools = await mcp_with_devices.list_tools()
        names = {t.name for t in tools}
        assert names == READ_TOOL_NAMES | WRITE_TOOL_NAMES

    async def test_write_tools_carry_write_tag(self, mcp_with_devices):
        tools = await mcp_with_devices.list_tools()
        for tool in tools:
            if tool.name in WRITE_TOOL_NAMES:
                assert "write" in tool.tags, f"{tool.name} missing 'write' tag"
            else:
                assert "write" not in tool.tags, f"{tool.name} should not carry 'write'"

    @pytest.mark.parametrize(
        ("name", "destructive"),
        [
            # Reboot is a service disruption (see #49).
            ("unifi_network_restart_device", True),
            # Adopt pushes configuration to a new device — destructive-by-intent.
            ("unifi_network_adopt_device", True),
            # Locate/unlocate/provision are effectively benign.
            ("unifi_network_locate_device", False),
            ("unifi_network_unlocate_device", False),
            ("unifi_network_provision_device", False),
        ],
    )
    async def test_destructive_hints_match_intent(self, mcp_with_devices, name, destructive):
        tools = await mcp_with_devices.list_tools()
        tool = next(t for t in tools if t.name == name)
        assert tool.annotations.destructiveHint is destructive


class TestDeviceModeGating:
    async def test_readonly_hides_all_device_write_tools(self):
        server = create_server(_full_config(UniFiMode.READONLY))
        tools = await server.list_tools()
        names = {t.name for t in tools}
        for write_tool in WRITE_TOOL_NAMES:
            assert write_tool not in names
        # Read tool remains visible.
        assert "unifi_network_get_device" in names

    async def test_readwrite_exposes_all_device_write_tools(self):
        server = create_server(_full_config(UniFiMode.READWRITE))
        tools = await server.list_tools()
        names = {t.name for t in tools}
        for tool_name in WRITE_TOOL_NAMES | READ_TOOL_NAMES:
            assert tool_name in names


class TestDeviceClientEndpoints:
    @respx.mock
    async def test_restart_device_posts_cmd_devmgr(self, network_client):
        route = respx.post(f"{SITE_PREFIX}/cmd/devmgr").mock(
            return_value=httpx.Response(200, json={"meta": {"rc": "ok"}})
        )
        result = await network_client.restart_device("aa:bb:cc:dd:ee:ff")
        assert result == {"meta": {"rc": "ok"}}
        # Body should address the device and the restart command.
        assert route.call_count == 1
        sent = route.calls[0].request
        assert b"restart" in sent.content
        assert b"aa:bb:cc:dd:ee:ff" in sent.content

    @respx.mock
    async def test_locate_device_posts_cmd_devmgr_with_set_locate(self, network_client):
        route = respx.post(f"{SITE_PREFIX}/cmd/devmgr").mock(return_value=httpx.Response(200, json={}))
        await network_client.locate_device("aa:bb:cc:dd:ee:ff")
        assert b"set-locate" in route.calls[0].request.content

    @respx.mock
    async def test_unlocate_device_posts_cmd_devmgr_with_unset_locate(self, network_client):
        route = respx.post(f"{SITE_PREFIX}/cmd/devmgr").mock(return_value=httpx.Response(200, json={}))
        await network_client.unlocate_device("aa:bb:cc:dd:ee:ff")
        assert b"unset-locate" in route.calls[0].request.content


class TestForgetDevice:
    """#93 part 2: forget_device adds a reverse of adopt_device."""

    async def test_forget_device_registered(self, mcp_with_devices):
        tools = await mcp_with_devices.list_tools()
        names = {t.name for t in tools}
        assert "unifi_network_forget_device" in names

    async def test_forget_device_marked_destructive(self, mcp_with_devices):
        tools = await mcp_with_devices.list_tools()
        tool = next(t for t in tools if t.name == "unifi_network_forget_device")
        assert tool.annotations.destructiveHint is True
        assert "write" in tool.tags

    @respx.mock
    async def test_forget_device_posts_delete_device(self, network_client):
        mac = "aa:bb:cc:dd:ee:ff"
        respx.get(f"{SITE_PREFIX}/stat/device").mock(
            return_value=httpx.Response(200, json={"data": [{"mac": mac, "adopted": True}]}),
        )
        route = respx.post(f"{SITE_PREFIX}/cmd/sitemgr").mock(return_value=httpx.Response(200, json={}))
        await network_client.forget_device(mac)
        body = route.calls[0].request.content
        assert b"delete-device" in body
        assert mac.encode() in body

    @respx.mock
    async def test_forget_device_unknown_mac_raises(self, network_client):
        from unifi_mcp.errors import UniFiNotFoundError

        respx.get(f"{SITE_PREFIX}/stat/device").mock(return_value=httpx.Response(200, json={"data": []}))
        post_route = respx.post(f"{SITE_PREFIX}/cmd/sitemgr").mock(
            return_value=httpx.Response(200, json={}),
        )
        with pytest.raises(UniFiNotFoundError, match="aa:bb"):
            await network_client.forget_device("aa:bb:cc:dd:ee:ff")
        assert post_route.call_count == 0


class TestForgetDeviceHandler:
    """Drive the forget tool through the handler to cover its read-only gate."""

    async def test_readonly_blocks_forget(self, mcp_with_devices):
        client = AsyncMock()
        ctx = _ctx(_full_config(UniFiMode.READONLY), network=client)
        tool = await mcp_with_devices.get_tool("unifi_network_forget_device")
        with pytest.raises(ToolError, match="read-only mode"):
            await tool.fn(ctx, mac="aa:bb:cc:dd:ee:ff")
        client.forget_device.assert_not_awaited()

    async def test_readwrite_forwards_mac(self, mcp_with_devices):
        client = AsyncMock()
        client.forget_device.return_value = {"ok": True}
        ctx = _ctx(_full_config(UniFiMode.READWRITE), network=client)
        tool = await mcp_with_devices.get_tool("unifi_network_forget_device")
        result = await tool.fn(ctx, mac="aa:bb:cc:dd:ee:ff")
        assert result == {"ok": True}
        client.forget_device.assert_awaited_once_with("aa:bb:cc:dd:ee:ff")
