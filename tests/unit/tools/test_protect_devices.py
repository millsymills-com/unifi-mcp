"""Tests for Protect accessory-device MCP tools (4 read + write)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
import respx
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from unifi_mcp.clients.protect import ProtectClient
from unifi_mcp.config import UniFiConfig, UniFiMode
from unifi_mcp.tools.protect.devices import register_protect_device_tools

BASE_URL = "https://10.0.0.1:443"
PROTECT_PREFIX = f"{BASE_URL}/proxy/protect/integration/v1"

READ_TOOL_NAMES = {
    "unifi_protect_list_chimes",
    "unifi_protect_list_lights",
    "unifi_protect_list_sensors",
    "unifi_protect_list_viewers",
}
WRITE_TOOL_NAMES = {
    "unifi_protect_update_chime",
    "unifi_protect_update_light",
    "unifi_protect_set_light_mode",
}


@pytest.fixture
def protect_client_local() -> ProtectClient:
    return ProtectClient(base_url=BASE_URL, api_key="test-key", timeout=5, max_retries=1)


@pytest.fixture
def mcp_with_accessories() -> FastMCP:
    server = FastMCP(name="test-accessories")
    register_protect_device_tools(server)
    return server


def _readwrite_config() -> UniFiConfig:
    return UniFiConfig(
        _env_file=None,
        unifi_mode=UniFiMode.READWRITE,
        unifi_network_api="k",
        unifi_protect_api="k",
        unifi_site_manager_api=None,
    )


def _readonly_config() -> UniFiConfig:
    return UniFiConfig(
        _env_file=None,
        unifi_mode=UniFiMode.READONLY,
        unifi_network_api="k",
        unifi_protect_api="k",
        unifi_site_manager_api=None,
    )


def _ctx_with_mock_chime_client(config: UniFiConfig) -> tuple[AsyncMock, AsyncMock]:
    """Build a ctx whose protect client has a mock update_chime method."""
    mock_client = AsyncMock()
    mock_client.update_chime = AsyncMock(return_value={"id": "ch1"})
    ctx = AsyncMock()
    ctx.lifespan_context = type("FakeLifespan", (), {"config": config, "clients": {"protect": mock_client}})()
    return ctx, mock_client


def _ctx_with_mock_light_client(config: UniFiConfig) -> tuple[AsyncMock, AsyncMock]:
    """Build a ctx whose protect client has a mock update_light method."""
    mock_client = AsyncMock()
    mock_client.update_light = AsyncMock(return_value={"id": "l1"})
    ctx = AsyncMock()
    ctx.lifespan_context = type("FakeLifespan", (), {"config": config, "clients": {"protect": mock_client}})()
    return ctx, mock_client


async def _call(server: FastMCP, tool_name: str, ctx: AsyncMock, **kwargs: Any) -> Any:
    tool = await server.get_tool(tool_name)
    return await tool.fn(ctx, **kwargs)


class TestProtectDeviceRegistration:
    async def test_all_tools_registered(self, mcp_with_accessories):
        tools = await mcp_with_accessories.list_tools()
        assert {t.name for t in tools} == READ_TOOL_NAMES | WRITE_TOOL_NAMES

    async def test_read_tools_are_read_only(self, mcp_with_accessories):
        tools = await mcp_with_accessories.list_tools()
        for tool in tools:
            if tool.name in READ_TOOL_NAMES:
                assert "write" not in tool.tags

    async def test_write_tools_carry_write_tag(self, mcp_with_accessories):
        tools = await mcp_with_accessories.list_tools()
        for tool in tools:
            if tool.name in WRITE_TOOL_NAMES:
                assert "write" in tool.tags


class TestProtectDeviceClientEndpoints:
    @pytest.mark.parametrize(
        ("method_name", "endpoint"),
        [
            ("list_chimes", "chimes"),
            ("list_lights", "lights"),
            ("list_sensors", "sensors"),
            ("list_viewers", "viewers"),
        ],
    )
    @respx.mock
    async def test_endpoint(self, protect_client_local, method_name, endpoint):
        payload = [{"id": "dev-1"}]
        respx.get(f"{PROTECT_PREFIX}/{endpoint}").mock(return_value=httpx.Response(200, json=payload))
        result = await getattr(protect_client_local, method_name)()
        assert result == payload


class TestUpdateChimeTool:
    async def test_named_args_build_flat_body(self):
        server = FastMCP(name="t")
        register_protect_device_tools(server)
        ctx, mock_client = _ctx_with_mock_chime_client(_readwrite_config())

        await _call(server, "unifi_protect_update_chime", ctx, chime_id="ch1", volume=75, repeat_times=2)

        mock_client.update_chime.assert_awaited_once_with(
            "ch1",
            {"volume": 75, "repeatTimes": 2},
        )

    async def test_readonly_raises_read_only_error(self):
        server = FastMCP(name="t")
        register_protect_device_tools(server)
        ctx, mock_client = _ctx_with_mock_chime_client(_readonly_config())

        with pytest.raises(ToolError) as exc:
            await _call(server, "unifi_protect_update_chime", ctx, chime_id="ch1", volume=50)
        assert "read-only" in str(exc.value).lower()
        mock_client.update_chime.assert_not_awaited()

    async def test_no_args_raises(self):
        server = FastMCP(name="t")
        register_protect_device_tools(server)
        ctx, mock_client = _ctx_with_mock_chime_client(_readwrite_config())

        with pytest.raises(ToolError) as exc:
            await _call(server, "unifi_protect_update_chime", ctx, chime_id="ch1")
        assert "at least one field" in str(exc.value).lower()
        mock_client.update_chime.assert_not_awaited()


class TestUpdateLightTool:
    async def test_named_args_build_nested_body(self):
        server = FastMCP(name="t")
        register_protect_device_tools(server)
        ctx, mock_client = _ctx_with_mock_light_client(_readwrite_config())

        await _call(server, "unifi_protect_update_light", ctx, light_id="l1", led_level=6, mode="motion")

        mock_client.update_light.assert_awaited_once_with(
            "l1",
            {"lightDeviceSettings": {"ledLevel": 6}, "lightModeSettings": {"mode": "motion"}},
        )

    async def test_readonly_raises_read_only_error(self):
        server = FastMCP(name="t")
        register_protect_device_tools(server)
        ctx, mock_client = _ctx_with_mock_light_client(_readonly_config())

        with pytest.raises(ToolError) as exc:
            await _call(server, "unifi_protect_update_light", ctx, light_id="l1", led_level=3)
        assert "read-only" in str(exc.value).lower()
        mock_client.update_light.assert_not_awaited()

    async def test_no_args_raises(self):
        server = FastMCP(name="t")
        register_protect_device_tools(server)
        ctx, mock_client = _ctx_with_mock_light_client(_readwrite_config())

        with pytest.raises(ToolError) as exc:
            await _call(server, "unifi_protect_update_light", ctx, light_id="l1")
        assert "at least one field" in str(exc.value).lower()
        mock_client.update_light.assert_not_awaited()


class TestSetLightModeTool:
    async def test_set_light_mode_always(self):
        server = FastMCP(name="t")
        register_protect_device_tools(server)
        ctx, mock_client = _ctx_with_mock_light_client(_readwrite_config())

        await _call(server, "unifi_protect_set_light_mode", ctx, light_id="l1", mode="always")

        mock_client.update_light.assert_awaited_once_with("l1", {"lightModeSettings": {"mode": "always"}})

    async def test_readonly_raises_read_only_error(self):
        server = FastMCP(name="t")
        register_protect_device_tools(server)
        ctx, mock_client = _ctx_with_mock_light_client(_readonly_config())

        with pytest.raises(ToolError) as exc:
            await _call(server, "unifi_protect_set_light_mode", ctx, light_id="l1", mode="motion")
        assert "read-only" in str(exc.value).lower()
        mock_client.update_light.assert_not_awaited()
