"""Network Integration ACL-rule read and write tools."""

from __future__ import annotations

from typing import Any

from fastmcp import Context, FastMCP

from unifi_mcp.errors import UniFiBadRequestError
from unifi_mcp.tools._common import (
    JsonObject,
    get_server_context,
    redact_secrets,
    reject_dangerous_keys,
    tool_handler,
    validate_id,
)
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

    # ── Write tools ─────────────────────────────────────────────────────

    @mcp.tool(tags={"write", "network_integration"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    @tool_handler(write=True)
    async def unifi_network_create_acl_rule(ctx: Context, data: JsonObject) -> dict[str, Any]:
        """Create an L2/L3 ACL rule (Network Integration API).

        The body is a discriminated union on ``type`` (``IPV4`` or ``MAC``).
        Required keys regardless of variant: ``type``, ``enabled``, ``name``
        (non-empty), ``action`` (``ALLOW``|``BLOCK``). IPV4 rules use IP
        source/destination filters and optional ``protocolFilter``
        (``TCP``/``UDP``); MAC rules use MAC filters and require
        ``networkIdFilter``. Do not set the deprecated ``index`` field — use
        ``unifi_network_reorder_acl_rules`` for priority.

        Args:
            ctx: FastMCP request context.
            data: Full ACL-rule body matching the controller's ACL-rule schema.

        Returns:
            The created rule (server-assigned ``id``), with sensitive fields redacted.

        Raises:
            ToolError: If write mode is disabled, ``data`` contains a denylisted
                key, or the controller rejects the body.
        """
        reject_dangerous_keys(data, tool_name="unifi_network_create_acl_rule")
        return redact_secrets(await get_server_context(ctx).clients["network_integration"].create_acl_rule(data))

    @mcp.tool(tags={"write", "network_integration"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    @tool_handler(write=True)
    async def unifi_network_update_acl_rule(ctx: Context, acl_rule_id: str, data: JsonObject) -> dict[str, Any]:
        """Update an existing ACL rule (Network Integration API).

        Full-object PUT: the body schema is identical to create, so send every
        field for the rule, not just the changed keys. Only user-defined rules
        are editable.

        Args:
            ctx: FastMCP request context.
            acl_rule_id: The ACL rule id.
            data: Full ACL-rule body (same schema as create).

        Returns:
            The updated rule with sensitive fields redacted.

        Raises:
            ToolError: If write mode is disabled, ``acl_rule_id`` is malformed,
                ``data`` contains a denylisted key, or the controller rejects it.
        """
        validate_id(acl_rule_id, field="acl_rule_id")
        reject_dangerous_keys(data, tool_name="unifi_network_update_acl_rule")
        return redact_secrets(
            await get_server_context(ctx).clients["network_integration"].update_acl_rule(acl_rule_id, data)
        )

    @mcp.tool(tags={"write", "network_integration"}, annotations={"readOnlyHint": False, "destructiveHint": True})
    @tool_handler(write=True)
    async def unifi_network_delete_acl_rule(ctx: Context, acl_rule_id: str, confirm: bool = False) -> dict[str, Any]:
        """Delete an ACL rule by id (Network Integration API).

        Irreversible. Pass ``confirm=True`` to proceed.

        Args:
            ctx: FastMCP request context.
            acl_rule_id: The ACL rule id to delete.
            confirm: Must be ``True`` to perform the deletion.

        Returns:
            The upstream API response (empty on a 200/204 with no body).

        Raises:
            ToolError: If write mode is disabled, ``acl_rule_id`` is malformed,
                or ``confirm`` is not ``True``.
        """
        validate_id(acl_rule_id, field="acl_rule_id")
        if not confirm:
            raise UniFiBadRequestError("delete is irreversible; pass confirm=True")
        return redact_secrets(await get_server_context(ctx).clients["network_integration"].delete_acl_rule(acl_rule_id))

    @mcp.tool(tags={"write", "network_integration"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    @tool_handler(write=True)
    async def unifi_network_reorder_acl_rules(ctx: Context, ordered_acl_rule_ids: list[str]) -> dict[str, Any]:
        """Replace the site-wide ACL-rule ordering (Network Integration API).

        Full-replacement: pass the COMPLETE current id set in the desired order.
        Any omitted rule loses its enforcement position. Pairs with the read
        tool ``unifi_network_get_acl_rules_ordering``.

        Args:
            ctx: FastMCP request context.
            ordered_acl_rule_ids: Every ACL rule id, in the new priority order.

        Returns:
            The upstream API response with sensitive fields redacted.

        Raises:
            ToolError: If write mode is disabled, the id list is empty, or any id is malformed.
        """
        if not ordered_acl_rule_ids:
            raise UniFiBadRequestError("ordered_acl_rule_ids must be non-empty; an empty list wipes all ACL ordering")
        for rule_id in ordered_acl_rule_ids:
            validate_id(rule_id, field="ordered_acl_rule_ids")
        return redact_secrets(
            await get_server_context(ctx).clients["network_integration"].update_acl_rules_ordering(ordered_acl_rule_ids)
        )
