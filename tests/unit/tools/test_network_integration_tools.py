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
    async def test_every_tool_tagged_and_not_write(self, server):
        tools = await server.list_tools()
        ni = [t for t in tools if "network_integration" in set(t.tags)]
        assert len(ni) == 28
        for t in ni:
            assert t.name.startswith("unifi_network_")
            assert "write" not in set(t.tags)


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
