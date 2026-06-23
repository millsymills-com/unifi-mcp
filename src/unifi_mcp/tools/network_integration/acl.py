"""Network Integration ACL-rule read tools."""

from __future__ import annotations

from typing import Any

from fastmcp import Context, FastMCP

from unifi_mcp.tools._common import get_server_context, redact_secrets, tool_handler, validate_id
from unifi_mcp.tools.network_integration._common import bound_pagination


def register_acl_tools(mcp: FastMCP) -> None:
    """Register the Network Integration ACL tools."""

    @mcp.tool(tags={"network_integration"})
    @tool_handler()
    async def unifi_network_list_acl_rules(ctx: Context, offset: int = 0, limit: int = 200) -> dict[str, Any]:
        """List L2/L3 ACL rules (Network Integration API).

        Distinct from the legacy firewall rules (``unifi_network_list_firewall_rules``).

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
        return redact_secrets(await context.clients["network_integration"].list_acl_rules(offset=offset, limit=limit))

    @mcp.tool(tags={"network_integration"})
    @tool_handler()
    async def unifi_network_get_acl_rules_ordering(ctx: Context) -> dict[str, Any]:
        """Get the ACL-rule ordering for the resolved site (Network Integration API).

        Args:
            ctx: FastMCP request context.

        Returns:
            The upstream API response with sensitive fields redacted.
        """
        return redact_secrets(await get_server_context(ctx).clients["network_integration"].get_acl_rules_ordering())

    @mcp.tool(tags={"network_integration"})
    @tool_handler()
    async def unifi_network_get_acl_rule(ctx: Context, acl_rule_id: str) -> dict[str, Any]:
        """Get a single ACL rule by id (Network Integration API).

        Args:
            ctx: FastMCP request context.
            acl_rule_id: The ACL rule id.

        Returns:
            The upstream API response with sensitive fields redacted.

        Raises:
            ToolError: If ``acl_rule_id`` is malformed.
        """
        validate_id(acl_rule_id, field="acl_rule_id")
        return redact_secrets(await get_server_context(ctx).clients["network_integration"].get_acl_rule(acl_rule_id))
