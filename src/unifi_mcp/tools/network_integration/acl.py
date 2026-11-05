"""Network Integration ACL-rule read and write tools."""

from __future__ import annotations

from typing import Annotated, Any

from fastmcp import Context, FastMCP
from pydantic import Field

from unifi_mcp.errors import UniFiBadRequestError
from unifi_mcp.tools._common import (
    get_server_context,
    redact_secrets,
    tool_handler,
    validate_id,
)
from unifi_mcp.tools.network_integration._acl_rule import AclAction, AclProtocol, AclRuleType, build_acl_rule_body
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
    async def unifi_network_create_acl_rule(
        ctx: Context,
        *,
        rule_type: Annotated[AclRuleType, Field(description="IPV4 or MAC; chooses the filter variant.")],
        enabled: Annotated[bool, Field(description="Whether this complete rule is enabled; False is explicit.")],
        name: Annotated[str, Field(min_length=1, description="Nonempty rule name.")],
        action: Annotated[AclAction, Field(description="ALLOW or BLOCK.")],
        description: Annotated[
            str | None, Field(description="Optional rule description; empty string is explicit.")
        ] = None,
        enforcing_device_ids: Annotated[
            list[str] | None,
            Field(description="Nonempty unique device IDs; None omits the property. Client does not copy old filters."),
        ] = None,
        network_id: Annotated[
            str | None, Field(description="Required network ID for MAC rules; forbidden for IPV4.")
        ] = None,
        protocol_filter: Annotated[
            list[AclProtocol] | None,
            Field(description="IPV4-only nonempty unique TCP/UDP list. None omits protocolFilter from the request."),
        ] = None,
        source_ip_addresses_or_subnets: Annotated[
            list[str] | None, Field(description="IPV4 source addresses/subnets; cannot combine with network IDs.")
        ] = None,
        source_network_ids: Annotated[
            list[str] | None, Field(description="IPV4 source network IDs; cannot combine with addresses/subnets.")
        ] = None,
        source_ports: Annotated[
            list[int] | None, Field(description="IPV4 source ports (1 to 65535), alone or with addresses/networks.")
        ] = None,
        source_mac_addresses: Annotated[list[str] | None, Field(description="MAC-only source address list.")] = None,
        source_mac_prefix_length: Annotated[
            int | None, Field(description="MAC-only source prefix (1 to 48); requires its address list.")
        ] = None,
        destination_ip_addresses_or_subnets: Annotated[
            list[str] | None, Field(description="IPV4 destination addresses/subnets; cannot combine with network IDs.")
        ] = None,
        destination_network_ids: Annotated[
            list[str] | None, Field(description="IPV4 destination network IDs; cannot combine with addresses/subnets.")
        ] = None,
        destination_ports: Annotated[
            list[int] | None,
            Field(description="IPV4 destination ports (1 to 65535), alone or with addresses/networks."),
        ] = None,
        destination_mac_addresses: Annotated[
            list[str] | None, Field(description="MAC-only destination address list.")
        ] = None,
        destination_mac_prefix_length: Annotated[
            int | None, Field(description="MAC-only destination prefix (1 to 48); requires its address list.")
        ] = None,
    ) -> dict[str, Any]:
        """Create a complete ACL rule using named fields (Network Integration API).

        Update is a full-object PUT: resupply the complete desired rule. This
        client never fetches or merges old fields. The API documents null
        device/protocol/port defaults, but does not define source/destination
        filter omission effects. Controller omission behavior is not live
        verified here. None omits a request property; explicit null-clearing,
        raw data and deprecated index are unavailable. Use the confirmed reorder
        tool for priority. IP/UUID semantics remain controller-validated; MAC
        syntax uses the shared validator.

        Returns:
            The upstream policy with sensitive fields redacted.
        """
        body = build_acl_rule_body(
            tool_name="unifi_network_create_acl_rule",
            values={
                "rule_type": rule_type,
                "enabled": enabled,
                "name": name,
                "action": action,
                "description": description,
                "enforcing_device_ids": enforcing_device_ids,
                "network_id": network_id,
                "protocol_filter": protocol_filter,
                "source_ip_addresses_or_subnets": source_ip_addresses_or_subnets,
                "source_network_ids": source_network_ids,
                "source_ports": source_ports,
                "source_mac_addresses": source_mac_addresses,
                "source_mac_prefix_length": source_mac_prefix_length,
                "destination_ip_addresses_or_subnets": destination_ip_addresses_or_subnets,
                "destination_network_ids": destination_network_ids,
                "destination_ports": destination_ports,
                "destination_mac_addresses": destination_mac_addresses,
                "destination_mac_prefix_length": destination_mac_prefix_length,
            },
        )
        return redact_secrets(await get_server_context(ctx).clients["network_integration"].create_acl_rule(body))

    @mcp.tool(tags={"write", "network_integration"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    @tool_handler(write=True)
    async def unifi_network_update_acl_rule(
        ctx: Context,
        acl_rule_id: Annotated[str, Field(description="ID of the user-defined ACL rule to replace.")],
        *,
        rule_type: Annotated[AclRuleType, Field(description="IPV4 or MAC; chooses the filter variant.")],
        enabled: Annotated[bool, Field(description="Whether this complete rule is enabled; False is explicit.")],
        name: Annotated[str, Field(min_length=1, description="Nonempty rule name.")],
        action: Annotated[AclAction, Field(description="ALLOW or BLOCK.")],
        description: Annotated[
            str | None, Field(description="Optional rule description; empty string is explicit.")
        ] = None,
        enforcing_device_ids: Annotated[
            list[str] | None,
            Field(description="Nonempty unique device IDs; None omits the property. Client does not copy old filters."),
        ] = None,
        network_id: Annotated[
            str | None, Field(description="Required network ID for MAC rules; forbidden for IPV4.")
        ] = None,
        protocol_filter: Annotated[
            list[AclProtocol] | None,
            Field(description="IPV4-only nonempty unique TCP/UDP list. None omits protocolFilter from the request."),
        ] = None,
        source_ip_addresses_or_subnets: Annotated[
            list[str] | None, Field(description="IPV4 source addresses/subnets; cannot combine with network IDs.")
        ] = None,
        source_network_ids: Annotated[
            list[str] | None, Field(description="IPV4 source network IDs; cannot combine with addresses/subnets.")
        ] = None,
        source_ports: Annotated[
            list[int] | None, Field(description="IPV4 source ports (1 to 65535), alone or with addresses/networks.")
        ] = None,
        source_mac_addresses: Annotated[list[str] | None, Field(description="MAC-only source address list.")] = None,
        source_mac_prefix_length: Annotated[
            int | None, Field(description="MAC-only source prefix (1 to 48); requires its address list.")
        ] = None,
        destination_ip_addresses_or_subnets: Annotated[
            list[str] | None, Field(description="IPV4 destination addresses/subnets; cannot combine with network IDs.")
        ] = None,
        destination_network_ids: Annotated[
            list[str] | None, Field(description="IPV4 destination network IDs; cannot combine with addresses/subnets.")
        ] = None,
        destination_ports: Annotated[
            list[int] | None,
            Field(description="IPV4 destination ports (1 to 65535), alone or with addresses/networks."),
        ] = None,
        destination_mac_addresses: Annotated[
            list[str] | None, Field(description="MAC-only destination address list.")
        ] = None,
        destination_mac_prefix_length: Annotated[
            int | None, Field(description="MAC-only destination prefix (1 to 48); requires its address list.")
        ] = None,
    ) -> dict[str, Any]:
        """Update a complete ACL rule using named fields (Network Integration API).

        Update is a full-object PUT: resupply the complete desired rule. This
        client never fetches or merges old fields. The API documents null
        device/protocol/port defaults, but does not define source/destination
        filter omission effects. Controller omission behavior is not live
        verified here. None omits a request property; explicit null-clearing,
        raw data and deprecated index are unavailable. Use the confirmed reorder
        tool for priority. IP/UUID semantics remain controller-validated; MAC
        syntax uses the shared validator.

        Returns:
            The upstream policy with sensitive fields redacted.
        """
        validate_id(acl_rule_id, field="acl_rule_id")
        body = build_acl_rule_body(
            tool_name="unifi_network_update_acl_rule",
            values={
                "rule_type": rule_type,
                "enabled": enabled,
                "name": name,
                "action": action,
                "description": description,
                "enforcing_device_ids": enforcing_device_ids,
                "network_id": network_id,
                "protocol_filter": protocol_filter,
                "source_ip_addresses_or_subnets": source_ip_addresses_or_subnets,
                "source_network_ids": source_network_ids,
                "source_ports": source_ports,
                "source_mac_addresses": source_mac_addresses,
                "source_mac_prefix_length": source_mac_prefix_length,
                "destination_ip_addresses_or_subnets": destination_ip_addresses_or_subnets,
                "destination_network_ids": destination_network_ids,
                "destination_ports": destination_ports,
                "destination_mac_addresses": destination_mac_addresses,
                "destination_mac_prefix_length": destination_mac_prefix_length,
            },
        )
        return redact_secrets(
            await get_server_context(ctx).clients["network_integration"].update_acl_rule(acl_rule_id, body)
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

    @mcp.tool(tags={"write", "network_integration"}, annotations={"readOnlyHint": False, "destructiveHint": True})
    @tool_handler(write=True)
    async def unifi_network_reorder_acl_rules(
        ctx: Context, ordered_acl_rule_ids: list[str], confirm: bool = False
    ) -> dict[str, Any]:
        """Replace the site-wide ACL-rule ordering (Network Integration API).

        Full-replacement: pass the COMPLETE current id set in the desired order.
        Any omitted rule loses its enforcement position, so this is destructive;
        pass ``confirm=True`` to proceed. Pairs with the read tool
        ``unifi_network_get_acl_rules_ordering``.

        Args:
            ctx: FastMCP request context.
            ordered_acl_rule_ids: Every ACL rule id, in the new priority order.
            confirm: Must be ``True`` to apply the full-replacement ordering.

        Returns:
            The upstream API response with sensitive fields redacted.

        Raises:
            ToolError: If write mode is disabled, ``confirm`` is not ``True``, the id
                list is empty, or any id is malformed.
        """
        if not confirm:
            raise UniFiBadRequestError("reorder replaces the full ACL ordering; pass confirm=True")
        if not ordered_acl_rule_ids:
            raise UniFiBadRequestError("ordered_acl_rule_ids must be non-empty; an empty list wipes all ACL ordering")
        for rule_id in ordered_acl_rule_ids:
            validate_id(rule_id, field="ordered_acl_rule_ids")
        return redact_secrets(
            await get_server_context(ctx).clients["network_integration"].update_acl_rules_ordering(ordered_acl_rule_ids)
        )
