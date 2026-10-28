"""Network API client for UniFi controllers."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from unifi_mcp.clients.base import BaseUniFiClient
from unifi_mcp.errors import (
    UniFiBadRequestError,
    UniFiDeviceAlreadyAdoptedError,
    UniFiError,
    UniFiNotFoundError,
    UniFiUnsupportedError,
)

logger = logging.getLogger(__name__)


class NetworkClient(BaseUniFiClient):
    """Client for the UniFi Network API on a local controller.

    Communicates with the controller's proxy API at
    ``/proxy/network/api/s/{site}/``.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        site: str = "default",
        verify_ssl: bool = False,
        cert_fingerprint: str | None = None,
        timeout: int = 30,
        max_retries: int = 3,
    ) -> None:
        self._path_prefix = f"/proxy/network/api/s/{site}/"
        super().__init__(
            base_url=base_url,
            api_key=api_key,
            verify_ssl=verify_ssl,
            cert_fingerprint=cert_fingerprint,
            timeout=timeout,
            max_retries=max_retries,
        )

    # ── Read methods ───────────────────────────────────────────────────

    async def get_health(self) -> dict[str, Any]:
        """Get controller health status."""
        result: dict[str, Any] = await self.get("stat/health")
        return result

    async def list_events(self, limit: int = 100) -> dict[str, Any]:
        """Read legacy alarm history, where supported (not a general event feed).

        ``list/alarm`` returns 404 on some controllers and 400 InvalidObject
        on Network 10.6.106 with API-key auth (#543). No supported replacement
        has been verified; do not fall back to a different resource.
        """
        try:
            result: dict[str, Any] = await self.get("list/alarm", params={"_limit": limit})
        except (UniFiBadRequestError, UniFiNotFoundError) as exc:
            if not isinstance(exc, UniFiNotFoundError) and "api.err.InvalidObject" not in str(exc):
                raise
            raise UniFiUnsupportedError(
                "Network event reads are unavailable through the legacy list/alarm endpoint "
                "on this controller with the configured API key. No supported replacement "
                "has been verified; use the UniFi Network application to view events (#543).",
                status_code=exc.status_code,
            ) from exc
        return result

    async def list_devices(self) -> dict[str, Any]:
        """List all adopted devices with full details."""
        result: dict[str, Any] = await self.get("stat/device")
        return result

    async def list_devices_basic(self) -> dict[str, Any]:
        """List all adopted devices with basic info only."""
        result: dict[str, Any] = await self.get("stat/device-basic")
        return result

    async def list_active_clients(self) -> dict[str, Any]:
        """List currently connected clients."""
        result: dict[str, Any] = await self.get("stat/sta")
        return result

    async def list_configured_clients(self) -> dict[str, Any]:
        """List all configured (known) clients."""
        result: dict[str, Any] = await self.get("rest/user")
        return result

    async def list_all_clients(self) -> dict[str, Any]:
        """List all clients (active and historical)."""
        result: dict[str, Any] = await self.get("stat/alluser", params={"type": "all", "conn": "all"})
        return result

    async def get_dpi_stats(self, dpi_type: str = "by_app") -> dict[str, Any]:
        """Get deep packet inspection statistics."""
        result: dict[str, Any] = await self.get("stat/dpi", params={"type": dpi_type})
        return result

    async def get_sysinfo(self) -> dict[str, Any]:
        """Get system information for the controller."""
        result: dict[str, Any] = await self.get("stat/sysinfo")
        return result

    async def list_wlans(self) -> dict[str, Any]:
        """List all WLAN configurations."""
        result: dict[str, Any] = await self.get("rest/wlanconf")
        return result

    async def get_wlan(self, wlan_id: str) -> dict[str, Any]:
        """Get a specific WLAN configuration."""
        result: dict[str, Any] = await self.get(f"rest/wlanconf/{self._segment(wlan_id)}")
        return result

    async def list_networks(self) -> dict[str, Any]:
        """List all network configurations."""
        result: dict[str, Any] = await self.get("rest/networkconf")
        return result

    async def get_network(self, network_id: str) -> dict[str, Any]:
        """Get a specific network configuration."""
        result: dict[str, Any] = await self.get(f"rest/networkconf/{self._segment(network_id)}")
        return result

    async def list_firewall_rules(self) -> dict[str, Any]:
        """List all firewall rules."""
        result: dict[str, Any] = await self.get("rest/firewallrule")
        return result

    async def get_firewall_rule(self, rule_id: str) -> dict[str, Any]:
        """Get a specific firewall rule."""
        result: dict[str, Any] = await self.get(f"rest/firewallrule/{self._segment(rule_id)}")
        return result

    async def list_firewall_groups(self) -> dict[str, Any]:
        """List all firewall groups."""
        result: dict[str, Any] = await self.get("rest/firewallgroup")
        return result

    async def get_firewall_group(self, group_id: str) -> dict[str, Any]:
        """Get a specific firewall group."""
        result: dict[str, Any] = await self.get(f"rest/firewallgroup/{self._segment(group_id)}")
        return result

    async def list_port_forwards(self) -> dict[str, Any]:
        """List all port forwarding rules."""
        result: dict[str, Any] = await self.get("rest/portforward")
        return result

    async def get_port_forward(self, pf_id: str) -> dict[str, Any]:
        """Get a specific port forwarding rule."""
        result: dict[str, Any] = await self.get(f"rest/portforward/{self._segment(pf_id)}")
        return result

    async def list_routes(self) -> dict[str, Any]:
        """List all static routes."""
        result: dict[str, Any] = await self.get("rest/routing")
        return result

    async def get_route(self, route_id: str) -> dict[str, Any]:
        """Get a specific static route."""
        result: dict[str, Any] = await self.get(f"rest/routing/{self._segment(route_id)}")
        return result

    async def get_settings(self) -> dict[str, Any]:
        """Get controller settings."""
        result: dict[str, Any] = await self.get("rest/setting")
        return result

    # ── Write methods: CRUD ────────────────────────────────────────────

    async def create_wlan(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new WLAN configuration."""
        result: dict[str, Any] = await self.post("rest/wlanconf", json=data)
        return result

    async def update_wlan(self, wlan_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update an existing WLAN configuration."""
        result: dict[str, Any] = await self.put(f"rest/wlanconf/{self._segment(wlan_id)}", json=data)
        return result

    async def delete_wlan(self, wlan_id: str) -> dict[str, Any]:
        """Delete a WLAN configuration."""
        result: dict[str, Any] = await self.delete(f"rest/wlanconf/{self._segment(wlan_id)}")
        return result

    async def create_network(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new network configuration."""
        result: dict[str, Any] = await self.post("rest/networkconf", json=data)
        return result

    async def update_network(self, network_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update an existing network configuration."""
        result: dict[str, Any] = await self.put(f"rest/networkconf/{self._segment(network_id)}", json=data)
        return result

    async def delete_network(self, network_id: str) -> dict[str, Any]:
        """Delete a network configuration."""
        result: dict[str, Any] = await self.delete(f"rest/networkconf/{self._segment(network_id)}")
        return result

    async def create_firewall_rule(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new firewall rule."""
        result: dict[str, Any] = await self.post("rest/firewallrule", json=data)
        return result

    async def update_firewall_rule(self, rule_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update an existing firewall rule."""
        result: dict[str, Any] = await self.put(f"rest/firewallrule/{self._segment(rule_id)}", json=data)
        return result

    async def delete_firewall_rule(self, rule_id: str) -> dict[str, Any]:
        """Delete a firewall rule."""
        result: dict[str, Any] = await self.delete(f"rest/firewallrule/{self._segment(rule_id)}")
        return result

    async def create_firewall_group(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new firewall group."""
        result: dict[str, Any] = await self.post("rest/firewallgroup", json=data)
        return result

    async def update_firewall_group(self, group_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update an existing firewall group."""
        result: dict[str, Any] = await self.put(f"rest/firewallgroup/{self._segment(group_id)}", json=data)
        return result

    async def delete_firewall_group(self, group_id: str) -> dict[str, Any]:
        """Delete a firewall group."""
        result: dict[str, Any] = await self.delete(f"rest/firewallgroup/{self._segment(group_id)}")
        return result

    async def create_port_forward(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new port forwarding rule."""
        result: dict[str, Any] = await self.post("rest/portforward", json=data)
        return result

    async def update_port_forward(self, pf_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update an existing port forwarding rule."""
        result: dict[str, Any] = await self.put(f"rest/portforward/{self._segment(pf_id)}", json=data)
        return result

    async def delete_port_forward(self, pf_id: str) -> dict[str, Any]:
        """Delete a port forwarding rule."""
        result: dict[str, Any] = await self.delete(f"rest/portforward/{self._segment(pf_id)}")
        return result

    async def create_route(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new static route."""
        result: dict[str, Any] = await self.post("rest/routing", json=data)
        return result

    async def update_route(self, route_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update an existing static route."""
        result: dict[str, Any] = await self.put(f"rest/routing/{self._segment(route_id)}", json=data)
        return result

    async def delete_route(self, route_id: str) -> dict[str, Any]:
        """Delete a static route."""
        result: dict[str, Any] = await self.delete(f"rest/routing/{self._segment(route_id)}")
        return result

    async def update_settings(self, data: dict[str, Any]) -> dict[str, Any]:
        """Update controller settings via per-section PUTs.

        The bare ``PUT rest/setting`` rejects multi-section bodies on current
        UCG firmware (HTTP 500). The controller accepts ``PUT rest/setting/<key>``
        with that section's partial body. Top-level keys in ``data`` that
        map to dict values are dispatched one PUT per section; the response
        from the last section is returned (final read-back is the caller's
        responsibility). See #211 for the live evidence.

        Not atomic across sections. If the body covers multiple sections and
        section N's PUT fails, sections 1..N-1 have already been applied; the
        caller sees the failure but the controller state is partially mutated.
        There is no UCG primitive for rollback. If order matters, the caller
        should re-read state after a failure or pass a single section per
        call. See #225.
        """
        section_responses: list[dict[str, Any]] = []
        for key, value in data.items():
            if not isinstance(value, dict):
                raise UniFiError(f"update_settings: section '{key}' must be a dict body, got {type(value).__name__}")
            section_responses.append(await self.put(f"rest/setting/{self._segment(key)}", json=value))
        if not section_responses:
            raise UniFiError("update_settings: no sections in body")
        return section_responses[-1]

    # ── Port profiles ──────────────────────────────────────────────────

    async def list_port_profiles(self) -> dict[str, Any]:
        """List switch-port profiles (``rest/portconf``)."""
        result: dict[str, Any] = await self.get("rest/portconf")
        return result

    async def get_port_profile(self, profile_id: str) -> dict[str, Any]:
        """Get a specific switch-port profile by id."""
        result: dict[str, Any] = await self.get(f"rest/portconf/{self._segment(profile_id)}")
        return result

    async def create_port_profile(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a switch-port profile.

        The controller requires at least ``name``, ``poe_mode`` (e.g. ``auto``),
        and ``forward`` (e.g. ``all`` / ``native`` / ``customize``). Callers
        should pass a full payload — we pass it through verbatim.
        """
        result: dict[str, Any] = await self.post("rest/portconf", json=data)
        return result

    async def update_port_profile(self, profile_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update a switch-port profile."""
        result: dict[str, Any] = await self.put(f"rest/portconf/{self._segment(profile_id)}", json=data)
        return result

    async def delete_port_profile(self, profile_id: str) -> dict[str, Any]:
        """Delete a switch-port profile."""
        result: dict[str, Any] = await self.delete(f"rest/portconf/{self._segment(profile_id)}")
        return result

    async def assign_port_profile(self, mac: str, port_idx: int, profile_id: str) -> dict[str, Any]:
        """Assign a port profile to one switch port.

        The legacy API doesn't expose a single-port endpoint — the whole
        device record must be PUT with an updated ``port_overrides`` array.
        Resolve the device's ``_id`` from ``stat/device``, splice the new
        override into the existing list (replacing any entry for the same
        ``port_idx``), and PUT ``rest/device/{_id}``. See #93.
        """
        devices = await self.list_devices()
        match = next(
            (d for d in devices.get("data", []) if d.get("mac", "").lower() == mac.lower()),
            None,
        )
        if match is None:
            raise UniFiNotFoundError(f"Device with MAC {mac} not adopted by this controller")
        device_id = match.get("_id")
        if not device_id:
            raise UniFiError(f"Device {mac} has no '_id' in list_devices response")

        existing: list[dict[str, Any]] = list(match.get("port_overrides", []))
        overrides = [entry for entry in existing if entry.get("port_idx") != port_idx]
        overrides.append({"port_idx": port_idx, "portconf_id": profile_id})
        result: dict[str, Any] = await self.put(
            f"rest/device/{self._segment(device_id)}", json={"port_overrides": overrides}
        )
        return result

    # ── Write methods: commands ────────────────────────────────────────

    async def run_speedtest(self) -> dict[str, Any]:
        """Initiate a speed test on the controller."""
        result: dict[str, Any] = await self.post("cmd/devmgr", json={"cmd": "speedtest"})
        return result

    async def create_backup(self) -> dict[str, Any]:
        """Create a controller backup.

        UniFi's ``cmd/backup`` endpoint can take several minutes on controllers
        with non-trivial configuration (see #89). Bumps the per-request timeout
        to 5 minutes so the call doesn't surface a spurious ``UniFiTimeoutError``
        before the backup actually completes.
        """
        result: dict[str, Any] = await self.post("cmd/backup", json={"cmd": "backup"}, timeout=300.0)
        return result

    async def restart_device(self, mac: str) -> dict[str, Any]:
        """Restart an adopted device."""
        result: dict[str, Any] = await self.post("cmd/devmgr", json={"cmd": "restart", "mac": mac})
        return result

    async def adopt_device(self, mac: str) -> dict[str, Any]:
        """Adopt a new device.

        The legacy endpoint responds with HTTP 400 ``api.err.InvalidTarget``
        when the device is already adopted — indistinguishable from
        "MAC unknown to controller" at the raw API level. Pre-check against
        ``list_devices`` so already-adopted devices surface a typed
        ``UniFiDeviceAlreadyAdoptedError`` that agents can branch on (#93).

        NOTE: not atomic. The pre-check and the ``cmd/devmgr`` POST are two
        separate requests; a concurrent adoption between them races. The
        legacy ``cmd/*`` endpoints offer no compare-and-set, so closing this
        TOCTOU window would require an unsafe assumption (treat any conflict
        as success) or an API the controller does not expose. Callers must
        tolerate a small chance of ``UniFiDeviceAlreadyAdoptedError`` being
        raised after a successful concurrent adopt. See #151.
        """
        existing = await self.list_devices()
        for device in existing.get("data", []):
            if device.get("mac", "").lower() == mac.lower() and device.get("adopted"):
                raise UniFiDeviceAlreadyAdoptedError(f"Device {mac} is already adopted by this controller")
        result: dict[str, Any] = await self.post("cmd/devmgr", json={"cmd": "adopt", "mac": mac})
        return result

    async def locate_device(self, mac: str) -> dict[str, Any]:
        """Enable the locate LED on a device."""
        result: dict[str, Any] = await self.post("cmd/devmgr", json={"cmd": "set-locate", "mac": mac})
        return result

    async def unlocate_device(self, mac: str) -> dict[str, Any]:
        """Disable the locate LED on a device."""
        result: dict[str, Any] = await self.post("cmd/devmgr", json={"cmd": "unset-locate", "mac": mac})
        return result

    async def forget_device(self, mac: str) -> dict[str, Any]:
        """Release (unadopt) a previously-adopted device so it can be re-adopted.

        Pre-checks against ``list_devices`` and raises ``UniFiNotFoundError``
        when the MAC isn't adopted by this controller. See #93.

        NOTE: not atomic. Same TOCTOU caveat as ``adopt_device``: the
        ``list_devices`` pre-check and the ``cmd/sitemgr`` POST run as
        separate requests, and a concurrent forget/re-adopt between them
        races. The legacy ``cmd/*`` API offers no compare-and-set. See #151.
        """
        devices = await self.list_devices()
        known = {entry.get("mac", "").lower() for entry in devices.get("data", [])}
        if mac.lower() not in known:
            raise UniFiNotFoundError(f"Device with MAC {mac} not adopted by this controller")
        result: dict[str, Any] = await self.post("cmd/sitemgr", json={"cmd": "delete-device", "mac": mac})
        return result

    async def provision_device(self, mac: str) -> dict[str, Any]:
        """Force provision a device."""
        result: dict[str, Any] = await self.post("cmd/devmgr", json={"cmd": "force-provision", "mac": mac})
        return result

    async def upgrade_device(self, mac: str) -> dict[str, Any]:
        """Upgrade a device to the latest firmware."""
        result: dict[str, Any] = await self.post("cmd/devmgr", json={"cmd": "upgrade", "mac": mac})
        return result

    async def power_cycle_port(self, mac: str, port_idx: int) -> dict[str, Any]:
        """Power cycle a PoE port on a switch."""
        result: dict[str, Any] = await self.post(
            "cmd/devmgr", json={"cmd": "power-cycle", "mac": mac, "port_idx": port_idx}
        )
        return result

    async def _assert_client_known(self, mac: str) -> None:
        """Raise UniFiNotFoundError if ``mac`` isn't in the controller's client list.

        The legacy ``cmd/stamgr`` endpoints (block-sta, unblock-sta,
        authorize-guest, unauthorize-guest) return HTTP 200 with
        ``meta.rc == "ok"`` regardless of whether the MAC corresponds to a
        real client, so an agent can't distinguish a real action from a
        silent no-op on a typo. Pre-check against ``list_all_clients``
        (active + historical) to surface a typed 404-style error instead.
        See #96.

        NOTE: not atomic. The pre-check and the subsequent ``cmd/stamgr``
        POST run as separate requests. A client that connects between the
        two will still be blocked/authorized; a client that disconnects
        between them may be acted on after its session ends. This is a
        legacy ``cmd/*`` API limitation — there is no compare-and-set
        primitive. See #151.
        """
        response = await self.list_all_clients()
        known = {entry.get("mac", "").lower() for entry in response.get("data", [])}
        if mac.lower() not in known:
            raise UniFiNotFoundError(f"Client with MAC {mac} not found")

    async def block_client(self, mac: str) -> dict[str, Any]:
        """Block a client from connecting.

        Raises ``UniFiNotFoundError`` (→ ``ToolError: Resource not found``)
        when ``mac`` is unknown to the controller, rather than silently
        succeeding on a typo. See #96.
        """
        await self._assert_client_known(mac)
        result: dict[str, Any] = await self.post("cmd/stamgr", json={"cmd": "block-sta", "mac": mac})
        return result

    async def unblock_client(self, mac: str) -> dict[str, Any]:
        """Unblock a previously blocked client.

        Raises ``UniFiNotFoundError`` when ``mac`` is unknown (see #96).
        """
        await self._assert_client_known(mac)
        result: dict[str, Any] = await self.post("cmd/stamgr", json={"cmd": "unblock-sta", "mac": mac})
        return result

    async def kick_client(self, mac: str) -> dict[str, Any]:
        """Disconnect (kick) a client.

        The controller already validates this endpoint (returns
        ``api.err.UnknownStation`` on missing MAC), so no pre-check.
        """
        result: dict[str, Any] = await self.post("cmd/stamgr", json={"cmd": "kick-sta", "mac": mac})
        return result

    async def _assert_client_is_guest(self, mac: str) -> None:
        """Raise if ``mac`` isn't a known guest-portal client.

        The controller silently no-ops ``authorize-guest`` / ``unauthorize-guest``
        on non-guest clients — HTTP 200, ``meta.rc == "ok"``, no state change.
        Pre-check the client's ``is_guest`` flag against ``list_all_clients``
        and surface a typed error instead. See #220.

        Same atomicity caveat as ``_assert_client_known`` (see #96, #151) —
        the pre-check and the subsequent POST are separate requests.
        """
        response = await self.list_all_clients()
        entry = next(
            (c for c in response.get("data", []) if c.get("mac", "").lower() == mac.lower()),
            None,
        )
        if entry is None:
            raise UniFiNotFoundError(f"Client with MAC {mac} not found")
        if not entry.get("is_guest"):
            raise UniFiBadRequestError(
                f"Client with MAC {mac} is not on a guest network; "
                "authorize_guest / unauthorize_guest only apply to guest-portal clients."
            )

    async def authorize_guest(self, mac: str, minutes: int = 60) -> dict[str, Any]:
        """Authorize a guest client for a given duration.

        Raises ``UniFiNotFoundError`` when ``mac`` is unknown (#96) and
        ``UniFiBadRequestError`` when ``mac`` is not a guest-portal client
        (#220).
        """
        await self._assert_client_is_guest(mac)
        result: dict[str, Any] = await self.post(
            "cmd/stamgr", json={"cmd": "authorize-guest", "mac": mac, "minutes": minutes}
        )
        return result

    async def unauthorize_guest(self, mac: str) -> dict[str, Any]:
        """Revoke guest authorization.

        Raises ``UniFiNotFoundError`` when ``mac`` is unknown (#96) and
        ``UniFiBadRequestError`` when ``mac`` is not a guest-portal client
        (#220).
        """
        await self._assert_client_is_guest(mac)
        result: dict[str, Any] = await self.post("cmd/stamgr", json={"cmd": "unauthorize-guest", "mac": mac})
        return result

    async def reset_dpi(self) -> dict[str, Any]:
        """Reset DPI counters."""
        result: dict[str, Any] = await self.post("cmd/stat", json={"cmd": "reset-dpi"})
        return result

    # ── Lifecycle ──────────────────────────────────────────────────────

    async def validate_connection(self) -> bool:
        """Validate connectivity by fetching system info.

        Returns False on any UniFi or HTTP error. The caught exception is
        stored on ``self._last_validation_error`` so the lifespan can
        surface the failure class in its WARN log.
        """
        try:
            await self.get_sysinfo()
        except (UniFiError, httpx.HTTPError) as exc:
            self._last_validation_error = exc
            logger.debug("Network API connection validation failed", exc_info=True)
            return False
        else:
            self._last_validation_error = None
            return True
