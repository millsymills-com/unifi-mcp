"""Network Integration device read tools (pending devices, device tags)."""

from __future__ import annotations

from typing import Any

from fastmcp import Context, FastMCP

from unifi_mcp.tools._common import get_server_context, redact_secrets, tool_handler


def register_devices_tools(mcp: FastMCP) -> None:
    """Register the Network Integration device tools."""

    @mcp.tool(tags={"network_integration"})
    @tool_handler()
    async def unifi_network_list_pending_devices(ctx: Context) -> dict[str, Any]:
        """List devices awaiting adoption (Network Integration API).

        Args:
            ctx: FastMCP request context.

        Returns:
            The upstream API response with sensitive fields redacted.
        """
        return redact_secrets(await get_server_context(ctx).clients["network_integration"].list_pending_devices())

    @mcp.tool(tags={"network_integration"})
    @tool_handler()
    async def unifi_network_list_device_tags(ctx: Context) -> dict[str, Any]:
        """List device tags for the resolved site (Network Integration API).

        Args:
            ctx: FastMCP request context.

        Returns:
            The upstream API response with sensitive fields redacted.
        """
        return redact_secrets(await get_server_context(ctx).clients["network_integration"].list_device_tags())
