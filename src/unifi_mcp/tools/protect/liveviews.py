"""Protect live-view and alarm-manager read tools (3 read).

Live views (list + get) and the read-only alarm-manager arm-profiles list. The
arm-profiles enable/disable/settings/{id} mutating endpoints stay out of scope.
"""

from __future__ import annotations

from typing import Any

from fastmcp import Context, FastMCP

from unifi_mcp.tools._common import get_server_context, redact_secrets, tool_handler, validate_id


def register_liveview_tools(mcp: FastMCP) -> None:
    """Register Protect live-view and arm-profile read tools."""

    @mcp.tool(tags={"protect"})
    @tool_handler()
    async def unifi_protect_list_liveviews(ctx: Context) -> list[dict[str, Any]]:
        """List all Protect live views.

        Args:
            ctx: FastMCP request context.

        Returns:
            The upstream API response with sensitive fields redacted.
        """
        return redact_secrets(await get_server_context(ctx).clients["protect"].list_liveviews())

    @mcp.tool(tags={"protect"})
    @tool_handler()
    async def unifi_protect_get_liveview(ctx: Context, liveview_id: str) -> dict[str, Any]:
        """Get detailed info for a specific Protect live view.

        Args:
            liveview_id: The live-view ID.

        Returns:
            The upstream API response with sensitive fields redacted.
        """
        validate_id(liveview_id, field="liveview_id")
        return redact_secrets(await get_server_context(ctx).clients["protect"].get_liveview(liveview_id))

    @mcp.tool(tags={"protect"})
    @tool_handler()
    async def unifi_protect_list_arm_profiles(ctx: Context) -> list[dict[str, Any]]:
        """List Protect alarm-manager arm profiles.

        Read-only view of the alarm-manager surface; the enable/disable/settings
        mutating endpoints are intentionally not exposed.

        Args:
            ctx: FastMCP request context.

        Returns:
            The upstream API response with sensitive fields redacted.
        """
        return redact_secrets(await get_server_context(ctx).clients["protect"].list_arm_profiles())
