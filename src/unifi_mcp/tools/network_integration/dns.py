"""Network Integration DNS-policy read and write tools."""

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

    # ── Write tools ─────────────────────────────────────────────────────

    @mcp.tool(tags={"write", "network_integration"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    @tool_handler(write=True)
    async def unifi_network_create_dns_policy(ctx: Context, data: JsonObject) -> dict[str, Any]:
        """Create a DNS policy (Network Integration API).

        The body is a discriminated union on ``type``
        (``A_RECORD``/``AAAA_RECORD``/``CNAME_RECORD``/``MX_RECORD``/
        ``TXT_RECORD``/``SRV_RECORD``/``FORWARD_DOMAIN``); ``type`` and
        ``enabled`` are always required, and per-type required fields differ.
        ``ttlSeconds`` applies only to A/AAAA/CNAME (CNAME max 604800; A/AAAA
        max 86400); MX/TXT/SRV/FORWARD_DOMAIN take no ``ttlSeconds``.

        Args:
            ctx: FastMCP request context.
            data: Full DNS-policy body for the chosen ``type``.

        Returns:
            The created policy (server-assigned ``id``), with sensitive fields redacted.

        Raises:
            ToolError: If write mode is disabled, ``data`` contains a denylisted
                key, or the controller rejects the body.
        """
        reject_dangerous_keys(data, tool_name="unifi_network_create_dns_policy")
        return redact_secrets(await get_server_context(ctx).clients["network_integration"].create_dns_policy(data))

    @mcp.tool(tags={"write", "network_integration"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    @tool_handler(write=True)
    async def unifi_network_update_dns_policy(ctx: Context, dns_policy_id: str, data: JsonObject) -> dict[str, Any]:
        """Update an existing DNS policy (Network Integration API).

        Full-object PUT: send every required field for the policy's ``type``,
        not just the changed keys.

        Args:
            ctx: FastMCP request context.
            dns_policy_id: The DNS policy id.
            data: Full DNS-policy body (same schema as create).

        Returns:
            The updated policy with sensitive fields redacted.

        Raises:
            ToolError: If write mode is disabled, ``dns_policy_id`` is malformed,
                ``data`` contains a denylisted key, or the controller rejects it.
        """
        validate_id(dns_policy_id, field="dns_policy_id")
        reject_dangerous_keys(data, tool_name="unifi_network_update_dns_policy")
        return redact_secrets(
            await get_server_context(ctx).clients["network_integration"].update_dns_policy(dns_policy_id, data)
        )

    @mcp.tool(tags={"write", "network_integration"}, annotations={"readOnlyHint": False, "destructiveHint": True})
    @tool_handler(write=True)
    async def unifi_network_delete_dns_policy(
        ctx: Context, dns_policy_id: str, confirm: bool = False
    ) -> dict[str, Any]:
        """Delete a DNS policy by id (Network Integration API).

        Irreversible. Pass ``confirm=True`` to proceed.

        Args:
            ctx: FastMCP request context.
            dns_policy_id: The DNS policy id to delete.
            confirm: Must be ``True`` to perform the deletion.

        Returns:
            The upstream API response (empty on a 200/204 with no body).

        Raises:
            ToolError: If write mode is disabled, ``dns_policy_id`` is malformed,
                or ``confirm`` is not ``True``.
        """
        validate_id(dns_policy_id, field="dns_policy_id")
        if not confirm:
            raise UniFiBadRequestError("delete is irreversible; pass confirm=True")
        return redact_secrets(
            await get_server_context(ctx).clients["network_integration"].delete_dns_policy(dns_policy_id)
        )
