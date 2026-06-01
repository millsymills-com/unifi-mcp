"""Network statistics and monitoring tools (9 read-only tools)."""

from __future__ import annotations

from typing import Any

from fastmcp import Context, FastMCP

from unifi_mcp.errors import UniFiBadRequestError
from unifi_mcp.tools._common import get_server_context, redact_secrets, tool_handler


def register_stats_tools(mcp: FastMCP) -> None:
    """Register network stats tools."""

    @mcp.tool(tags={"network"})
    @tool_handler()
    async def unifi_network_get_health(ctx: Context) -> dict[str, Any]:
        """Get health status for all network subsystems (www, wlan, lan, wan).

        Args:
            ctx: FastMCP request context.

        Returns:
            The upstream API response with sensitive fields redacted.
        """
        return redact_secrets(await get_server_context(ctx).clients["network"].get_health())

    @mcp.tool(tags={"network"})
    @tool_handler()
    async def unifi_network_list_events(ctx: Context, limit: int = 100) -> dict[str, Any]:
        """List recent network events and alerts.

        Args:
            limit: Maximum number of events to return (default: 100). Capped
                by ``unifi_max_list_items`` (default 1000).

        Returns:
            The upstream API response with sensitive fields redacted.
        """
        context = get_server_context(ctx)
        max_items = context.config.unifi_max_list_items
        if not isinstance(limit, int) or limit < 1 or limit > max_items:
            raise UniFiBadRequestError(f"limit must be between 1 and {max_items} (got {limit!r})")
        return redact_secrets(await context.clients["network"].list_events(limit=limit))

    @mcp.tool(tags={"network"})
    @tool_handler()
    async def unifi_network_list_devices(ctx: Context) -> dict[str, Any]:
        """List all adopted network devices with full details (APs, switches, gateways).

        Args:
            ctx: FastMCP request context.

        Returns:
            The upstream API response.
        """
        return redact_secrets(await get_server_context(ctx).clients["network"].list_devices())

    @mcp.tool(tags={"network"})
    @tool_handler()
    async def unifi_network_list_devices_basic(ctx: Context) -> dict[str, Any]:
        """List all adopted network devices with basic info only (faster than full list).

        Args:
            ctx: FastMCP request context.

        Returns:
            The upstream API response.
        """
        return redact_secrets(await get_server_context(ctx).clients["network"].list_devices_basic())

    @mcp.tool(tags={"network"})
    @tool_handler()
    async def unifi_network_list_active_clients(ctx: Context) -> dict[str, Any]:
        """List all currently connected network clients.

        Args:
            ctx: FastMCP request context.

        Returns:
            The upstream API response.
        """
        return redact_secrets(await get_server_context(ctx).clients["network"].list_active_clients())

    @mcp.tool(tags={"network"})
    @tool_handler()
    async def unifi_network_list_configured_clients(ctx: Context) -> dict[str, Any]:
        """List all configured (known) clients, including those not currently connected.

        Args:
            ctx: FastMCP request context.

        Returns:
            The upstream API response.
        """
        return redact_secrets(await get_server_context(ctx).clients["network"].list_configured_clients())

    @mcp.tool(tags={"network"})
    @tool_handler()
    async def unifi_network_list_all_clients(ctx: Context) -> dict[str, Any]:
        """List all clients (active and historical) across all time.

        Args:
            ctx: FastMCP request context.

        Returns:
            The upstream API response.
        """
        return redact_secrets(await get_server_context(ctx).clients["network"].list_all_clients())

    @mcp.tool(tags={"network"})
    @tool_handler()
    async def unifi_network_get_dpi_stats(ctx: Context, dpi_type: str = "by_app") -> dict[str, Any]:
        """Get deep packet inspection (DPI) statistics.

        Args:
            dpi_type: Type of DPI stats — "by_app" or "by_cat" (by category).

        Returns:
            The upstream API response with sensitive fields redacted.
        """
        return redact_secrets(await get_server_context(ctx).clients["network"].get_dpi_stats(dpi_type=dpi_type))

    @mcp.tool(tags={"network"})
    @tool_handler()
    async def unifi_network_get_sysinfo(ctx: Context) -> dict[str, Any]:
        """Get controller system information (version, timezone, etc.).

        Args:
            ctx: FastMCP request context.

        Returns:
            The upstream API response with sensitive fields redacted.
        """
        return redact_secrets(await get_server_context(ctx).clients["network"].get_sysinfo())
