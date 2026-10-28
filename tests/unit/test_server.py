"""Tests for server creation and mode gating."""

import pytest
import respx
from fastmcp import Client

from unifi_mcp.clients.network import NetworkClient
from unifi_mcp.clients.network_integration import NetworkIntegrationClient
from unifi_mcp.clients.protect import ProtectClient
from unifi_mcp.clients.site_manager import SiteManagerClient
from unifi_mcp.config import ToolProfile, UniFiConfig, UniFiMode
from unifi_mcp.server import _configured_lifespan, create_server


def _make_config(**overrides):
    defaults = {
        "_env_file": None,
        "unifi_network_api": "test-net-key",
        "unifi_protect_api": "test-prot-key",
        "unifi_site_manager_api": "test-sm-key",
    }
    defaults.update(overrides)
    return UniFiConfig(**defaults)


class TestCreateServer:
    @pytest.mark.parametrize("source", ["default", "environment", "dotenv", "explicit"])
    async def test_resolved_raw_body_policy_reaches_every_client(self, monkeypatch, tmp_path, source):
        async def valid_connection(self):
            return True

        for client_type in (NetworkClient, NetworkIntegrationClient, ProtectClient, SiteManagerClient):
            monkeypatch.setattr(client_type, "validate_connection", valid_connection)

        if source in {"environment", "explicit"}:
            monkeypatch.setenv("UNIFI_LOG_RAW_BODIES", "true")
        else:
            monkeypatch.delenv("UNIFI_LOG_RAW_BODIES", raising=False)
        env_file = tmp_path / ".env"
        env_file.write_text("UNIFI_LOG_RAW_BODIES=true\n")
        kwargs = {"_env_file": env_file if source == "dotenv" else None}
        if source == "explicit":
            kwargs["unifi_log_raw_bodies"] = False
        config = _make_config(**kwargs)
        expected = source in {"environment", "dotenv"}
        assert config.unifi_log_raw_bodies is expected

        async with _configured_lifespan(None, config) as context:
            assert set(context.clients) == {"network", "network_integration", "protect", "site_manager"}
            assert all(client._log_raw_bodies is expected for client in context.clients.values())

    @pytest.mark.parametrize("mode", [UniFiMode.READONLY, UniFiMode.READWRITE])
    @respx.mock
    async def test_explicit_config_controls_startup_and_runtime_policy(self, monkeypatch, mode):
        # The environment deliberately disagrees with the injected settings.
        monkeypatch.setenv("UNIFI_MODE", "readonly" if mode == UniFiMode.READWRITE else "readwrite")
        monkeypatch.setenv("UNIFI_NETWORK_API", "environment-key")
        monkeypatch.setenv("UNIFI_NETWORK_HOST", "192.0.2.20")
        config = _make_config(
            unifi_mode=mode,
            unifi_network_host="192.0.2.10",
            unifi_network_site="injected",
            unifi_network_integration_enabled=False,
            unifi_protect_api=None,
            unifi_site_manager_api=None,
        )
        prefix = "https://192.0.2.10:443/proxy/network/api/s/injected"
        startup = respx.get(f"{prefix}/stat/sysinfo").respond(200, json={"data": []})
        respx.get(f"{prefix}/stat/health").respond(200, json={"data": [{"status": "ok"}]})
        write = respx.post(f"{prefix}/rest/networkconf").respond(200, json={"data": []})
        server = create_server(config)
        async with Client(server) as client:
            result = await client.call_tool("unifi_network_get_health")
            assert result.data == {"data": [{"status": "ok"}]}
            names = {tool.name for tool in await client.list_tools()}
            assert ("unifi_network_create_network" in names) == config.writes_enabled
            if config.writes_enabled:
                await client.call_tool("unifi_network_create_network", {"name": "guest"})
        assert startup.calls[0].request.headers["X-API-Key"] == "test-net-key"
        assert write.call_count == int(config.writes_enabled)

    def test_creates_server_with_all_apis(self):
        config = _make_config()
        server = create_server(config)
        assert server.name == "unifi-mcp"

    def test_creates_server_with_network_only(self):
        config = _make_config(unifi_protect_api=None, unifi_site_manager_api=None)
        server = create_server(config)
        assert server.name == "unifi-mcp"

    def test_creates_server_with_no_apis(self):
        config = _make_config(unifi_network_api=None, unifi_protect_api=None, unifi_site_manager_api=None)
        server = create_server(config)
        assert server.name == "unifi-mcp"


class TestModeGating:
    async def test_write_tools_disabled_in_readonly_mode(self):
        config = _make_config(unifi_mode=UniFiMode.READONLY)
        server = create_server(config)
        tools = await server.list_tools()
        tool_names = {t.name for t in tools}
        # Write tools should not be visible
        assert "unifi_network_create_wlan" not in tool_names
        assert "unifi_network_delete_wlan" not in tool_names
        assert "unifi_network_restart_device" not in tool_names
        assert "unifi_protect_update_camera" not in tool_names
        # Read tools should be visible
        assert "unifi_network_get_health" in tool_names
        assert "unifi_network_list_devices" in tool_names
        assert "unifi_protect_list_cameras" in tool_names
        assert "unifi_site_manager_list_hosts" in tool_names

    async def test_write_tools_enabled_in_readwrite_mode(self):
        config = _make_config(unifi_mode=UniFiMode.READWRITE)
        server = create_server(config)
        tools = await server.list_tools()
        tool_names = {t.name for t in tools}
        # Write tools should be visible
        assert "unifi_network_create_wlan" in tool_names
        assert "unifi_network_delete_wlan" in tool_names
        assert "unifi_network_restart_device" in tool_names
        assert "unifi_protect_update_camera" in tool_names
        # Read tools should still be visible
        assert "unifi_network_get_health" in tool_names
        assert "unifi_protect_list_cameras" in tool_names

    async def test_no_protect_tools_when_not_configured(self):
        config = _make_config(unifi_protect_api=None)
        server = create_server(config)
        tools = await server.list_tools()
        tool_names = {t.name for t in tools}
        assert "unifi_protect_list_cameras" not in tool_names
        assert "unifi_network_get_health" in tool_names

    async def test_no_site_manager_tools_when_not_configured(self):
        config = _make_config(unifi_site_manager_api=None)
        server = create_server(config)
        tools = await server.list_tools()
        tool_names = {t.name for t in tools}
        assert "unifi_site_manager_list_hosts" not in tool_names
        assert "unifi_network_get_health" in tool_names

    async def test_tool_count_readwrite_all_apis(self):
        config = _make_config(unifi_mode=UniFiMode.READWRITE)
        server = create_server(config)
        tools = await server.list_tools()
        # Should have all tools registered
        assert len(tools) > 50

    async def test_tool_count_readonly_has_fewer_tools(self):
        config = _make_config(unifi_mode=UniFiMode.READONLY)
        server = create_server(config)
        readonly_tools = await server.list_tools()

        config_rw = _make_config(unifi_mode=UniFiMode.READWRITE)
        server_rw = create_server(config_rw)
        readwrite_tools = await server_rw.list_tools()

        assert len(readonly_tools) < len(readwrite_tools)


class TestToolProfiles:
    @pytest.mark.parametrize("mode", [UniFiMode.READONLY, UniFiMode.READWRITE])
    async def test_each_profile_exposes_exactly_its_family(self, mode):
        all_server = create_server(_make_config(unifi_mode=mode, unifi_tools=ToolProfile.ALL))
        all_tools = await all_server.list_tools()
        all_names = {tool.name for tool in all_tools}

        for profile in ToolProfile:
            server = create_server(_make_config(unifi_mode=mode, unifi_tools=profile))
            names = {tool.name for tool in await server.list_tools()}
            expected = (
                all_names
                if profile == ToolProfile.ALL
                else {tool.name for tool in all_tools if profile.value in tool.tags}
            )
            assert names == expected
            assert names
            if mode == UniFiMode.READONLY:
                assert all("write" not in tool.tags for tool in await server.list_tools())

    async def test_profile_does_not_enable_unconfigured_api(self):
        config = _make_config(unifi_network_api=None, unifi_tools=ToolProfile.NETWORK)
        assert await create_server(config).list_tools() == []
