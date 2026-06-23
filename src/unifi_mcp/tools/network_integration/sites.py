"""Network Integration site-listing read tool."""

from __future__ import annotations

from typing import Any

from fastmcp import Context, FastMCP

from unifi_mcp.tools._common import get_server_context, redact_secrets, tool_handler
from unifi_mcp.tools.network_integration._common import bound_pagination


def register_sites_tools(mcp: FastMCP) -> None:
    """Register the Network Integration sites tool."""

    @mcp.tool(tags={"network_integration"})
    @tool_handler()
    async def unifi_network_list_sites(ctx: Context, offset: int = 0, limit: int = 200) -> dict[str, Any]:
        """List local sites on the controller (Network Integration API).

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
        return redact_secrets(await context.clients["network_integration"].list_sites(offset=offset, limit=limit))
