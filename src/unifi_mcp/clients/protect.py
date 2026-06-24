"""Protect API client for UniFi Protect NVRs."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from unifi_mcp._redaction import flatten_key_names
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

    # -- HTTP helpers -------------------------------------------------------

    async def patch(self, path: str, **kwargs: Any) -> Any:
        """HTTP PATCH that logs the outbound write's target and body key-set.

        Every Protect write tool funnels through here. The integration-v1 API
        returns 200 + empty body even when a nested field key is unrecognized,
        so a write can silently no-op with no other evidence; this INFO line
        records what was attempted. Only key *names* are logged (top-level and
        nested, dotted) — never values, which may carry credentials. PATCH is
        Protect-only, so this override is the single choke point. See #329.
        """
        body = kwargs.get("json")
        keys = flatten_key_names(body)
        logger.info("PATCH %s keys=[%s]", path, ", ".join(keys))
        return await super().patch(path, **kwargs)

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

    async def get_chime(self, chime_id: str) -> dict[str, Any]:
        """Get a specific chime by ID."""
        result: dict[str, Any] = await self.get(f"chimes/{self._segment(chime_id)}")
        return result

    async def get_light(self, light_id: str) -> dict[str, Any]:
        """Get a specific light by ID."""
        result: dict[str, Any] = await self.get(f"lights/{self._segment(light_id)}")
        return result

    async def get_sensor(self, sensor_id: str) -> dict[str, Any]:
        """Get a specific sensor by ID."""
        result: dict[str, Any] = await self.get(f"sensors/{self._segment(sensor_id)}")
        return result

    async def get_viewer(self, viewer_id: str) -> dict[str, Any]:
        """Get a specific viewer by ID."""
        result: dict[str, Any] = await self.get(f"viewers/{self._segment(viewer_id)}")
        return result

    async def list_speakers(self) -> list[dict[str, Any]]:
        """List all speakers."""
        result: list[dict[str, Any]] = await self.get("speakers")
        return result

    async def get_speaker(self, speaker_id: str) -> dict[str, Any]:
        """Get a specific speaker by ID."""
        result: dict[str, Any] = await self.get(f"speakers/{self._segment(speaker_id)}")
        return result

    async def list_sirens(self) -> list[dict[str, Any]]:
        """List all sirens."""
        result: list[dict[str, Any]] = await self.get("sirens")
        return result

    async def get_siren(self, siren_id: str) -> dict[str, Any]:
        """Get a specific siren by ID."""
        result: dict[str, Any] = await self.get(f"sirens/{self._segment(siren_id)}")
        return result

    async def list_bridges(self) -> list[dict[str, Any]]:
        """List all bridges."""
        result: list[dict[str, Any]] = await self.get("bridges")
        return result

    async def get_bridge(self, bridge_id: str) -> dict[str, Any]:
        """Get a specific bridge by ID."""
        result: dict[str, Any] = await self.get(f"bridges/{self._segment(bridge_id)}")
        return result

    async def list_relays(self) -> list[dict[str, Any]]:
        """List all relays."""
        result: list[dict[str, Any]] = await self.get("relays")
        return result

    async def get_relay(self, relay_id: str) -> dict[str, Any]:
        """Get a specific relay by ID."""
        result: dict[str, Any] = await self.get(f"relays/{self._segment(relay_id)}")
        return result

    async def list_link_stations(self) -> list[dict[str, Any]]:
        """List all link stations."""
        result: list[dict[str, Any]] = await self.get("link-stations")
        return result

    async def get_link_station(self, link_station_id: str) -> dict[str, Any]:
        """Get a specific link station by ID."""
        result: dict[str, Any] = await self.get(f"link-stations/{self._segment(link_station_id)}")
        return result

    async def list_fobs(self) -> list[dict[str, Any]]:
        """List all fobs."""
        result: list[dict[str, Any]] = await self.get("fobs")
        return result

    async def get_fob(self, fob_id: str) -> dict[str, Any]:
        """Get a specific fob by ID."""
        result: dict[str, Any] = await self.get(f"fobs/{self._segment(fob_id)}")
        return result

    async def list_alarm_hubs(self) -> list[dict[str, Any]]:
        """List all alarm hubs."""
        result: list[dict[str, Any]] = await self.get("alarm-hubs")
        return result

    async def get_alarm_hub(self, alarm_hub_id: str) -> dict[str, Any]:
        """Get a specific alarm hub by ID."""
        result: dict[str, Any] = await self.get(f"alarm-hubs/{self._segment(alarm_hub_id)}")
        return result

    async def list_liveviews(self) -> list[dict[str, Any]]:
        """List all live views."""
        result: list[dict[str, Any]] = await self.get("liveviews")
        return result

    async def get_liveview(self, liveview_id: str) -> dict[str, Any]:
        """Get a specific live view by ID."""
        result: dict[str, Any] = await self.get(f"liveviews/{self._segment(liveview_id)}")
        return result

    async def list_arm_profiles(self) -> list[dict[str, Any]]:
        """List all alarm-manager arm profiles."""
        result: list[dict[str, Any]] = await self.get("arm-profiles")
        return result

    async def list_users(self) -> list[dict[str, Any]]:
        """List all Protect users."""
        result: list[dict[str, Any]] = await self.get("users")
        return result

    async def get_user(self, user_id: str) -> dict[str, Any]:
        """Get a specific Protect user by ID."""
        result: dict[str, Any] = await self.get(f"users/{self._segment(user_id)}")
        return result

    async def list_ulp_users(self) -> list[dict[str, Any]]:
        """List all UniFi Local Portal (ULP) users."""
        result: list[dict[str, Any]] = await self.get("ulp-users")
        return result

    async def get_ulp_user(self, ulp_user_id: str) -> dict[str, Any]:
        """Get a specific ULP user by ID."""
        result: dict[str, Any] = await self.get(f"ulp-users/{self._segment(ulp_user_id)}")
        return result

    async def get_meta_info(self) -> dict[str, Any]:
        """Get Protect application metadata."""
        result: dict[str, Any] = await self.get("meta/info")
        return result

    async def get_rtsps_stream(self, camera_id: str, qualities: list[str] | None = None) -> dict[str, Any]:
        """Get the RTSPS stream descriptor(s) for a camera.

        Args:
            camera_id: The camera ID.
            qualities: Optional list of stream qualities to request (e.g.
                ``["high", "medium"]``). When ``None``, the controller returns
                its default set.

        Returns:
            The RTSPS stream descriptor. May be empty or 404 when no stream is
            active — callers must tolerate both (mirrors ``export_video``, #227).
        """
        params: dict[str, list[str]] = {}
        if qualities is not None:
            params["qualities"] = qualities
        result: dict[str, Any] = await self.get(f"cameras/{self._segment(camera_id)}/rtsps-stream", params=params)
        return result

    async def get_file_asset(self, file_type: str) -> dict[str, Any]:
        """Get a device asset descriptor for a file type.

        The integration v1 ``files/{fileType}`` endpoint's content-type is
        unverified against live hardware. This client assumes JSON metadata
        (``self.get``); if it serves raw bytes, the tool moves to ``media.py``
        with ``get_raw`` + a byte cap. See the Phase 2 caveat in #407.

        Args:
            file_type: The file/asset type segment.

        Returns:
            The asset descriptor as parsed JSON.
        """
        result: dict[str, Any] = await self.get(f"files/{self._segment(file_type)}")
        return result

    # -- Write methods ------------------------------------------------------

    async def update_camera(self, camera_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update camera settings."""
        result: dict[str, Any] = await self.patch(f"cameras/{self._segment(camera_id)}", json=data)
        return result

    async def update_chime(self, chime_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update chime settings."""
        result: dict[str, Any] = await self.patch(f"chimes/{self._segment(chime_id)}", json=data)
        return result

    async def update_light(self, light_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update light settings."""
        result: dict[str, Any] = await self.patch(f"lights/{self._segment(light_id)}", json=data)
        return result

    async def update_sensor(self, sensor_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update sensor settings."""
        result: dict[str, Any] = await self.patch(f"sensors/{self._segment(sensor_id)}", json=data)
        return result

    async def update_viewer(self, viewer_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update viewer settings."""
        result: dict[str, Any] = await self.patch(f"viewers/{self._segment(viewer_id)}", json=data)
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

    # -- Media methods ------------------------------------------------------

    async def get_snapshot(self, camera_id: str, timestamp: int | None = None, *, max_bytes: int) -> bytes:
        """Get a snapshot image from a camera.

        Args:
            camera_id: The camera ID.
            timestamp: Optional Unix timestamp (ms) for a historical snapshot.
            max_bytes: Stream the response and abort if the snapshot exceeds
                this many bytes. Prevents OOM on a malformed or hostile camera
                returning an oversized image.

        Returns:
            Raw snapshot bytes (JPEG).
        """
        params: dict[str, int] = {}
        if timestamp is not None:
            params["ts"] = timestamp
        return await self.get_raw(f"cameras/{self._segment(camera_id)}/snapshot", params=params, max_bytes=max_bytes)

    async def export_video(self, camera_id: str, start: int, end: int, *, max_bytes: int) -> bytes:
        """Export a video clip from a camera.

        Args:
            camera_id: The camera ID.
            start: Start timestamp in milliseconds.
            end: End timestamp in milliseconds.
            max_bytes: Stream the response and abort if the export exceeds this
                many bytes. Prevents OOM on unbounded clips.

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
