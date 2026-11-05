"""Network firewall rules and groups tools (4 read + 6 write)."""

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

_FIREWALL_GROUP_FIELD_PATHS: dict[str, tuple[str, ...]] = {
    name: (name,) for name in ("name", "group_type", "group_members")
}


_FIREWALL_RULE_FIELD_PATHS: dict[str, tuple[str, ...]] = {
    name: (name,)
    for name in (
        "name",
        "ruleset",
        "action",
        "enabled",
        "protocol",
        "src_address",
        "dst_address",
        "rule_index",
        "logging",
        "state_new",
        "state_established",
        "state_invalid",
        "state_related",
        "icmp_typename",
        "ipsec",
        "src_firewallgroup_ids",
        "dst_firewallgroup_ids",
    )
}


def _validate_rule_fields(values: dict[str, Any]) -> None:
    """Check named scalar/list types without guessing controller vocabularies."""
    for field, value in values.items():
        if value is None:
            continue
        if field in (
            "name",
            "ruleset",
            "action",
            "protocol",
            "src_address",
            "dst_address",
            "icmp_typename",
            "ipsec",
        ) and not isinstance(value, str):
            raise UniFiBadRequestError(f"{field} must be a string")
        if (
            field in ("enabled", "logging", "state_new", "state_established", "state_invalid", "state_related")
            and type(value) is not bool
        ):
            raise UniFiBadRequestError(f"{field} must be a boolean")
        if field == "rule_index" and type(value) is not int:
            raise UniFiBadRequestError("rule_index must be an integer")
        if field in {"src_firewallgroup_ids", "dst_firewallgroup_ids"}:
            if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                raise UniFiBadRequestError(f"{field} must be a list of IDs")
            for index, item in enumerate(value):
                validate_id(item, field=f"{field}[{index}]")


def register_firewall_tools(mcp: FastMCP) -> None:
    """Register firewall tools."""

    # ── Read tools ──────────────────────────────────────────────────────

    @mcp.tool(tags={"network"})
    @tool_handler()
    async def unifi_network_list_firewall_rules(ctx: Context) -> dict[str, Any]:
        """List all firewall rules.

        Args:
            ctx: FastMCP request context.

        Returns:
            The upstream API response with sensitive fields redacted.
        """
        return redact_secrets(await get_server_context(ctx).clients["network"].list_firewall_rules())

    @mcp.tool(tags={"network"})
    @tool_handler()
    async def unifi_network_get_firewall_rule(ctx: Context, rule_id: str) -> dict[str, Any]:
        """Get a specific firewall rule by ID.

        Args:
            rule_id: The firewall rule ID.

        Returns:
            The upstream API response with sensitive fields redacted.
        """
        validate_id(rule_id, field="rule_id")
        return redact_secrets(await get_server_context(ctx).clients["network"].get_firewall_rule(rule_id))

    @mcp.tool(tags={"network"})
    @tool_handler()
    async def unifi_network_list_firewall_groups(ctx: Context) -> dict[str, Any]:
        """List all firewall groups (address groups, port groups).

        Args:
            ctx: FastMCP request context.

        Returns:
            The upstream API response with sensitive fields redacted.
        """
        return redact_secrets(await get_server_context(ctx).clients["network"].list_firewall_groups())

    @mcp.tool(tags={"network"})
    @tool_handler()
    async def unifi_network_get_firewall_group(ctx: Context, group_id: str) -> dict[str, Any]:
        """Get a specific firewall group by ID.

        Args:
            group_id: The firewall group ID.

        Returns:
            The upstream API response with sensitive fields redacted.
        """
        validate_id(group_id, field="group_id")
        return redact_secrets(await get_server_context(ctx).clients["network"].get_firewall_group(group_id))

    # ── Write tools ─────────────────────────────────────────────────────

    @mcp.tool(tags={"write", "network"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    @tool_handler(write=True)
    async def unifi_network_create_firewall_rule(
        ctx: Context,
        *,
        name: str,
        ruleset: str,
        action: str = "drop",
        enabled: bool = True,
        protocol: str = "all",
        src_address: str | None = None,
        dst_address: str | None = None,
        rule_index: int | None = None,
        logging: bool | None = None,
        state_new: bool | None = None,
        state_established: bool | None = None,
        state_invalid: bool | None = None,
        state_related: bool | None = None,
        icmp_typename: str | None = None,
        ipsec: str | None = None,
        src_firewallgroup_ids: list[str] | None = None,
        dst_firewallgroup_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a legacy firewall rule using named fields.

        Modern controllers require additional fields beyond name/ruleset.
        Supply the explicit ordering, state flags and selectors needed by your
        controller; no ordering or connection-state defaults are invented.
        The existing action=drop, enabled=True and protocol=all defaults remain.
        Raw data, arbitrary controller keys and null-clearing are unsupported.

        Args:
            name: Rule name.
            ruleset: Controller ruleset such as LAN_IN or WAN_IN.
            action: Controller action; default drop.
            enabled: Whether the new rule is enabled; default True.
            protocol: Controller protocol; default all.
            src_address: Optional source address/CIDR.
            dst_address: Optional destination address/CIDR.
            rule_index: Explicit rule ordering; not calculated or assigned by this tool.
            logging: Explicit logging flag when required by the controller.
            state_new: Explicit new-connection match flag.
            state_established: Explicit established-connection match flag.
            state_invalid: Explicit invalid-connection match flag.
            state_related: Explicit related-connection match flag.
            icmp_typename: Controller ICMP selector; an empty string is sent as supplied.
            ipsec: Controller IPsec selector; an empty string is sent as supplied.
            src_firewallgroup_ids: Source group IDs; [] explicitly sends an empty list.
            dst_firewallgroup_ids: Destination group IDs; [] explicitly sends an empty list.

        Returns:
            The upstream response with sensitive fields redacted.

        Note:
            The allowlist follows the existing full-payload fixtures for #90.
            Legacy controller requirements vary; the minimum Python signature
            is not a promise that those fields suffice on every controller.
        """
        if any(value is None for value in (name, ruleset, action, enabled, protocol)):
            raise UniFiBadRequestError("name, ruleset, action, enabled and protocol cannot be null")
        values = {
            "name": name,
            "ruleset": ruleset,
            "action": action,
            "enabled": enabled,
            "protocol": protocol,
            "src_address": src_address,
            "dst_address": dst_address,
            "rule_index": rule_index,
            "logging": logging,
            "state_new": state_new,
            "state_established": state_established,
            "state_invalid": state_invalid,
            "state_related": state_related,
            "icmp_typename": icmp_typename,
            "ipsec": ipsec,
            "src_firewallgroup_ids": src_firewallgroup_ids,
            "dst_firewallgroup_ids": dst_firewallgroup_ids,
        }
        _validate_rule_fields(values)
        body = build_named_arg_body(
            tool_name="unifi_network_create_firewall_rule",
            field_paths=_FIREWALL_RULE_FIELD_PATHS,
            named_values=values,
            data=None,
        )
        reject_dangerous_keys(body, tool_name="unifi_network_create_firewall_rule")
        return redact_secrets(await get_server_context(ctx).clients["network"].create_firewall_rule(body))

    @mcp.tool(tags={"write", "network"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    @tool_handler(write=True)
    async def unifi_network_update_firewall_rule(
        ctx: Context,
        rule_id: str,
        *,
        name: str | None = None,
        ruleset: str | None = None,
        action: str | None = None,
        enabled: bool | None = None,
        protocol: str | None = None,
        src_address: str | None = None,
        dst_address: str | None = None,
        rule_index: int | None = None,
        logging: bool | None = None,
        state_new: bool | None = None,
        state_established: bool | None = None,
        state_invalid: bool | None = None,
        state_related: bool | None = None,
        icmp_typename: str | None = None,
        ipsec: str | None = None,
        src_firewallgroup_ids: list[str] | None = None,
        dst_firewallgroup_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Update named legacy firewall-rule fields; other fields are unchanged.

        At least one non-null field is required. None omits a field; raw data
        and explicit null-clearing are unsupported. Empty group-ID lists are
        sent explicitly and may broaden matching. Ordering and state flags are
        never inferred; the controller validates rule semantics and values.

        Args:
            rule_id: Existing rule ID.
            name: Rule name.
            ruleset: Controller ruleset such as LAN_IN or WAN_IN.
            action: Controller action such as accept, drop or reject.
            enabled: False explicitly disables the rule.
            protocol: Controller protocol such as all, tcp or udp.
            src_address: Source address/CIDR; omitted fields are unchanged.
            dst_address: Destination address/CIDR.
            rule_index: Explicit controller rule ordering value; never calculated.
            logging: Whether matching traffic is logged.
            state_new: Match new connections.
            state_established: Match established connections.
            state_invalid: Match invalid connections.
            state_related: Match related connections.
            icmp_typename: Controller ICMP selector; empty string is sent as supplied.
            ipsec: Controller IPsec selector; empty string is sent as supplied.
            src_firewallgroup_ids: Source group IDs; [] explicitly clears this match list.
            dst_firewallgroup_ids: Destination group IDs; [] explicitly clears this match list.

        Returns:
            The upstream API response with sensitive fields redacted.
        """
        validate_id(rule_id, field="rule_id")
        values = {
            "name": name,
            "ruleset": ruleset,
            "action": action,
            "enabled": enabled,
            "protocol": protocol,
            "src_address": src_address,
            "dst_address": dst_address,
            "rule_index": rule_index,
            "logging": logging,
            "state_new": state_new,
            "state_established": state_established,
            "state_invalid": state_invalid,
            "state_related": state_related,
            "icmp_typename": icmp_typename,
            "ipsec": ipsec,
            "src_firewallgroup_ids": src_firewallgroup_ids,
            "dst_firewallgroup_ids": dst_firewallgroup_ids,
        }
        _validate_rule_fields(values)
        body = build_named_arg_body(
            tool_name="unifi_network_update_firewall_rule",
            field_paths=_FIREWALL_RULE_FIELD_PATHS,
            named_values=values,
            data=None,
        )
        reject_dangerous_keys(body, tool_name="unifi_network_update_firewall_rule")
        return redact_secrets(await get_server_context(ctx).clients["network"].update_firewall_rule(rule_id, body))

    @mcp.tool(tags={"write", "network"}, annotations={"readOnlyHint": False, "destructiveHint": True})
    @tool_handler(write=True)
    async def unifi_network_delete_firewall_rule(ctx: Context, rule_id: str, confirm: bool = False) -> dict[str, Any]:
        """Delete a firewall rule.

        Irreversible. Pass ``confirm=True`` to proceed.

        Args:
            rule_id: The firewall rule ID to delete.
            confirm: Must be ``True`` to perform the deletion.

        Returns:
            The upstream API response.

        Raises:
            ToolError: If write mode is disabled, ``rule_id`` is malformed, or
                ``confirm`` is not ``True``.
        """
        validate_id(rule_id, field="rule_id")
        if not confirm:
            raise UniFiBadRequestError("deleting the firewall rule is irreversible; pass confirm=True")
        return redact_secrets(await get_server_context(ctx).clients["network"].delete_firewall_rule(rule_id))

    @mcp.tool(tags={"write", "network"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    @tool_handler(write=True)
    async def unifi_network_create_firewall_group(
        ctx: Context,
        name: str,
        group_type: str,
        group_members: list[str],
    ) -> dict[str, Any]:
        """Create a new firewall group.

        Args:
            name: Group name.
            group_type: Type — "address-group", "port-group", "ipv6-address-group".
            group_members: List of members (IPs/CIDRs for address groups, ports for port groups).

        Returns:
            The upstream API response.
        """
        data: JsonObject = {
            "name": name,
            "group_type": group_type,
            "group_members": group_members,
        }
        return redact_secrets(await get_server_context(ctx).clients["network"].create_firewall_group(data))

    @mcp.tool(tags={"write", "network"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    @tool_handler(write=True)
    async def unifi_network_update_firewall_group(
        ctx: Context,
        group_id: str,
        *,
        name: str | None = None,
        group_type: str | None = None,
        group_members: list[str] | None = None,
    ) -> dict[str, Any]:
        """Update an existing firewall group. Pass only fields to change.

        Args:
            group_id: The firewall group ID.
            name: Group name.
            group_type: Type: "address-group", "port-group", or "ipv6-address-group".
            group_members: IPs/CIDRs or ports as strings. An empty list explicitly requests empty membership.

        At least one non-null named field is required. Omitted or None fields
        are unchanged; raw ``data`` and explicit null-clearing are unsupported.

        Returns:
            The upstream API response.
        """
        validate_id(group_id, field="group_id")
        if group_members is not None and (
            not isinstance(group_members, list) or any(not isinstance(member, str) for member in group_members)
        ):
            raise UniFiBadRequestError("group_members must be a list of strings")
        body = build_named_arg_body(
            tool_name="unifi_network_update_firewall_group",
            field_paths=_FIREWALL_GROUP_FIELD_PATHS,
            named_values={"name": name, "group_type": group_type, "group_members": group_members},
            data=None,
        )
        reject_dangerous_keys(body, tool_name="unifi_network_update_firewall_group")
        return redact_secrets(await get_server_context(ctx).clients["network"].update_firewall_group(group_id, body))

    @mcp.tool(tags={"write", "network"}, annotations={"readOnlyHint": False, "destructiveHint": True})
    @tool_handler(write=True)
    async def unifi_network_delete_firewall_group(ctx: Context, group_id: str, confirm: bool = False) -> dict[str, Any]:
        """Delete a firewall group.

        Irreversible. Pass ``confirm=True`` to proceed.

        Args:
            group_id: The firewall group ID to delete.
            confirm: Must be ``True`` to perform the deletion.

        Returns:
            The upstream API response.

        Raises:
            ToolError: If write mode is disabled, ``group_id`` is malformed, or
                ``confirm`` is not ``True``.
        """
        validate_id(group_id, field="group_id")
        if not confirm:
            raise UniFiBadRequestError("deleting the firewall group is irreversible; pass confirm=True")
        return redact_secrets(await get_server_context(ctx).clients["network"].delete_firewall_group(group_id))
