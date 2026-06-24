"""Network Integration hotspot-voucher read and write tools."""

from __future__ import annotations

from typing import Any

from fastmcp import Context, FastMCP

from unifi_mcp.errors import UniFiBadRequestError
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

    # ── Write tools ─────────────────────────────────────────────────────

    @mcp.tool(tags={"write", "network_integration"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    @tool_handler(write=True)
    async def unifi_network_create_vouchers(
        ctx: Context,
        *,
        name: str,
        time_limit_minutes: int,
        count: int = 1,
        authorized_guest_limit: int | None = None,
        data_usage_limit_mbytes: int | None = None,
        rx_rate_limit_kbps: int | None = None,
        tx_rate_limit_kbps: int | None = None,
    ) -> dict[str, Any]:
        """Generate guest-hotspot vouchers (Network Integration API).

        Args:
            ctx: FastMCP request context.
            name: Voucher note/name.
            time_limit_minutes: Validity window per voucher (1-1000000).
            count: Number of vouchers to generate (1-1000).
            authorized_guest_limit: Max simultaneous authorized guests per voucher.
            data_usage_limit_mbytes: Per-voucher data cap in MB (1-1048576).
            rx_rate_limit_kbps: Download rate cap in Kbps (2-100000).
            tx_rate_limit_kbps: Upload rate cap in Kbps (2-100000).

        Returns:
            The created vouchers with sensitive fields redacted.

        Raises:
            ToolError: If write mode is disabled or the controller rejects the body.
        """
        return redact_secrets(
            await get_server_context(ctx)
            .clients["network_integration"]
            .create_vouchers(
                name=name,
                time_limit_minutes=time_limit_minutes,
                count=count,
                authorized_guest_limit=authorized_guest_limit,
                data_usage_limit_mbytes=data_usage_limit_mbytes,
                rx_rate_limit_kbps=rx_rate_limit_kbps,
                tx_rate_limit_kbps=tx_rate_limit_kbps,
            )
        )

    @mcp.tool(tags={"write", "network_integration"}, annotations={"readOnlyHint": False, "destructiveHint": True})
    @tool_handler(write=True)
    async def unifi_network_delete_vouchers(ctx: Context, voucher_filter: str, confirm: bool = False) -> dict[str, Any]:
        """Delete vouchers matching a filter (Network Integration API) — BULK.

        Destructive and bulk: a broad ``voucher_filter`` mass-deletes vouchers.
        The filter is forwarded verbatim as the API's ``filter`` query param and
        treated as an opaque expression (only non-blank is enforced here). Pass
        ``confirm=True`` to proceed.

        Args:
            ctx: FastMCP request context.
            voucher_filter: Non-blank filter expression selecting vouchers to delete.
            confirm: Must be ``True`` to perform the deletion.

        Returns:
            The API's deletion-count response, with sensitive fields redacted.

        Raises:
            ToolError: If write mode is disabled, ``voucher_filter`` is blank, or
                ``confirm`` is not ``True``.
        """
        if not voucher_filter.strip():
            raise UniFiBadRequestError("voucher_filter must be a non-blank expression")
        if not confirm:
            raise UniFiBadRequestError("bulk delete is irreversible; pass confirm=True")
        return redact_secrets(
            await get_server_context(ctx).clients["network_integration"].delete_vouchers(voucher_filter=voucher_filter)
        )

    @mcp.tool(tags={"write", "network_integration"}, annotations={"readOnlyHint": False, "destructiveHint": True})
    @tool_handler(write=True)
    async def unifi_network_delete_voucher(ctx: Context, voucher_id: str, confirm: bool = False) -> dict[str, Any]:
        """Delete a single hotspot voucher by id (Network Integration API).

        Irreversible. Pass ``confirm=True`` to proceed.

        Args:
            ctx: FastMCP request context.
            voucher_id: The voucher id to delete.
            confirm: Must be ``True`` to perform the deletion.

        Returns:
            The upstream API response (empty on a 200/204 with no body).

        Raises:
            ToolError: If write mode is disabled, ``voucher_id`` is malformed, or
                ``confirm`` is not ``True``.
        """
        validate_id(voucher_id, field="voucher_id")
        if not confirm:
            raise UniFiBadRequestError("delete is irreversible; pass confirm=True")
        return redact_secrets(await get_server_context(ctx).clients["network_integration"].delete_voucher(voucher_id))
