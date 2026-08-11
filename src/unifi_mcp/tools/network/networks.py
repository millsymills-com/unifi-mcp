"""Network configuration tools (2 read + 3 write)."""

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


def register_network_config_tools(mcp: FastMCP) -> None:
    """Register network config tools."""

    @mcp.tool(tags={"network"})
    @tool_handler()
    async def unifi_network_list_networks(ctx: Context) -> dict[str, Any]:
        """List all network (VLAN/subnet) configurations.

        Args:
            ctx: FastMCP request context.

        Returns:
            The upstream API response.
        """
        return redact_secrets(await get_server_context(ctx).clients["network"].list_networks())

    @mcp.tool(tags={"network"})
    @tool_handler()
    async def unifi_network_get_network(ctx: Context, network_id: str) -> dict[str, Any]:
        """Get a specific network configuration by ID.

        Portal credentials and other secret keys are redacted before the
        response leaves this tool — see ``unifi_mcp._redaction`` (#146).

        Args:
            network_id: The network configuration ID.

        Returns:
            The upstream API response with sensitive fields redacted.
        """
        validate_id(network_id, field="network_id")
        return redact_secrets(await get_server_context(ctx).clients["network"].get_network(network_id))

    @mcp.tool(tags={"write", "network"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    @tool_handler(write=True)
    async def unifi_network_create_network(
        ctx: Context,
        *,
        name: str,
        purpose: str = "corporate",
        subnet: str | None = None,
        vlan: int | None = None,
        dhcpd_enabled: bool = True,
    ) -> dict[str, Any]:
        """Create a new network (VLAN/subnet).

        Args:
            name: Network name.
            purpose: Purpose — "corporate", "guest", "wan", "vlan-only".
            subnet: Subnet in CIDR notation (e.g., "192.168.2.0/24").
            vlan: VLAN ID (optional).
            dhcpd_enabled: Whether DHCP server is enabled.

        Returns:
            The upstream API response.
        """
        data: JsonObject = {"name": name, "purpose": purpose, "dhcpd_enabled": dhcpd_enabled}
        if subnet is not None:
            data["subnet"] = subnet
        if vlan is not None:
            data["vlan"] = vlan
        return redact_secrets(await get_server_context(ctx).clients["network"].create_network(data))

    @mcp.tool(tags={"write", "network"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    @tool_handler(write=True)
    async def unifi_network_update_network(ctx: Context, network_id: str, data: JsonObject) -> dict[str, Any]:
        """Update an existing network configuration. Pass only fields to change.

        Args:
            network_id: The network configuration ID.
            data: Fields to update (e.g., {"name": "new-name", "vlan": 100}).

        Returns:
            The upstream API response.
        """
        validate_id(network_id, field="network_id")
        reject_dangerous_keys(data, tool_name="unifi_network_update_network")
        return redact_secrets(await get_server_context(ctx).clients["network"].update_network(network_id, data))

    @mcp.tool(tags={"write", "network"}, annotations={"readOnlyHint": False, "destructiveHint": True})
    @tool_handler(write=True)
    async def unifi_network_delete_network(ctx: Context, network_id: str, confirm: bool = False) -> dict[str, Any]:
        """Delete a network configuration.

        Irreversible. Pass ``confirm=True`` to proceed.

        Args:
            network_id: The network configuration ID to delete.
            confirm: Must be ``True`` to perform the deletion.

        Returns:
            The upstream API response.

        Raises:
            ToolError: If write mode is disabled, ``network_id`` is malformed, or
                ``confirm`` is not ``True``.
        """
        validate_id(network_id, field="network_id")
        if not confirm:
            raise UniFiBadRequestError("deleting the network is irreversible; pass confirm=True")
        return redact_secrets(await get_server_context(ctx).clients["network"].delete_network(network_id))
