"""Network WLAN configuration tools (2 read + 3 write)."""

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


def register_wlan_tools(mcp: FastMCP) -> None:
    """Register WLAN tools."""

    # ── Read tools ──────────────────────────────────────────────────────

    @mcp.tool(tags={"network"})
    @tool_handler()
    async def unifi_network_list_wlans(ctx: Context) -> dict[str, Any]:
        """List all WLAN (Wi-Fi network) configurations.

        Wi-Fi PSKs (``x_passphrase``), RADIUS shared secrets, and other
        credential fields are redacted before the response leaves this
        tool — see ``unifi_mcp._redaction`` (#146).

        Args:
            ctx: FastMCP request context.

        Returns:
            The upstream API response with sensitive fields redacted.
        """
        return redact_secrets(await get_server_context(ctx).clients["network"].list_wlans())

    @mcp.tool(tags={"network"})
    @tool_handler()
    async def unifi_network_get_wlan(ctx: Context, wlan_id: str) -> dict[str, Any]:
        """Get a specific WLAN configuration by ID.

        Wi-Fi PSKs (``x_passphrase``), RADIUS shared secrets, and other
        credential fields are redacted before the response leaves this
        tool — see ``unifi_mcp._redaction`` (#146).

        Args:
            wlan_id: The WLAN configuration ID.

        Returns:
            The upstream API response with sensitive fields redacted.
        """
        validate_id(wlan_id, field="wlan_id")
        return redact_secrets(await get_server_context(ctx).clients["network"].get_wlan(wlan_id))

    # ── Write tools ─────────────────────────────────────────────────────

    @mcp.tool(tags={"write", "network"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    @tool_handler(write=True)
    async def unifi_network_create_wlan(
        ctx: Context,
        name: str,
        security: str = "wpapsk",
        wpa_mode: str = "wpa2",
        x_passphrase: str = "",
        enabled: bool = True,
    ) -> dict[str, Any]:
        """Create a new WLAN (Wi-Fi network).

        Args:
            name: SSID name for the wireless network.
            security: Security mode — "wpapsk", "wpaeap", or "open".
            wpa_mode: WPA mode — "wpa2" or "wpa3".
            x_passphrase: Wi-Fi password (required for wpapsk).
            enabled: Whether the WLAN is enabled.

        Returns:
            The upstream API response.
        """
        data: JsonObject = {
            "name": name,
            "security": security,
            "wpa_mode": wpa_mode,
            "x_passphrase": x_passphrase,
            "enabled": enabled,
        }
        return redact_secrets(await get_server_context(ctx).clients["network"].create_wlan(data))

    @mcp.tool(tags={"write", "network"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    @tool_handler(write=True)
    async def unifi_network_update_wlan(ctx: Context, wlan_id: str, data: JsonObject) -> dict[str, Any]:
        """Update an existing WLAN configuration. Pass only fields to change.

        Args:
            wlan_id: The WLAN configuration ID to update.
            data: Fields to update (e.g., {"name": "new-name", "enabled": false}).

        Returns:
            The upstream API response.
        """
        validate_id(wlan_id, field="wlan_id")
        reject_dangerous_keys(data, tool_name="unifi_network_update_wlan")
        return redact_secrets(await get_server_context(ctx).clients["network"].update_wlan(wlan_id, data))

    @mcp.tool(tags={"write", "network"}, annotations={"readOnlyHint": False, "destructiveHint": True})
    @tool_handler(write=True)
    async def unifi_network_delete_wlan(ctx: Context, wlan_id: str) -> dict[str, Any]:
        """Delete a WLAN configuration.

        Args:
            wlan_id: The WLAN configuration ID to delete.

        Returns:
            The upstream API response.
        """
        validate_id(wlan_id, field="wlan_id")
        return redact_secrets(await get_server_context(ctx).clients["network"].delete_wlan(wlan_id))
