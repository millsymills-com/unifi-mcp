"""Protect camera tools (2 read + 3 write)."""

from __future__ import annotations

from typing import Any

from fastmcp import Context, FastMCP

from unifi_mcp.errors import UniFiReadOnlyError, handle_client_error
from unifi_mcp.tools._common import (
    JsonObject,
    build_named_arg_body,
    get_server_context,
    redact_secrets,
    reject_dangerous_keys,
    validate_id,
)

# ── Option-1 allowlist for unifi_protect_update_camera (#202) ──────────────
#
# A flat scalar -> nested-dict path. Each entry tells the named-arg builder
# where to place the value in the outgoing Protect body. Adding a new safe
# camera field is a one-line change here plus the matching kwarg on the
# tool signature; the deliberately-omitted families (recordingSettings,
# smartDetectSettings, talkbackSettings) stay outside this allowlist so the
# named API can never set them — they have dedicated tools instead.
_CAMERA_FIELD_PATHS: dict[str, tuple[str, ...]] = {
    "name": ("name",),
    "led_settings_is_enabled": ("ledSettings", "isEnabled"),
    "osd_settings_is_name_enabled": ("osdSettings", "isNameEnabled"),
    "osd_settings_is_date_enabled": ("osdSettings", "isDateEnabled"),
    "osd_settings_is_logo_enabled": ("osdSettings", "isLogoEnabled"),
    "osd_settings_is_debug_enabled": ("osdSettings", "isDebugEnabled"),
}


def register_camera_tools(mcp: FastMCP) -> None:
    """Register Protect camera tools."""

    @mcp.tool(tags={"protect"})
    async def unifi_protect_list_cameras(ctx: Context) -> list[dict[str, Any]]:
        """List all cameras managed by UniFi Protect.

        Args:
            ctx: FastMCP request context.

        Returns:
            The upstream API response.
        """
        try:
            context = get_server_context(ctx)
            return redact_secrets(await context.clients["protect"].list_cameras())
        except Exception as e:
            handle_client_error(e)

    @mcp.tool(tags={"protect"})
    async def unifi_protect_get_camera(ctx: Context, camera_id: str) -> dict[str, Any]:
        """Get detailed info for a specific camera.

        Camera credentials and token fields are redacted before the
        response leaves this tool — see ``unifi_mcp._redaction`` (#146).

        Args:
            camera_id: The camera ID.

        Returns:
            The upstream API response with sensitive fields redacted.
        """
        try:
            validate_id(camera_id, field="camera_id")
            context = get_server_context(ctx)
            return redact_secrets(await context.clients["protect"].get_camera(camera_id))
        except Exception as e:
            handle_client_error(e)

    @mcp.tool(tags={"write", "protect"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    async def unifi_protect_update_camera(
        ctx: Context,
        camera_id: str,
        *,
        name: str | None = None,
        led_settings_is_enabled: bool | None = None,
        osd_settings_is_name_enabled: bool | None = None,
        osd_settings_is_date_enabled: bool | None = None,
        osd_settings_is_logo_enabled: bool | None = None,
        osd_settings_is_debug_enabled: bool | None = None,
        data: JsonObject | None = None,
    ) -> dict[str, Any]:
        """Update camera settings using named scalar args.

        Pass only the fields to change. ``recordingSettings``,
        ``smartDetectSettings``, and ``talkbackSettings`` are intentionally
        not exposed here — they have dedicated tools (e.g.,
        ``unifi_protect_set_recording_mode``,
        ``unifi_protect_set_smart_detection``).

        Args:
            camera_id: The camera ID.
            name: Camera display name.
            led_settings_is_enabled: Toggle the status LED (``ledSettings.isEnabled``).
            osd_settings_is_name_enabled: Show camera name in the OSD
                (``osdSettings.isNameEnabled``).
            osd_settings_is_date_enabled: Show date in the OSD
                (``osdSettings.isDateEnabled``).
            osd_settings_is_logo_enabled: Show logo in the OSD
                (``osdSettings.isLogoEnabled``).
            osd_settings_is_debug_enabled: Show debug overlay in the OSD
                (``osdSettings.isDebugEnabled``).
            data: DEPRECATED — raw camera settings dict. Kept for
                back-compat with existing agents; prefer the named scalar
                args above. Still passes through the dangerous-key
                denylist. Cannot be combined with any named arg.

        Returns:
            The upstream API response.
        """
        try:
            validate_id(camera_id, field="camera_id")
            context = get_server_context(ctx)
            if not context.config.writes_enabled:
                raise UniFiReadOnlyError("Cannot update camera in read-only mode")
            body = build_named_arg_body(
                tool_name="unifi_protect_update_camera",
                field_paths=_CAMERA_FIELD_PATHS,
                named_values={
                    "name": name,
                    "led_settings_is_enabled": led_settings_is_enabled,
                    "osd_settings_is_name_enabled": osd_settings_is_name_enabled,
                    "osd_settings_is_date_enabled": osd_settings_is_date_enabled,
                    "osd_settings_is_logo_enabled": osd_settings_is_logo_enabled,
                    "osd_settings_is_debug_enabled": osd_settings_is_debug_enabled,
                },
                data=data,
            )
            reject_dangerous_keys(body, tool_name="unifi_protect_update_camera")
            return await context.clients["protect"].update_camera(camera_id, body)
        except Exception as e:
            handle_client_error(e)

    @mcp.tool(tags={"write", "protect"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    async def unifi_protect_set_recording_mode(
        ctx: Context,
        camera_id: str,
        mode: str,
        pre_padding: int | None = None,
        post_padding: int | None = None,
    ) -> dict[str, Any]:
        """Set the recording mode for a camera.

        Args:
            camera_id: The camera ID.
            mode: Recording mode — "always", "motion", "never", "schedule".
            pre_padding: Pre-event recording padding in seconds (optional).
            post_padding: Post-event recording padding in seconds (optional).

        Returns:
            The upstream API response.
        """
        try:
            validate_id(camera_id, field="camera_id")
            context = get_server_context(ctx)
            if not context.config.writes_enabled:
                raise UniFiReadOnlyError("Cannot set recording mode in read-only mode")
            return await context.clients["protect"].set_recording_mode(
                camera_id, mode, pre_padding=pre_padding, post_padding=post_padding
            )
        except Exception as e:
            handle_client_error(e)

    @mcp.tool(tags={"write", "protect"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    async def unifi_protect_set_smart_detection(
        ctx: Context, camera_id: str, object_types: list[str]
    ) -> dict[str, Any]:
        """Configure smart detection object types for a camera.

        Args:
            camera_id: The camera ID.
            object_types: List of object types to detect — e.g., ["person", "vehicle", "animal"].

        Returns:
            The upstream API response.
        """
        try:
            validate_id(camera_id, field="camera_id")
            context = get_server_context(ctx)
            if not context.config.writes_enabled:
                raise UniFiReadOnlyError("Cannot set smart detection in read-only mode")
            return await context.clients["protect"].set_smart_detection(camera_id, object_types)
        except Exception as e:
            handle_client_error(e)
