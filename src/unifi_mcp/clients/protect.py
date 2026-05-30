"""Protect API client for UniFi Protect NVRs."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from unifi_mcp.clients.base import BaseUniFiClient
from unifi_mcp.errors import UniFiError

logger = logging.getLogger(__name__)


class ProtectClient(BaseUniFiClient):
    """Client for the UniFi Protect integration API on a local controller.

    Uses ``/proxy/protect/integration/v1/`` (X-API-Key compatible). The
    legacy ``/proxy/protect/api/`` path only accepts session-cookie auth.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        verify_ssl: bool = False,
        cert_fingerprint: str | None = None,
        timeout: int = 30,
        max_retries: int = 3,
    ) -> None:
        self._path_prefix = "/proxy/protect/integration/v1/"
        super().__init__(
            base_url=base_url,
            api_key=api_key,
            verify_ssl=verify_ssl,
            cert_fingerprint=cert_fingerprint,
            timeout=timeout,
            max_retries=max_retries,
        )

    # -- Read methods -------------------------------------------------------

    async def list_cameras(self) -> list[dict[str, Any]]:
        """List all cameras."""
        result: list[dict[str, Any]] = await self.get("cameras")
        return result

    async def get_camera(self, camera_id: str) -> dict[str, Any]:
        """Get a specific camera by ID."""
        result: dict[str, Any] = await self.get(f"cameras/{self._segment(camera_id)}")
        return result

    async def get_nvr(self) -> dict[str, Any]:
        """Get NVR system information.

        The integration API exposes the NVR at ``nvrs`` (plural) but returns
        a single object — there is one NVR per controller.
        """
        result: dict[str, Any] = await self.get("nvrs")
        return result

    async def list_chimes(self) -> list[dict[str, Any]]:
        """List all chimes."""
        result: list[dict[str, Any]] = await self.get("chimes")
        return result

    async def list_lights(self) -> list[dict[str, Any]]:
        """List all lights."""
        result: list[dict[str, Any]] = await self.get("lights")
        return result

    async def list_sensors(self) -> list[dict[str, Any]]:
        """List all sensors."""
        result: list[dict[str, Any]] = await self.get("sensors")
        return result

    async def list_viewers(self) -> list[dict[str, Any]]:
        """List all viewers."""
        result: list[dict[str, Any]] = await self.get("viewers")
        return result

    # -- Write methods ------------------------------------------------------

    async def update_camera(self, camera_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update camera settings."""
        result: dict[str, Any] = await self.patch(f"cameras/{self._segment(camera_id)}", json=data)
        return result

    async def set_recording_mode(
        self,
        camera_id: str,
        mode: str,
        pre_padding: int | None = None,
        post_padding: int | None = None,
    ) -> dict[str, Any]:
        """Set the recording mode for a camera.

        Args:
            camera_id: The camera ID.
            mode: Recording mode (e.g. ``always``, ``motion``, ``never``).
            pre_padding: Optional pre-event recording padding in seconds.
            post_padding: Optional post-event recording padding in seconds.
        """
        recording_settings: dict[str, Any] = {"mode": mode}
        if pre_padding is not None:
            recording_settings["prePaddingSecs"] = pre_padding
        if post_padding is not None:
            recording_settings["postPaddingSecs"] = post_padding

        result: dict[str, Any] = await self.patch(
            f"cameras/{self._segment(camera_id)}",
            json={"recordingSettings": recording_settings},
        )
        return result

    async def set_smart_detection(self, camera_id: str, object_types: list[str]) -> dict[str, Any]:
        """Set smart detection object types for a camera.

        Args:
            camera_id: The camera ID.
            object_types: List of smart detection object types to enable.
        """
        result: dict[str, Any] = await self.patch(
            f"cameras/{self._segment(camera_id)}",
            json={"smartDetectSettings": {"objectTypes": object_types}},
        )
        return result

    async def update_nvr(self, data: dict[str, Any]) -> dict[str, Any]:
        """Update NVR settings."""
        # TODO(#43): live-verify PUT /nvrs (vs /nvrs/{id}) against a real Protect NVR.
        result: dict[str, Any] = await self.put("nvrs", json=data)
        return result

    # -- Media methods ------------------------------------------------------

    async def get_snapshot(
        self, camera_id: str, timestamp: int | None = None, *, max_bytes: int | None = None
    ) -> bytes:
        """Get a snapshot image from a camera.

        Args:
            camera_id: The camera ID.
            timestamp: Optional Unix timestamp (ms) for a historical snapshot.
            max_bytes: If set, stream the response and abort if the snapshot
                exceeds this many bytes. Prevents OOM on a malformed or
                hostile camera returning an oversized image.

        Returns:
            Raw snapshot bytes (JPEG).
        """
        params: dict[str, int] = {}
        if timestamp is not None:
            params["ts"] = timestamp
        return await self.get_raw(f"cameras/{self._segment(camera_id)}/snapshot", params=params, max_bytes=max_bytes)

    async def export_video(self, camera_id: str, start: int, end: int, *, max_bytes: int | None = None) -> bytes:
        """Export a video clip from a camera.

        Args:
            camera_id: The camera ID.
            start: Start timestamp in milliseconds.
            end: End timestamp in milliseconds.
            max_bytes: If set, stream the response and abort if the export
                exceeds this many bytes. Prevents OOM on unbounded clips.

        Returns:
            Raw video bytes.
        """
        return await self.get_raw(
            f"cameras/{self._segment(camera_id)}/video/export",
            params={"start": start, "end": end},
            max_bytes=max_bytes,
        )

    # -- Lifecycle ----------------------------------------------------------

    async def validate_connection(self) -> bool:
        """Validate connectivity by fetching NVR info.

        Returns False on any UniFi or HTTP error. The caught exception is
        stored on ``self._last_validation_error`` so the lifespan can
        surface the failure class in its WARN log.
        """
        try:
            await self.get_nvr()
        except (UniFiError, httpx.HTTPError) as exc:
            self._last_validation_error = exc
            logger.debug("Protect API connection validation failed", exc_info=True)
            return False
        else:
            self._last_validation_error = None
            return True
