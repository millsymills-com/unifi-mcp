"""Site Manager API client for UniFi cloud services."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from unifi_mcp.clients.base import BaseUniFiClient
from unifi_mcp.errors import UniFiError

logger = logging.getLogger(__name__)

SITE_MANAGER_BASE_URL = "https://api.ui.com"


class SiteManagerClient(BaseUniFiClient):
    """Client for the UniFi Site Manager cloud API.

    The Site Manager API is a public cloud service (api.ui.com) that provides
    a unified view of all hosts, sites, and devices across an account.
    """

    _path_prefix: str = "/v1/"
    # The Site Manager early-access (EA) surface sits beside ``/v1/``, not
    # under it: ``/ea/sd-wan-configs`` is a sibling of ``/v1/hosts``. The
    # client routes EA calls with this per-request prefix override so the
    # realized URL is exactly ``/ea/...`` and never ``/v1/ea/...``.
    _EA_PREFIX: str = "/ea/"

    def __init__(
        self,
        api_key: str,
        *,
        timeout: int = 30,
        max_retries: int = 3,
    ) -> None:
        super().__init__(
            base_url=SITE_MANAGER_BASE_URL,
            api_key=api_key,
            verify_ssl=True,
            timeout=timeout,
            max_retries=max_retries,
        )

    async def list_hosts(self) -> dict[str, Any]:
        """List all hosts (controllers) registered in Site Manager."""
        result: dict[str, Any] = await self.get("hosts")
        return result

    async def list_sites(self) -> dict[str, Any]:
        """List all sites across all hosts."""
        result: dict[str, Any] = await self.get("sites")
        return result

    async def list_devices(self, host_id: str | None = None) -> dict[str, Any]:
        """List all devices, optionally filtered by host ID."""
        params: dict[str, str] = {}
        if host_id is not None:
            params["hostId"] = host_id
        result: dict[str, Any] = await self.get("devices", params=params)
        return result

    async def get_host(self, host_id: str) -> dict[str, Any]:
        """Get a single host's detail record by ID."""
        result: dict[str, Any] = await self.get(f"hosts/{self._segment(host_id)}")
        return result

    async def get_isp_metrics(
        self,
        metric_type: str,
        *,
        begin_timestamp: str | None = None,
        end_timestamp: str | None = None,
        duration: str | None = None,
    ) -> dict[str, Any]:
        """Get ISP performance metrics for the given metric window.

        Only the non-``None`` time-range params are forwarded as query
        parameters so the upstream defaults apply when a caller omits them.
        """
        params: dict[str, str] = {}
        if begin_timestamp is not None:
            params["beginTimestamp"] = begin_timestamp
        if end_timestamp is not None:
            params["endTimestamp"] = end_timestamp
        if duration is not None:
            params["duration"] = duration
        result: dict[str, Any] = await self.get(f"isp-metrics/{self._segment(metric_type)}", params=params)
        return result

    async def query_isp_metrics(self, metric_type: str, sites: list[dict[str, Any]]) -> dict[str, Any]:
        """Query ISP metrics for specific sites via a pure selector body.

        This is a read despite being a POST: the body is a site selector and
        mutates nothing on the upstream.
        """
        result: dict[str, Any] = await self.post(
            f"isp-metrics/{self._segment(metric_type)}/query", json={"sites": sites}
        )
        return result

    async def _get_ea(self, suffix: str) -> Any:
        """GET an early-access (``/ea/``) endpoint with the EA prefix override.

        ``suffix`` is a bare relative path built from ``_segment`` for any
        agent-controlled ID, so the leading-slash/scheme gate in ``_url``
        still applies.
        """
        response = await self._request("GET", suffix, prefix=self._EA_PREFIX)
        return self._parse_json(response)

    async def list_sdwan_configs(self) -> dict[str, Any]:
        """List SD-WAN configs (early-access surface)."""
        result: dict[str, Any] = await self._get_ea("sd-wan-configs")
        return result

    async def get_sdwan_config(self, config_id: str) -> dict[str, Any]:
        """Get a single SD-WAN config by ID (early-access surface)."""
        result: dict[str, Any] = await self._get_ea(f"sd-wan-configs/{self._segment(config_id)}")
        return result

    async def get_sdwan_config_status(self, config_id: str) -> dict[str, Any]:
        """Get SD-WAN config deployment status by ID (early-access surface)."""
        result: dict[str, Any] = await self._get_ea(f"sd-wan-configs/{self._segment(config_id)}/status")
        return result

    async def validate_connection(self) -> bool:
        """Validate connectivity by attempting to list hosts.

        Returns False on any UniFi or HTTP error. The caught exception is
        stored on ``self._last_validation_error`` so the lifespan can
        surface the failure class in its WARN log.
        """
        try:
            await self.list_hosts()
        except (UniFiError, httpx.HTTPError) as exc:
            self._last_validation_error = exc
            logger.debug("Site Manager connection validation failed", exc_info=True)
            return False
        else:
            self._last_validation_error = None
            return True
