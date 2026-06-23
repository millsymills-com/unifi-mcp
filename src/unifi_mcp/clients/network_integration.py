"""Network Integration API client for UniFi controllers.

Read and write client for the official Integration API at
``/proxy/network/integration/v1/`` (UUID site ids, ``X-API-Key``). This is a
distinct surface from the legacy :class:`~unifi_mcp.clients.network.NetworkClient`,
which targets ``/proxy/network/api/s/{site}/``. See #408.

Path-prefix convention (locked by ``tests/unit/clients/test_network_integration.py``):
``_path_prefix = "/proxy/network/integration/v1/"`` and every method passes a
*relative* suffix (``sites``, ``dpi/applications``), so the sites-list URL is
exactly ``/proxy/network/integration/v1/sites``. Per-site resources route
through :meth:`_site_path`, which injects the resolved UUID as
``sites/{siteId}/{suffix}``.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from unifi_mcp.clients.base import BaseUniFiClient
from unifi_mcp.errors import UniFiError

logger = logging.getLogger(__name__)


class NetworkIntegrationClient(BaseUniFiClient):
    """Read and write client for the UniFi Network Integration API.

    Communicates with the controller's Integration proxy at
    ``/proxy/network/integration/v1/``. The site id is a UUID resolved once at
    ``validate_connection`` time (the configured value when set, else the
    controller's default/first site) and cached for the process lifetime, so
    per-site tools never take a ``siteId`` argument.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        site: str | None = None,
        verify_ssl: bool = False,
        cert_fingerprint: str | None = None,
        timeout: int = 30,
        max_retries: int = 3,
    ) -> None:
        self._path_prefix = "/proxy/network/integration/v1/"
        super().__init__(
            base_url=base_url,
            api_key=api_key,
            verify_ssl=verify_ssl,
            cert_fingerprint=cert_fingerprint,
            timeout=timeout,
            max_retries=max_retries,
        )
        self._site: str | None = site
        self._resolved_site: str | None = None

    # ── Site resolution ─────────────────────────────────────────────────

    def _site_path(self, suffix: str) -> str:
        """Build a per-site path with the resolved UUID injected.

        Returns ``sites/{siteId}/{suffix}``. The site id flows through
        ``_segment`` so a malformed cached value cannot reshape the prefix.

        Raises:
            UniFiError: If the site has not been resolved yet (i.e.
                ``validate_connection`` has not run or failed).
        """
        if self._resolved_site is None:
            raise UniFiError("Network Integration site id is not resolved; validate_connection must succeed first")
        return f"sites/{self._segment(self._resolved_site)}/{suffix}"

    # ── Read methods: global ────────────────────────────────────────────

    async def list_sites(self, offset: int = 0, limit: int = 200) -> dict[str, Any]:
        """List local sites (paginated envelope)."""
        result: dict[str, Any] = await self.get("sites", params={"offset": offset, "limit": limit})
        return result

    async def list_pending_devices(self) -> dict[str, Any]:
        """List devices awaiting adoption."""
        result: dict[str, Any] = await self.get("pending-devices")
        return result

    async def list_dpi_applications(self, offset: int = 0, limit: int = 200) -> dict[str, Any]:
        """List the DPI application reference set (paginated envelope)."""
        result: dict[str, Any] = await self.get("dpi/applications", params={"offset": offset, "limit": limit})
        return result

    async def list_dpi_categories(self, offset: int = 0, limit: int = 200) -> dict[str, Any]:
        """List the DPI category reference set (paginated envelope)."""
        result: dict[str, Any] = await self.get("dpi/categories", params={"offset": offset, "limit": limit})
        return result

    # ── Read methods: per-site ──────────────────────────────────────────

    async def list_device_tags(self) -> dict[str, Any]:
        """List device tags for the resolved site."""
        result: dict[str, Any] = await self.get(self._site_path("device-tags"))
        return result

    async def list_acl_rules(self, offset: int = 0, limit: int = 200) -> dict[str, Any]:
        """List L2/L3 ACL rules (paginated envelope)."""
        result: dict[str, Any] = await self.get(self._site_path("acl-rules"), params={"offset": offset, "limit": limit})
        return result

    async def get_acl_rules_ordering(self) -> dict[str, Any]:
        """Get the ACL-rule ordering for the resolved site."""
        result: dict[str, Any] = await self.get(self._site_path("acl-rules/ordering"))
        return result

    async def get_acl_rule(self, acl_rule_id: str) -> dict[str, Any]:
        """Get a single ACL rule by id."""
        result: dict[str, Any] = await self.get(self._site_path(f"acl-rules/{self._segment(acl_rule_id)}"))
        return result

    async def get_firewall_policies_ordering(self) -> dict[str, Any]:
        """Get the firewall-policy ordering for the resolved site."""
        result: dict[str, Any] = await self.get(self._site_path("firewall/policies/ordering"))
        return result

    async def list_firewall_zones(self, offset: int = 0, limit: int = 200) -> dict[str, Any]:
        """List zone-based firewall zones (paginated envelope)."""
        result: dict[str, Any] = await self.get(
            self._site_path("firewall/zones"), params={"offset": offset, "limit": limit}
        )
        return result

    async def get_firewall_zone(self, zone_id: str) -> dict[str, Any]:
        """Get a single firewall zone by id."""
        result: dict[str, Any] = await self.get(self._site_path(f"firewall/zones/{self._segment(zone_id)}"))
        return result

    async def list_dns_policies(self, offset: int = 0, limit: int = 200) -> dict[str, Any]:
        """List DNS policies (paginated envelope)."""
        result: dict[str, Any] = await self.get(
            self._site_path("dns/policies"), params={"offset": offset, "limit": limit}
        )
        return result

    async def get_dns_policy(self, dns_policy_id: str) -> dict[str, Any]:
        """Get a single DNS policy by id."""
        result: dict[str, Any] = await self.get(self._site_path(f"dns/policies/{self._segment(dns_policy_id)}"))
        return result

    async def get_network_references(self, network_id: str) -> dict[str, Any]:
        """Get dependency references for a network."""
        result: dict[str, Any] = await self.get(self._site_path(f"networks/{self._segment(network_id)}/references"))
        return result

    async def list_vouchers(self, offset: int = 0, limit: int = 200) -> dict[str, Any]:
        """List guest-hotspot vouchers (paginated envelope)."""
        result: dict[str, Any] = await self.get(
            self._site_path("hotspot/vouchers"), params={"offset": offset, "limit": limit}
        )
        return result

    async def get_voucher(self, voucher_id: str) -> dict[str, Any]:
        """Get a single hotspot voucher by id."""
        result: dict[str, Any] = await self.get(self._site_path(f"hotspot/vouchers/{self._segment(voucher_id)}"))
        return result

    async def list_traffic_matching_lists(self, offset: int = 0, limit: int = 200) -> dict[str, Any]:
        """List traffic-matching lists (paginated envelope)."""
        result: dict[str, Any] = await self.get(
            self._site_path("traffic-matching-lists"), params={"offset": offset, "limit": limit}
        )
        return result

    async def get_traffic_matching_list(self, list_id: str) -> dict[str, Any]:
        """Get a single traffic-matching list by id."""
        result: dict[str, Any] = await self.get(self._site_path(f"traffic-matching-lists/{self._segment(list_id)}"))
        return result

    async def list_lags(self, offset: int = 0, limit: int = 200) -> dict[str, Any]:
        """List link-aggregation groups (paginated envelope)."""
        result: dict[str, Any] = await self.get(
            self._site_path("switching/lags"), params={"offset": offset, "limit": limit}
        )
        return result

    async def get_lag(self, lag_id: str) -> dict[str, Any]:
        """Get a single LAG by id."""
        result: dict[str, Any] = await self.get(self._site_path(f"switching/lags/{self._segment(lag_id)}"))
        return result

    async def list_mc_lag_domains(self, offset: int = 0, limit: int = 200) -> dict[str, Any]:
        """List MC-LAG domains (paginated envelope)."""
        result: dict[str, Any] = await self.get(
            self._site_path("switching/mc-lag-domains"), params={"offset": offset, "limit": limit}
        )
        return result

    async def get_mc_lag_domain(self, domain_id: str) -> dict[str, Any]:
        """Get a single MC-LAG domain by id."""
        result: dict[str, Any] = await self.get(self._site_path(f"switching/mc-lag-domains/{self._segment(domain_id)}"))
        return result

    async def list_switch_stacks(self, offset: int = 0, limit: int = 200) -> dict[str, Any]:
        """List switch stacks (paginated envelope)."""
        result: dict[str, Any] = await self.get(
            self._site_path("switching/switch-stacks"), params={"offset": offset, "limit": limit}
        )
        return result

    async def get_switch_stack(self, stack_id: str) -> dict[str, Any]:
        """Get a single switch stack by id."""
        result: dict[str, Any] = await self.get(self._site_path(f"switching/switch-stacks/{self._segment(stack_id)}"))
        return result

    async def list_vpn_servers(self, offset: int = 0, limit: int = 200) -> dict[str, Any]:
        """List VPN servers (paginated envelope)."""
        result: dict[str, Any] = await self.get(
            self._site_path("vpn/servers"), params={"offset": offset, "limit": limit}
        )
        return result

    async def list_site_to_site_tunnels(self, offset: int = 0, limit: int = 200) -> dict[str, Any]:
        """List site-to-site VPN tunnels (paginated envelope)."""
        result: dict[str, Any] = await self.get(
            self._site_path("vpn/site-to-site-tunnels"), params={"offset": offset, "limit": limit}
        )
        return result

    async def list_wans(self, offset: int = 0, limit: int = 200) -> dict[str, Any]:
        """List WAN interfaces (paginated envelope)."""
        result: dict[str, Any] = await self.get(self._site_path("wans"), params={"offset": offset, "limit": limit})
        return result

    async def list_radius_profiles(self, offset: int = 0, limit: int = 200) -> dict[str, Any]:
        """List RADIUS profiles (paginated envelope)."""
        result: dict[str, Any] = await self.get(
            self._site_path("radius/profiles"), params={"offset": offset, "limit": limit}
        )
        return result

    # ── Write methods: ACL ──────────────────────────────────────────────

    async def create_acl_rule(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create an L2/L3 ACL rule."""
        result: dict[str, Any] = await self.post(self._site_path("acl-rules"), json=data)
        return result

    async def update_acl_rule(self, acl_rule_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update an existing ACL rule (full-object PUT)."""
        result: dict[str, Any] = await self.put(self._site_path(f"acl-rules/{self._segment(acl_rule_id)}"), json=data)
        return result

    async def delete_acl_rule(self, acl_rule_id: str) -> dict[str, Any]:
        """Delete an ACL rule by id."""
        result: dict[str, Any] = await self.delete(self._site_path(f"acl-rules/{self._segment(acl_rule_id)}"))
        return result

    async def update_acl_rules_ordering(self, ordered_acl_rule_ids: list[str]) -> dict[str, Any]:
        """Replace the site-wide ACL-rule ordering with the supplied id sequence."""
        result: dict[str, Any] = await self.put(
            self._site_path("acl-rules/ordering"), json={"orderedAclRuleIds": ordered_acl_rule_ids}
        )
        return result

    # ── Write methods: DNS policies ─────────────────────────────────────

    async def create_dns_policy(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a DNS policy."""
        result: dict[str, Any] = await self.post(self._site_path("dns/policies"), json=data)
        return result

    async def update_dns_policy(self, dns_policy_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update an existing DNS policy (full-object PUT)."""
        result: dict[str, Any] = await self.put(
            self._site_path(f"dns/policies/{self._segment(dns_policy_id)}"), json=data
        )
        return result

    async def delete_dns_policy(self, dns_policy_id: str) -> dict[str, Any]:
        """Delete a DNS policy by id."""
        result: dict[str, Any] = await self.delete(self._site_path(f"dns/policies/{self._segment(dns_policy_id)}"))
        return result

    # ── Write methods: firewall zones ───────────────────────────────────

    async def create_firewall_zone(self, name: str, network_ids: list[str]) -> dict[str, Any]:
        """Create a zone-based firewall zone."""
        result: dict[str, Any] = await self.post(
            self._site_path("firewall/zones"), json={"name": name, "networkIds": network_ids}
        )
        return result

    async def update_firewall_zone(self, zone_id: str, name: str, network_ids: list[str]) -> dict[str, Any]:
        """Update a firewall zone (full-object PUT)."""
        result: dict[str, Any] = await self.put(
            self._site_path(f"firewall/zones/{self._segment(zone_id)}"),
            json={"name": name, "networkIds": network_ids},
        )
        return result

    async def delete_firewall_zone(self, zone_id: str) -> dict[str, Any]:
        """Delete a firewall zone by id."""
        result: dict[str, Any] = await self.delete(self._site_path(f"firewall/zones/{self._segment(zone_id)}"))
        return result

    # ── Lifecycle ───────────────────────────────────────────────────────

    @staticmethod
    def _pick_default_site(entries: list[dict[str, Any]]) -> str | None:
        """Return the id of the default site, falling back to the first entry.

        Recent firmware flags the default site with ``isDefault`` /
        ``"default": true``; older shapes may omit it, so the first entry is
        the fallback. Returns ``None`` only when the controller reports no
        sites at all.
        """
        for entry in entries:
            if entry.get("isDefault") or entry.get("default"):
                site_id = entry.get("id")
                if isinstance(site_id, str):
                    return site_id
        for entry in entries:
            site_id = entry.get("id")
            if isinstance(site_id, str):
                return site_id
        return None

    async def validate_connection(self) -> bool:
        """Validate connectivity and resolve the site id.

        Fetches ``GET sites`` (exactly ``/proxy/network/integration/v1/sites``)
        and resolves ``_resolved_site`` to the configured UUID when set, else
        the controller's default/first site. The resolved value is cached for
        the process lifetime.

        Returns False on any UniFi or HTTP error — notably a 404 on firmware
        without ``/integration/v1``, the UniFi OS portal HTML on a wrong path,
        or a 401 from a wrongly-scoped key. The caught exception is stored on
        ``self._last_validation_error`` so the lifespan can surface why the
        Integration tools were disabled.
        """
        try:
            response = await self.list_sites()
        except (UniFiError, httpx.HTTPError) as exc:
            self._last_validation_error = exc
            logger.debug("Network Integration API connection validation failed", exc_info=True)
            return False

        if self._site is not None:
            self._resolved_site = self._site
            logger.info("Network Integration bound to configured site id %s", self._resolved_site)
        else:
            entries = response.get("data") if isinstance(response, dict) else None
            resolved = self._pick_default_site(entries) if isinstance(entries, list) else None
            if resolved is None:
                self._last_validation_error = UniFiError(
                    "Network Integration API returned no sites; cannot resolve a site id"
                )
                logger.debug("Network Integration site resolution failed: empty site list")
                return False
            self._resolved_site = resolved
            logger.info("Network Integration auto-resolved default site id %s", self._resolved_site)
        self._last_validation_error = None
        return True
