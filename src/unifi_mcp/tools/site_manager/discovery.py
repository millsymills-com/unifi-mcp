"""Site Manager discovery tools — read-only host, site, and device listing."""

from __future__ import annotations

from typing import Any

from fastmcp import Context, FastMCP

from unifi_mcp.tools._common import get_server_context, redact_secrets, tool_handler, validate_id


def register_site_manager_tools(mcp: FastMCP) -> None:
    """Register all Site Manager tools on the given FastMCP server."""

    @mcp.tool(tags={"site_manager"})
    @tool_handler()
    async def unifi_site_manager_list_hosts(ctx: Context) -> dict[str, Any]:
        """List all hosts (controllers) registered in UniFi Site Manager.

        Bearer tokens and other secret keys are redacted before the response
        leaves this tool — see ``unifi_mcp._redaction`` (#146, #203).

        Args:
            ctx: FastMCP request context — supplied by the framework.

        Returns:
            The Site Manager API response with sensitive fields redacted,
            shaped as ``{"data": [...], "httpStatusCode": 200}``. Each entry
            in ``data`` is a host record with at least ``id``, ``hostName``,
            ``isBlocked``, ``reportedState``, and ``hardwareId``.
        """
        return redact_secrets(await get_server_context(ctx).clients["site_manager"].list_hosts())

    @mcp.tool(tags={"site_manager"})
    @tool_handler()
    async def unifi_site_manager_get_host(ctx: Context, host_id: str) -> dict[str, Any]:
        """Get a single host's detail record from UniFi Site Manager.

        Returns the full record for one controller — including its reported
        state and user data — where ``unifi_site_manager_list_hosts`` only
        lists. Bearer tokens and other secret keys are redacted before the
        response leaves this tool — see ``unifi_mcp._redaction`` (#146, #203).

        Args:
            ctx: FastMCP request context — supplied by the framework.
            host_id: The host (controller) ID to fetch, as returned in the
                ``id`` field of ``unifi_site_manager_list_hosts``.

        Returns:
            The Site Manager API response with sensitive fields redacted,
            shaped as ``{"data": {...}, "httpStatusCode": 200}``, where
            ``data`` is a single host record with ``id``, ``hostName``,
            ``reportedState``, ``userData``, and ``hardwareId``.
        """
        validate_id(host_id, field="host_id")
        return redact_secrets(await get_server_context(ctx).clients["site_manager"].get_host(host_id))

    @mcp.tool(tags={"site_manager"})
    @tool_handler()
    async def unifi_site_manager_list_sites(ctx: Context) -> dict[str, Any]:
        """List all sites across all hosts in UniFi Site Manager.

        Bearer tokens and other secret keys are redacted before the response
        leaves this tool — see ``unifi_mcp._redaction`` (#146, #203).

        Args:
            ctx: FastMCP request context — supplied by the framework.

        Returns:
            The Site Manager API response with sensitive fields redacted,
            shaped as ``{"data": [...], "httpStatusCode": 200}``. Each entry
            in ``data`` is a site record with ``id``, ``hostId``, ``meta``
            (display name, description, timezone), and ``statistics``.
        """
        return redact_secrets(await get_server_context(ctx).clients["site_manager"].list_sites())

    @mcp.tool(tags={"site_manager"})
    @tool_handler()
    async def unifi_site_manager_list_devices(ctx: Context, host_id: str | None = None) -> dict[str, Any]:
        """List all devices in UniFi Site Manager, optionally filtered by host ID.

        Bearer tokens and other secret keys are redacted before the response
        leaves this tool — see ``unifi_mcp._redaction`` (#146, #203).

        Args:
            ctx: FastMCP request context — supplied by the framework.
            host_id: Optional host ID. When set, the response is filtered to devices
                belonging to that host; when ``None``, devices across every host are
                returned.

        Returns:
            The Site Manager API response with sensitive fields redacted,
            shaped as ``{"data": [...], "httpStatusCode": 200}``. Each entry
            in ``data`` is a device record with ``id``, ``hostId``, ``mac``,
            ``model``, ``firmwareVersion``, and ``state``.
        """
        if host_id is not None:
            validate_id(host_id, field="host_id")
        return redact_secrets(await get_server_context(ctx).clients["site_manager"].list_devices(host_id=host_id))
