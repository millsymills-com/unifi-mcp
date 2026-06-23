"""Network Integration firewall (policy ordering + zones) read and write tools."""

from __future__ import annotations

from typing import Any

from fastmcp import Context, FastMCP

from unifi_mcp.errors import UniFiBadRequestError
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

    # ── Write tools: firewall zones ─────────────────────────────────────

    @mcp.tool(tags={"write", "network_integration"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    @tool_handler(write=True)
    async def unifi_network_create_firewall_zone(ctx: Context, name: str, network_ids: list[str]) -> dict[str, Any]:
        """Create a zone-based firewall zone (Network Integration API).

        ``metadata`` is response-only and must not be supplied. Some
        system-defined zones may reject a rename; that surfaces as a controller
        4xx through the error funnel rather than being pre-validated.

        Args:
            ctx: FastMCP request context.
            name: Zone name.
            network_ids: Network ids assigned to the zone.

        Returns:
            The created zone with sensitive fields redacted.

        Raises:
            ToolError: If write mode is disabled or the controller rejects the body.
        """
        return redact_secrets(
            await get_server_context(ctx).clients["network_integration"].create_firewall_zone(name, network_ids)
        )

    @mcp.tool(tags={"write", "network_integration"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    @tool_handler(write=True)
    async def unifi_network_update_firewall_zone(
        ctx: Context, zone_id: str, name: str, network_ids: list[str]
    ) -> dict[str, Any]:
        """Update a firewall zone (Network Integration API).

        Full-replace: ``network_ids`` overwrites the zone's network set, so an
        incomplete list silently detaches networks. Send the complete set.

        Args:
            ctx: FastMCP request context.
            zone_id: The firewall zone id.
            name: Zone name.
            network_ids: The complete set of network ids for the zone.

        Returns:
            The updated zone with sensitive fields redacted.

        Raises:
            ToolError: If write mode is disabled, ``zone_id`` is malformed, or
                the controller rejects the body.
        """
        validate_id(zone_id, field="zone_id")
        return redact_secrets(
            await get_server_context(ctx)
            .clients["network_integration"]
            .update_firewall_zone(zone_id, name, network_ids)
        )

    @mcp.tool(tags={"write", "network_integration"}, annotations={"readOnlyHint": False, "destructiveHint": True})
    @tool_handler(write=True)
    async def unifi_network_delete_firewall_zone(ctx: Context, zone_id: str, confirm: bool = False) -> dict[str, Any]:
        """Delete a firewall zone by id (Network Integration API).

        Irreversible, and unlinks the zone from any referencing firewall
        policies. Pass ``confirm=True`` to proceed.

        Args:
            ctx: FastMCP request context.
            zone_id: The firewall zone id to delete.
            confirm: Must be ``True`` to perform the deletion.

        Returns:
            The upstream API response (empty on a 200/204 with no body).

        Raises:
            ToolError: If write mode is disabled, ``zone_id`` is malformed, or
                ``confirm`` is not ``True``.
        """
        validate_id(zone_id, field="zone_id")
        if not confirm:
            raise UniFiBadRequestError("delete is irreversible; pass confirm=True")
        return redact_secrets(
            await get_server_context(ctx).clients["network_integration"].delete_firewall_zone(zone_id)
        )
