"""Protect accessory device tools - chimes, lights, sensors, viewers (4 read + 5 write)."""

from __future__ import annotations

from typing import Any

from fastmcp import Context, FastMCP

from unifi_mcp.tools._common import (
    JsonObject,
    build_named_arg_body,
    get_server_context,
    redact_secrets,
    reject_dangerous_keys,
    tool_handler,
    validate_id,
)

_CHIME_FIELD_PATHS: dict[str, tuple[str, ...]] = {
    "volume": ("volume",),
    "repeat_times": ("repeatTimes",),
}

_LIGHT_FIELD_PATHS: dict[str, tuple[str, ...]] = {
    "led_level": ("lightDeviceSettings", "ledLevel"),
    "pir_duration": ("lightDeviceSettings", "pirDuration"),
    "pir_sensitivity": ("lightDeviceSettings", "pirSensitivity"),
    "mode": ("lightModeSettings", "mode"),
}

_SENSOR_FIELD_PATHS: dict[str, tuple[str, ...]] = {
    "mount_type": ("mountType",),
    "motion_is_enabled": ("motionSettings", "isEnabled"),
    "light_is_enabled": ("lightSettings", "isEnabled"),
}


def register_protect_device_tools(mcp: FastMCP) -> None:
    """Register Protect accessory device tools."""

    @mcp.tool(tags={"protect"})
    @tool_handler()
    async def unifi_protect_list_chimes(ctx: Context) -> list[dict[str, Any]]:
        """List all Protect chime devices.

        Args:
            ctx: FastMCP request context.

        Returns:
            The upstream API response with sensitive fields redacted.
        """
        return redact_secrets(await get_server_context(ctx).clients["protect"].list_chimes())

    @mcp.tool(tags={"protect"})
    @tool_handler()
    async def unifi_protect_list_lights(ctx: Context) -> list[dict[str, Any]]:
        """List all Protect smart light devices.

        Args:
            ctx: FastMCP request context.

        Returns:
            The upstream API response with sensitive fields redacted.
        """
        return redact_secrets(await get_server_context(ctx).clients["protect"].list_lights())

    @mcp.tool(tags={"protect"})
    @tool_handler()
    async def unifi_protect_list_sensors(ctx: Context) -> list[dict[str, Any]]:
        """List all Protect sensor devices.

        Args:
            ctx: FastMCP request context.

        Returns:
            The upstream API response with sensitive fields redacted.
        """
        return redact_secrets(await get_server_context(ctx).clients["protect"].list_sensors())

    @mcp.tool(tags={"protect"})
    @tool_handler()
    async def unifi_protect_list_viewers(ctx: Context) -> list[dict[str, Any]]:
        """List all Protect viewport devices.

        Args:
            ctx: FastMCP request context.

        Returns:
            The upstream API response with sensitive fields redacted.
        """
        return redact_secrets(await get_server_context(ctx).clients["protect"].list_viewers())

    @mcp.tool(tags={"write", "protect"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    @tool_handler(write=True)
    async def unifi_protect_update_chime(
        ctx: Context,
        chime_id: str,
        *,
        volume: int | None = None,
        repeat_times: int | None = None,
        data: JsonObject | None = None,
    ) -> dict[str, Any]:
        """Update chime settings using named scalar args.

        Pass only the fields to change. At least one named arg or ``data``
        must be supplied.

        Args:
            chime_id: The chime device ID.
            volume: Chime volume, 0-100 (``volume``).
            repeat_times: Number of ring repeats (``repeatTimes``).
            data: Raw settings dict for fields outside the named args above; cannot be
                combined with any named arg. Still passes the dangerous-key denylist.

        Returns:
            The upstream API response.
        """
        validate_id(chime_id, field="chime_id")
        body = build_named_arg_body(
            tool_name="unifi_protect_update_chime",
            field_paths=_CHIME_FIELD_PATHS,
            named_values={
                "volume": volume,
                "repeat_times": repeat_times,
            },
            data=data,
        )
        reject_dangerous_keys(body, tool_name="unifi_protect_update_chime")
        return redact_secrets(await get_server_context(ctx).clients["protect"].update_chime(chime_id, body))

    @mcp.tool(tags={"write", "protect"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    @tool_handler(write=True)
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
            data: Raw settings dict for fields outside the named args above; cannot be
                combined with any named arg. Still passes the dangerous-key denylist.

        Returns:
            The upstream API response.
        """
        validate_id(light_id, field="light_id")
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
        return redact_secrets(await get_server_context(ctx).clients["protect"].update_light(light_id, body))

    @mcp.tool(tags={"write", "protect"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    @tool_handler(write=True)
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
        validate_id(light_id, field="light_id")
        return redact_secrets(
            await get_server_context(ctx)
            .clients["protect"]
            .update_light(light_id, {"lightModeSettings": {"mode": mode}})
        )

    @mcp.tool(tags={"write", "protect"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    @tool_handler(write=True)
    async def unifi_protect_update_sensor(
        ctx: Context,
        sensor_id: str,
        *,
        mount_type: str | None = None,
        motion_is_enabled: bool | None = None,
        light_is_enabled: bool | None = None,
        data: JsonObject | None = None,
    ) -> dict[str, Any]:
        """Update sensor settings using named scalar args.

        Pass only the fields to change. At least one named arg or ``data``
        must be supplied.

        Args:
            sensor_id: The sensor device ID.
            mount_type: Physical mount type, e.g. "door", "window", or "garage"
                (``mountType``).
            motion_is_enabled: Enable or disable motion detection
                (``motionSettings.isEnabled``).
            light_is_enabled: Enable or disable ambient-light (lux) sensor reporting
                (``lightSettings.isEnabled``).
            data: Raw settings dict for fields outside the named args above; cannot be
                combined with any named arg. Still passes the dangerous-key denylist.

        Returns:
            The upstream API response.
        """
        validate_id(sensor_id, field="sensor_id")
        body = build_named_arg_body(
            tool_name="unifi_protect_update_sensor",
            field_paths=_SENSOR_FIELD_PATHS,
            named_values={
                "mount_type": mount_type,
                "motion_is_enabled": motion_is_enabled,
                "light_is_enabled": light_is_enabled,
            },
            data=data,
        )
        reject_dangerous_keys(body, tool_name="unifi_protect_update_sensor")
        return redact_secrets(await get_server_context(ctx).clients["protect"].update_sensor(sensor_id, body))

    @mcp.tool(tags={"write", "protect"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    @tool_handler(write=True)
    async def unifi_protect_set_viewer_liveview(
        ctx: Context,
        viewer_id: str,
        liveview_id: str,
    ) -> dict[str, Any]:
        """Set the active liveview displayed on a Protect viewport.

        Args:
            viewer_id: The viewer device ID.
            liveview_id: The liveview ID to display on this viewer.

        Returns:
            The upstream API response.
        """
        validate_id(viewer_id, field="viewer_id")
        validate_id(liveview_id, field="liveview_id")
        return redact_secrets(
            await get_server_context(ctx).clients["protect"].update_viewer(viewer_id, {"liveview": liveview_id})
        )
