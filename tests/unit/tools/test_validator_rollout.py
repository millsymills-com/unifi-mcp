"""Validator rollout regression tests (#206 + #207).

PR #206 wired ``validate_id`` / ``validate_mac`` (from
``unifi_mcp.tools._common``) into a starter set of tools; #207 extended
the gate to every remaining ID-taking and MAC-taking tool. This file is
the combined regression net: it asserts, for *every* ID/MAC-taking tool
across Network, Protect, and Site Manager, that a path-traversal payload
is rejected at the tool layer before the request reaches the upstream
client method. A future change that drops a validator on any of these
tools will fail here.

The contract:

- Traversal payload (``../foo``) -> ``UniFiBadRequestError``
  -> wrapped as ``ToolError`` by ``handle_client_error``.
- Mocked client method is configured to ``raise AssertionError`` if
  called — the validator must short-circuit before then.
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
from unifi_mcp.tools.network.devices import register_device_tools
from unifi_mcp.tools.network.firewall import register_firewall_tools
from unifi_mcp.tools.network.networks import register_network_config_tools
from unifi_mcp.tools.network.port_forward import register_port_forward_tools
from unifi_mcp.tools.network.port_profiles import register_port_profile_tools
from unifi_mcp.tools.network.routing import register_routing_tools
from unifi_mcp.tools.network.system import register_system_tools
from unifi_mcp.tools.network.wlan import register_wlan_tools
from unifi_mcp.tools.protect.cameras import register_camera_tools
from unifi_mcp.tools.protect.media import register_media_tools
from unifi_mcp.tools.site_manager.discovery import register_site_manager_tools

TRAVERSAL = "../foo"


@dataclass
class _FakeLifespan:
    config: UniFiConfig
    clients: dict[str, Any] = field(default_factory=dict)


def _readwrite_config() -> UniFiConfig:
    return UniFiConfig(
        _env_file=None,
        unifi_mode=UniFiMode.READWRITE,
        unifi_network_api="k",
        unifi_protect_api="k",
        unifi_site_manager_api="k",
    )


def _ctx(**clients: Any) -> AsyncMock:
    ctx = AsyncMock()
    ctx.lifespan_context = _FakeLifespan(config=_readwrite_config(), clients=clients)
    return ctx


async def _call(server: FastMCP, tool_name: str, ctx: AsyncMock, **kwargs: Any) -> Any:
    tool = await server.get_tool(tool_name)
    return await tool.fn(ctx, **kwargs)


# Each entry: (register_fn, tool_name, kwargs_with_traversal, client_method, client_key).
# The named-arg in ``kwargs_with_traversal`` is the validated field; every
# other arg is a placeholder good enough to reach the validator call.
ID_TAKING_TOOLS: list[tuple[Any, str, dict[str, Any], str, str]] = [
    # network/wlan
    (register_wlan_tools, "unifi_network_get_wlan", {"wlan_id": TRAVERSAL}, "get_wlan", "network"),
    (
        register_wlan_tools,
        "unifi_network_update_wlan",
        {"wlan_id": TRAVERSAL, "data": {}},
        "update_wlan",
        "network",
    ),
    (register_wlan_tools, "unifi_network_delete_wlan", {"wlan_id": TRAVERSAL}, "delete_wlan", "network"),
    # network/firewall
    (
        register_firewall_tools,
        "unifi_network_get_firewall_rule",
        {"rule_id": TRAVERSAL},
        "get_firewall_rule",
        "network",
    ),
    (
        register_firewall_tools,
        "unifi_network_update_firewall_rule",
        {"rule_id": TRAVERSAL, "data": {}},
        "update_firewall_rule",
        "network",
    ),
    (
        register_firewall_tools,
        "unifi_network_delete_firewall_rule",
        {"rule_id": TRAVERSAL},
        "delete_firewall_rule",
        "network",
    ),
    (
        register_firewall_tools,
        "unifi_network_get_firewall_group",
        {"group_id": TRAVERSAL},
        "get_firewall_group",
        "network",
    ),
    (
        register_firewall_tools,
        "unifi_network_update_firewall_group",
        {"group_id": TRAVERSAL, "data": {}},
        "update_firewall_group",
        "network",
    ),
    (
        register_firewall_tools,
        "unifi_network_delete_firewall_group",
        {"group_id": TRAVERSAL},
        "delete_firewall_group",
        "network",
    ),
    # network/networks
    (
        register_network_config_tools,
        "unifi_network_get_network",
        {"network_id": TRAVERSAL},
        "get_network",
        "network",
    ),
    (
        register_network_config_tools,
        "unifi_network_update_network",
        {"network_id": TRAVERSAL, "data": {}},
        "update_network",
        "network",
    ),
    (
        register_network_config_tools,
        "unifi_network_delete_network",
        {"network_id": TRAVERSAL},
        "delete_network",
        "network",
    ),
    # network/port_forward
    (
        register_port_forward_tools,
        "unifi_network_get_port_forward",
        {"port_forward_id": TRAVERSAL},
        "get_port_forward",
        "network",
    ),
    (
        register_port_forward_tools,
        "unifi_network_update_port_forward",
        {"port_forward_id": TRAVERSAL, "data": {}},
        "update_port_forward",
        "network",
    ),
    (
        register_port_forward_tools,
        "unifi_network_delete_port_forward",
        {"port_forward_id": TRAVERSAL},
        "delete_port_forward",
        "network",
    ),
    # network/port_profiles
    (
        register_port_profile_tools,
        "unifi_network_get_port_profile",
        {"profile_id": TRAVERSAL},
        "get_port_profile",
        "network",
    ),
    (
        register_port_profile_tools,
        "unifi_network_update_port_profile",
        {"profile_id": TRAVERSAL, "data": {}},
        "update_port_profile",
        "network",
    ),
    (
        register_port_profile_tools,
        "unifi_network_delete_port_profile",
        {"profile_id": TRAVERSAL},
        "delete_port_profile",
        "network",
    ),
    (
        register_port_profile_tools,
        "unifi_network_assign_port_profile",
        {"mac": "aa:bb:cc:dd:ee:ff", "port_idx": 1, "profile_id": TRAVERSAL},
        "assign_port_profile",
        "network",
    ),
    # network/routing
    (register_routing_tools, "unifi_network_get_route", {"route_id": TRAVERSAL}, "get_route", "network"),
    (
        register_routing_tools,
        "unifi_network_update_route",
        {"route_id": TRAVERSAL, "data": {}},
        "update_route",
        "network",
    ),
    (
        register_routing_tools,
        "unifi_network_delete_route",
        {"route_id": TRAVERSAL},
        "delete_route",
        "network",
    ),
    # site_manager — host_id is optional but, when provided, must validate
    (
        register_site_manager_tools,
        "unifi_site_manager_list_devices",
        {"host_id": TRAVERSAL},
        "list_devices",
        "site_manager",
    ),
    # protect/cameras — wired in #206, pinned here so a future regression fails
    (
        register_camera_tools,
        "unifi_protect_get_camera",
        {"camera_id": TRAVERSAL},
        "get_camera",
        "protect",
    ),
    (
        register_camera_tools,
        "unifi_protect_update_camera",
        {"camera_id": TRAVERSAL, "name": "x"},
        "update_camera",
        "protect",
    ),
    (
        register_camera_tools,
        "unifi_protect_set_recording_mode",
        {"camera_id": TRAVERSAL, "mode": "motion"},
        "set_recording_mode",
        "protect",
    ),
    (
        register_camera_tools,
        "unifi_protect_set_smart_detection",
        {"camera_id": TRAVERSAL, "object_types": ["person"]},
        "set_smart_detection",
        "protect",
    ),
    # protect/media — wired in #206
    (
        register_media_tools,
        "unifi_protect_get_snapshot",
        {"camera_id": TRAVERSAL},
        "get_snapshot",
        "protect",
    ),
    (
        register_media_tools,
        "unifi_protect_export_video",
        {"camera_id": TRAVERSAL, "start": 1, "end": 2},
        "export_video",
        "protect",
    ),
]


MAC_TAKING_TOOLS: list[tuple[Any, str, dict[str, Any], str, str]] = [
    # network/devices
    (register_device_tools, "unifi_network_get_device", {"mac": TRAVERSAL}, "list_devices", "network"),
    (
        register_device_tools,
        "unifi_network_restart_device",
        {"mac": TRAVERSAL},
        "restart_device",
        "network",
    ),
    (register_device_tools, "unifi_network_adopt_device", {"mac": TRAVERSAL}, "adopt_device", "network"),
    (
        register_device_tools,
        "unifi_network_locate_device",
        {"mac": TRAVERSAL},
        "locate_device",
        "network",
    ),
    (
        register_device_tools,
        "unifi_network_unlocate_device",
        {"mac": TRAVERSAL},
        "unlocate_device",
        "network",
    ),
    (
        register_device_tools,
        "unifi_network_provision_device",
        {"mac": TRAVERSAL},
        "provision_device",
        "network",
    ),
    (
        register_device_tools,
        "unifi_network_forget_device",
        {"mac": TRAVERSAL},
        "forget_device",
        "network",
    ),
    # network/clients
    (
        register_client_tools,
        "unifi_network_get_client",
        {"mac": TRAVERSAL},
        "list_active_clients",
        "network",
    ),
    (
        register_client_tools,
        "unifi_network_block_client",
        {"mac": TRAVERSAL},
        "block_client",
        "network",
    ),
    (
        register_client_tools,
        "unifi_network_unblock_client",
        {"mac": TRAVERSAL},
        "unblock_client",
        "network",
    ),
    (register_client_tools, "unifi_network_kick_client", {"mac": TRAVERSAL}, "kick_client", "network"),
    (
        register_client_tools,
        "unifi_network_authorize_guest",
        {"mac": TRAVERSAL},
        "authorize_guest",
        "network",
    ),
    # network/system
    (
        register_system_tools,
        "unifi_network_upgrade_device",
        {"mac": TRAVERSAL},
        "upgrade_device",
        "network",
    ),
    (
        register_system_tools,
        "unifi_network_power_cycle_port",
        {"mac": TRAVERSAL, "port_idx": 1},
        "power_cycle_port",
        "network",
    ),
    (
        register_system_tools,
        "unifi_network_unauthorize_guest",
        {"mac": TRAVERSAL},
        "unauthorize_guest",
        "network",
    ),
    # network/port_profiles — mac is the validated field here
    (
        register_port_profile_tools,
        "unifi_network_assign_port_profile",
        {"mac": TRAVERSAL, "port_idx": 1, "profile_id": "p-1"},
        "assign_port_profile",
        "network",
    ),
]


def _trip_client(client_key: str, client_method: str) -> AsyncMock:
    """Return a mocked client that raises if its method is awaited."""
    client = AsyncMock()
    getattr(client, client_method).side_effect = AssertionError(
        f"client.{client_method}() must NOT be called: validator should reject the {client_key} payload"
    )
    return client


@pytest.mark.parametrize(
    ("register_fn", "tool_name", "kwargs", "client_method", "client_key"),
    ID_TAKING_TOOLS,
)
async def test_id_taking_tool_rejects_traversal(register_fn, tool_name, kwargs, client_method, client_key):
    server = FastMCP(name="t")
    register_fn(server)
    client = _trip_client(client_key, client_method)
    ctx = _ctx(**{client_key: client})

    with pytest.raises(ToolError, match="invalid id format"):
        await _call(server, tool_name, ctx, **kwargs)

    getattr(client, client_method).assert_not_awaited()


@pytest.mark.parametrize(
    ("register_fn", "tool_name", "kwargs", "client_method", "client_key"),
    MAC_TAKING_TOOLS,
)
async def test_mac_taking_tool_rejects_traversal(register_fn, tool_name, kwargs, client_method, client_key):
    server = FastMCP(name="t")
    register_fn(server)
    client = _trip_client(client_key, client_method)
    ctx = _ctx(**{client_key: client})

    with pytest.raises(ToolError, match="invalid mac format"):
        await _call(server, tool_name, ctx, **kwargs)

    getattr(client, client_method).assert_not_awaited()
