"""Protect per-device read tools — detail lookups + new device classes (18 read).

``get_{id}`` detail tools for the four device classes already exposed via list
tools (chimes, lights, sensors, viewers) plus list+get for seven device classes
with no prior tooling (speakers, sirens, bridges, relays, link-stations, fobs,
alarm-hubs).
"""

from __future__ import annotations

from typing import Any

from fastmcp import Context, FastMCP

from unifi_mcp.tools._common import get_server_context, redact_secrets, tool_handler, validate_id


def register_protect_device_read_tools(mcp: FastMCP) -> None:
    """Register Protect per-device read tools."""

    @mcp.tool(tags={"protect"})
    @tool_handler()
    async def unifi_protect_get_chime(ctx: Context, chime_id: str) -> dict[str, Any]:
        """Get detailed info for a specific Protect chime.

        Args:
            chime_id: The chime device ID.

        Returns:
            The upstream API response with sensitive fields redacted.
        """
        validate_id(chime_id, field="chime_id")
        return redact_secrets(await get_server_context(ctx).clients["protect"].get_chime(chime_id))

    @mcp.tool(tags={"protect"})
    @tool_handler()
    async def unifi_protect_get_light(ctx: Context, light_id: str) -> dict[str, Any]:
        """Get detailed info for a specific Protect smart light.

        Args:
            light_id: The light device ID.

        Returns:
            The upstream API response with sensitive fields redacted.
        """
        validate_id(light_id, field="light_id")
        return redact_secrets(await get_server_context(ctx).clients["protect"].get_light(light_id))

    @mcp.tool(tags={"protect"})
    @tool_handler()
    async def unifi_protect_get_sensor(ctx: Context, sensor_id: str) -> dict[str, Any]:
        """Get detailed info for a specific Protect sensor.

        Args:
            sensor_id: The sensor device ID.

        Returns:
            The upstream API response with sensitive fields redacted.
        """
        validate_id(sensor_id, field="sensor_id")
        return redact_secrets(await get_server_context(ctx).clients["protect"].get_sensor(sensor_id))

    @mcp.tool(tags={"protect"})
    @tool_handler()
    async def unifi_protect_get_viewer(ctx: Context, viewer_id: str) -> dict[str, Any]:
        """Get detailed info for a specific Protect viewport.

        Args:
            viewer_id: The viewer device ID.

        Returns:
            The upstream API response with sensitive fields redacted.
        """
        validate_id(viewer_id, field="viewer_id")
        return redact_secrets(await get_server_context(ctx).clients["protect"].get_viewer(viewer_id))

    @mcp.tool(tags={"protect"})
    @tool_handler()
    async def unifi_protect_list_speakers(ctx: Context) -> list[dict[str, Any]]:
        """List all Protect speaker devices.

        Args:
            ctx: FastMCP request context.

        Returns:
            The upstream API response with sensitive fields redacted.
        """
        return redact_secrets(await get_server_context(ctx).clients["protect"].list_speakers())

    @mcp.tool(tags={"protect"})
    @tool_handler()
    async def unifi_protect_get_speaker(ctx: Context, speaker_id: str) -> dict[str, Any]:
        """Get detailed info for a specific Protect speaker.

        Args:
            speaker_id: The speaker device ID.

        Returns:
            The upstream API response with sensitive fields redacted.
        """
        validate_id(speaker_id, field="speaker_id")
        return redact_secrets(await get_server_context(ctx).clients["protect"].get_speaker(speaker_id))

    @mcp.tool(tags={"protect"})
    @tool_handler()
    async def unifi_protect_list_sirens(ctx: Context) -> list[dict[str, Any]]:
        """List all Protect siren devices.

        Args:
            ctx: FastMCP request context.

        Returns:
            The upstream API response with sensitive fields redacted.
        """
        return redact_secrets(await get_server_context(ctx).clients["protect"].list_sirens())

    @mcp.tool(tags={"protect"})
    @tool_handler()
    async def unifi_protect_get_siren(ctx: Context, siren_id: str) -> dict[str, Any]:
        """Get detailed info for a specific Protect siren.

        Args:
            siren_id: The siren device ID.

        Returns:
            The upstream API response with sensitive fields redacted.
        """
        validate_id(siren_id, field="siren_id")
        return redact_secrets(await get_server_context(ctx).clients["protect"].get_siren(siren_id))

    @mcp.tool(tags={"protect"})
    @tool_handler()
    async def unifi_protect_list_bridges(ctx: Context) -> list[dict[str, Any]]:
        """List all Protect bridge devices.

        Args:
            ctx: FastMCP request context.

        Returns:
            The upstream API response with sensitive fields redacted.
        """
        return redact_secrets(await get_server_context(ctx).clients["protect"].list_bridges())

    @mcp.tool(tags={"protect"})
    @tool_handler()
    async def unifi_protect_get_bridge(ctx: Context, bridge_id: str) -> dict[str, Any]:
        """Get detailed info for a specific Protect bridge.

        Args:
            bridge_id: The bridge device ID.

        Returns:
            The upstream API response with sensitive fields redacted.
        """
        validate_id(bridge_id, field="bridge_id")
        return redact_secrets(await get_server_context(ctx).clients["protect"].get_bridge(bridge_id))

    @mcp.tool(tags={"protect"})
    @tool_handler()
    async def unifi_protect_list_relays(ctx: Context) -> list[dict[str, Any]]:
        """List all Protect relay devices.

        Args:
            ctx: FastMCP request context.

        Returns:
            The upstream API response with sensitive fields redacted.
        """
        return redact_secrets(await get_server_context(ctx).clients["protect"].list_relays())

    @mcp.tool(tags={"protect"})
    @tool_handler()
    async def unifi_protect_get_relay(ctx: Context, relay_id: str) -> dict[str, Any]:
        """Get detailed info for a specific Protect relay.

        Args:
            relay_id: The relay device ID.

        Returns:
            The upstream API response with sensitive fields redacted.
        """
        validate_id(relay_id, field="relay_id")
        return redact_secrets(await get_server_context(ctx).clients["protect"].get_relay(relay_id))

    @mcp.tool(tags={"protect"})
    @tool_handler()
    async def unifi_protect_list_link_stations(ctx: Context) -> list[dict[str, Any]]:
        """List all Protect link-station devices.

        Args:
            ctx: FastMCP request context.

        Returns:
            The upstream API response with sensitive fields redacted.
        """
        return redact_secrets(await get_server_context(ctx).clients["protect"].list_link_stations())

    @mcp.tool(tags={"protect"})
    @tool_handler()
    async def unifi_protect_get_link_station(ctx: Context, link_station_id: str) -> dict[str, Any]:
        """Get detailed info for a specific Protect link station.

        Args:
            link_station_id: The link-station device ID.

        Returns:
            The upstream API response with sensitive fields redacted.
        """
        validate_id(link_station_id, field="link_station_id")
        return redact_secrets(await get_server_context(ctx).clients["protect"].get_link_station(link_station_id))

    @mcp.tool(tags={"protect"})
    @tool_handler()
    async def unifi_protect_list_fobs(ctx: Context) -> list[dict[str, Any]]:
        """List all Protect key-fob devices.

        Args:
            ctx: FastMCP request context.

        Returns:
            The upstream API response with sensitive fields redacted.
        """
        return redact_secrets(await get_server_context(ctx).clients["protect"].list_fobs())

    @mcp.tool(tags={"protect"})
    @tool_handler()
    async def unifi_protect_get_fob(ctx: Context, fob_id: str) -> dict[str, Any]:
        """Get detailed info for a specific Protect key fob.

        Args:
            fob_id: The fob device ID.

        Returns:
            The upstream API response with sensitive fields redacted.
        """
        validate_id(fob_id, field="fob_id")
        return redact_secrets(await get_server_context(ctx).clients["protect"].get_fob(fob_id))

    @mcp.tool(tags={"protect"})
    @tool_handler()
    async def unifi_protect_list_alarm_hubs(ctx: Context) -> list[dict[str, Any]]:
        """List all Protect alarm-hub devices.

        Args:
            ctx: FastMCP request context.

        Returns:
            The upstream API response with sensitive fields redacted.
        """
        return redact_secrets(await get_server_context(ctx).clients["protect"].list_alarm_hubs())

    @mcp.tool(tags={"protect"})
    @tool_handler()
    async def unifi_protect_get_alarm_hub(ctx: Context, alarm_hub_id: str) -> dict[str, Any]:
        """Get detailed info for a specific Protect alarm hub.

        Args:
            alarm_hub_id: The alarm-hub device ID.

        Returns:
            The upstream API response with sensitive fields redacted.
        """
        validate_id(alarm_hub_id, field="alarm_hub_id")
        return redact_secrets(await get_server_context(ctx).clients["protect"].get_alarm_hub(alarm_hub_id))
