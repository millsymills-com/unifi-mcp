"""Network WLAN configuration tools (2 read + 3 write)."""

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


async def _resolve_structural_ids(
    client: Any, ap_group_ids: list[str] | None, usergroup_id: str | None
) -> tuple[list[str], str]:
    """Resolve and validate the site-specific ids the controller demands.

    ``ap_group_ids`` and ``usergroup_id`` are mandatory — a create without
    them is rejected as ``api.err.ApGroupMissing`` — but their values are
    per-site ids no caller can know up front. Every WLAN on a site carries the
    same defaults, so copy them off an existing one when not supplied.

    Raises:
        UniFiBadRequestError: If neither argument nor site lookup yields a value.
    """
    if ap_group_ids is None or usergroup_id is None:
        wlans = (await client.list_wlans()).get("data") or []
        template = next((w for w in wlans if w.get("ap_group_ids") and w.get("usergroup_id")), {})
        ap_group_ids = ap_group_ids or template.get("ap_group_ids")
        usergroup_id = usergroup_id or template.get("usergroup_id")
    if not ap_group_ids or not usergroup_id:
        raise UniFiBadRequestError(
            "cannot resolve ap_group_ids/usergroup_id from an existing WLAN; "
            "pass them explicitly (the controller rejects a create without them)"
        )
    validate_id(usergroup_id, field="usergroup_id")
    for group_id in ap_group_ids:
        validate_id(group_id, field="ap_group_ids")
    return ap_group_ids, usergroup_id


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
        *,
        name: str,
        security: str = "wpapsk",
        wpa_mode: str = "wpa2",
        x_passphrase: str = "",
        enabled: bool = True,
        networkconf_id: str | None = None,
        is_guest: bool = False,
        l2_isolation: bool = False,
        wpa_enc: str = "ccmp",
        wlan_band: str = "both",
        ap_group_ids: list[str] | None = None,
        usergroup_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a new WLAN (Wi-Fi network).

        Omitting ``networkconf_id`` lands the SSID on the site's default
        network, so a guest SSID must pass the id of a ``purpose="guest"``
        network explicitly. ``is_guest`` marks the SSID as a guest network;
        ``l2_isolation`` additionally blocks client-to-client traffic within
        it, which the guest firewall zone does not cover on its own.

        ``ap_group_ids`` and ``usergroup_id`` are required by the controller
        but are per-site ids; when omitted they are copied from an existing
        WLAN on the site.

        Args:
            name: SSID name for the wireless network.
            security: Security mode — "wpapsk", "wpaeap", or "open".
            wpa_mode: WPA mode — "wpa2" or "wpa3".
            x_passphrase: Wi-Fi password (required for wpapsk).
            enabled: Whether the WLAN is enabled.
            networkconf_id: Network (VLAN) id to attach the SSID to.
            is_guest: Whether to mark the SSID as a guest network.
            l2_isolation: Whether to block client-to-client traffic.
            wpa_enc: WPA encryption cipher.
            wlan_band: Radio band — "both", "2g", or "5g".
            ap_group_ids: AP group ids to broadcast on; copied from the site
                when omitted.
            usergroup_id: User group id; copied from the site when omitted.

        Returns:
            The upstream API response.

        Raises:
            ToolError: If write mode is disabled, an id is malformed, or the
                site's structural ids cannot be resolved.
        """
        client = get_server_context(ctx).clients["network"]
        ap_group_ids, usergroup_id = await _resolve_structural_ids(client, ap_group_ids, usergroup_id)
        data: JsonObject = {
            "name": name,
            "security": security,
            "wpa_mode": wpa_mode,
            "wpa_enc": wpa_enc,
            "x_passphrase": x_passphrase,
            "enabled": enabled,
            "is_guest": is_guest,
            "l2_isolation": l2_isolation,
            "wlan_band": wlan_band,
            "wlan_bands": ["2g", "5g"] if wlan_band == "both" else [wlan_band],
            "ap_group_mode": "all",
            "ap_group_ids": ap_group_ids,
            "usergroup_id": usergroup_id,
        }
        if networkconf_id is not None:
            validate_id(networkconf_id, field="networkconf_id")
            data["networkconf_id"] = networkconf_id
        return redact_secrets(await client.create_wlan(data))

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
    async def unifi_network_delete_wlan(ctx: Context, wlan_id: str, confirm: bool = False) -> dict[str, Any]:
        """Delete a WLAN configuration.

        Irreversible. Pass ``confirm=True`` to proceed.

        Args:
            wlan_id: The WLAN configuration ID to delete.
            confirm: Must be ``True`` to perform the deletion.

        Returns:
            The upstream API response.

        Raises:
            ToolError: If write mode is disabled, ``wlan_id`` is malformed, or
                ``confirm`` is not ``True``.
        """
        validate_id(wlan_id, field="wlan_id")
        if not confirm:
            raise UniFiBadRequestError("deleting the WLAN is irreversible; pass confirm=True")
        return redact_secrets(await get_server_context(ctx).clients["network"].delete_wlan(wlan_id))
