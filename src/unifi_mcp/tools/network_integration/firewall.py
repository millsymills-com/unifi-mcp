"""Network Integration firewall (policy ordering + zones) read tools."""

from __future__ import annotations

from typing import Any

from fastmcp import Context, FastMCP

from unifi_mcp.tools._common import get_server_context, redact_secrets, tool_handler, validate_id
from unifi_mcp.tools.network_integration._common import bound_pagination


def register_firewall_tools(mcp: FastMCP) -> None:
    """Register the Network Integration firewall tools."""

    @mcp.tool(tags={"network_integration"})
    @tool_handler()
    async def unifi_network_get_firewall_policies_ordering(ctx: Context) -> dict[str, Any]:
        """Get the firewall-policy ordering for the resolved site (Network Integration API).

        Args:
            ctx: FastMCP request context.

        Returns:
            The upstream API response with sensitive fields redacted.
        """
        return redact_secrets(
            await get_server_context(ctx).clients["network_integration"].get_firewall_policies_ordering()
        )

    @mcp.tool(tags={"network_integration"})
    @tool_handler()
    async def unifi_network_list_firewall_zones(ctx: Context, offset: int = 0, limit: int = 200) -> dict[str, Any]:
        """List zone-based firewall zones (Network Integration API).

        Distinct from the legacy firewall groups (``unifi_network_list_firewall_groups``).

        Args:
            ctx: FastMCP request context.
            offset: Page offset (default 0). Bounded by ``unifi_max_list_offset``.
            limit: Page size (default 200). Bounded by ``unifi_max_list_items``.

        Returns:
            The paginated ``{data, offset, limit, count, totalCount}`` envelope
            with sensitive fields redacted.
        """
        context = get_server_context(ctx)
        bound_pagination(context.config, offset=offset, limit=limit)
        return redact_secrets(
            await context.clients["network_integration"].list_firewall_zones(offset=offset, limit=limit)
        )

    @mcp.tool(tags={"network_integration"})
    @tool_handler()
    async def unifi_network_get_firewall_zone(ctx: Context, zone_id: str) -> dict[str, Any]:
        """Get a single firewall zone by id (Network Integration API).

        Args:
            ctx: FastMCP request context.
            zone_id: The firewall zone id.

        Returns:
            The upstream API response with sensitive fields redacted.

        Raises:
            ToolError: If ``zone_id`` is malformed.
        """
        validate_id(zone_id, field="zone_id")
        return redact_secrets(await get_server_context(ctx).clients["network_integration"].get_firewall_zone(zone_id))
