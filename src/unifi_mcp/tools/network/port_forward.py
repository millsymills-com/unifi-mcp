"""Network port forwarding tools (2 read + 3 write)."""

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


def register_port_forward_tools(mcp: FastMCP) -> None:
    """Register port forward tools."""

    @mcp.tool(tags={"network"})
    @tool_handler()
    async def unifi_network_list_port_forwards(ctx: Context) -> dict[str, Any]:
        """List all port forwarding rules.

        Args:
            ctx: FastMCP request context.

        Returns:
            The upstream API response with sensitive fields redacted.
        """
        return redact_secrets(await get_server_context(ctx).clients["network"].list_port_forwards())

    @mcp.tool(tags={"network"})
    @tool_handler()
    async def unifi_network_get_port_forward(ctx: Context, port_forward_id: str) -> dict[str, Any]:
        """Get a specific port forwarding rule by ID.

        Args:
            port_forward_id: The port forward rule ID.

        Returns:
            The upstream API response with sensitive fields redacted.
        """
        validate_id(port_forward_id, field="port_forward_id")
        return redact_secrets(await get_server_context(ctx).clients["network"].get_port_forward(port_forward_id))

    @mcp.tool(tags={"write", "network"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    @tool_handler(write=True)
    async def unifi_network_create_port_forward(
        ctx: Context,
        name: str,
        dst_port: str,
        fwd: str,
        fwd_port: str,
        proto: str = "tcp_udp",
        enabled: bool = True,
    ) -> dict[str, Any]:
        """Create a new port forwarding rule.

        Args:
            name: Rule name.
            dst_port: Destination port (external port).
            fwd: Forward-to IP address (internal host).
            fwd_port: Forward-to port (internal port).
            proto: Protocol — "tcp", "udp", or "tcp_udp".
            enabled: Whether the rule is enabled.

        Returns:
            The upstream API response.
        """
        data: JsonObject = {
            "name": name,
            "dst_port": dst_port,
            "fwd": fwd,
            "fwd_port": fwd_port,
            "proto": proto,
            "enabled": enabled,
        }
        return redact_secrets(await get_server_context(ctx).clients["network"].create_port_forward(data))

    @mcp.tool(tags={"write", "network"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    @tool_handler(write=True)
    async def unifi_network_update_port_forward(ctx: Context, port_forward_id: str, data: JsonObject) -> dict[str, Any]:
        """Update an existing port forwarding rule. Pass only fields to change.

        Args:
            port_forward_id: The port forward rule ID.
            data: Fields to update (e.g., {"enabled": false, "fwd_port": "8080"}).

        Returns:
            The upstream API response.
        """
        validate_id(port_forward_id, field="port_forward_id")
        reject_dangerous_keys(data, tool_name="unifi_network_update_port_forward")
        return redact_secrets(
            await get_server_context(ctx).clients["network"].update_port_forward(port_forward_id, data)
        )

    @mcp.tool(tags={"write", "network"}, annotations={"readOnlyHint": False, "destructiveHint": True})
    @tool_handler(write=True)
    async def unifi_network_delete_port_forward(
        ctx: Context, port_forward_id: str, confirm: bool = False
    ) -> dict[str, Any]:
        """Delete a port forwarding rule.

        Irreversible. Pass ``confirm=True`` to proceed.

        Args:
            port_forward_id: The port forward rule ID to delete.
            confirm: Must be ``True`` to perform the deletion.

        Returns:
            The upstream API response.

        Raises:
            ToolError: If write mode is disabled, ``port_forward_id`` is malformed,
                or ``confirm`` is not ``True``.
        """
        validate_id(port_forward_id, field="port_forward_id")
        if not confirm:
            raise UniFiBadRequestError("deleting the port-forward rule is irreversible; pass confirm=True")
        return redact_secrets(await get_server_context(ctx).clients["network"].delete_port_forward(port_forward_id))
