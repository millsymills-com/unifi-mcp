"""Every tool handler routes client exceptions through handle_client_error.

The happy-path tests in ``test_handler_bodies_full.py`` leave the ``except``
branches uncovered. This file parametrises every read tool plus one sample
write tool per module and asserts that a raised ``UniFiAuthError`` flows
through to a ``ToolError``. Exercising these paths lifts each tool module's
coverage into the 90s without duplicating HTTP-wire tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from unifi_mcp.config import UniFiConfig, UniFiMode
from unifi_mcp.errors import UniFiAuthError
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
from unifi_mcp.tools.protect.media import register_media_tools
from unifi_mcp.tools.protect.nvr import register_nvr_tools
from unifi_mcp.tools.site_manager.discovery import register_site_manager_tools


@dataclass
class _FakeLifespan:
    config: UniFiConfig
    clients: dict[str, Any] = field(default_factory=dict)


def _config() -> UniFiConfig:
    return UniFiConfig(
        _env_file=None,
        unifi_mode=UniFiMode.READWRITE,
        unifi_network_api="k",
        unifi_protect_api="k",
        unifi_site_manager_api="k",
    )


def _ctx(client_key: str, client: AsyncMock) -> AsyncMock:
    ctx = AsyncMock()
    ctx.lifespan_context = _FakeLifespan(config=_config(), clients={client_key: client})
    return ctx


async def _call_and_assert_tool_error(server, tool_name, ctx, **kwargs):
    tool = await server.get_tool(tool_name)
    with pytest.raises(ToolError, match="Authentication failed"):
        await tool.fn(ctx, **kwargs)


ERROR_PATH_CASES: list[tuple[Any, str, str, str, dict[str, Any]]] = [
    # Network stats (read-only)
    (register_stats_tools, "unifi_network_get_health", "get_health", "network", {}),
    (register_stats_tools, "unifi_network_list_events", "list_events", "network", {}),
    (register_stats_tools, "unifi_network_list_devices", "list_devices", "network", {}),
    (register_stats_tools, "unifi_network_list_devices_basic", "list_devices_basic", "network", {}),
    (register_stats_tools, "unifi_network_list_active_clients", "list_active_clients", "network", {}),
    (register_stats_tools, "unifi_network_list_configured_clients", "list_configured_clients", "network", {}),
    (register_stats_tools, "unifi_network_list_all_clients", "list_all_clients", "network", {}),
    (register_stats_tools, "unifi_network_get_dpi_stats", "get_dpi_stats", "network", {}),
    (register_stats_tools, "unifi_network_get_sysinfo", "get_sysinfo", "network", {}),
    # Network devices (one write per verb covers the except branch)
    (register_device_tools, "unifi_network_restart_device", "restart_device", "network", {"mac": "aa:bb:cc:dd:ee:ff"}),
    (register_device_tools, "unifi_network_adopt_device", "adopt_device", "network", {"mac": "aa:bb:cc:dd:ee:ff"}),
    (register_device_tools, "unifi_network_locate_device", "locate_device", "network", {"mac": "aa:bb:cc:dd:ee:ff"}),
    (
        register_device_tools,
        "unifi_network_unlocate_device",
        "unlocate_device",
        "network",
        {"mac": "aa:bb:cc:dd:ee:ff"},
    ),
    (
        register_device_tools,
        "unifi_network_provision_device",
        "provision_device",
        "network",
        {"mac": "aa:bb:cc:dd:ee:ff"},
    ),
    # Network clients
    (register_client_tools, "unifi_network_block_client", "block_client", "network", {"mac": "aa:bb:cc:dd:ee:ff"}),
    (register_client_tools, "unifi_network_unblock_client", "unblock_client", "network", {"mac": "aa:bb:cc:dd:ee:ff"}),
    (register_client_tools, "unifi_network_kick_client", "kick_client", "network", {"mac": "aa:bb:cc:dd:ee:ff"}),
    (
        register_client_tools,
        "unifi_network_authorize_guest",
        "authorize_guest",
        "network",
        {"mac": "aa:bb:cc:dd:ee:ff"},
    ),
    # WLAN
    (register_wlan_tools, "unifi_network_list_wlans", "list_wlans", "network", {}),
    (register_wlan_tools, "unifi_network_get_wlan", "get_wlan", "network", {"wlan_id": "w-1"}),
    (register_wlan_tools, "unifi_network_create_wlan", "create_wlan", "network", {"name": "n"}),
    (register_wlan_tools, "unifi_network_update_wlan", "update_wlan", "network", {"wlan_id": "w-1", "data": {}}),
    (register_wlan_tools, "unifi_network_delete_wlan", "delete_wlan", "network", {"wlan_id": "w-1"}),
    # Firewall
    (register_firewall_tools, "unifi_network_list_firewall_rules", "list_firewall_rules", "network", {}),
    (register_firewall_tools, "unifi_network_get_firewall_rule", "get_firewall_rule", "network", {"rule_id": "r"}),
    (register_firewall_tools, "unifi_network_list_firewall_groups", "list_firewall_groups", "network", {}),
    (register_firewall_tools, "unifi_network_get_firewall_group", "get_firewall_group", "network", {"group_id": "g"}),
    (
        register_firewall_tools,
        "unifi_network_create_firewall_rule",
        "create_firewall_rule",
        "network",
        {"name": "r", "ruleset": "WAN_IN"},
    ),
    (
        register_firewall_tools,
        "unifi_network_update_firewall_rule",
        "update_firewall_rule",
        "network",
        {"rule_id": "r", "data": {}},
    ),
    (
        register_firewall_tools,
        "unifi_network_delete_firewall_rule",
        "delete_firewall_rule",
        "network",
        {"rule_id": "r"},
    ),
    (
        register_firewall_tools,
        "unifi_network_create_firewall_group",
        "create_firewall_group",
        "network",
        {"name": "g", "group_type": "address-group", "group_members": []},
    ),
    (
        register_firewall_tools,
        "unifi_network_update_firewall_group",
        "update_firewall_group",
        "network",
        {"group_id": "g", "data": {}},
    ),
    (
        register_firewall_tools,
        "unifi_network_delete_firewall_group",
        "delete_firewall_group",
        "network",
        {"group_id": "g"},
    ),
    # Networks
    (register_network_config_tools, "unifi_network_list_networks", "list_networks", "network", {}),
    (register_network_config_tools, "unifi_network_get_network", "get_network", "network", {"network_id": "n"}),
    (
        register_network_config_tools,
        "unifi_network_create_network",
        "create_network",
        "network",
        {"name": "n", "purpose": "corporate"},
    ),
    (
        register_network_config_tools,
        "unifi_network_update_network",
        "update_network",
        "network",
        {"network_id": "n", "data": {}},
    ),
    (register_network_config_tools, "unifi_network_delete_network", "delete_network", "network", {"network_id": "n"}),
    # Port forward
    (register_port_forward_tools, "unifi_network_list_port_forwards", "list_port_forwards", "network", {}),
    (
        register_port_forward_tools,
        "unifi_network_get_port_forward",
        "get_port_forward",
        "network",
        {"port_forward_id": "pf"},
    ),
    (
        register_port_forward_tools,
        "unifi_network_create_port_forward",
        "create_port_forward",
        "network",
        {"name": "pf", "dst_port": "22", "fwd": "10.0.0.1", "fwd_port": "22"},
    ),
    (
        register_port_forward_tools,
        "unifi_network_update_port_forward",
        "update_port_forward",
        "network",
        {"port_forward_id": "pf", "data": {}},
    ),
    (
        register_port_forward_tools,
        "unifi_network_delete_port_forward",
        "delete_port_forward",
        "network",
        {"port_forward_id": "pf"},
    ),
    # Routing
    (register_routing_tools, "unifi_network_list_routes", "list_routes", "network", {}),
    (register_routing_tools, "unifi_network_get_route", "get_route", "network", {"route_id": "r"}),
    (
        register_routing_tools,
        "unifi_network_create_route",
        "create_route",
        "network",
        {"name": "r", "network": "10.0.0.0/24", "gateway_ip": "10.0.0.1"},
    ),
    (register_routing_tools, "unifi_network_update_route", "update_route", "network", {"route_id": "r", "data": {}}),
    (register_routing_tools, "unifi_network_delete_route", "delete_route", "network", {"route_id": "r"}),
    # System
    (register_system_tools, "unifi_network_get_settings", "get_settings", "network", {}),
    (
        register_system_tools,
        "unifi_network_update_settings",
        "update_settings",
        "network",
        {"ntp_server_1": "time.example.com"},
    ),
    (register_system_tools, "unifi_network_run_speedtest", "run_speedtest", "network", {}),
    (register_system_tools, "unifi_network_create_backup", "create_backup", "network", {}),
    (register_system_tools, "unifi_network_upgrade_device", "upgrade_device", "network", {"mac": "aa:bb:cc:dd:ee:ff"}),
    (
        register_system_tools,
        "unifi_network_power_cycle_port",
        "power_cycle_port",
        "network",
        {"mac": "aa:bb:cc:dd:ee:ff", "port_idx": 1},
    ),
    (
        register_system_tools,
        "unifi_network_unauthorize_guest",
        "unauthorize_guest",
        "network",
        {"mac": "aa:bb:cc:dd:ee:ff"},
    ),
    (register_system_tools, "unifi_network_reset_dpi", "reset_dpi", "network", {}),
    # Protect
    (register_camera_tools, "unifi_protect_list_cameras", "list_cameras", "protect", {}),
    (register_camera_tools, "unifi_protect_get_camera", "get_camera", "protect", {"camera_id": "c"}),
    (
        register_camera_tools,
        "unifi_protect_update_camera",
        "update_camera",
        "protect",
        {"camera_id": "c", "name": "cam"},
    ),
    (
        register_camera_tools,
        "unifi_protect_set_recording_mode",
        "set_recording_mode",
        "protect",
        {"camera_id": "c", "mode": "motion"},
    ),
    (
        register_camera_tools,
        "unifi_protect_set_smart_detection",
        "set_smart_detection",
        "protect",
        {"camera_id": "c", "object_types": []},
    ),
    (register_protect_device_tools, "unifi_protect_list_chimes", "list_chimes", "protect", {}),
    (register_protect_device_tools, "unifi_protect_list_lights", "list_lights", "protect", {}),
    (register_protect_device_tools, "unifi_protect_list_sensors", "list_sensors", "protect", {}),
    (register_protect_device_tools, "unifi_protect_list_viewers", "list_viewers", "protect", {}),
    (
        register_protect_device_tools,
        "unifi_protect_update_chime",
        "update_chime",
        "protect",
        {"chime_id": "ch", "volume": 50},
    ),
    (
        register_protect_device_tools,
        "unifi_protect_update_light",
        "update_light",
        "protect",
        {"light_id": "li", "led_level": 3},
    ),
    (
        register_protect_device_tools,
        "unifi_protect_set_light_mode",
        "update_light",
        "protect",
        {"light_id": "li", "mode": "motion"},
    ),
    (
        register_protect_device_tools,
        "unifi_protect_update_sensor",
        "update_sensor",
        "protect",
        {"sensor_id": "se", "mount_type": "door"},
    ),
    (
        register_protect_device_tools,
        "unifi_protect_set_viewer_liveview",
        "update_viewer",
        "protect",
        {"viewer_id": "vi", "liveview_id": "lv"},
    ),
    (register_nvr_tools, "unifi_protect_get_nvr", "get_nvr", "protect", {}),
    (register_media_tools, "unifi_protect_get_snapshot", "get_snapshot", "protect", {"camera_id": "c"}),
    (
        register_media_tools,
        "unifi_protect_export_video",
        "export_video",
        "protect",
        {"camera_id": "c", "start": 1, "end": 2},
    ),
    # Site Manager
    (register_site_manager_tools, "unifi_site_manager_list_hosts", "list_hosts", "site_manager", {}),
    (register_site_manager_tools, "unifi_site_manager_list_sites", "list_sites", "site_manager", {}),
    (register_site_manager_tools, "unifi_site_manager_list_devices", "list_devices", "site_manager", {}),
]


@pytest.mark.parametrize(
    ("register_fn", "tool_name", "client_method", "client_key", "kwargs"),
    ERROR_PATH_CASES,
)
async def test_tool_propagates_unifi_auth_error_as_tool_error(
    register_fn, tool_name, client_method, client_key, kwargs
):
    server = FastMCP(name="err-test")
    register_fn(server)
    client = AsyncMock()
    getattr(client, client_method).side_effect = UniFiAuthError("bad", status_code=401)
    ctx = _ctx(client_key, client)
    await _call_and_assert_tool_error(server, tool_name, ctx, **kwargs)
