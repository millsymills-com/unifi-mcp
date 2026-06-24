"""Confirm-gate invariant for destructive write tools (ADR-0001).

Two guards:

1. ``TestConfirmInvariant`` pins the server-wide rule that a tool is marked
   ``destructiveHint: True`` **iff** it exposes a ``confirm: boolean = false``
   parameter. This is the testable form of ADR-0001's decision and fails the
   moment a new destructive tool ships without the gate (or vice versa).
2. ``TestLegacyConfirmGuards`` drives every legacy-network destructive tool
   through its handler and asserts that omitting ``confirm`` raises before the
   client is ever called.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from unifi_mcp.config import UniFiConfig, UniFiMode
from unifi_mcp.server import create_server
from unifi_mcp.tools.network.clients import register_client_tools
from unifi_mcp.tools.network.devices import register_device_tools
from unifi_mcp.tools.network.firewall import register_firewall_tools
from unifi_mcp.tools.network.networks import register_network_config_tools
from unifi_mcp.tools.network.port_forward import register_port_forward_tools
from unifi_mcp.tools.network.port_profiles import register_port_profile_tools
from unifi_mcp.tools.network.routing import register_routing_tools
from unifi_mcp.tools.network.system import register_system_tools
from unifi_mcp.tools.network.wlan import register_wlan_tools

VALID_MAC = "aa:bb:cc:dd:ee:ff"


@dataclass
class _FakeLifespan:
    config: UniFiConfig
    clients: dict[str, Any] = field(default_factory=dict)


def _config() -> UniFiConfig:
    return UniFiConfig(
        _env_file=None,
        unifi_mode=UniFiMode.READWRITE,
        unifi_network_api="net",
        unifi_protect_api="prot",
        unifi_site_manager_api="sm",
    )


def _ctx(client: AsyncMock) -> AsyncMock:
    ctx = AsyncMock()
    ctx.lifespan_context = _FakeLifespan(config=_config(), clients={"network": client})
    return ctx


class TestConfirmInvariant:
    """``destructiveHint: True`` iff a ``confirm`` boolean param exists."""

    async def test_destructive_hint_matches_confirm_param(self):
        tools = await create_server(_config()).list_tools()
        mismatches: list[str] = []
        for tool in tools:
            destructive = bool(tool.annotations and tool.annotations.destructiveHint)
            properties = (tool.parameters or {}).get("properties") or {}
            has_confirm = "confirm" in properties
            if destructive != has_confirm:
                mismatches.append(f"{tool.name}: destructiveHint={destructive} confirm_param={has_confirm}")
        assert mismatches == [], "destructiveHint must match presence of a confirm param:\n" + "\n".join(mismatches)

    async def test_confirm_param_is_boolean_defaulting_false(self):
        tools = await create_server(_config()).list_tools()
        confirm_tools = [t for t in tools if "confirm" in ((t.parameters or {}).get("properties") or {})]
        assert confirm_tools, "expected at least one confirm-gated tool"
        for tool in confirm_tools:
            spec = tool.parameters["properties"]["confirm"]
            assert spec.get("type") == "boolean", f"{tool.name} confirm is not boolean: {spec}"
            assert spec.get("default") is False, f"{tool.name} confirm default is not False: {spec}"
            required = (tool.parameters or {}).get("required") or []
            assert "confirm" not in required, f"{tool.name} confirm should be optional"


# Each row pairs a register fn and tool name with the client method it should
# reach and the call kwargs to use, deliberately omitting the confirm argument.
LEGACY_DESTRUCTIVE: list[tuple[Any, str, str, dict[str, Any]]] = [
    (register_firewall_tools, "unifi_network_delete_firewall_rule", "delete_firewall_rule", {"rule_id": "r"}),
    (register_firewall_tools, "unifi_network_delete_firewall_group", "delete_firewall_group", {"group_id": "g"}),
    (
        register_port_forward_tools,
        "unifi_network_delete_port_forward",
        "delete_port_forward",
        {"port_forward_id": "pf"},
    ),
    (register_wlan_tools, "unifi_network_delete_wlan", "delete_wlan", {"wlan_id": "w"}),
    (register_network_config_tools, "unifi_network_delete_network", "delete_network", {"network_id": "n"}),
    (register_routing_tools, "unifi_network_delete_route", "delete_route", {"route_id": "r"}),
    (register_port_profile_tools, "unifi_network_delete_port_profile", "delete_port_profile", {"profile_id": "p"}),
    (
        register_port_profile_tools,
        "unifi_network_assign_port_profile",
        "assign_port_profile",
        {"mac": VALID_MAC, "port_idx": 3, "profile_id": "p"},
    ),
    (register_system_tools, "unifi_network_upgrade_device", "upgrade_device", {"mac": VALID_MAC}),
    (register_system_tools, "unifi_network_power_cycle_port", "power_cycle_port", {"mac": VALID_MAC, "port_idx": 3}),
    (register_system_tools, "unifi_network_reset_dpi", "reset_dpi", {}),
    (register_client_tools, "unifi_network_block_client", "block_client", {"mac": VALID_MAC}),
    (register_device_tools, "unifi_network_restart_device", "restart_device", {"mac": VALID_MAC}),
    (register_device_tools, "unifi_network_adopt_device", "adopt_device", {"mac": VALID_MAC}),
    (register_device_tools, "unifi_network_forget_device", "forget_device", {"mac": VALID_MAC}),
]


class TestLegacyConfirmGuards:
    """Each legacy destructive tool refuses to act without ``confirm=True``."""

    @pytest.mark.parametrize(("register_fn", "tool_name", "client_method", "kwargs"), LEGACY_DESTRUCTIVE)
    async def test_without_confirm_raises_before_client(self, register_fn, tool_name, client_method, kwargs):
        server = FastMCP(name="t")
        register_fn(server)
        client = AsyncMock()
        ctx = _ctx(client)
        tool = await server.get_tool(tool_name)
        with pytest.raises(ToolError, match="confirm=True"):
            await tool.fn(ctx, **kwargs)
        getattr(client, client_method).assert_not_awaited()

    @pytest.mark.parametrize(("register_fn", "tool_name", "client_method", "kwargs"), LEGACY_DESTRUCTIVE)
    async def test_explicit_confirm_false_raises_before_client(self, register_fn, tool_name, client_method, kwargs):
        server = FastMCP(name="t")
        register_fn(server)
        client = AsyncMock()
        ctx = _ctx(client)
        tool = await server.get_tool(tool_name)
        with pytest.raises(ToolError, match="confirm=True"):
            await tool.fn(ctx, **kwargs, confirm=False)
        getattr(client, client_method).assert_not_awaited()

    @pytest.mark.parametrize(("register_fn", "tool_name", "client_method", "kwargs"), LEGACY_DESTRUCTIVE)
    async def test_with_confirm_calls_client(self, register_fn, tool_name, client_method, kwargs):
        server = FastMCP(name="t")
        register_fn(server)
        client = AsyncMock()
        getattr(client, client_method).return_value = {"ok": True}
        ctx = _ctx(client)
        tool = await server.get_tool(tool_name)
        result = await tool.fn(ctx, **kwargs, confirm=True)
        assert result == {"ok": True}
        getattr(client, client_method).assert_awaited_once()
