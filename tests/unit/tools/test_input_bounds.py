"""Tool-layer numeric bounds on write-tool inputs (#151).

Each test covers a sub-item from the #151 hardening cluster:

- ``unifi_network_authorize_guest`` clamps ``minutes`` to ``1..43200`` (30 days)
  so a prompt-injected agent can't stamp a permanent guest session.
- ``unifi_network_power_cycle_port`` / ``unifi_network_assign_port_profile``
  clamp ``port_idx`` to ``1..52`` so an arbitrary integer can't reach the
  controller's ``cmd/devmgr`` or ``rest/device`` endpoint.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from unifi_mcp.config import UniFiConfig, UniFiMode
from unifi_mcp.tools.network.clients import register_client_tools
from unifi_mcp.tools.network.port_profiles import register_port_profile_tools
from unifi_mcp.tools.network.system import register_system_tools


@dataclass
class _Lifespan:
    config: UniFiConfig
    clients: dict[str, Any] = field(default_factory=dict)


def _readwrite_config() -> UniFiConfig:
    return UniFiConfig(
        _env_file=None,
        unifi_mode=UniFiMode.READWRITE,
        unifi_network_api="k",
        unifi_protect_api=None,
        unifi_site_manager_api=None,
    )


def _ctx(client: AsyncMock) -> AsyncMock:
    ctx = AsyncMock()
    ctx.lifespan_context = _Lifespan(config=_readwrite_config(), clients={"network": client})
    return ctx


async def _call(server: FastMCP, tool_name: str, ctx: AsyncMock, **kwargs: Any) -> Any:
    tool = await server.get_tool(tool_name)
    return await tool.fn(ctx, **kwargs)


VALID_MAC = "aa:bb:cc:dd:ee:ff"


class TestAuthorizeGuestMinutesBound:
    """``minutes`` must fall in ``[1, 43200]`` (30 days)."""

    @pytest.fixture
    def server(self) -> FastMCP:
        s = FastMCP(name="t")
        register_client_tools(s)
        return s

    @pytest.mark.parametrize("minutes", [1, 60, 1440, 43200])
    async def test_in_range_passes_through(self, server, minutes):
        client = AsyncMock()
        client.authorize_guest.return_value = {}
        ctx = _ctx(client)
        await _call(server, "unifi_network_authorize_guest", ctx, mac=VALID_MAC, minutes=minutes)
        client.authorize_guest.assert_awaited_once_with(VALID_MAC, minutes=minutes)

    @pytest.mark.parametrize("minutes", [0, -1, 43201, 10**9])
    async def test_out_of_range_rejected(self, server, minutes):
        client = AsyncMock()
        ctx = _ctx(client)
        with pytest.raises(ToolError, match="minutes must be between 1 and 43200"):
            await _call(server, "unifi_network_authorize_guest", ctx, mac=VALID_MAC, minutes=minutes)
        client.authorize_guest.assert_not_called()

    async def test_invalid_mac_rejected_before_minutes(self, server):
        """MAC validation runs first — bad MAC raises ``invalid mac format``,
        not ``minutes must be between``.
        """
        client = AsyncMock()
        ctx = _ctx(client)
        with pytest.raises(ToolError, match="invalid mac format"):
            await _call(server, "unifi_network_authorize_guest", ctx, mac="not-a-mac", minutes=60)
        client.authorize_guest.assert_not_called()


class TestPowerCyclePortIdxBound:
    """``port_idx`` must fall in ``[1, 52]``."""

    @pytest.fixture
    def server(self) -> FastMCP:
        s = FastMCP(name="t")
        register_system_tools(s)
        return s

    @pytest.mark.parametrize("port_idx", [1, 5, 24, 48, 52])
    async def test_in_range_passes_through(self, server, port_idx):
        client = AsyncMock()
        client.power_cycle_port.return_value = {}
        ctx = _ctx(client)
        await _call(server, "unifi_network_power_cycle_port", ctx, mac=VALID_MAC, port_idx=port_idx, confirm=True)
        client.power_cycle_port.assert_awaited_once_with(VALID_MAC, port_idx)

    @pytest.mark.parametrize("port_idx", [0, -1, 53, 10_000])
    async def test_out_of_range_rejected(self, server, port_idx):
        client = AsyncMock()
        ctx = _ctx(client)
        with pytest.raises(ToolError, match="port_idx must be between 1 and 52"):
            await _call(server, "unifi_network_power_cycle_port", ctx, mac=VALID_MAC, port_idx=port_idx)
        client.power_cycle_port.assert_not_called()


class TestAssignPortProfilePortIdxBound:
    """Same bound for ``unifi_network_assign_port_profile``."""

    @pytest.fixture
    def server(self) -> FastMCP:
        s = FastMCP(name="t")
        register_port_profile_tools(s)
        return s

    async def test_in_range_passes_through(self, server):
        client = AsyncMock()
        client.assign_port_profile.return_value = {}
        ctx = _ctx(client)
        await _call(
            server,
            "unifi_network_assign_port_profile",
            ctx,
            mac=VALID_MAC,
            port_idx=12,
            profile_id="p-1",
            confirm=True,
        )
        client.assign_port_profile.assert_awaited_once_with(VALID_MAC, 12, "p-1")

    @pytest.mark.parametrize("port_idx", [0, -3, 100])
    async def test_out_of_range_rejected(self, server, port_idx):
        client = AsyncMock()
        ctx = _ctx(client)
        with pytest.raises(ToolError, match="port_idx must be between 1 and 52"):
            await _call(
                server,
                "unifi_network_assign_port_profile",
                ctx,
                mac=VALID_MAC,
                port_idx=port_idx,
                profile_id="p-1",
            )
        client.assign_port_profile.assert_not_called()
