"""Network static routing tools (2 read + 3 write)."""

from __future__ import annotations

from typing import Any

from fastmcp import Context, FastMCP

from unifi_mcp.tools._common import (
    JsonObject,
    get_server_context,
    redact_secrets,
    reject_dangerous_keys,
    tool_handler,
    validate_id,
)


def register_routing_tools(mcp: FastMCP) -> None:
    """Register routing tools."""

    @mcp.tool(tags={"network"})
    @tool_handler()
    async def unifi_network_list_routes(ctx: Context) -> dict[str, Any]:
        """List all static routes.

        Args:
            ctx: FastMCP request context.

        Returns:
            The upstream API response with sensitive fields redacted.
        """
        return redact_secrets(await get_server_context(ctx).clients["network"].list_routes())

    @mcp.tool(tags={"network"})
    @tool_handler()
    async def unifi_network_get_route(ctx: Context, route_id: str) -> dict[str, Any]:
        """Get a specific static route by ID.

        Args:
            route_id: The route ID.

        Returns:
            The upstream API response with sensitive fields redacted.
        """
        validate_id(route_id, field="route_id")
        return redact_secrets(await get_server_context(ctx).clients["network"].get_route(route_id))

    @mcp.tool(tags={"write", "network"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    @tool_handler(write=True)
    async def unifi_network_create_route(
        ctx: Context,
        name: str,
        network: str,
        route_type: str = "nexthop-route",
        gateway_ip: str | None = None,
        interface: str | None = None,
        enabled: bool = True,
    ) -> dict[str, Any]:
        """Create a new static route.

        Returns:
            The upstream API response.

        Args:
            name: Route name.
            network: Destination CIDR (e.g. "10.0.0.0/24").
            route_type: "nexthop-route" or "interface-route".
            gateway_ip: Next-hop gateway IP (for nexthop-route).
            interface: Interface name (for interface-route).
            enabled: Whether the route is enabled.
        """
        data: JsonObject = {
            "name": name,
            "type": "static-route",
            "enabled": enabled,
            "static-route_type": route_type,
            "static-route_network": network,
            "static-route_distance": 1,
        }
        if gateway_ip is not None:
            data["static-route_nexthop"] = gateway_ip
        if interface is not None:
            data["static-route_interface"] = interface
        return await get_server_context(ctx).clients["network"].create_route(data)

    @mcp.tool(tags={"write", "network"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    @tool_handler(write=True)
    async def unifi_network_update_route(ctx: Context, route_id: str, data: JsonObject) -> dict[str, Any]:
        """Update an existing static route. Pass only fields to change.

        Args:
            route_id: The route ID.
            data: Fields to update using controller's prefixed key shape
                (e.g., {"enabled": false, "static-route_nexthop": "10.0.0.1"}).
                Flat keys like ``gateway_ip`` / ``network`` are rejected with
                api.err.InvalidPayload.

        Returns:
            The upstream API response.
        """
        validate_id(route_id, field="route_id")
        reject_dangerous_keys(data, tool_name="unifi_network_update_route")
        return await get_server_context(ctx).clients["network"].update_route(route_id, data)

    @mcp.tool(tags={"write", "network"}, annotations={"readOnlyHint": False, "destructiveHint": True})
    @tool_handler(write=True)
    async def unifi_network_delete_route(ctx: Context, route_id: str) -> dict[str, Any]:
        """Delete a static route.

        Args:
            route_id: The route ID to delete.

        Returns:
            The upstream API response.
        """
        validate_id(route_id, field="route_id")
        return await get_server_context(ctx).clients["network"].delete_route(route_id)
