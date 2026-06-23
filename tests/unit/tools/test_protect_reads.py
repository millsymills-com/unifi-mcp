"""Tests for the Protect read MCP tools added in #407 (Phase 2).

Covers registration (read-only, no write tag), client delegation, validate_id
rejection on path params, and secret redaction in the returned payload.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from unifi_mcp._redaction import REDACTED
from unifi_mcp.config import UniFiConfig, UniFiMode
from unifi_mcp.tools.protect.access import register_protect_access_tools
from unifi_mcp.tools.protect.device_reads import register_protect_device_read_tools
from unifi_mcp.tools.protect.liveviews import register_liveview_tools

DEVICE_READ_TOOLS = {
    "unifi_protect_get_chime",
    "unifi_protect_get_light",
    "unifi_protect_get_sensor",
    "unifi_protect_get_viewer",
    "unifi_protect_list_speakers",
    "unifi_protect_get_speaker",
    "unifi_protect_list_sirens",
    "unifi_protect_get_siren",
    "unifi_protect_list_bridges",
    "unifi_protect_get_bridge",
    "unifi_protect_list_relays",
    "unifi_protect_get_relay",
    "unifi_protect_list_link_stations",
    "unifi_protect_get_link_station",
    "unifi_protect_list_fobs",
    "unifi_protect_get_fob",
    "unifi_protect_list_alarm_hubs",
    "unifi_protect_get_alarm_hub",
}
LIVEVIEW_TOOLS = {
    "unifi_protect_list_liveviews",
    "unifi_protect_get_liveview",
    "unifi_protect_list_arm_profiles",
}
ACCESS_TOOLS = {
    "unifi_protect_list_users",
    "unifi_protect_get_user",
    "unifi_protect_list_ulp_users",
    "unifi_protect_get_ulp_user",
    "unifi_protect_get_meta_info",
    "unifi_protect_get_rtsps_stream",
    "unifi_protect_get_file_asset",
}


@dataclass
class FakeLifespan:
    config: UniFiConfig
    clients: dict[str, Any] = field(default_factory=dict)


def _readonly_config() -> UniFiConfig:
    return UniFiConfig(
        _env_file=None,
        unifi_mode=UniFiMode.READONLY,
        unifi_network_api="k",
        unifi_protect_api="k",
        unifi_site_manager_api=None,
    )


def _ctx(client: Any) -> AsyncMock:
    ctx = AsyncMock()
    ctx.lifespan_context = FakeLifespan(config=_readonly_config(), clients={"protect": client})
    return ctx


def _server() -> FastMCP:
    server = FastMCP(name="test-protect-reads")
    register_protect_device_read_tools(server)
    register_liveview_tools(server)
    register_protect_access_tools(server)
    return server


async def _call(server: FastMCP, tool_name: str, ctx: AsyncMock, **kwargs: Any) -> Any:
    tool = await server.get_tool(tool_name)
    return await tool.fn(ctx, **kwargs)


class TestRegistration:
    async def test_all_tools_registered(self):
        tools = await _server().list_tools()
        assert {t.name for t in tools} == DEVICE_READ_TOOLS | LIVEVIEW_TOOLS | ACCESS_TOOLS

    async def test_all_tools_are_read_only(self):
        tools = await _server().list_tools()
        for tool in tools:
            assert "write" not in tool.tags
            assert "protect" in tool.tags

    async def test_count_is_28(self):
        tools = await _server().list_tools()
        assert len(tools) == 28


class TestClientDelegation:
    async def test_get_chime_delegates(self):
        client = AsyncMock()
        client.get_chime = AsyncMock(return_value={"id": "ch1"})
        result = await _call(_server(), "unifi_protect_get_chime", _ctx(client), chime_id="ch1")
        client.get_chime.assert_awaited_once_with("ch1")
        assert result == {"id": "ch1"}

    async def test_list_speakers_delegates(self):
        client = AsyncMock()
        client.list_speakers = AsyncMock(return_value=[{"id": "sp1"}])
        result = await _call(_server(), "unifi_protect_list_speakers", _ctx(client))
        client.list_speakers.assert_awaited_once_with()
        assert result == [{"id": "sp1"}]

    async def test_rtsps_stream_passes_qualities(self):
        client = AsyncMock()
        client.get_rtsps_stream = AsyncMock(return_value={})
        await _call(_server(), "unifi_protect_get_rtsps_stream", _ctx(client), camera_id="cam-1", qualities=["high"])
        client.get_rtsps_stream.assert_awaited_once_with("cam-1", qualities=["high"])


class TestValidateIdRejection:
    @pytest.mark.parametrize(
        ("tool_name", "param"),
        [
            ("unifi_protect_get_chime", "chime_id"),
            ("unifi_protect_get_light", "light_id"),
            ("unifi_protect_get_speaker", "speaker_id"),
            ("unifi_protect_get_link_station", "link_station_id"),
            ("unifi_protect_get_alarm_hub", "alarm_hub_id"),
            ("unifi_protect_get_liveview", "liveview_id"),
            ("unifi_protect_get_user", "user_id"),
            ("unifi_protect_get_ulp_user", "ulp_user_id"),
            ("unifi_protect_get_rtsps_stream", "camera_id"),
            ("unifi_protect_get_file_asset", "file_type"),
        ],
    )
    async def test_traversal_id_rejected_before_client_call(self, tool_name, param):
        client = AsyncMock()
        with pytest.raises(ToolError):
            await _call(_server(), tool_name, _ctx(client), **{param: "../etc"})
        # No client method should have been awaited.
        for call in client.method_calls:
            assert not call[0].startswith(("get_", "list_"))


class TestRedaction:
    async def test_get_user_redacts_token(self):
        client = AsyncMock()
        client.get_user = AsyncMock(return_value={"id": "u1", "accessToken": "secret-value"})
        result = await _call(_server(), "unifi_protect_get_user", _ctx(client), user_id="u1")
        assert result["accessToken"] == REDACTED
        assert result["id"] == "u1"

    async def test_rtsps_stream_redacts_token(self):
        client = AsyncMock()
        client.get_rtsps_stream = AsyncMock(return_value={"streamToken": "abc123"})
        result = await _call(_server(), "unifi_protect_get_rtsps_stream", _ctx(client), camera_id="cam-1")
        assert result["streamToken"] == REDACTED
