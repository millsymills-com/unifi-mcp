"""Denylist guard for ``dict[str, Any]`` write tools (#147).

Verifies ``unifi_mcp.tools._common.reject_dangerous_keys`` raises on every
denylist key (exact / prefix / suffix), at every nesting depth, and that
each of the 12 affected write tools wires the guard before the client call.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from unifi_mcp.config import UniFiConfig, UniFiMode
from unifi_mcp.errors import UniFiBadRequestError
from unifi_mcp.tools._common import reject_dangerous_keys
from unifi_mcp.tools.network.firewall import register_firewall_tools
from unifi_mcp.tools.network.networks import register_network_config_tools
from unifi_mcp.tools.network.port_forward import register_port_forward_tools
from unifi_mcp.tools.network.port_profiles import register_port_profile_tools
from unifi_mcp.tools.network.routing import register_routing_tools
from unifi_mcp.tools.network.system import register_system_tools
from unifi_mcp.tools.network.wlan import register_wlan_tools
from unifi_mcp.tools.protect.cameras import register_camera_tools

# ── Helper: direct denylist tests ──────────────────────────────────────────


class TestRejectDangerousKeysExact:
    @pytest.mark.parametrize(
        "key",
        ["cmd", "x_cmd", "is_admin", "role", "roles", "permissions", "mac_filter_list", "mac_filter_enabled"],
    )
    def test_top_level_exact_key_raises(self, key):
        with pytest.raises(UniFiBadRequestError) as exc:
            reject_dangerous_keys({key: "v"}, tool_name="t")
        assert key in str(exc.value)

    def test_top_level_safe_keys_pass(self):
        reject_dangerous_keys({"name": "x", "enabled": True}, tool_name="t")  # no raise


class TestRejectDangerousKeysWildcards:
    @pytest.mark.parametrize(
        "key",
        ["super_mgmt_url", "super_smtp_password", "super_identity_url", "super_anything"],
    )
    def test_super_prefix_raises(self, key):
        with pytest.raises(UniFiBadRequestError) as exc:
            reject_dangerous_keys({key: "v"}, tool_name="t")
        assert key in str(exc.value)

    @pytest.mark.parametrize("key", ["radius_secret", "radius_servers", "radius_acct_port"])
    def test_radius_prefix_raises(self, key):
        with pytest.raises(UniFiBadRequestError):
            reject_dangerous_keys({key: "v"}, tool_name="t")

    @pytest.mark.parametrize("key", ["callback_url", "webhook_url", "smtp_url"])
    def test_url_suffix_raises(self, key):
        with pytest.raises(UniFiBadRequestError):
            reject_dangerous_keys({key: "v"}, tool_name="t")

    @pytest.mark.parametrize("key", ["x_command", "shutdown_command", "boot_command"])
    def test_command_suffix_raises(self, key):
        with pytest.raises(UniFiBadRequestError):
            reject_dangerous_keys({key: "v"}, tool_name="t")


class TestRejectDangerousKeysRecursion:
    def test_nested_dict_radius_secret_raises(self):
        with pytest.raises(UniFiBadRequestError) as exc:
            reject_dangerous_keys({"wlan": {"settings": {"radius_secret": "x"}}}, tool_name="t")
        assert "wlan.settings.radius_secret" in str(exc.value)

    def test_inside_list_of_dicts_raises(self):
        with pytest.raises(UniFiBadRequestError) as exc:
            reject_dangerous_keys({"data": [{"ok": 1}, {"super_x_password": "y"}]}, tool_name="t")
        msg = str(exc.value)
        assert "data[1].super_x_password" in msg

    def test_deep_safe_payload_passes(self):
        reject_dangerous_keys(
            {"data": [{"name": "g", "subnet": "10.0.0.0/24", "vlan": 10}]},
            tool_name="t",
        )

    def test_x_passphrase_is_not_on_smuggling_denylist(self):
        """x_passphrase is sensitive on output (see #146) but is the
        legitimate Wi-Fi-creation field on write, so the denylist must not
        block it."""
        reject_dangerous_keys({"name": "g", "x_passphrase": "ok-pw"}, tool_name="t")


class TestRejectDangerousKeysNormalization:
    """Keys are normalized (lowercase + strip underscores) before matching
    so the same denylist catches snake_case (Network) and camelCase
    (Protect) variants."""

    @pytest.mark.parametrize(
        "key",
        ["RADIUS_secret", "Radius_Servers", "radiusServers", "RadiusServers"],
    )
    def test_radius_prefix_case_and_form_insensitive(self, key):
        with pytest.raises(UniFiBadRequestError):
            reject_dangerous_keys({key: "v"}, tool_name="t")

    @pytest.mark.parametrize("key", ["Cmd", "CMD", "isAdmin", "is_Admin"])
    def test_exact_keys_case_and_form_insensitive(self, key):
        with pytest.raises(UniFiBadRequestError):
            reject_dangerous_keys({key: "v"}, tool_name="t")

    @pytest.mark.parametrize(
        "key",
        ["callbackUrl", "webhookUrl", "smtpUrl", "callbackURL"],
    )
    def test_camelcase_url_suffix_caught(self, key):
        with pytest.raises(UniFiBadRequestError) as exc:
            reject_dangerous_keys({key: "v"}, tool_name="t")
        assert key in str(exc.value)

    @pytest.mark.parametrize("key", ["xCommand", "shutdownCommand", "bootCommand"])
    def test_camelcase_command_suffix_caught(self, key):
        with pytest.raises(UniFiBadRequestError):
            reject_dangerous_keys({key: "v"}, tool_name="t")

    @pytest.mark.parametrize("key", ["superMgmtUrl", "superSmtpPassword"])
    def test_camelcase_super_pattern_caught(self, key):
        # `superMgmtUrl` normalizes to `supermgmturl` which starts with `super`
        # (the normalized prefix) — caught by the prefix rule, no special case
        # needed.
        with pytest.raises(UniFiBadRequestError):
            reject_dangerous_keys({key: "v"}, tool_name="t")


# ── Per-tool integration: guard runs before client ─────────────────────────


@dataclass
class FakeLifespan:
    config: UniFiConfig
    clients: dict[str, Any] = field(default_factory=dict)


def _readwrite_config() -> UniFiConfig:
    return UniFiConfig(
        _env_file=None,
        unifi_mode=UniFiMode.READWRITE,
        unifi_network_api="k",
        unifi_protect_api="k",
        unifi_site_manager_api=None,
    )


def _fake_ctx(**clients: Any) -> AsyncMock:
    ctx = AsyncMock()
    ctx.lifespan_context = FakeLifespan(config=_readwrite_config(), clients=clients)
    return ctx


async def _call(server: FastMCP, tool_name: str, ctx: AsyncMock, **kwargs: Any) -> Any:
    tool = await server.get_tool(tool_name)
    return await tool.fn(ctx, **kwargs)


# Each entry: tool_name -> (register_fn, payload_kwargs)
# Payload uses a denied key so a successful call would mean the guard missed.
DENIED_PAYLOAD = {"radius_secret": "boom"}
GUARDED_WRITE_TOOLS = [
    ("unifi_network_update_settings", register_system_tools, {"data": DENIED_PAYLOAD}),
    ("unifi_network_update_wlan", register_wlan_tools, {"wlan_id": "w-1", "data": DENIED_PAYLOAD}),
    ("unifi_network_update_network", register_network_config_tools, {"network_id": "n-1", "data": DENIED_PAYLOAD}),
    (
        "unifi_network_create_firewall_rule",
        register_firewall_tools,
        {"name": "x", "ruleset": "LAN_IN", "data": DENIED_PAYLOAD},
    ),
    ("unifi_network_update_firewall_rule", register_firewall_tools, {"rule_id": "r-1", "data": DENIED_PAYLOAD}),
    ("unifi_network_update_firewall_group", register_firewall_tools, {"group_id": "g-1", "data": DENIED_PAYLOAD}),
    (
        "unifi_network_update_port_forward",
        register_port_forward_tools,
        {"port_forward_id": "p-1", "data": DENIED_PAYLOAD},
    ),
    ("unifi_network_create_port_profile", register_port_profile_tools, {"data": DENIED_PAYLOAD}),
    (
        "unifi_network_update_port_profile",
        register_port_profile_tools,
        {"profile_id": "p-1", "data": DENIED_PAYLOAD},
    ),
    ("unifi_network_update_route", register_routing_tools, {"route_id": "r-1", "data": DENIED_PAYLOAD}),
    ("unifi_protect_update_camera", register_camera_tools, {"camera_id": "c-1", "data": DENIED_PAYLOAD}),
]


@pytest.mark.parametrize(("tool_name", "register_fn", "kwargs"), GUARDED_WRITE_TOOLS)
async def test_each_write_tool_blocks_radius_secret(tool_name, register_fn, kwargs):
    server = FastMCP(name="t")
    register_fn(server)

    # Mocks: client methods raise if called — the guard must short-circuit.
    network_client = AsyncMock()
    protect_client = AsyncMock()
    for name in (
        "update_settings",
        "update_wlan",
        "update_network",
        "create_firewall_rule",
        "update_firewall_rule",
        "update_firewall_group",
        "update_port_forward",
        "create_port_profile",
        "update_port_profile",
        "update_route",
    ):
        getattr(network_client, name).side_effect = AssertionError(
            f"client {name}() must NOT be called when payload contains a denied key"
        )
    for name in ("update_camera",):
        getattr(protect_client, name).side_effect = AssertionError(
            f"client {name}() must NOT be called when payload contains a denied key"
        )

    ctx = _fake_ctx(network=network_client, protect=protect_client)

    # Tools wrap the error via `handle_client_error`, which maps
    # `UniFiBadRequestError` to FastMCP `ToolError`.
    with pytest.raises(ToolError) as exc:
        await _call(server, tool_name, ctx, **kwargs)
    assert "radius_secret" in str(exc.value)
