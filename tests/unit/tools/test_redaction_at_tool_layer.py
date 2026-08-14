"""Read-mode tools must redact secrets before returning to the agent (#146, #203)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastmcp import FastMCP

from unifi_mcp._redaction import REDACTED
from unifi_mcp.config import UniFiConfig, UniFiMode
from unifi_mcp.tools.network.clients import register_client_tools
from unifi_mcp.tools.network.firewall import register_firewall_tools
from unifi_mcp.tools.network.port_forward import register_port_forward_tools
from unifi_mcp.tools.network.port_profiles import register_port_profile_tools
from unifi_mcp.tools.network.routing import register_routing_tools
from unifi_mcp.tools.network.stats import register_stats_tools
from unifi_mcp.tools.network.system import register_system_tools
from unifi_mcp.tools.network.wlan import register_wlan_tools
from unifi_mcp.tools.protect.devices import register_protect_device_tools
from unifi_mcp.tools.protect.nvr import register_nvr_tools
from unifi_mcp.tools.site_manager.discovery import register_site_manager_tools


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


def _fake_ctx(**clients: Any) -> AsyncMock:
    ctx = AsyncMock()
    ctx.lifespan_context = FakeLifespan(config=_readonly_config(), clients=clients)
    return ctx


def _fake_rw_ctx(**clients: Any) -> AsyncMock:
    ctx = AsyncMock()
    ctx.lifespan_context = FakeLifespan(config=_readwrite_config(), clients=clients)
    return ctx


async def _call(server: FastMCP, tool_name: str, ctx: AsyncMock, **kwargs: Any) -> Any:
    tool = await server.get_tool(tool_name)
    return await tool.fn(ctx, **kwargs)


class TestNetworkWlanRedaction:
    @pytest.fixture
    def server(self) -> FastMCP:
        s = FastMCP(name="t")
        register_wlan_tools(s)
        return s

    async def test_list_wlans_redacts_psk_in_payload(self, server):
        network_client = AsyncMock()
        network_client.list_wlans = AsyncMock(
            return_value={"data": [{"name": "Home", "x_passphrase": "secret"}]},
        )
        ctx = _fake_ctx(network=network_client)
        result = await _call(server, "unifi_network_list_wlans", ctx)
        assert result["data"][0]["x_passphrase"] == REDACTED
        assert result["data"][0]["name"] == "Home"

    async def test_get_wlan_redacts_radius_secret(self, server):
        network_client = AsyncMock()
        network_client.get_wlan = AsyncMock(
            return_value={"_id": "w-1", "radius_secret": "r-sec", "name": "Corp"},
        )
        ctx = _fake_ctx(network=network_client)
        result = await _call(server, "unifi_network_get_wlan", ctx, wlan_id="w-1")
        assert result["radius_secret"] == REDACTED
        assert result["name"] == "Corp"


class TestNetworkSystemRedaction:
    @pytest.fixture
    def server(self) -> FastMCP:
        s = FastMCP(name="t")
        register_system_tools(s)
        return s

    async def test_get_settings_redacts_smtp_and_super_url(self, server):
        network_client = AsyncMock()
        network_client.get_settings = AsyncMock(
            return_value={
                "data": [
                    {
                        "key": "smtp",
                        "x_password": "smtp-pw",
                        "password": "raw",
                        "super_smtp_password": "super-pw",
                        "super_mgmt_url": "https://attacker.example/cb",
                        "name": "alerts",
                    }
                ]
            },
        )
        ctx = _fake_ctx(network=network_client)
        result = await _call(server, "unifi_network_get_settings", ctx)
        row = result["data"][0]
        assert row["x_password"] == REDACTED
        assert row["password"] == REDACTED
        assert row["super_smtp_password"] == REDACTED
        assert row["super_mgmt_url"] == REDACTED
        assert row["name"] == "alerts"


class TestNetworkClientsRedaction:
    @pytest.fixture
    def server(self) -> FastMCP:
        s = FastMCP(name="t")
        register_client_tools(s)
        return s

    async def test_get_client_redacts_token_in_returned_record(self, server):
        network_client = AsyncMock()
        network_client.list_active_clients = AsyncMock(
            return_value={
                "data": [
                    {"mac": "aa:bb:cc:dd:ee:01", "name": "Other", "token": "shouldnt"},
                    {"mac": "aa:bb:cc:dd:ee:02", "name": "Mine", "token": "secret-tok"},
                ]
            },
        )
        ctx = _fake_ctx(network=network_client)
        result = await _call(server, "unifi_network_get_client", ctx, mac="AA:BB:CC:DD:EE:02")
        assert result["token"] == REDACTED
        assert result["name"] == "Mine"


class TestProtectNvrRedaction:
    @pytest.fixture
    def server(self) -> FastMCP:
        s = FastMCP(name="t")
        register_nvr_tools(s)
        return s

    async def test_get_nvr_redacts_sso_token(self, server):
        protect_client = AsyncMock()
        protect_client.get_nvr = AsyncMock(
            return_value={"id": "nvr-1", "ssoToken": "tok", "name": "CloudKey"},
        )
        ctx = _fake_ctx(protect=protect_client)
        result = await _call(server, "unifi_protect_get_nvr", ctx)
        assert result["ssoToken"] == REDACTED
        assert result["name"] == "CloudKey"


class TestNetworkStatsRedaction:
    """#203 — extend redaction to remaining stats tools."""

    @pytest.fixture
    def server(self) -> FastMCP:
        s = FastMCP(name="t")
        register_stats_tools(s)
        return s

    async def test_get_health_redacts_token(self, server):
        network_client = AsyncMock()
        network_client.get_health = AsyncMock(
            return_value={"data": [{"subsystem": "wlan", "token": "leak", "status": "ok"}]},
        )
        ctx = _fake_ctx(network=network_client)
        result = await _call(server, "unifi_network_get_health", ctx)
        assert result["data"][0]["token"] == REDACTED
        assert result["data"][0]["subsystem"] == "wlan"

    async def test_list_events_redacts_password(self, server):
        network_client = AsyncMock()
        network_client.list_events = AsyncMock(
            return_value={"data": [{"msg": "User login", "password": "raw-pw"}]},
        )
        ctx = _fake_ctx(network=network_client)
        result = await _call(server, "unifi_network_list_events", ctx, limit=10)
        assert result["data"][0]["password"] == REDACTED
        assert result["data"][0]["msg"] == "User login"

    async def test_get_dpi_stats_redacts_secret(self, server):
        network_client = AsyncMock()
        network_client.get_dpi_stats = AsyncMock(
            return_value={"data": [{"app": "https", "client_secret": "leak"}]},
        )
        ctx = _fake_ctx(network=network_client)
        result = await _call(server, "unifi_network_get_dpi_stats", ctx)
        assert result["data"][0]["client_secret"] == REDACTED

    async def test_get_sysinfo_redacts_super_password(self, server):
        network_client = AsyncMock()
        network_client.get_sysinfo = AsyncMock(
            return_value={"data": [{"version": "9.0.0", "super_mgmt_password": "leak"}]},
        )
        ctx = _fake_ctx(network=network_client)
        result = await _call(server, "unifi_network_get_sysinfo", ctx)
        assert result["data"][0]["super_mgmt_password"] == REDACTED


class TestNetworkFirewallRedaction:
    """#203 — firewall read tools may surface RADIUS-like secrets."""

    @pytest.fixture
    def server(self) -> FastMCP:
        s = FastMCP(name="t")
        register_firewall_tools(s)
        return s

    async def test_list_firewall_rules_redacts_secret(self, server):
        network_client = AsyncMock()
        network_client.list_firewall_rules = AsyncMock(
            return_value={"data": [{"name": "block-x", "secret": "leak"}]},
        )
        ctx = _fake_ctx(network=network_client)
        result = await _call(server, "unifi_network_list_firewall_rules", ctx)
        assert result["data"][0]["secret"] == REDACTED
        assert result["data"][0]["name"] == "block-x"

    async def test_get_firewall_rule_redacts_token(self, server):
        network_client = AsyncMock()
        network_client.get_firewall_rule = AsyncMock(
            return_value={"_id": "fw-1", "token": "leak", "name": "r1"},
        )
        ctx = _fake_ctx(network=network_client)
        result = await _call(server, "unifi_network_get_firewall_rule", ctx, rule_id="fw-1")
        assert result["token"] == REDACTED

    async def test_list_firewall_groups_redacts_password(self, server):
        network_client = AsyncMock()
        network_client.list_firewall_groups = AsyncMock(
            return_value={"data": [{"name": "g1", "password": "leak"}]},
        )
        ctx = _fake_ctx(network=network_client)
        result = await _call(server, "unifi_network_list_firewall_groups", ctx)
        assert result["data"][0]["password"] == REDACTED

    async def test_get_firewall_group_redacts_apikey(self, server):
        network_client = AsyncMock()
        network_client.get_firewall_group = AsyncMock(
            return_value={"_id": "g-1", "api_key": "leak", "name": "g"},
        )
        ctx = _fake_ctx(network=network_client)
        result = await _call(server, "unifi_network_get_firewall_group", ctx, group_id="g-1")
        assert result["api_key"] == REDACTED


class TestNetworkPortForwardRedaction:
    @pytest.fixture
    def server(self) -> FastMCP:
        s = FastMCP(name="t")
        register_port_forward_tools(s)
        return s

    async def test_list_port_forwards_redacts_password(self, server):
        network_client = AsyncMock()
        network_client.list_port_forwards = AsyncMock(
            return_value={"data": [{"name": "ssh", "password": "leak"}]},
        )
        ctx = _fake_ctx(network=network_client)
        result = await _call(server, "unifi_network_list_port_forwards", ctx)
        assert result["data"][0]["password"] == REDACTED

    async def test_get_port_forward_redacts_secret(self, server):
        network_client = AsyncMock()
        network_client.get_port_forward = AsyncMock(
            return_value={"_id": "pf-1", "client_secret": "leak", "name": "pf"},
        )
        ctx = _fake_ctx(network=network_client)
        result = await _call(server, "unifi_network_get_port_forward", ctx, port_forward_id="pf-1")
        assert result["client_secret"] == REDACTED


class TestNetworkPortProfileRedaction:
    @pytest.fixture
    def server(self) -> FastMCP:
        s = FastMCP(name="t")
        register_port_profile_tools(s)
        return s

    async def test_list_port_profiles_redacts_token(self, server):
        network_client = AsyncMock()
        network_client.list_port_profiles = AsyncMock(
            return_value={"data": [{"name": "default", "token": "leak"}]},
        )
        ctx = _fake_ctx(network=network_client)
        result = await _call(server, "unifi_network_list_port_profiles", ctx)
        assert result["data"][0]["token"] == REDACTED

    async def test_get_port_profile_redacts_password(self, server):
        network_client = AsyncMock()
        network_client.get_port_profile = AsyncMock(
            return_value={"_id": "p-1", "password": "leak", "name": "ap-default"},
        )
        ctx = _fake_ctx(network=network_client)
        result = await _call(server, "unifi_network_get_port_profile", ctx, profile_id="p-1")
        assert result["password"] == REDACTED


class TestNetworkRoutingRedaction:
    @pytest.fixture
    def server(self) -> FastMCP:
        s = FastMCP(name="t")
        register_routing_tools(s)
        return s

    async def test_list_routes_redacts_secret(self, server):
        network_client = AsyncMock()
        network_client.list_routes = AsyncMock(
            return_value={"data": [{"name": "lan", "secret": "leak"}]},
        )
        ctx = _fake_ctx(network=network_client)
        result = await _call(server, "unifi_network_list_routes", ctx)
        assert result["data"][0]["secret"] == REDACTED

    async def test_get_route_redacts_token(self, server):
        network_client = AsyncMock()
        network_client.get_route = AsyncMock(
            return_value={"_id": "r-1", "token": "leak", "name": "r"},
        )
        ctx = _fake_ctx(network=network_client)
        result = await _call(server, "unifi_network_get_route", ctx, route_id="r-1")
        assert result["token"] == REDACTED


class TestProtectDevicesRedaction:
    """#203 — Protect accessory list tools return list[dict]."""

    @pytest.fixture
    def server(self) -> FastMCP:
        s = FastMCP(name="t")
        register_protect_device_tools(s)
        return s

    async def test_list_chimes_redacts_password(self, server):
        protect_client = AsyncMock()
        protect_client.list_chimes = AsyncMock(
            return_value=[{"id": "c-1", "name": "Doorbell", "password": "leak"}],
        )
        ctx = _fake_ctx(protect=protect_client)
        result = await _call(server, "unifi_protect_list_chimes", ctx)
        assert result[0]["password"] == REDACTED
        assert result[0]["name"] == "Doorbell"

    async def test_list_lights_redacts_token(self, server):
        protect_client = AsyncMock()
        protect_client.list_lights = AsyncMock(
            return_value=[{"id": "l-1", "name": "Porch", "token": "leak"}],
        )
        ctx = _fake_ctx(protect=protect_client)
        result = await _call(server, "unifi_protect_list_lights", ctx)
        assert result[0]["token"] == REDACTED

    async def test_list_sensors_redacts_secret(self, server):
        protect_client = AsyncMock()
        protect_client.list_sensors = AsyncMock(
            return_value=[{"id": "s-1", "name": "Door", "client_secret": "leak"}],
        )
        ctx = _fake_ctx(protect=protect_client)
        result = await _call(server, "unifi_protect_list_sensors", ctx)
        assert result[0]["client_secret"] == REDACTED

    async def test_list_viewers_redacts_sso_token(self, server):
        protect_client = AsyncMock()
        protect_client.list_viewers = AsyncMock(
            return_value=[{"id": "v-1", "name": "Wall", "ssoToken": "leak"}],
        )
        ctx = _fake_ctx(protect=protect_client)
        result = await _call(server, "unifi_protect_list_viewers", ctx)
        assert result[0]["ssoToken"] == REDACTED


class TestWriteResponseRedaction:
    """#325 — write tools echo the upstream object and must redact secrets too."""

    @pytest.fixture
    def server(self) -> FastMCP:
        s = FastMCP(name="t")
        register_wlan_tools(s)
        register_nvr_tools(s)
        return s

    async def test_update_wlan_redacts_passphrase_in_echoed_object(self, server):
        network_client = AsyncMock()
        network_client.update_wlan = AsyncMock(
            return_value={"_id": "w-1", "name": "Home", "x_passphrase": "super-secret", "radius_secret": "r-sec"},
        )
        ctx = _fake_rw_ctx(network=network_client)
        result = await _call(server, "unifi_network_update_wlan", ctx, wlan_id="w-1", data={"name": "Home"})
        assert result["x_passphrase"] == REDACTED
        assert result["radius_secret"] == REDACTED
        assert result["name"] == "Home"
        assert "super-secret" not in str(result)

    async def test_create_wlan_redacts_passphrase_in_echoed_object(self, server):
        network_client = AsyncMock()
        network_client.create_wlan = AsyncMock(
            return_value={"data": [{"_id": "w-2", "name": "Guest", "x_passphrase": "leak-me"}]},
        )
        ctx = _fake_rw_ctx(network=network_client)
        result = await _call(
            server,
            "unifi_network_create_wlan",
            ctx,
            name="Guest",
            x_passphrase="pw",
            ap_group_ids=["ap-1"],
            usergroup_id="ug-1",
        )
        assert result["data"][0]["x_passphrase"] == REDACTED
        assert "leak-me" not in str(result)


class TestSiteManagerDiscoveryRedaction:
    """#203 — Site Manager listings could surface controller bearer tokens."""

    @pytest.fixture
    def server(self) -> FastMCP:
        s = FastMCP(name="t")
        register_site_manager_tools(s)
        return s

    async def test_list_hosts_redacts_token(self, server):
        site_manager_client = AsyncMock()
        site_manager_client.list_hosts = AsyncMock(
            return_value={"data": [{"id": "h-1", "hostName": "uck", "token": "leak"}]},
        )
        ctx = _fake_ctx(site_manager=site_manager_client)
        result = await _call(server, "unifi_site_manager_list_hosts", ctx)
        assert result["data"][0]["token"] == REDACTED
        assert result["data"][0]["hostName"] == "uck"

    async def test_list_sites_redacts_secret(self, server):
        site_manager_client = AsyncMock()
        site_manager_client.list_sites = AsyncMock(
            return_value={"data": [{"id": "s-1", "meta": {"name": "HQ"}, "secret": "leak"}]},
        )
        ctx = _fake_ctx(site_manager=site_manager_client)
        result = await _call(server, "unifi_site_manager_list_sites", ctx)
        assert result["data"][0]["secret"] == REDACTED

    async def test_list_devices_redacts_apikey(self, server):
        site_manager_client = AsyncMock()
        site_manager_client.list_devices = AsyncMock(
            return_value={"data": [{"id": "d-1", "mac": "aa:bb", "api_key": "leak"}]},
        )
        ctx = _fake_ctx(site_manager=site_manager_client)
        result = await _call(server, "unifi_site_manager_list_devices", ctx)
        assert result["data"][0]["api_key"] == REDACTED
