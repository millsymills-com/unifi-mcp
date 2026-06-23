"""Network Integration hotspot-voucher read tools."""

from __future__ import annotations

from typing import Any

from fastmcp import Context, FastMCP

from unifi_mcp.tools._common import get_server_context, redact_secrets, tool_handler, validate_id
from unifi_mcp.tools.network_integration._common import bound_pagination


def register_hotspot_tools(mcp: FastMCP) -> None:
    """Register the Network Integration hotspot-voucher tools."""

    @mcp.tool(tags={"network_integration"})
    @tool_handler()
    async def unifi_network_list_vouchers(ctx: Context, offset: int = 0, limit: int = 200) -> dict[str, Any]:
        """List guest-hotspot vouchers (Network Integration API).

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
        return redact_secrets(await context.clients["network_integration"].list_vouchers(offset=offset, limit=limit))

    @mcp.tool(tags={"network_integration"})
    @tool_handler()
    async def unifi_network_get_voucher(ctx: Context, voucher_id: str) -> dict[str, Any]:
        """Get a single hotspot voucher by id (Network Integration API).

        Args:
            ctx: FastMCP request context.
            voucher_id: The voucher id.

        Returns:
            The upstream API response with sensitive fields redacted.

        Raises:
            ToolError: If ``voucher_id`` is malformed.
        """
        validate_id(voucher_id, field="voucher_id")
        return redact_secrets(await get_server_context(ctx).clients["network_integration"].get_voucher(voucher_id))
