"""Protect accessory device tools — chimes, lights, sensors, viewers (4 read + writes)."""

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

_LIGHT_FIELD_PATHS: dict[str, tuple[str, ...]] = {
    "led_level": ("lightDeviceSettings", "ledLevel"),
    "pir_duration": ("lightDeviceSettings", "pirDuration"),
    "pir_sensitivity": ("lightDeviceSettings", "pirSensitivity"),
    "mode": ("lightModeSettings", "mode"),
}


def register_protect_device_tools(mcp: FastMCP) -> None:
    """Register Protect accessory device tools."""

    @mcp.tool(tags={"protect"})
    async def unifi_protect_list_chimes(ctx: Context) -> list[dict[str, Any]]:
        """List all Protect chime devices.

        Args:
            ctx: FastMCP request context.

        Returns:
            The upstream API response with sensitive fields redacted.
        """
        try:
            context = get_server_context(ctx)
            return redact_secrets(await context.clients["protect"].list_chimes())
        except Exception as e:
            handle_client_error(e)

    @mcp.tool(tags={"protect"})
    async def unifi_protect_list_lights(ctx: Context) -> list[dict[str, Any]]:
        """List all Protect smart light devices.

        Args:
            ctx: FastMCP request context.

        Returns:
            The upstream API response with sensitive fields redacted.
        """
        try:
            context = get_server_context(ctx)
            return redact_secrets(await context.clients["protect"].list_lights())
        except Exception as e:
            handle_client_error(e)

    @mcp.tool(tags={"protect"})
    async def unifi_protect_list_sensors(ctx: Context) -> list[dict[str, Any]]:
        """List all Protect sensor devices.

        Args:
            ctx: FastMCP request context.

        Returns:
            The upstream API response with sensitive fields redacted.
        """
        try:
            context = get_server_context(ctx)
            return redact_secrets(await context.clients["protect"].list_sensors())
        except Exception as e:
            handle_client_error(e)

    @mcp.tool(tags={"protect"})
    async def unifi_protect_list_viewers(ctx: Context) -> list[dict[str, Any]]:
        """List all Protect viewport devices.

        Args:
            ctx: FastMCP request context.

        Returns:
            The upstream API response with sensitive fields redacted.
        """
        try:
            context = get_server_context(ctx)
            return redact_secrets(await context.clients["protect"].list_viewers())
        except Exception as e:
            handle_client_error(e)

    @mcp.tool(tags={"write", "protect"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    async def unifi_protect_update_light(
        ctx: Context,
        light_id: str,
        *,
        led_level: int | None = None,
        pir_duration: int | None = None,
        pir_sensitivity: int | None = None,
        mode: str | None = None,
        data: JsonObject | None = None,
    ) -> dict[str, Any]:
        """Update light settings using named scalar args.

        Pass only the fields to change. At least one named arg or ``data``
        must be supplied.

        Args:
            light_id: The light device ID.
            led_level: LED brightness level (``lightDeviceSettings.ledLevel``),
                1-6.
            pir_duration: PIR motion detection hold duration in milliseconds
                (``lightDeviceSettings.pirDuration``).
            pir_sensitivity: PIR motion detection sensitivity, 0-100
                (``lightDeviceSettings.pirSensitivity``).
            mode: Light activation mode (``lightModeSettings.mode``) —
                "off", "motion", or "always".
            data: DEPRECATED — raw light settings dict. Kept for
                back-compat with existing agents; prefer the named scalar
                args above. Still passes through the dangerous-key
                denylist. Cannot be combined with any named arg.

        Returns:
            The upstream API response.
        """
        try:
            validate_id(light_id, field="light_id")
            context = get_server_context(ctx)
            if not context.config.writes_enabled:
                raise UniFiReadOnlyError("Cannot update light in read-only mode")
            body = build_named_arg_body(
                tool_name="unifi_protect_update_light",
                field_paths=_LIGHT_FIELD_PATHS,
                named_values={
                    "led_level": led_level,
                    "pir_duration": pir_duration,
                    "pir_sensitivity": pir_sensitivity,
                    "mode": mode,
                },
                data=data,
            )
            reject_dangerous_keys(body, tool_name="unifi_protect_update_light")
            return await context.clients["protect"].update_light(light_id, body)
        except Exception as e:
            handle_client_error(e)

    @mcp.tool(tags={"write", "protect"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    async def unifi_protect_set_light_mode(
        ctx: Context,
        light_id: str,
        mode: str,
    ) -> dict[str, Any]:
        """Set the activation mode for a Protect smart light.

        Args:
            light_id: The light device ID.
            mode: Light activation mode — "off", "motion", or "always".

        Returns:
            The upstream API response.
        """
        try:
            validate_id(light_id, field="light_id")
            context = get_server_context(ctx)
            if not context.config.writes_enabled:
                raise UniFiReadOnlyError("Cannot set light mode in read-only mode")
            return await context.clients["protect"].update_light(light_id, {"lightModeSettings": {"mode": mode}})
        except Exception as e:
            handle_client_error(e)
