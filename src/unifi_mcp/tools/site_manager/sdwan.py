"""Site Manager SD-WAN tools — read-only early-access (``/ea/``) configs."""

from __future__ import annotations

from typing import Any

from fastmcp import Context, FastMCP

from unifi_mcp.tools._common import get_server_context, redact_secrets, tool_handler, validate_id


def register_site_manager_sdwan_tools(mcp: FastMCP) -> None:
    """Register Site Manager SD-WAN tools on the given FastMCP server."""

    @mcp.tool(tags={"site_manager"})
    @tool_handler()
    async def unifi_site_manager_list_sdwan_configs(ctx: Context) -> dict[str, Any]:
        """List SD-WAN configs from UniFi Site Manager (early-access surface).

        SD-WAN configs can carry pre-shared keys, so secret keys are redacted
        before the response leaves this tool — see ``unifi_mcp._redaction``
        (#146, #203).

        Args:
            ctx: FastMCP request context — supplied by the framework.

        Returns:
            The Site Manager API response with sensitive fields redacted,
            shaped as ``{"data": [...], "httpStatusCode": 200}``. Each entry
            in ``data`` is an SD-WAN config record.
        """
        return redact_secrets(await get_server_context(ctx).clients["site_manager"].list_sdwan_configs())

    @mcp.tool(tags={"site_manager"})
    @tool_handler()
    async def unifi_site_manager_get_sdwan_config(ctx: Context, config_id: str) -> dict[str, Any]:
        """Get a single SD-WAN config from UniFi Site Manager (early-access surface).

        SD-WAN configs can carry pre-shared keys, so secret keys are redacted
        before the response leaves this tool — see ``unifi_mcp._redaction``
        (#146, #203).

        Args:
            ctx: FastMCP request context — supplied by the framework.
            config_id: The SD-WAN config ID, as returned in the ``id`` field of
                ``unifi_site_manager_list_sdwan_configs``.

        Returns:
            The Site Manager API response with sensitive fields redacted,
            shaped as ``{"data": {...}, "httpStatusCode": 200}``, where
            ``data`` is a single SD-WAN config record.
        """
        validate_id(config_id, field="config_id")
        return redact_secrets(await get_server_context(ctx).clients["site_manager"].get_sdwan_config(config_id))

    @mcp.tool(tags={"site_manager"})
    @tool_handler()
    async def unifi_site_manager_get_sdwan_config_status(ctx: Context, config_id: str) -> dict[str, Any]:
        """Get SD-WAN config deployment status from UniFi Site Manager (early-access).

        Secret keys are redacted before the response leaves this tool — see
        ``unifi_mcp._redaction`` (#146, #203).

        Args:
            ctx: FastMCP request context — supplied by the framework.
            config_id: The SD-WAN config ID whose deployment status to fetch.

        Returns:
            The Site Manager API response with sensitive fields redacted,
            shaped as ``{"data": {...}, "httpStatusCode": 200}``, where
            ``data`` describes the config's deployment status.
        """
        validate_id(config_id, field="config_id")
        return redact_secrets(await get_server_context(ctx).clients["site_manager"].get_sdwan_config_status(config_id))
