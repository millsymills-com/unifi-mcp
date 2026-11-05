"""Network Integration DNS-policy read and write tools."""

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
from unifi_mcp.tools.network_integration._common import bound_pagination
from unifi_mcp.tools.network_integration._dns_policy import DnsPolicyType, build_dns_policy_body


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
    async def unifi_network_create_dns_policy(
        ctx: Context,
        *,
        policy_type: Annotated[
            DnsPolicyType, Field(description="DNS policy variant; determines required named fields.")
        ],
        enabled: Annotated[bool, Field(description="Whether the policy is enabled; False explicitly disables it.")],
        domain: Annotated[str, Field(min_length=1, max_length=127, description="Policy domain (1 to 127 characters).")],
        ipv4_address: Annotated[str | None, Field(description="Required for A_RECORD.")] = None,
        ipv6_address: Annotated[str | None, Field(description="Required for AAAA_RECORD.")] = None,
        target_domain: Annotated[
            str | None, Field(description="Required for CNAME_RECORD (1 to 127 characters).")
        ] = None,
        mail_server_domain: Annotated[
            str | None, Field(description="Required for MX_RECORD (1 to 127 characters).")
        ] = None,
        text: Annotated[str | None, Field(description="Required for TXT_RECORD (1 to 1024 characters).")] = None,
        server_domain: Annotated[
            str | None, Field(description="Required for SRV_RECORD (1 to 127 characters).")
        ] = None,
        ip_address: Annotated[str | None, Field(description="DNS server address required for FORWARD_DOMAIN.")] = None,
        service: Annotated[str | None, Field(description="Required for SRV_RECORD, for example _ldap.")] = None,
        protocol: Annotated[str | None, Field(description="Required for SRV_RECORD, for example _tcp.")] = None,
        ttl_seconds: Annotated[
            int | None,
            Field(description="Required for A/AAAA (0 to 86400) or CNAME (0 to 604800); forbidden for other variants."),
        ] = None,
        priority: Annotated[int | None, Field(description="Required for MX or SRV (0 to 65535).")] = None,
        port: Annotated[int | None, Field(description="Required for SRV (0 to 65535).")] = None,
        weight: Annotated[int | None, Field(description="Required for SRV (0 to 65535).")] = None,
    ) -> dict[str, Any]:
        """Create a DNS policy using named fields (Network Integration API).

        Send a complete policy for the selected variant; update is a full-object
        PUT, not a patch. Raw data, arbitrary fields and null-clearing are not
        supported. None omits a field, but cannot omit a required variant field.
        IP address syntax and DNS semantics are checked by the controller.

        Returns:
            The policy with sensitive fields redacted.
        """
        body = build_dns_policy_body(
            tool_name="unifi_network_create_dns_policy",
            policy_type=policy_type,
            enabled=enabled,
            domain=domain,
            fields={
                "ipv4_address": ipv4_address,
                "ipv6_address": ipv6_address,
                "target_domain": target_domain,
                "mail_server_domain": mail_server_domain,
                "text": text,
                "server_domain": server_domain,
                "ip_address": ip_address,
                "service": service,
                "protocol": protocol,
                "ttl_seconds": ttl_seconds,
                "priority": priority,
                "port": port,
                "weight": weight,
            },
        )
        return redact_secrets(await get_server_context(ctx).clients["network_integration"].create_dns_policy(body))

    @mcp.tool(tags={"write", "network_integration"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    @tool_handler(write=True)
    async def unifi_network_update_dns_policy(
        ctx: Context,
        dns_policy_id: Annotated[str, Field(description="ID of the DNS policy to replace with this complete body.")],
        *,
        policy_type: Annotated[
            DnsPolicyType, Field(description="DNS policy variant; determines required named fields.")
        ],
        enabled: Annotated[bool, Field(description="Whether the policy is enabled; False explicitly disables it.")],
        domain: Annotated[str, Field(min_length=1, max_length=127, description="Policy domain (1 to 127 characters).")],
        ipv4_address: Annotated[str | None, Field(description="Required for A_RECORD.")] = None,
        ipv6_address: Annotated[str | None, Field(description="Required for AAAA_RECORD.")] = None,
        target_domain: Annotated[
            str | None, Field(description="Required for CNAME_RECORD (1 to 127 characters).")
        ] = None,
        mail_server_domain: Annotated[
            str | None, Field(description="Required for MX_RECORD (1 to 127 characters).")
        ] = None,
        text: Annotated[str | None, Field(description="Required for TXT_RECORD (1 to 1024 characters).")] = None,
        server_domain: Annotated[
            str | None, Field(description="Required for SRV_RECORD (1 to 127 characters).")
        ] = None,
        ip_address: Annotated[str | None, Field(description="DNS server address required for FORWARD_DOMAIN.")] = None,
        service: Annotated[str | None, Field(description="Required for SRV_RECORD, for example _ldap.")] = None,
        protocol: Annotated[str | None, Field(description="Required for SRV_RECORD, for example _tcp.")] = None,
        ttl_seconds: Annotated[
            int | None,
            Field(description="Required for A/AAAA (0 to 86400) or CNAME (0 to 604800); forbidden for other variants."),
        ] = None,
        priority: Annotated[int | None, Field(description="Required for MX or SRV (0 to 65535).")] = None,
        port: Annotated[int | None, Field(description="Required for SRV (0 to 65535).")] = None,
        weight: Annotated[int | None, Field(description="Required for SRV (0 to 65535).")] = None,
    ) -> dict[str, Any]:
        """Update a DNS policy using named fields (Network Integration API).

        Send a complete policy for the selected variant; update is a full-object
        PUT, not a patch. Raw data, arbitrary fields and null-clearing are not
        supported. None omits a field, but cannot omit a required variant field.
        IP address syntax and DNS semantics are checked by the controller.

        Returns:
            The policy with sensitive fields redacted.
        """
        validate_id(dns_policy_id, field="dns_policy_id")
        body = build_dns_policy_body(
            tool_name="unifi_network_update_dns_policy",
            policy_type=policy_type,
            enabled=enabled,
            domain=domain,
            fields={
                "ipv4_address": ipv4_address,
                "ipv6_address": ipv6_address,
                "target_domain": target_domain,
                "mail_server_domain": mail_server_domain,
                "text": text,
                "server_domain": server_domain,
                "ip_address": ip_address,
                "service": service,
                "protocol": protocol,
                "ttl_seconds": ttl_seconds,
                "priority": priority,
                "port": port,
                "weight": weight,
            },
        )
        return redact_secrets(
            await get_server_context(ctx).clients["network_integration"].update_dns_policy(dns_policy_id, body)
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
