"""Tests for Protect media MCP tools (snapshots + video export)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
import respx
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from unifi_mcp.clients.protect import ProtectClient
from unifi_mcp.config import UniFiConfig, UniFiMode
from unifi_mcp.errors import UniFiError
from unifi_mcp.tools.protect.media import register_media_tools


@dataclass
class _FakeLifespan:
    config: UniFiConfig
    clients: dict[str, Any] = field(default_factory=dict)


BASE_URL = "https://10.0.0.1:443"
PROTECT_PREFIX = f"{BASE_URL}/proxy/protect/integration/v1"


@pytest.fixture
def protect_client_local() -> ProtectClient:
    return ProtectClient(base_url=BASE_URL, api_key="test-key", timeout=5, max_retries=1)


@pytest.fixture
def mcp_with_media() -> FastMCP:
    server = FastMCP(name="test-media")
    register_media_tools(server)
    return server


class TestMediaRegistration:
    async def test_all_tools_registered(self, mcp_with_media):
        tools = await mcp_with_media.list_tools()
        assert {t.name for t in tools} == {"unifi_protect_get_snapshot", "unifi_protect_export_video"}

    async def test_media_tools_are_read_only(self, mcp_with_media):
        # Snapshots and exports are reads of existing recording data — no write tag.
        tools = await mcp_with_media.list_tools()
        for tool in tools:
            assert "write" not in tool.tags


class TestMediaClientEndpoints:
    @respx.mock
    async def test_get_snapshot_without_timestamp(self, protect_client_local):
        route = respx.get(f"{PROTECT_PREFIX}/cameras/cam-1/snapshot").mock(
            return_value=httpx.Response(200, content=b"\xff\xd8\xff\xe0"),
        )
        result = await protect_client_local.get_snapshot("cam-1", max_bytes=1024)
        assert result == b"\xff\xd8\xff\xe0"
        # No ts param by default
        assert "ts" not in route.calls[0].request.url.params

    @respx.mock
    async def test_get_snapshot_with_timestamp(self, protect_client_local):
        route = respx.get(f"{PROTECT_PREFIX}/cameras/cam-1/snapshot").mock(
            return_value=httpx.Response(200, content=b"\xff\xd8"),
        )
        await protect_client_local.get_snapshot("cam-1", timestamp=1700000000000, max_bytes=1024)
        assert route.calls[0].request.url.params["ts"] == "1700000000000"

    @respx.mock
    async def test_export_video_uses_camera_scoped_path(self, protect_client_local):
        # Locks in the fix from #47 / PR #50.
        route = respx.get(f"{PROTECT_PREFIX}/cameras/cam-1/video/export").mock(
            return_value=httpx.Response(200, content=b"mp4-bytes"),
        )
        result = await protect_client_local.export_video("cam-1", start=1000, end=2000, max_bytes=1_000_000)
        assert result == b"mp4-bytes"
        params = route.calls[0].request.url.params
        assert params["start"] == "1000"
        assert params["end"] == "2000"
        assert "camera" not in params  # dropped in #47 fix

    @respx.mock
    async def test_export_video_respects_max_bytes(self, protect_client_local):
        # Streaming path (#32 / PR #64): abort when body exceeds the cap.
        payload = b"x" * 2048
        respx.get(f"{PROTECT_PREFIX}/cameras/cam-1/video/export").mock(
            return_value=httpx.Response(200, content=payload),
        )
        with pytest.raises(UniFiError, match="max_bytes=1024"):
            await protect_client_local.export_video("cam-1", start=1, end=2, max_bytes=1024)


class TestExportVideoToolLayerCap:
    """End-to-end handler test for unifi_protect_export_video respecting the configured cap.

    The respx test above (``test_export_video_respects_max_bytes``) hits the client
    method directly. This one drives the actual MCP tool handler — proving that
    the config value ``unifi_max_export_bytes`` is read from the lifespan context
    and forwarded to ``ProtectClient.export_video`` at call time. Closes #73.
    """

    async def test_tool_aborts_when_payload_exceeds_cap(self):
        server = FastMCP(name="media-cap-test")
        register_media_tools(server)

        # Real client so the streaming abort in BaseUniFiClient.get_raw actually runs.
        client = ProtectClient(base_url=BASE_URL, api_key="k", timeout=5, max_retries=1)

        # Config with a tight cap.
        config = UniFiConfig(
            _env_file=None,
            unifi_mode=UniFiMode.READONLY,
            unifi_network_api="k",
            unifi_protect_api="k",
            unifi_max_export_bytes=1024,
        )

        ctx = AsyncMock()
        ctx.lifespan_context = _FakeLifespan(config=config, clients={"protect": client})

        tool = await server.get_tool("unifi_protect_export_video")

        with respx.mock:
            respx.get(f"{PROTECT_PREFIX}/cameras/cam-1/video/export").mock(
                return_value=httpx.Response(200, content=b"x" * 2048),
            )
            with pytest.raises(ToolError, match="max_bytes=1024"):
                await tool.fn(ctx, camera_id="cam-1", start=1, end=2)


class TestGetSnapshotToolLayerCap:
    """End-to-end handler test for unifi_protect_get_snapshot respecting the configured cap.

    Mirrors ``TestExportVideoToolLayerCap`` for the snapshot path: the tool must
    forward ``unifi_max_snapshot_bytes`` from the lifespan context to
    ``ProtectClient.get_snapshot`` so that an oversized snapshot (a misconfigured
    or hostile camera) aborts mid-stream instead of loading into memory.
    """

    async def test_tool_aborts_when_snapshot_exceeds_cap(self):
        server = FastMCP(name="snapshot-cap-test")
        register_media_tools(server)

        client = ProtectClient(base_url=BASE_URL, api_key="k", timeout=5, max_retries=1)

        config = UniFiConfig(
            _env_file=None,
            unifi_mode=UniFiMode.READONLY,
            unifi_network_api="k",
            unifi_protect_api="k",
            unifi_max_snapshot_bytes=1024,
        )

        ctx = AsyncMock()
        ctx.lifespan_context = _FakeLifespan(config=config, clients={"protect": client})

        tool = await server.get_tool("unifi_protect_get_snapshot")

        with respx.mock:
            respx.get(f"{PROTECT_PREFIX}/cameras/cam-1/snapshot").mock(
                return_value=httpx.Response(200, content=b"x" * 2048),
            )
            with pytest.raises(ToolError, match="max_bytes=1024"):
                await tool.fn(ctx, camera_id="cam-1")

    async def test_tool_returns_base64_body_when_under_cap(self):
        """Happy path: a small snapshot streams through and returns base64 + size."""
        import base64

        server = FastMCP(name="snapshot-ok-test")
        register_media_tools(server)

        client = ProtectClient(base_url=BASE_URL, api_key="k", timeout=5, max_retries=1)

        config = UniFiConfig(
            _env_file=None,
            unifi_mode=UniFiMode.READONLY,
            unifi_network_api="k",
            unifi_protect_api="k",
            unifi_max_snapshot_bytes=50 * 1024 * 1024,
        )

        ctx = AsyncMock()
        ctx.lifespan_context = _FakeLifespan(config=config, clients={"protect": client})

        tool = await server.get_tool("unifi_protect_get_snapshot")
        jpeg = b"\xff\xd8\xff\xe0fake-jpeg"

        with respx.mock:
            respx.get(f"{PROTECT_PREFIX}/cameras/cam-1/snapshot").mock(return_value=httpx.Response(200, content=jpeg))
            result = await tool.fn(ctx, camera_id="cam-1")

        assert result["format"] == "jpeg"
        assert result["size_bytes"] == len(jpeg)
        assert base64.b64decode(result["data_base64"]) == jpeg
