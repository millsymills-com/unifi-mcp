"""Exhaustive handler-body coverage — one happy path per remaining tool.

Supplements ``test_handler_bodies.py`` (which covers a selection). This file
parametrises the rest so every handler body executes at least once against a
mocked client + fake lifespan context, pushing tool-module coverage from
~30-55% up to the high-80s/90s.
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
from unifi_mcp.tools.network.routing import register_routing_tools
from unifi_mcp.tools.network.stats import register_stats_tools
from unifi_mcp.tools.network.system import register_system_tools
from unifi_mcp.tools.network.wlan import register_wlan_tools
from unifi_mcp.tools.protect.cameras import register_camera_tools
from unifi_mcp.tools.protect.devices import register_protect_device_tools
from unifi_mcp.tools.protect.nvr import register_nvr_tools
from unifi_mcp.tools.site_manager.discovery import register_site_manager_tools


@dataclass
class _FakeLifespan:
    config: UniFiConfig
    clients: dict[str, Any] = field(default_factory=dict)


def _config(mode: UniFiMode = UniFiMode.READWRITE) -> UniFiConfig:
    return UniFiConfig(
        _env_file=None,
        unifi_mode=mode,
        unifi_network_api="k",
        unifi_protect_api="k",
        unifi_site_manager_api="k",
    )


def _ctx(config: UniFiConfig, **clients: Any) -> AsyncMock:
    ctx = AsyncMock()
    ctx.lifespan_context = _FakeLifespan(config=config, clients=clients)
    return ctx


async def _call(server: FastMCP, tool_name: str, ctx: AsyncMock, **kwargs: Any) -> Any:
    tool = await server.get_tool(tool_name)
    return await tool.fn(ctx, **kwargs)


# Each entry: (register_fn, tool_name, client_method_name, tool_kwargs, client_expected_kwargs_subset)
# The client returns the sentinel {} — we just care the handler body runs.
NETWORK_HAPPY_PATHS = [
    # stats
    (register_stats_tools, "unifi_network_list_devices", "list_devices", {}, None),
    (register_stats_tools, "unifi_network_list_devices_basic", "list_devices_basic", {}, None),
    (register_stats_tools, "unifi_network_list_active_clients", "list_active_clients", {}, None),
    (register_stats_tools, "unifi_network_list_configured_clients", "list_configured_clients", {}, None),
    (register_stats_tools, "unifi_network_list_all_clients", "list_all_clients", {}, None),
    (
        register_stats_tools,
        "unifi_network_get_dpi_stats",
        "get_dpi_stats",
        {"dpi_type": "by_cat"},
        {"dpi_type": "by_cat"},
    ),
    (register_stats_tools, "unifi_network_get_sysinfo", "get_sysinfo", {}, None),
    # devices
    (
        register_device_tools,
        "unifi_network_adopt_device",
        "adopt_device",
        {"mac": "aa:bb:cc:dd:ee:ff", "confirm": True},
        None,
    ),
    (register_device_tools, "unifi_network_locate_device", "locate_device", {"mac": "aa:bb:cc:dd:ee:ff"}, None),
    (register_device_tools, "unifi_network_unlocate_device", "unlocate_device", {"mac": "aa:bb:cc:dd:ee:ff"}, None),
    (register_device_tools, "unifi_network_provision_device", "provision_device", {"mac": "aa:bb:cc:dd:ee:ff"}, None),
    # clients
    (register_client_tools, "unifi_network_unblock_client", "unblock_client", {"mac": "aa:bb:cc:dd:ee:ff"}, None),
    (register_client_tools, "unifi_network_kick_client", "kick_client", {"mac": "aa:bb:cc:dd:ee:ff"}, None),
    # wlan
    (register_wlan_tools, "unifi_network_list_wlans", "list_wlans", {}, None),
    (register_wlan_tools, "unifi_network_get_wlan", "get_wlan", {"wlan_id": "w-1"}, None),
    (register_wlan_tools, "unifi_network_update_wlan", "update_wlan", {"wlan_id": "w-1", "data": {}}, None),
    # firewall reads
    (register_firewall_tools, "unifi_network_list_firewall_rules", "list_firewall_rules", {}, None),
    (register_firewall_tools, "unifi_network_get_firewall_rule", "get_firewall_rule", {"rule_id": "r-1"}, None),
    (register_firewall_tools, "unifi_network_list_firewall_groups", "list_firewall_groups", {}, None),
    (register_firewall_tools, "unifi_network_get_firewall_group", "get_firewall_group", {"group_id": "g-1"}, None),
    # firewall writes
    (
        register_firewall_tools,
        "unifi_network_create_firewall_rule",
        "create_firewall_rule",
        {"name": "r", "ruleset": "WAN_IN"},
        None,
    ),
    (
        register_firewall_tools,
        "unifi_network_update_firewall_rule",
        "update_firewall_rule",
        {"rule_id": "r-1", "data": {}},
        None,
    ),
    (
        register_firewall_tools,
        "unifi_network_delete_firewall_rule",
        "delete_firewall_rule",
        {"rule_id": "r-1", "confirm": True},
        None,
    ),
    (
        register_firewall_tools,
        "unifi_network_create_firewall_group",
        "create_firewall_group",
        {"name": "g", "group_type": "address-group", "group_members": []},
        None,
    ),
    (
        register_firewall_tools,
        "unifi_network_update_firewall_group",
        "update_firewall_group",
        {"group_id": "g-1", "data": {}},
        None,
    ),
    (
        register_firewall_tools,
        "unifi_network_delete_firewall_group",
        "delete_firewall_group",
        {"group_id": "g-1", "confirm": True},
        None,
    ),
    # networks
    (register_network_config_tools, "unifi_network_list_networks", "list_networks", {}, None),
    (register_network_config_tools, "unifi_network_get_network", "get_network", {"network_id": "n-1"}, None),
    (
        register_network_config_tools,
        "unifi_network_create_network",
        "create_network",
        {"name": "n", "purpose": "corporate"},
        None,
    ),
    (
        register_network_config_tools,
        "unifi_network_update_network",
        "update_network",
        {"network_id": "n-1", "data": {}},
        None,
    ),
    (
        register_network_config_tools,
        "unifi_network_delete_network",
        "delete_network",
        {"network_id": "n-1", "confirm": True},
        None,
    ),
    # port forward
    (register_port_forward_tools, "unifi_network_list_port_forwards", "list_port_forwards", {}, None),
    (
        register_port_forward_tools,
        "unifi_network_get_port_forward",
        "get_port_forward",
        {"port_forward_id": "pf-1"},
        None,
    ),
    (
        register_port_forward_tools,
        "unifi_network_create_port_forward",
        "create_port_forward",
        {"name": "pf", "dst_port": "22", "fwd": "10.0.0.1", "fwd_port": "22"},
        None,
    ),
    (
        register_port_forward_tools,
        "unifi_network_update_port_forward",
        "update_port_forward",
        {"port_forward_id": "pf-1", "data": {}},
        None,
    ),
    (
        register_port_forward_tools,
        "unifi_network_delete_port_forward",
        "delete_port_forward",
        {"port_forward_id": "pf-1", "confirm": True},
        None,
    ),
    # routing
    (register_routing_tools, "unifi_network_list_routes", "list_routes", {}, None),
    (register_routing_tools, "unifi_network_get_route", "get_route", {"route_id": "r-1"}, None),
    (
        register_routing_tools,
        "unifi_network_create_route",
        "create_route",
        {"name": "r", "network": "10.0.0.0/24", "gateway_ip": "10.0.0.1"},
        None,
    ),
    (register_routing_tools, "unifi_network_update_route", "update_route", {"route_id": "r-1", "data": {}}, None),
    (
        register_routing_tools,
        "unifi_network_delete_route",
        "delete_route",
        {"route_id": "r-1", "confirm": True},
        None,
    ),
    # system
    (register_system_tools, "unifi_network_get_settings", "get_settings", {}, None),
    (
        register_system_tools,
        "unifi_network_update_settings",
        "update_settings",
        {"ntp_server_1": "time.example.com"},
        None,
    ),
    (register_system_tools, "unifi_network_run_speedtest", "run_speedtest", {}, None),
    (register_system_tools, "unifi_network_create_backup", "create_backup", {}, None),
    (
        register_system_tools,
        "unifi_network_power_cycle_port",
        "power_cycle_port",
        {"mac": "aa:bb:cc:dd:ee:ff", "port_idx": 3, "confirm": True},
        None,
    ),
    (register_system_tools, "unifi_network_unauthorize_guest", "unauthorize_guest", {"mac": "aa:bb:cc:dd:ee:ff"}, None),
    (register_system_tools, "unifi_network_reset_dpi", "reset_dpi", {"confirm": True}, None),
]


@pytest.mark.parametrize(
    ("register_fn", "tool_name", "client_method", "tool_kwargs", "client_kwargs_subset"),
    NETWORK_HAPPY_PATHS,
)
async def test_network_tool_happy_path(register_fn, tool_name, client_method, tool_kwargs, client_kwargs_subset):
    server = FastMCP(name="t")
    register_fn(server)
    client = AsyncMock()
    getattr(client, client_method).return_value = {"ok": True}
    ctx = _ctx(_config(), network=client)

    result = await _call(server, tool_name, ctx, **tool_kwargs)
    assert result == {"ok": True}

    getattr(client, client_method).assert_awaited_once()
    if client_kwargs_subset is not None:
        _, call_kwargs = getattr(client, client_method).call_args
        for key, value in client_kwargs_subset.items():
            assert call_kwargs[key] == value


PROTECT_HAPPY_PATHS = [
    (register_camera_tools, "unifi_protect_get_camera", "get_camera", {"camera_id": "cam-1"}),
    (
        register_camera_tools,
        "unifi_protect_update_camera",
        "update_camera",
        {"camera_id": "cam-1", "name": "cam"},
    ),
    (
        register_camera_tools,
        "unifi_protect_set_smart_detection",
        "set_smart_detection",
        {"camera_id": "cam-1", "object_types": ["person"]},
    ),
    (register_protect_device_tools, "unifi_protect_list_lights", "list_lights", {}),
    (register_protect_device_tools, "unifi_protect_list_sensors", "list_sensors", {}),
    (register_protect_device_tools, "unifi_protect_list_viewers", "list_viewers", {}),
]


@pytest.mark.parametrize(
    ("register_fn", "tool_name", "client_method", "tool_kwargs"),
    PROTECT_HAPPY_PATHS,
)
async def test_protect_tool_happy_path(register_fn, tool_name, client_method, tool_kwargs):
    server = FastMCP(name="t")
    register_fn(server)
    client = AsyncMock()
    getattr(client, client_method).return_value = {"ok": True}
    ctx = _ctx(_config(), protect=client)

    result = await _call(server, tool_name, ctx, **tool_kwargs)
    assert result == {"ok": True}
    getattr(client, client_method).assert_awaited_once()


SITE_MANAGER_HAPPY_PATHS = [
    ("unifi_site_manager_list_hosts", "list_hosts", {}),
    ("unifi_site_manager_list_sites", "list_sites", {}),
    ("unifi_site_manager_list_devices", "list_devices", {"host_id": "h-1"}),
]


@pytest.mark.parametrize(("tool_name", "client_method", "tool_kwargs"), SITE_MANAGER_HAPPY_PATHS)
async def test_site_manager_tool_happy_path(tool_name, client_method, tool_kwargs):
    server = FastMCP(name="t")
    register_site_manager_tools(server)
    client = AsyncMock()
    getattr(client, client_method).return_value = {"ok": True}
    ctx = _ctx(_config(), site_manager=client)

    result = await _call(server, tool_name, ctx, **tool_kwargs)
    assert result == {"ok": True}
    getattr(client, client_method).assert_awaited_once()


# Error propagation: exercise the handle_client_error branch on a handful of
# handlers across apis. The error-mapping branch is already extensively tested
# in tests/unit/test_errors.py — here we just confirm the tool body routes
# exceptions through handle_client_error instead of swallowing them.
@pytest.mark.parametrize(
    ("register_fn", "tool_name", "client_method", "client_key"),
    [
        (register_stats_tools, "unifi_network_get_health", "get_health", "network"),
        (register_nvr_tools, "unifi_protect_get_nvr", "get_nvr", "protect"),
        (register_site_manager_tools, "unifi_site_manager_list_hosts", "list_hosts", "site_manager"),
    ],
)
async def test_client_error_maps_to_tool_error(register_fn, tool_name, client_method, client_key):
    from unifi_mcp.errors import UniFiAuthError

    server = FastMCP(name="t")
    register_fn(server)
    client = AsyncMock()
    getattr(client, client_method).side_effect = UniFiAuthError("bad", status_code=401)
    ctx = _ctx(_config(), **{client_key: client})
    with pytest.raises(ToolError, match="Authentication failed"):
        await _call(server, tool_name, ctx)
