"""Network Integration switching (LAGs, MC-LAG domains, switch stacks) read tools."""

from __future__ import annotations

from typing import Any

from fastmcp import Context, FastMCP

from unifi_mcp.tools._common import get_server_context, redact_secrets, tool_handler, validate_id
from unifi_mcp.tools.network_integration._common import bound_pagination


def register_switching_tools(mcp: FastMCP) -> None:
    """Register the Network Integration switching tools."""

    @mcp.tool(tags={"network_integration"})
    @tool_handler()
    async def unifi_network_list_lags(ctx: Context, offset: int = 0, limit: int = 200) -> dict[str, Any]:
        """List link-aggregation groups (Network Integration API).

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
        return redact_secrets(await context.clients["network_integration"].list_lags(offset=offset, limit=limit))

    @mcp.tool(tags={"network_integration"})
    @tool_handler()
    async def unifi_network_get_lag(ctx: Context, lag_id: str) -> dict[str, Any]:
        """Get a single LAG by id (Network Integration API).

        Args:
            ctx: FastMCP request context.
            lag_id: The LAG id.

        Returns:
            The upstream API response with sensitive fields redacted.

        Raises:
            ToolError: If ``lag_id`` is malformed.
        """
        validate_id(lag_id, field="lag_id")
        return redact_secrets(await get_server_context(ctx).clients["network_integration"].get_lag(lag_id))

    @mcp.tool(tags={"network_integration"})
    @tool_handler()
    async def unifi_network_list_mc_lag_domains(ctx: Context, offset: int = 0, limit: int = 200) -> dict[str, Any]:
        """List MC-LAG domains (Network Integration API).

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
            await context.clients["network_integration"].list_mc_lag_domains(offset=offset, limit=limit)
        )

    @mcp.tool(tags={"network_integration"})
    @tool_handler()
    async def unifi_network_get_mc_lag_domain(ctx: Context, domain_id: str) -> dict[str, Any]:
        """Get a single MC-LAG domain by id (Network Integration API).

        Args:
            ctx: FastMCP request context.
            domain_id: The MC-LAG domain id.

        Returns:
            The upstream API response with sensitive fields redacted.

        Raises:
            ToolError: If ``domain_id`` is malformed.
        """
        validate_id(domain_id, field="domain_id")
        return redact_secrets(await get_server_context(ctx).clients["network_integration"].get_mc_lag_domain(domain_id))

    @mcp.tool(tags={"network_integration"})
    @tool_handler()
    async def unifi_network_list_switch_stacks(ctx: Context, offset: int = 0, limit: int = 200) -> dict[str, Any]:
        """List switch stacks (Network Integration API).

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
            await context.clients["network_integration"].list_switch_stacks(offset=offset, limit=limit)
        )

    @mcp.tool(tags={"network_integration"})
    @tool_handler()
    async def unifi_network_get_switch_stack(ctx: Context, stack_id: str) -> dict[str, Any]:
        """Get a single switch stack by id (Network Integration API).

        Args:
            ctx: FastMCP request context.
            stack_id: The switch stack id.

        Returns:
            The upstream API response with sensitive fields redacted.

        Raises:
            ToolError: If ``stack_id`` is malformed.
        """
        validate_id(stack_id, field="stack_id")
        return redact_secrets(await get_server_context(ctx).clients["network_integration"].get_switch_stack(stack_id))
