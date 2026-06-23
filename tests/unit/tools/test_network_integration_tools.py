"""Tool-layer tests for Network Integration read tools (#409).

Covers pagination-cap enforcement, validate_id rejection, response redaction,
and the error funnel (404 → ToolError) for the new ``unifi_network_*``
Integration tools, all tagged ``{"network_integration"}``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from unifi_mcp.config import UniFiConfig, UniFiMode
from unifi_mcp.errors import UniFiNotFoundError
from unifi_mcp.tools.network_integration import register_network_integration_tools

_REDACTED = "***REDACTED***"


@dataclass
class _Lifespan:
    config: UniFiConfig
    clients: dict[str, Any] = field(default_factory=dict)


def _config(max_items: int = 1000, max_offset: int = 100_000) -> UniFiConfig:
    return UniFiConfig(
        _env_file=None,
        unifi_mode=UniFiMode.READONLY,
        unifi_network_api="k",
        unifi_protect_api=None,
        unifi_site_manager_api=None,
        unifi_max_list_items=max_items,
        unifi_max_list_offset=max_offset,
    )


def _config_rw(max_items: int = 1000, max_offset: int = 100_000) -> UniFiConfig:
    return UniFiConfig(
        _env_file=None,
        unifi_mode=UniFiMode.READWRITE,
        unifi_network_api="k",
        unifi_protect_api=None,
        unifi_site_manager_api=None,
        unifi_max_list_items=max_items,
        unifi_max_list_offset=max_offset,
    )


def _ctx(config: UniFiConfig, client: AsyncMock) -> AsyncMock:
    ctx = AsyncMock()
    ctx.lifespan_context = _Lifespan(config=config, clients={"network_integration": client})
    return ctx


@pytest.fixture
def server() -> FastMCP:
    s = FastMCP(name="t")
    register_network_integration_tools(s)
    return s


async def _call(server: FastMCP, tool_name: str, ctx: AsyncMock, **kwargs: Any) -> Any:
    tool = await server.get_tool(tool_name)
    return await tool.fn(ctx, **kwargs)


class TestAllTaggedNetworkIntegration:
    async def test_read_tools_tagged_and_named(self, server):
        tools = await server.list_tools()
        reads = [t for t in tools if "network_integration" in set(t.tags) and "write" not in set(t.tags)]
        assert len(reads) == 28
        for t in reads:
            assert t.name.startswith("unifi_network_")

    async def test_write_tools_tagged_and_named(self, server):
        tools = await server.list_tools()
        writes = [t for t in tools if "network_integration" in set(t.tags) and "write" in set(t.tags)]
        assert len(writes) == 13
        for t in writes:
            assert t.name.startswith("unifi_network_")


class TestPaginationCaps:
    async def test_within_cap_passes_through(self, server):
        client = AsyncMock()
        client.list_sites.return_value = {"data": []}
        ctx = _ctx(_config(), client)
        await _call(server, "unifi_network_list_sites", ctx, offset=10, limit=50)
        client.list_sites.assert_awaited_once_with(offset=10, limit=50)

    async def test_limit_above_cap_rejected(self, server):
        client = AsyncMock()
        ctx = _ctx(_config(max_items=1000), client)
        with pytest.raises(ToolError, match="limit must be between 1 and 1000"):
            await _call(server, "unifi_network_list_sites", ctx, limit=5000)
        client.list_sites.assert_not_called()

    async def test_offset_above_cap_rejected(self, server):
        client = AsyncMock()
        ctx = _ctx(_config(max_offset=100), client)
        with pytest.raises(ToolError, match="offset must be between 0 and 100"):
            await _call(server, "unifi_network_list_acl_rules", ctx, offset=999)
        client.list_acl_rules.assert_not_called()

    async def test_negative_offset_rejected(self, server):
        client = AsyncMock()
        ctx = _ctx(_config(), client)
        with pytest.raises(ToolError, match="offset must be between 0"):
            await _call(server, "unifi_network_list_acl_rules", ctx, offset=-1)

    async def test_zero_limit_rejected(self, server):
        client = AsyncMock()
        ctx = _ctx(_config(), client)
        with pytest.raises(ToolError, match="limit must be between 1"):
            await _call(server, "unifi_network_list_acl_rules", ctx, limit=0)


class TestValidateIdRejection:
    async def test_get_acl_rule_rejects_bad_id(self, server):
        client = AsyncMock()
        ctx = _ctx(_config(), client)
        with pytest.raises(ToolError, match="acl_rule_id: invalid id format"):
            await _call(server, "unifi_network_get_acl_rule", ctx, acl_rule_id="../escape")
        client.get_acl_rule.assert_not_called()

    async def test_get_voucher_rejects_bad_id(self, server):
        client = AsyncMock()
        ctx = _ctx(_config(), client)
        with pytest.raises(ToolError, match="voucher_id: invalid id format"):
            await _call(server, "unifi_network_get_voucher", ctx, voucher_id="a/b")

    async def test_get_acl_rule_accepts_uuid(self, server):
        client = AsyncMock()
        client.get_acl_rule.return_value = {"id": "x"}
        ctx = _ctx(_config(), client)
        await _call(server, "unifi_network_get_acl_rule", ctx, acl_rule_id="11111111-2222-3333-4444-555555555555")
        client.get_acl_rule.assert_awaited_once()


class TestRedaction:
    async def test_radius_response_redacted(self, server):
        client = AsyncMock()
        client.list_radius_profiles.return_value = {
            "data": [{"name": "corp", "x_secret": "topsecret", "radius_secret": "shared"}]
        }
        ctx = _ctx(_config(), client)
        result = await _call(server, "unifi_network_list_radius_profiles", ctx)
        entry = result["data"][0]
        assert entry["x_secret"] == _REDACTED
        assert entry["radius_secret"] == _REDACTED
        assert entry["name"] == "corp"

    async def test_vpn_response_redacted(self, server):
        client = AsyncMock()
        client.list_vpn_servers.return_value = {"data": [{"name": "vpn1", "x_passphrase": "psk"}]}
        ctx = _ctx(_config(), client)
        result = await _call(server, "unifi_network_list_vpn_servers", ctx)
        assert result["data"][0]["x_passphrase"] == _REDACTED


class TestErrorFunnel:
    async def test_not_found_becomes_tool_error(self, server):
        client = AsyncMock()
        client.get_firewall_zone.side_effect = UniFiNotFoundError("HTTP 404: missing", status_code=404)
        ctx = _ctx(_config(), client)
        with pytest.raises(ToolError):
            await _call(server, "unifi_network_get_firewall_zone", ctx, zone_id="z1")


class TestAclWrites:
    async def test_create_acl_rule_happy_path(self, server):
        client = AsyncMock()
        client.create_acl_rule.return_value = {"id": "new", "x_secret": "s"}
        ctx = _ctx(_config_rw(), client)
        result = await _call(server, "unifi_network_create_acl_rule", ctx, data={"name": "iot", "type": "IPV4"})
        client.create_acl_rule.assert_awaited_once_with({"name": "iot", "type": "IPV4"})
        assert result["x_secret"] == _REDACTED

    async def test_create_acl_rule_blocked_in_readonly(self, server):
        client = AsyncMock()
        ctx = _ctx(_config(), client)
        with pytest.raises(ToolError, match="read-only mode"):
            await _call(server, "unifi_network_create_acl_rule", ctx, data={"name": "iot"})
        client.create_acl_rule.assert_not_called()

    async def test_create_acl_rule_rejects_dangerous_key(self, server):
        client = AsyncMock()
        ctx = _ctx(_config_rw(), client)
        with pytest.raises(ToolError):
            await _call(server, "unifi_network_create_acl_rule", ctx, data={"roles": ["admin"]})
        client.create_acl_rule.assert_not_called()

    async def test_update_acl_rule_validates_id(self, server):
        client = AsyncMock()
        ctx = _ctx(_config_rw(), client)
        with pytest.raises(ToolError, match="acl_rule_id: invalid id format"):
            await _call(server, "unifi_network_update_acl_rule", ctx, acl_rule_id="../x", data={"name": "y"})
        client.update_acl_rule.assert_not_called()

    async def test_update_acl_rule_happy_path(self, server):
        client = AsyncMock()
        client.update_acl_rule.return_value = {"id": "r1"}
        ctx = _ctx(_config_rw(), client)
        await _call(server, "unifi_network_update_acl_rule", ctx, acl_rule_id="r1", data={"name": "y"})
        client.update_acl_rule.assert_awaited_once_with("r1", {"name": "y"})

    async def test_delete_acl_rule_requires_confirm(self, server):
        client = AsyncMock()
        ctx = _ctx(_config_rw(), client)
        with pytest.raises(ToolError, match="confirm=True"):
            await _call(server, "unifi_network_delete_acl_rule", ctx, acl_rule_id="r1")
        client.delete_acl_rule.assert_not_called()

    async def test_delete_acl_rule_with_confirm_calls_client(self, server):
        client = AsyncMock()
        client.delete_acl_rule.return_value = {}
        ctx = _ctx(_config_rw(), client)
        await _call(server, "unifi_network_delete_acl_rule", ctx, acl_rule_id="r1", confirm=True)
        client.delete_acl_rule.assert_awaited_once_with("r1")

    async def test_reorder_acl_rules_validates_each_id(self, server):
        client = AsyncMock()
        ctx = _ctx(_config_rw(), client)
        with pytest.raises(ToolError, match="ordered_acl_rule_ids: invalid id format"):
            await _call(server, "unifi_network_reorder_acl_rules", ctx, ordered_acl_rule_ids=["ok", "../bad"])
        client.update_acl_rules_ordering.assert_not_called()

    async def test_reorder_acl_rules_happy_path(self, server):
        client = AsyncMock()
        client.update_acl_rules_ordering.return_value = {}
        ctx = _ctx(_config_rw(), client)
        await _call(server, "unifi_network_reorder_acl_rules", ctx, ordered_acl_rule_ids=["a", "b"])
        client.update_acl_rules_ordering.assert_awaited_once_with(["a", "b"])

    async def test_delete_acl_rule_marked_destructive(self, server):
        tools = await server.list_tools()
        tool = next(t for t in tools if t.name == "unifi_network_delete_acl_rule")
        assert tool.annotations.destructiveHint is True


class TestDnsWrites:
    async def test_create_dns_policy_happy_path(self, server):
        client = AsyncMock()
        client.create_dns_policy.return_value = {"id": "new"}
        ctx = _ctx(_config_rw(), client)
        await _call(server, "unifi_network_create_dns_policy", ctx, data={"type": "A_RECORD", "enabled": True})
        client.create_dns_policy.assert_awaited_once_with({"type": "A_RECORD", "enabled": True})

    async def test_create_dns_policy_blocked_in_readonly(self, server):
        client = AsyncMock()
        ctx = _ctx(_config(), client)
        with pytest.raises(ToolError, match="read-only mode"):
            await _call(server, "unifi_network_create_dns_policy", ctx, data={"type": "A_RECORD"})
        client.create_dns_policy.assert_not_called()

    async def test_create_dns_policy_rejects_dangerous_key(self, server):
        client = AsyncMock()
        ctx = _ctx(_config_rw(), client)
        with pytest.raises(ToolError):
            await _call(server, "unifi_network_create_dns_policy", ctx, data={"permissions": "x"})
        client.create_dns_policy.assert_not_called()

    async def test_update_dns_policy_validates_id(self, server):
        client = AsyncMock()
        ctx = _ctx(_config_rw(), client)
        with pytest.raises(ToolError, match="dns_policy_id: invalid id format"):
            await _call(server, "unifi_network_update_dns_policy", ctx, dns_policy_id="../x", data={"enabled": False})
        client.update_dns_policy.assert_not_called()

    async def test_delete_dns_policy_requires_confirm(self, server):
        client = AsyncMock()
        ctx = _ctx(_config_rw(), client)
        with pytest.raises(ToolError, match="confirm=True"):
            await _call(server, "unifi_network_delete_dns_policy", ctx, dns_policy_id="p1")
        client.delete_dns_policy.assert_not_called()

    async def test_delete_dns_policy_with_confirm_calls_client(self, server):
        client = AsyncMock()
        client.delete_dns_policy.return_value = {}
        ctx = _ctx(_config_rw(), client)
        await _call(server, "unifi_network_delete_dns_policy", ctx, dns_policy_id="p1", confirm=True)
        client.delete_dns_policy.assert_awaited_once_with("p1")

    async def test_delete_dns_policy_marked_destructive(self, server):
        tools = await server.list_tools()
        tool = next(t for t in tools if t.name == "unifi_network_delete_dns_policy")
        assert tool.annotations.destructiveHint is True


class TestFirewallZoneWrites:
    async def test_create_firewall_zone_happy_path(self, server):
        client = AsyncMock()
        client.create_firewall_zone.return_value = {"id": "z-new"}
        ctx = _ctx(_config_rw(), client)
        await _call(server, "unifi_network_create_firewall_zone", ctx, name="iot", network_ids=["net-1"])
        client.create_firewall_zone.assert_awaited_once_with("iot", ["net-1"])

    async def test_create_firewall_zone_blocked_in_readonly(self, server):
        client = AsyncMock()
        ctx = _ctx(_config(), client)
        with pytest.raises(ToolError, match="read-only mode"):
            await _call(server, "unifi_network_create_firewall_zone", ctx, name="iot", network_ids=[])
        client.create_firewall_zone.assert_not_called()

    async def test_update_firewall_zone_validates_id(self, server):
        client = AsyncMock()
        ctx = _ctx(_config_rw(), client)
        with pytest.raises(ToolError, match="zone_id: invalid id format"):
            await _call(server, "unifi_network_update_firewall_zone", ctx, zone_id="../x", name="n", network_ids=[])
        client.update_firewall_zone.assert_not_called()

    async def test_update_firewall_zone_happy_path(self, server):
        client = AsyncMock()
        client.update_firewall_zone.return_value = {"id": "z1"}
        ctx = _ctx(_config_rw(), client)
        await _call(server, "unifi_network_update_firewall_zone", ctx, zone_id="z1", name="n", network_ids=["a"])
        client.update_firewall_zone.assert_awaited_once_with("z1", "n", ["a"])

    async def test_delete_firewall_zone_requires_confirm(self, server):
        client = AsyncMock()
        ctx = _ctx(_config_rw(), client)
        with pytest.raises(ToolError, match="confirm=True"):
            await _call(server, "unifi_network_delete_firewall_zone", ctx, zone_id="z1")
        client.delete_firewall_zone.assert_not_called()

    async def test_delete_firewall_zone_with_confirm_calls_client(self, server):
        client = AsyncMock()
        client.delete_firewall_zone.return_value = {}
        ctx = _ctx(_config_rw(), client)
        await _call(server, "unifi_network_delete_firewall_zone", ctx, zone_id="z1", confirm=True)
        client.delete_firewall_zone.assert_awaited_once_with("z1")

    async def test_delete_firewall_zone_marked_destructive(self, server):
        tools = await server.list_tools()
        tool = next(t for t in tools if t.name == "unifi_network_delete_firewall_zone")
        assert tool.annotations.destructiveHint is True


class TestVoucherWrites:
    async def test_create_vouchers_happy_path(self, server):
        client = AsyncMock()
        client.create_vouchers.return_value = {"data": []}
        ctx = _ctx(_config_rw(), client)
        await _call(server, "unifi_network_create_vouchers", ctx, name="g", time_limit_minutes=60, count=2)
        client.create_vouchers.assert_awaited_once_with(
            name="g",
            time_limit_minutes=60,
            count=2,
            authorized_guest_limit=None,
            data_usage_limit_mbytes=None,
            rx_rate_limit_kbps=None,
            tx_rate_limit_kbps=None,
        )

    async def test_create_vouchers_blocked_in_readonly(self, server):
        client = AsyncMock()
        ctx = _ctx(_config(), client)
        with pytest.raises(ToolError, match="read-only mode"):
            await _call(server, "unifi_network_create_vouchers", ctx, name="g", time_limit_minutes=60)
        client.create_vouchers.assert_not_called()

    async def test_delete_vouchers_rejects_blank_filter(self, server):
        client = AsyncMock()
        ctx = _ctx(_config_rw(), client)
        with pytest.raises(ToolError, match="non-blank"):
            await _call(server, "unifi_network_delete_vouchers", ctx, voucher_filter="   ", confirm=True)
        client.delete_vouchers.assert_not_called()

    async def test_delete_vouchers_requires_confirm(self, server):
        client = AsyncMock()
        ctx = _ctx(_config_rw(), client)
        with pytest.raises(ToolError, match="confirm=True"):
            await _call(server, "unifi_network_delete_vouchers", ctx, voucher_filter="name.eq('t')")
        client.delete_vouchers.assert_not_called()

    async def test_delete_vouchers_with_confirm_calls_client(self, server):
        client = AsyncMock()
        client.delete_vouchers.return_value = {"vouchersDeleted": 1}
        ctx = _ctx(_config_rw(), client)
        await _call(server, "unifi_network_delete_vouchers", ctx, voucher_filter="name.eq('t')", confirm=True)
        client.delete_vouchers.assert_awaited_once_with(voucher_filter="name.eq('t')")

    async def test_delete_voucher_requires_confirm(self, server):
        client = AsyncMock()
        ctx = _ctx(_config_rw(), client)
        with pytest.raises(ToolError, match="confirm=True"):
            await _call(server, "unifi_network_delete_voucher", ctx, voucher_id="v1")
        client.delete_voucher.assert_not_called()

    async def test_delete_voucher_validates_id(self, server):
        client = AsyncMock()
        ctx = _ctx(_config_rw(), client)
        with pytest.raises(ToolError, match="voucher_id: invalid id format"):
            await _call(server, "unifi_network_delete_voucher", ctx, voucher_id="../x", confirm=True)
        client.delete_voucher.assert_not_called()

    async def test_delete_voucher_with_confirm_calls_client(self, server):
        client = AsyncMock()
        client.delete_voucher.return_value = {}
        ctx = _ctx(_config_rw(), client)
        await _call(server, "unifi_network_delete_voucher", ctx, voucher_id="v1", confirm=True)
        client.delete_voucher.assert_awaited_once_with("v1")

    async def test_voucher_deletes_marked_destructive(self, server):
        tools = await server.list_tools()
        for name in ("unifi_network_delete_vouchers", "unifi_network_delete_voucher"):
            tool = next(t for t in tools if t.name == name)
            assert tool.annotations.destructiveHint is True
