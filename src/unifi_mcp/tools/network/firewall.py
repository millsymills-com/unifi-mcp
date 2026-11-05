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
        data: JsonObject | None = None,
    ) -> dict[str, Any]:
        """Create a new firewall rule.

        Returns:
            The upstream API response.

        Args:
            name: Rule name (ignored if ``data`` set).
            ruleset: "WAN_IN" / "WAN_OUT" / "LAN_IN" / "LAN_OUT" / etc.
            action: "accept" / "drop" / "reject".
            enabled: Whether the rule is enabled.
            protocol: "all" / "tcp" / "udp" / "tcp_udp" / "icmp".
            src_address: Source IP/CIDR (optional).
            dst_address: Destination IP/CIDR (optional).
            data: Full firewall-rule payload — overrides the scalar args
                when set. Use this to populate required fields like
                ``rule_index`` that the scalars don't expose.

        Note:
            Modern controllers reject scalar-only calls with HTTP 400
            ``api.err.FirewallRuleFieldsRequired`` (#90). The legacy
            ``rest/firewallrule`` endpoint also expects ``rule_index``,
            ``logging``, the ``state_new`` / ``state_established`` /
            ``state_invalid`` / ``state_related`` flags, ``icmp_typename``,
            ``ipsec``, ``src_firewallgroup_ids``, and
            ``dst_firewallgroup_ids``; pass them via ``data``.
        """
        if data is None:
            data = {
                "name": name,
                "ruleset": ruleset,
                "action": action,
                "enabled": enabled,
                "protocol": protocol,
            }
            if src_address is not None:
                data["src_address"] = src_address
            if dst_address is not None:
                data["dst_address"] = dst_address
        else:
            reject_dangerous_keys(data, tool_name="unifi_network_create_firewall_rule")
        return redact_secrets(await get_server_context(ctx).clients["network"].create_firewall_rule(data))

    @mcp.tool(tags={"write", "network"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    @tool_handler(write=True)
    async def unifi_network_update_firewall_rule(ctx: Context, rule_id: str, data: JsonObject) -> dict[str, Any]:
        """Update an existing firewall rule. Pass only fields to change.

        Args:
            rule_id: The firewall rule ID.
            data: Fields to update (e.g., {"enabled": false, "action": "accept"}).

        Returns:
            The upstream API response.
        """
        validate_id(rule_id, field="rule_id")
        reject_dangerous_keys(data, tool_name="unifi_network_update_firewall_rule")
        return redact_secrets(await get_server_context(ctx).clients["network"].update_firewall_rule(rule_id, data))

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
