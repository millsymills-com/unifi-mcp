"""Handler-level tests: exercise tool function bodies (not just the client call).

These tests invoke the registered tool's underlying Python function (``tool.fn``)
with a fake FastMCP Context whose ``lifespan_context`` is a small stand-in that
holds the config and a mocked client. That way the tool body itself runs (the
``try`` / ``get_server_context`` / ``context.clients[...]`` / ``handle_client_error``
branches), not just the delegated client method.

The existing respx-based tool tests cover HTTP wire format; these tests cover
the tool's own logic. Both are kept deliberately.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from unifi_mcp.config import UniFiConfig, UniFiMode
from unifi_mcp.errors import UniFiAuthError, UniFiNotFoundError
from unifi_mcp.tools.network.clients import register_client_tools
from unifi_mcp.tools.network.devices import register_device_tools
from unifi_mcp.tools.network.firewall import register_firewall_tools
from unifi_mcp.tools.network.stats import register_stats_tools
from unifi_mcp.tools.network.system import register_system_tools
from unifi_mcp.tools.network.wlan import register_wlan_tools
from unifi_mcp.tools.protect.cameras import register_camera_tools
from unifi_mcp.tools.protect.devices import register_protect_device_tools
from unifi_mcp.tools.protect.media import register_media_tools
from unifi_mcp.tools.protect.nvr import register_nvr_tools


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


def _readwrite_config() -> UniFiConfig:
    return UniFiConfig(
        _env_file=None,
        unifi_mode=UniFiMode.READWRITE,
        unifi_network_api="k",
        unifi_protect_api="k",
        unifi_site_manager_api=None,
    )


def _fake_ctx(config: UniFiConfig, **clients: Any) -> AsyncMock:
    ctx = AsyncMock()
    ctx.lifespan_context = FakeLifespan(config=config, clients=clients)
    return ctx


async def _call(server: FastMCP, tool_name: str, ctx: AsyncMock, **kwargs: Any) -> Any:
    tool = await server.get_tool(tool_name)
    return await tool.fn(ctx, **kwargs)


# ── Network stats (read-only) ──────────────────────────────────────────────


class TestNetworkStatsHandlers:
    @pytest.fixture
    def server(self) -> FastMCP:
        s = FastMCP(name="t")
        register_stats_tools(s)
        return s

    async def test_get_health_delegates_to_client(self, server):
        client = AsyncMock()
        client.get_health.return_value = {"data": "ok"}
        ctx = _fake_ctx(_readonly_config(), network=client)
        result = await _call(server, "unifi_network_get_health", ctx)
        assert result == {"data": "ok"}
        client.get_health.assert_awaited_once()

    async def test_list_events_passes_limit(self, server):
        client = AsyncMock()
        client.list_events.return_value = {"data": []}
        ctx = _fake_ctx(_readonly_config(), network=client)
        await _call(server, "unifi_network_list_events", ctx, limit=7)
        client.list_events.assert_awaited_once_with(limit=7)

    async def test_error_maps_to_tool_error(self, server):
        client = AsyncMock()
        client.get_health.side_effect = UniFiAuthError("bad", status_code=401)
        ctx = _fake_ctx(_readonly_config(), network=client)
        with pytest.raises(ToolError, match="Authentication failed"):
            await _call(server, "unifi_network_get_health", ctx)


# ── Network devices: covers readonly gate + not-found raise path ───────────


class TestNetworkDeviceHandlers:
    @pytest.fixture
    def server(self) -> FastMCP:
        s = FastMCP(name="t")
        register_device_tools(s)
        return s

    async def test_get_device_returns_match(self, server):
        client = AsyncMock()
        client.list_devices.return_value = {"data": [{"mac": "AA:BB:CC:DD:EE:FF", "name": "ap-1"}]}
        ctx = _fake_ctx(_readonly_config(), network=client)
        result = await _call(server, "unifi_network_get_device", ctx, mac="aa:bb:cc:dd:ee:ff")
        assert result["name"] == "ap-1"

    async def test_get_device_raises_not_found(self, server):
        client = AsyncMock()
        client.list_devices.return_value = {"data": []}
        ctx = _fake_ctx(_readonly_config(), network=client)
        with pytest.raises(ToolError, match="Resource not found"):
            await _call(server, "unifi_network_get_device", ctx, mac="aa:bb:cc:dd:ee:ff")

    async def test_readonly_blocks_restart(self, server):
        client = AsyncMock()
        ctx = _fake_ctx(_readonly_config(), network=client)
        with pytest.raises(ToolError, match="read-only mode"):
            await _call(server, "unifi_network_restart_device", ctx, mac="aa:bb:cc:dd:ee:ff")
        client.restart_device.assert_not_awaited()

    async def test_readwrite_allows_restart(self, server):
        client = AsyncMock()
        client.restart_device.return_value = {"meta": {"rc": "ok"}}
        ctx = _fake_ctx(_readwrite_config(), network=client)
        result = await _call(server, "unifi_network_restart_device", ctx, mac="aa:bb:cc:dd:ee:ff", confirm=True)
        assert result == {"meta": {"rc": "ok"}}


# ── Network clients: get_client lookup + raise on miss ─────────────────────


class TestNetworkClientHandlers:
    @pytest.fixture
    def server(self) -> FastMCP:
        s = FastMCP(name="t")
        register_client_tools(s)
        return s

    async def test_get_client_match(self, server):
        client = AsyncMock()
        client.list_active_clients.return_value = {"data": [{"mac": "AA:BB:CC:DD:EE:FF", "hostname": "host"}]}
        ctx = _fake_ctx(_readonly_config(), network=client)
        result = await _call(server, "unifi_network_get_client", ctx, mac="aa:bb:cc:dd:ee:ff")
        assert result["hostname"] == "host"

    async def test_get_client_not_found(self, server):
        client = AsyncMock()
        client.list_active_clients.return_value = {"data": []}
        ctx = _fake_ctx(_readonly_config(), network=client)
        with pytest.raises(ToolError, match="Resource not found"):
            await _call(server, "unifi_network_get_client", ctx, mac="aa:bb:cc:dd:ee:ff")

    async def test_block_client_readonly_blocked(self, server):
        client = AsyncMock()
        ctx = _fake_ctx(_readonly_config(), network=client)
        with pytest.raises(ToolError, match="read-only mode"):
            await _call(server, "unifi_network_block_client", ctx, mac="aa:bb:cc:dd:ee:ff")

    async def test_authorize_guest_passes_minutes(self, server):
        client = AsyncMock()
        client.authorize_guest.return_value = {}
        ctx = _fake_ctx(_readwrite_config(), network=client)
        await _call(server, "unifi_network_authorize_guest", ctx, mac="aa:bb:cc:dd:ee:ff", minutes=45)
        client.authorize_guest.assert_awaited_once_with("aa:bb:cc:dd:ee:ff", minutes=45)


# ── Network wlan: create assembles payload, delete marks readonly ──────────


class TestNetworkWlanHandlers:
    @pytest.fixture
    def server(self) -> FastMCP:
        s = FastMCP(name="t")
        register_wlan_tools(s)
        return s

    async def test_create_wlan_assembles_payload(self, server):
        client = AsyncMock()
        client.create_wlan.return_value = {}
        ctx = _fake_ctx(_readwrite_config(), network=client)
        await _call(server, "unifi_network_create_wlan", ctx, name="Guest", x_passphrase="pw", enabled=False)
        args, _ = client.create_wlan.call_args
        payload = args[0]
        assert payload["name"] == "Guest"
        assert payload["x_passphrase"] == "pw"  # noqa: S105
        assert payload["enabled"] is False
        # Defaults fill in for security and wpa_mode.
        assert payload["security"] == "wpapsk"
        assert payload["wpa_mode"] == "wpa2"

    async def test_delete_wlan_readonly_blocked(self, server):
        client = AsyncMock()
        ctx = _fake_ctx(_readonly_config(), network=client)
        with pytest.raises(ToolError, match="read-only mode"):
            await _call(server, "unifi_network_delete_wlan", ctx, wlan_id="w-1")


# ── Network firewall, networks, port_forward, routing, system — smoke ──────
# One happy-path + one readonly test each to exercise the tool body.


@pytest.mark.parametrize(
    ("register_fn", "write_tool", "client_method", "kwargs"),
    [
        (
            register_firewall_tools,
            "unifi_network_delete_firewall_rule",
            "delete_firewall_rule",
            {"rule_id": "r-1", "confirm": True},
        ),
        (
            register_system_tools,
            "unifi_network_upgrade_device",
            "upgrade_device",
            {"mac": "aa:bb:cc:dd:ee:ff", "confirm": True},
        ),
    ],
)
async def test_write_tool_readonly_blocks_and_readwrite_delegates(register_fn, write_tool, client_method, kwargs):
    s = FastMCP(name="t")
    register_fn(s)
    client = AsyncMock()
    getattr(client, client_method).return_value = {"ok": True}

    # Readonly path.
    ctx_ro = _fake_ctx(_readonly_config(), network=client)
    with pytest.raises(ToolError, match="read-only mode"):
        await _call(s, write_tool, ctx_ro, **kwargs)

    # Readwrite path.
    ctx_rw = _fake_ctx(_readwrite_config(), network=client)
    result = await _call(s, write_tool, ctx_rw, **kwargs)
    assert result == {"ok": True}


# ── Protect: cameras, devices, events, nvr, media ──────────────────────────


class TestProtectHandlers:
    async def test_list_cameras_delegates(self):
        s = FastMCP(name="t")
        register_camera_tools(s)
        client = AsyncMock()
        client.list_cameras.return_value = [{"id": "cam-1"}]
        ctx = _fake_ctx(_readonly_config(), protect=client)
        result = await _call(s, "unifi_protect_list_cameras", ctx)
        assert result == [{"id": "cam-1"}]

    async def test_update_camera_readonly_blocked(self):
        s = FastMCP(name="t")
        register_camera_tools(s)
        client = AsyncMock()
        ctx = _fake_ctx(_readonly_config(), protect=client)
        with pytest.raises(ToolError, match="read-only mode"):
            await _call(s, "unifi_protect_update_camera", ctx, camera_id="cam-1", name="x")

    async def test_set_recording_mode_forwards_padding(self):
        s = FastMCP(name="t")
        register_camera_tools(s)
        client = AsyncMock()
        client.set_recording_mode.return_value = {}
        ctx = _fake_ctx(_readwrite_config(), protect=client)
        await _call(s, "unifi_protect_set_recording_mode", ctx, camera_id="cam-1", mode="motion", pre_padding=5)
        client.set_recording_mode.assert_awaited_once_with("cam-1", "motion", pre_padding=5, post_padding=None)

    async def test_list_chimes_delegates(self):
        s = FastMCP(name="t")
        register_protect_device_tools(s)
        client = AsyncMock()
        client.list_chimes.return_value = [{"id": "c-1"}]
        ctx = _fake_ctx(_readonly_config(), protect=client)
        result = await _call(s, "unifi_protect_list_chimes", ctx)
        assert result == [{"id": "c-1"}]

    async def test_get_nvr_delegates(self):
        s = FastMCP(name="t")
        register_nvr_tools(s)
        client = AsyncMock()
        client.get_nvr.return_value = {"name": "nvr"}
        ctx = _fake_ctx(_readonly_config(), protect=client)
        result = await _call(s, "unifi_protect_get_nvr", ctx)
        assert result == {"name": "nvr"}

    async def test_export_video_plumbs_max_bytes(self):
        s = FastMCP(name="t")
        register_media_tools(s)
        client = AsyncMock()
        client.export_video.return_value = b"mp4"
        ctx = _fake_ctx(_readonly_config(), protect=client)
        result = await _call(s, "unifi_protect_export_video", ctx, camera_id="cam-1", start=1, end=2)
        assert result["format"] == "mp4"
        # The max_bytes kwarg should be pulled from config and forwarded.
        _, kwargs = client.export_video.call_args
        assert "max_bytes" in kwargs
        assert kwargs["max_bytes"] == _readonly_config().unifi_max_export_bytes

    async def test_get_snapshot_returns_jpeg_payload(self):
        s = FastMCP(name="t")
        register_media_tools(s)
        client = AsyncMock()
        client.get_snapshot.return_value = b"\xff\xd8\xff\xe0"
        ctx = _fake_ctx(_readonly_config(), protect=client)
        result = await _call(s, "unifi_protect_get_snapshot", ctx, camera_id="cam-1")
        assert result["format"] == "jpeg"
        assert result["size_bytes"] == 4


class TestErrorPropagation:
    async def test_unifi_not_found_maps_to_tool_error(self):
        s = FastMCP(name="t")
        register_stats_tools(s)
        client = AsyncMock()
        client.get_health.side_effect = UniFiNotFoundError("missing", status_code=404)
        ctx = _fake_ctx(_readonly_config(), network=client)
        with pytest.raises(ToolError, match="Resource not found"):
            await _call(s, "unifi_network_get_health", ctx)
