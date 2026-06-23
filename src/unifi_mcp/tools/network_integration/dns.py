"""Network Integration DNS-policy read tools."""

from __future__ import annotations

from typing import Any

from fastmcp import Context, FastMCP

from unifi_mcp.tools._common import get_server_context, redact_secrets, tool_handler, validate_id
from unifi_mcp.tools.network_integration._common import bound_pagination


def register_dns_tools(mcp: FastMCP) -> None:
    """Register the Network Integration DNS tools."""

    @mcp.tool(tags={"network_integration"})
    @tool_handler()
    async def unifi_network_list_dns_policies(ctx: Context, offset: int = 0, limit: int = 200) -> dict[str, Any]:
        """List DNS policies (Network Integration API).

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
            await context.clients["network_integration"].list_dns_policies(offset=offset, limit=limit)
        )

    @mcp.tool(tags={"network_integration"})
    @tool_handler()
    async def unifi_network_get_dns_policy(ctx: Context, dns_policy_id: str) -> dict[str, Any]:
        """Get a single DNS policy by id (Network Integration API).

        Args:
            ctx: FastMCP request context.
            dns_policy_id: The DNS policy id.

        Returns:
            The upstream API response with sensitive fields redacted.

        Raises:
            ToolError: If ``dns_policy_id`` is malformed.
        """
        validate_id(dns_policy_id, field="dns_policy_id")
        return redact_secrets(
            await get_server_context(ctx).clients["network_integration"].get_dns_policy(dns_policy_id)
        )
