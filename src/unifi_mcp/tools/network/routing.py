"""Network static routing tools (2 read + 3 write)."""

from __future__ import annotations

from typing import Any

from fastmcp import Context, FastMCP

from unifi_mcp.errors import UniFiBadRequestError
from unifi_mcp.tools._common import (
    JsonObject,
    build_named_arg_body,
    get_server_context,
    redact_secrets,
    reject_dangerous_keys,
    tool_handler,
    validate_id,
)

_ROUTE_FIELD_PATHS: dict[str, tuple[str, ...]] = {
    "name": ("name",),
    "network": ("static-route_network",),
    "route_type": ("static-route_type",),
    "gateway_ip": ("static-route_nexthop",),
    "interface": ("static-route_interface",),
    "enabled": ("enabled",),
}


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
        *,
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
        return redact_secrets(await get_server_context(ctx).clients["network"].create_route(data))

    @mcp.tool(tags={"write", "network"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    @tool_handler(write=True)
    async def unifi_network_update_route(
        ctx: Context,
        route_id: str,
        *,
        name: str | None = None,
        network: str | None = None,
        route_type: str | None = None,
        gateway_ip: str | None = None,
        interface: str | None = None,
        enabled: bool | None = None,
    ) -> dict[str, Any]:
        """Update an existing static route. Pass only fields to change.

        Args:
            route_id: The route ID.
            name: Route name.
            network: Destination CIDR, mapped to ``static-route_network``.
            route_type: Route type, mapped to ``static-route_type``.
            gateway_ip: Next-hop IP, mapped to ``static-route_nexthop``.
            interface: Interface name, mapped to ``static-route_interface``.
            enabled: Whether the route is enabled. False is an explicit update.

        At least one named field is required. Omitted or None fields are left
        unchanged; raw ``data`` and controller-prefixed arguments are unsupported.

        Returns:
            The upstream API response.
        """
        validate_id(route_id, field="route_id")
        body = build_named_arg_body(
            tool_name="unifi_network_update_route",
            field_paths=_ROUTE_FIELD_PATHS,
            named_values={
                "name": name,
                "network": network,
                "route_type": route_type,
                "gateway_ip": gateway_ip,
                "interface": interface,
                "enabled": enabled,
            },
            data=None,
        )
        reject_dangerous_keys(body, tool_name="unifi_network_update_route")
        return redact_secrets(await get_server_context(ctx).clients["network"].update_route(route_id, body))

    @mcp.tool(tags={"write", "network"}, annotations={"readOnlyHint": False, "destructiveHint": True})
    @tool_handler(write=True)
    async def unifi_network_delete_route(ctx: Context, route_id: str, confirm: bool = False) -> dict[str, Any]:
        """Delete a static route.

        Irreversible. Pass ``confirm=True`` to proceed.

        Args:
            route_id: The route ID to delete.
            confirm: Must be ``True`` to perform the deletion.

        Returns:
            The upstream API response.

        Raises:
            ToolError: If write mode is disabled, ``route_id`` is malformed, or
                ``confirm`` is not ``True``.
        """
        validate_id(route_id, field="route_id")
        if not confirm:
            raise UniFiBadRequestError("deleting the route is irreversible; pass confirm=True")
        return redact_secrets(await get_server_context(ctx).clients["network"].delete_route(route_id))
