"""Protect accessory device tools — chimes, lights, sensors, viewers (4 read)."""

from __future__ import annotations

from typing import Any

from fastmcp import Context, FastMCP

from unifi_mcp.tools._common import get_server_context, redact_secrets, tool_handler


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
