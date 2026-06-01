"""Tests for Protect camera MCP tools (2 read + 3 write)."""

from __future__ import annotations

import httpx
import pytest
import respx
from fastmcp import FastMCP

from unifi_mcp.clients.protect import ProtectClient
from unifi_mcp.config import UniFiConfig, UniFiMode
from unifi_mcp.server import create_server
from unifi_mcp.tools.protect.cameras import register_camera_tools

BASE_URL = "https://10.0.0.1:443"
PROTECT_PREFIX = f"{BASE_URL}/proxy/protect/integration/v1"

READ_TOOL_NAMES = {"unifi_protect_list_cameras", "unifi_protect_get_camera"}
WRITE_TOOL_NAMES = {
    "unifi_protect_update_camera",
    "unifi_protect_set_recording_mode",
    "unifi_protect_set_smart_detection",
}


@pytest.fixture
def protect_client_local() -> ProtectClient:
    return ProtectClient(base_url=BASE_URL, api_key="test-key", timeout=5, max_retries=1)


@pytest.fixture
def mcp_with_cameras() -> FastMCP:
    server = FastMCP(name="test-cameras")
    register_camera_tools(server)
    return server


def _full_config(mode: UniFiMode) -> UniFiConfig:
    return UniFiConfig(
        _env_file=None,
        unifi_mode=mode,
        unifi_network_api="test-net",
        unifi_protect_api="test-prot",
        unifi_site_manager_api=None,
    )


class TestCameraToolRegistration:
    async def test_all_camera_tools_registered(self, mcp_with_cameras):
        tools = await mcp_with_cameras.list_tools()
        names = {t.name for t in tools}
        assert names == READ_TOOL_NAMES | WRITE_TOOL_NAMES

    async def test_write_tools_carry_write_tag(self, mcp_with_cameras):
        tools = await mcp_with_cameras.list_tools()
        for tool in tools:
            if tool.name in WRITE_TOOL_NAMES:
                assert "write" in tool.tags
            else:
                assert "write" not in tool.tags


class TestCameraModeGating:
    async def test_readonly_hides_camera_write_tools(self):
        server = create_server(_full_config(UniFiMode.READONLY))
        tools = await server.list_tools()
        names = {t.name for t in tools}
        for w in WRITE_TOOL_NAMES:
            assert w not in names
        for r in READ_TOOL_NAMES:
            assert r in names

    async def test_readwrite_exposes_camera_write_tools(self):
        server = create_server(_full_config(UniFiMode.READWRITE))
        tools = await server.list_tools()
        names = {t.name for t in tools}
        for name in READ_TOOL_NAMES | WRITE_TOOL_NAMES:
            assert name in names


class TestCameraClientEndpoints:
    @respx.mock
    async def test_list_cameras_hits_cameras(self, protect_client_local):
        respx.get(f"{PROTECT_PREFIX}/cameras").mock(return_value=httpx.Response(200, json=[{"id": "cam-1"}]))
        result = await protect_client_local.list_cameras()
        assert result == [{"id": "cam-1"}]

    @respx.mock
    async def test_get_camera_hits_cameras_id(self, protect_client_local):
        respx.get(f"{PROTECT_PREFIX}/cameras/cam-1").mock(return_value=httpx.Response(200, json={"id": "cam-1"}))
        result = await protect_client_local.get_camera("cam-1")
        assert result == {"id": "cam-1"}

    @respx.mock
    async def test_update_camera_patches_with_body(self, protect_client_local):
        route = respx.patch(f"{PROTECT_PREFIX}/cameras/cam-1").mock(return_value=httpx.Response(200, json={"ok": True}))
        result = await protect_client_local.update_camera("cam-1", {"name": "Front Door"})
        assert result == {"ok": True}
        assert b"Front Door" in route.calls[0].request.content

    @respx.mock
    async def test_set_recording_mode_patches_recording_settings(self, protect_client_local):
        route = respx.patch(f"{PROTECT_PREFIX}/cameras/cam-1").mock(return_value=httpx.Response(200, json={}))
        await protect_client_local.set_recording_mode("cam-1", "motion", pre_padding=5, post_padding=10)
        body = route.calls[0].request.content
        assert b"recordingSettings" in body
        assert b"motion" in body
        assert b"prePaddingSecs" in body
        assert b"postPaddingSecs" in body

    @respx.mock
    async def test_set_smart_detection_patches_smart_detect_settings(self, protect_client_local):
        route = respx.patch(f"{PROTECT_PREFIX}/cameras/cam-1").mock(return_value=httpx.Response(200, json={}))
        await protect_client_local.set_smart_detection("cam-1", ["person", "vehicle"])
        body = route.calls[0].request.content
        assert b"smartDetectSettings" in body
        assert b"person" in body
        assert b"vehicle" in body
