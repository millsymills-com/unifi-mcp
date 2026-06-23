"""Network Integration traffic-matching-list read tools."""

from __future__ import annotations

from typing import Any

from fastmcp import Context, FastMCP

from unifi_mcp.tools._common import get_server_context, redact_secrets, tool_handler, validate_id
from unifi_mcp.tools.network_integration._common import bound_pagination


def register_traffic_tools(mcp: FastMCP) -> None:
    """Register the Network Integration traffic-matching-list tools."""

    @mcp.tool(tags={"network_integration"})
    @tool_handler()
    async def unifi_network_list_traffic_matching_lists(
        ctx: Context, offset: int = 0, limit: int = 200
    ) -> dict[str, Any]:
        """List traffic-matching lists (Network Integration API).

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
            await context.clients["network_integration"].list_traffic_matching_lists(offset=offset, limit=limit)
        )

    @mcp.tool(tags={"network_integration"})
    @tool_handler()
    async def unifi_network_get_traffic_matching_list(ctx: Context, list_id: str) -> dict[str, Any]:
        """Get a single traffic-matching list by id (Network Integration API).

        Args:
            ctx: FastMCP request context.
            list_id: The traffic-matching list id.

        Returns:
            The upstream API response with sensitive fields redacted.

        Raises:
            ToolError: If ``list_id`` is malformed.
        """
        validate_id(list_id, field="list_id")
        return redact_secrets(
            await get_server_context(ctx).clients["network_integration"].get_traffic_matching_list(list_id)
        )
