"""Tests for the Network Integration API client (#408)."""

from __future__ import annotations

import logging

import httpx
import pytest
import respx

from unifi_mcp.clients.network_integration import NetworkIntegrationClient
from unifi_mcp.errors import UniFiError, UniFiNotFoundError

BASE_URL = "https://10.0.0.1:443"
PREFIX = f"{BASE_URL}/proxy/network/integration/v1/"
SITE_UUID = "11111111-2222-3333-4444-555555555555"

_PAGE = {"data": [], "offset": 0, "limit": 200, "count": 0, "totalCount": 0}


def _make_client(site: str | None = SITE_UUID) -> NetworkIntegrationClient:
    return NetworkIntegrationClient(
        base_url=BASE_URL,
        api_key="test-net-key",
        site=site,
        timeout=5,
        max_retries=2,
    )


@pytest.fixture
def client():
    """A client with a pre-resolved site (most per-site method tests)."""
    c = _make_client()
    c._resolved_site = SITE_UUID
    return c


class TestPathPrefix:
    def test_prefix_is_integration_v1(self):
        assert _make_client()._path_prefix == "/proxy/network/integration/v1/"


class TestRealizedSitesUrl:
    """Locks the prefix arithmetic: the sites-list URL must be exactly
    ``/proxy/network/integration/v1/sites`` — not ``.../v1/v1/sites``.
    """

    @respx.mock
    async def test_list_sites_realized_url(self):
        route = respx.get(f"{PREFIX}sites").mock(return_value=httpx.Response(200, json=_PAGE))
        await _make_client().list_sites()
        assert route.called
        # The realized path must be exactly the Integration sites endpoint —
        # not doubled (``/v1/v1/sites``) by the prefix arithmetic.
        assert route.calls[0].request.url.path == "/proxy/network/integration/v1/sites"

    @respx.mock
    async def test_list_sites_sends_api_key_header(self):
        route = respx.get(f"{PREFIX}sites").mock(return_value=httpx.Response(200, json=_PAGE))
        await _make_client().list_sites()
        assert route.calls[0].request.headers["X-API-Key"] == "test-net-key"

    @respx.mock
    async def test_list_sites_passes_pagination_params(self):
        route = respx.get(f"{PREFIX}sites").mock(return_value=httpx.Response(200, json=_PAGE))
        await _make_client().list_sites(offset=40, limit=10)
        params = route.calls[0].request.url.params
        assert params["offset"] == "40"
        assert params["limit"] == "10"


class TestGlobalReads:
    @respx.mock
    async def test_list_pending_devices(self, client):
        route = respx.get(f"{PREFIX}pending-devices").mock(return_value=httpx.Response(200, json={"data": []}))
        result = await client.list_pending_devices()
        assert route.called
        assert result == {"data": []}

    @respx.mock
    async def test_list_dpi_applications(self, client):
        route = respx.get(f"{PREFIX}dpi/applications").mock(return_value=httpx.Response(200, json=_PAGE))
        await client.list_dpi_applications()
        assert route.called

    @respx.mock
    async def test_list_dpi_categories(self, client):
        route = respx.get(f"{PREFIX}dpi/categories").mock(return_value=httpx.Response(200, json=_PAGE))
        await client.list_dpi_categories()
        assert route.called


class TestSiteIdInjection:
    """Per-site methods interpolate the resolved UUID into the path."""

    @respx.mock
    async def test_list_acl_rules_injects_site(self, client):
        route = respx.get(f"{PREFIX}sites/{SITE_UUID}/acl-rules").mock(return_value=httpx.Response(200, json=_PAGE))
        await client.list_acl_rules()
        assert route.called

    @respx.mock
    async def test_get_acl_rule_injects_site_and_id(self, client):
        route = respx.get(f"{PREFIX}sites/{SITE_UUID}/acl-rules/rule-9").mock(
            return_value=httpx.Response(200, json={"id": "rule-9"})
        )
        result = await client.get_acl_rule("rule-9")
        assert route.called
        assert result == {"id": "rule-9"}

    @respx.mock
    async def test_get_network_references_injects_site_and_id(self, client):
        route = respx.get(f"{PREFIX}sites/{SITE_UUID}/networks/net-1/references").mock(
            return_value=httpx.Response(200, json={"data": []})
        )
        await client.get_network_references("net-1")
        assert route.called

    @respx.mock
    async def test_list_radius_profiles_injects_site(self, client):
        route = respx.get(f"{PREFIX}sites/{SITE_UUID}/radius/profiles").mock(
            return_value=httpx.Response(200, json=_PAGE)
        )
        await client.list_radius_profiles()
        assert route.called

    @respx.mock
    async def test_list_vpn_servers_injects_site(self, client):
        route = respx.get(f"{PREFIX}sites/{SITE_UUID}/vpn/servers").mock(return_value=httpx.Response(200, json=_PAGE))
        await client.list_vpn_servers()
        assert route.called

    @respx.mock
    async def test_get_switch_stack_injects_site(self, client):
        route = respx.get(f"{PREFIX}sites/{SITE_UUID}/switching/switch-stacks/s-1").mock(
            return_value=httpx.Response(200, json={"id": "s-1"})
        )
        await client.get_switch_stack("s-1")
        assert route.called


class TestAclWriteMethods:
    @respx.mock
    async def test_create_acl_rule_posts_to_site(self, client):
        route = respx.post(f"{PREFIX}sites/{SITE_UUID}/acl-rules").mock(
            return_value=httpx.Response(200, json={"id": "new"})
        )
        result = await client.create_acl_rule({"name": "block-iot", "type": "IPV4"})
        assert route.called
        assert route.calls[0].request.url.path == f"/proxy/network/integration/v1/sites/{SITE_UUID}/acl-rules"
        assert b"block-iot" in route.calls[0].request.content
        assert result == {"id": "new"}

    @respx.mock
    async def test_update_acl_rule_puts_with_id(self, client):
        route = respx.put(f"{PREFIX}sites/{SITE_UUID}/acl-rules/rule-7").mock(
            return_value=httpx.Response(200, json={"id": "rule-7"})
        )
        await client.update_acl_rule("rule-7", {"name": "renamed"})
        assert route.called
        assert b"renamed" in route.calls[0].request.content

    @respx.mock
    async def test_delete_acl_rule_returns_empty_on_204(self, client):
        route = respx.delete(f"{PREFIX}sites/{SITE_UUID}/acl-rules/rule-7").mock(return_value=httpx.Response(204))
        assert await client.delete_acl_rule("rule-7") == {}
        assert route.call_count == 1

    @respx.mock
    async def test_reorder_acl_rules_sends_ordered_ids(self, client):
        route = respx.put(f"{PREFIX}sites/{SITE_UUID}/acl-rules/ordering").mock(
            return_value=httpx.Response(200, json={})
        )
        await client.update_acl_rules_ordering(["a", "b", "c"])
        assert route.called
        assert b"orderedAclRuleIds" in route.calls[0].request.content


class TestDnsWriteMethods:
    @respx.mock
    async def test_create_dns_policy_posts_to_site(self, client):
        route = respx.post(f"{PREFIX}sites/{SITE_UUID}/dns/policies").mock(
            return_value=httpx.Response(200, json={"id": "new"})
        )
        await client.create_dns_policy({"type": "A_RECORD", "enabled": True})
        assert route.called
        assert b"A_RECORD" in route.calls[0].request.content

    @respx.mock
    async def test_update_dns_policy_puts_with_id(self, client):
        route = respx.put(f"{PREFIX}sites/{SITE_UUID}/dns/policies/p-1").mock(
            return_value=httpx.Response(200, json={"id": "p-1"})
        )
        await client.update_dns_policy("p-1", {"enabled": False})
        assert route.called
        assert b"enabled" in route.calls[0].request.content

    @respx.mock
    async def test_delete_dns_policy_returns_empty_on_204(self, client):
        route = respx.delete(f"{PREFIX}sites/{SITE_UUID}/dns/policies/p-1").mock(return_value=httpx.Response(204))
        assert await client.delete_dns_policy("p-1") == {}
        assert route.call_count == 1


class TestFirewallZoneWriteMethods:
    @respx.mock
    async def test_create_firewall_zone_posts_name_and_networks(self, client):
        route = respx.post(f"{PREFIX}sites/{SITE_UUID}/firewall/zones").mock(
            return_value=httpx.Response(200, json={"id": "z-new"})
        )
        await client.create_firewall_zone("iot", ["net-1", "net-2"])
        assert route.called
        body = route.calls[0].request.content
        assert b"networkIds" in body
        assert b"iot" in body

    @respx.mock
    async def test_update_firewall_zone_puts_with_id(self, client):
        route = respx.put(f"{PREFIX}sites/{SITE_UUID}/firewall/zones/z-1").mock(
            return_value=httpx.Response(200, json={"id": "z-1"})
        )
        await client.update_firewall_zone("z-1", "renamed", ["net-1"])
        assert route.called
        assert b"renamed" in route.calls[0].request.content

    @respx.mock
    async def test_delete_firewall_zone_returns_empty_on_204(self, client):
        route = respx.delete(f"{PREFIX}sites/{SITE_UUID}/firewall/zones/z-1").mock(return_value=httpx.Response(204))
        assert await client.delete_firewall_zone("z-1") == {}
        assert route.call_count == 1


class TestVoucherWriteMethods:
    @respx.mock
    async def test_create_vouchers_posts_required_and_omits_none(self, client):
        route = respx.post(f"{PREFIX}sites/{SITE_UUID}/hotspot/vouchers").mock(
            return_value=httpx.Response(200, json={"data": []})
        )
        await client.create_vouchers(name="guest", time_limit_minutes=60, count=5)
        body = route.calls[0].request.content
        assert b"timeLimitMinutes" in body
        assert b"guest" in body
        # Unset optional fields are omitted, not sent as null.
        assert b"rxRateLimitKbps" not in body

    @respx.mock
    async def test_create_vouchers_includes_supplied_optionals(self, client):
        route = respx.post(f"{PREFIX}sites/{SITE_UUID}/hotspot/vouchers").mock(
            return_value=httpx.Response(200, json={"data": []})
        )
        await client.create_vouchers(name="g", time_limit_minutes=60, rx_rate_limit_kbps=1000)
        assert b"rxRateLimitKbps" in route.calls[0].request.content

    @respx.mock
    async def test_delete_vouchers_sends_filter_query(self, client):
        route = respx.delete(f"{PREFIX}sites/{SITE_UUID}/hotspot/vouchers").mock(
            return_value=httpx.Response(200, json={"vouchersDeleted": 3})
        )
        await client.delete_vouchers(voucher_filter="name.eq('test')")
        assert route.called
        assert route.calls[0].request.url.params["filter"] == "name.eq('test')"

    @respx.mock
    async def test_delete_voucher_by_id(self, client):
        route = respx.delete(f"{PREFIX}sites/{SITE_UUID}/hotspot/vouchers/v-1").mock(return_value=httpx.Response(204))
        assert await client.delete_voucher("v-1") == {}
        assert route.call_count == 1


class TestSitePathGuard:
    def test_site_path_raises_when_unresolved(self):
        c = _make_client()
        assert c._resolved_site is None
        with pytest.raises(UniFiError, match="not resolved"):
            c._site_path("acl-rules")


class TestErrorPath:
    @respx.mock
    async def test_404_maps_to_not_found(self, client):
        respx.get(f"{PREFIX}sites/{SITE_UUID}/acl-rules/missing").mock(
            return_value=httpx.Response(404, json={"error": {"message": "no such rule"}})
        )
        with pytest.raises(UniFiNotFoundError):
            await client.get_acl_rule("missing")


class TestValidateConnection:
    @respx.mock
    async def test_success_with_explicit_uuid(self, caplog):
        respx.get(f"{PREFIX}sites").mock(return_value=httpx.Response(200, json={"data": [{"id": "other"}]}))
        c = _make_client(site=SITE_UUID)
        with caplog.at_level(logging.INFO, logger="unifi_mcp.clients.network_integration"):
            assert await c.validate_connection() is True
        # Configured UUID is used verbatim, not the discovered "other".
        assert c._resolved_site == SITE_UUID
        assert any(SITE_UUID in r.getMessage() and r.levelno == logging.INFO for r in caplog.records)

    @respx.mock
    async def test_auto_discovery_picks_default(self, caplog):
        respx.get(f"{PREFIX}sites").mock(
            return_value=httpx.Response(
                200,
                json={"data": [{"id": "first"}, {"id": "the-default", "isDefault": True}]},
            )
        )
        c = _make_client(site=None)
        with caplog.at_level(logging.INFO, logger="unifi_mcp.clients.network_integration"):
            assert await c.validate_connection() is True
        assert c._resolved_site == "the-default"
        assert any("the-default" in r.getMessage() and r.levelno == logging.INFO for r in caplog.records)

    @respx.mock
    async def test_auto_discovery_falls_back_to_first(self):
        respx.get(f"{PREFIX}sites").mock(
            return_value=httpx.Response(200, json={"data": [{"id": "only-one"}, {"id": "second"}]})
        )
        c = _make_client(site=None)
        assert await c.validate_connection() is True
        assert c._resolved_site == "only-one"

    @respx.mock
    async def test_empty_site_list_returns_false(self):
        respx.get(f"{PREFIX}sites").mock(return_value=httpx.Response(200, json={"data": []}))
        c = _make_client(site=None)
        assert await c.validate_connection() is False
        assert c._resolved_site is None
        assert c._last_validation_error is not None

    @respx.mock
    async def test_404_old_firmware_returns_false(self):
        respx.get(f"{PREFIX}sites").mock(return_value=httpx.Response(404, text="Not Found"))
        c = _make_client(site=None)
        assert await c.validate_connection() is False
        assert c._last_validation_error is not None

    @respx.mock
    async def test_html_portal_returns_false(self):
        respx.get(f"{PREFIX}sites").mock(
            return_value=httpx.Response(200, html="<!doctype html><title>UniFi OS</title>")
        )
        c = _make_client(site=None)
        assert await c.validate_connection() is False
        assert c._last_validation_error is not None

    @respx.mock
    async def test_401_returns_false(self):
        respx.get(f"{PREFIX}sites").mock(return_value=httpx.Response(401, text="Unauthorized"))
        c = _make_client(site=SITE_UUID)
        assert await c.validate_connection() is False
        assert c._last_validation_error is not None


class TestConfigUuidValidator:
    def test_reject_non_uuid(self):
        from unifi_mcp.config import UniFiConfig

        with pytest.raises(ValueError, match="expected a UUID"):
            UniFiConfig(
                _env_file=None,
                unifi_network_api="k",
                unifi_protect_api=None,
                unifi_site_manager_api=None,
                unifi_network_integration_site="not-a-uuid",
            )

    def test_accept_uuid(self):
        from unifi_mcp.config import UniFiConfig

        cfg = UniFiConfig(
            _env_file=None,
            unifi_network_api="k",
            unifi_protect_api=None,
            unifi_site_manager_api=None,
            unifi_network_integration_site=SITE_UUID,
        )
        assert cfg.unifi_network_integration_site == SITE_UUID

    def test_blank_becomes_none(self):
        from unifi_mcp.config import UniFiConfig

        cfg = UniFiConfig(
            _env_file=None,
            unifi_network_api="k",
            unifi_protect_api=None,
            unifi_site_manager_api=None,
            unifi_network_integration_site="   ",
        )
        assert cfg.unifi_network_integration_site is None

    def test_integration_enabled_requires_network_key(self):
        from unifi_mcp.config import UniFiConfig

        cfg = UniFiConfig(
            _env_file=None,
            unifi_network_api=None,
            unifi_protect_api=None,
            unifi_site_manager_api=None,
        )
        assert cfg.network_integration_enabled is False

    def test_integration_opt_out(self):
        from unifi_mcp.config import UniFiConfig

        cfg = UniFiConfig(
            _env_file=None,
            unifi_network_api="k",
            unifi_protect_api=None,
            unifi_site_manager_api=None,
            unifi_network_integration_enabled=False,
        )
        assert cfg.network_integration_enabled is False

    def test_base_url_matches_network(self):
        from unifi_mcp.config import UniFiConfig

        cfg = UniFiConfig(
            _env_file=None,
            unifi_network_api="k",
            unifi_protect_api=None,
            unifi_site_manager_api=None,
        )
        assert cfg.network_integration_base_url == cfg.network_base_url
