"""Network client management tools (3 read + 4 write)."""

from __future__ import annotations

from typing import Any

from fastmcp import Context, FastMCP

from unifi_mcp.errors import UniFiBadRequestError, UniFiNotFoundError
from unifi_mcp.tools._common import get_server_context, redact_secrets, tool_handler, validate_mac

# UniFi controllers accept guest authorization durations in minutes. Capping
# at 30 days (43200 min) prevents prompt-injection from stamping an effectively
# permanent guest session — anything longer should go through an MDM-shaped
# tool, not the freeform agent surface. Lower bound of 1 rejects zero/negative
# values that the legacy API silently accepts as "permanent" on some firmwares.
# See #151.
_AUTHORIZE_GUEST_MIN_MINUTES = 1
_AUTHORIZE_GUEST_MAX_MINUTES = 43200


def register_client_tools(mcp: FastMCP) -> None:
    """Register network client tools."""

    # ── Read tools ──────────────────────────────────────────────────────

    @mcp.tool(tags={"network"})
    @tool_handler()
    async def unifi_network_get_client(ctx: Context, mac: str) -> dict[str, Any]:
        """Get detailed info for a specific client by MAC address.

        Portal credential fields and other secret keys are redacted before
        the response leaves this tool — see ``unifi_mcp._redaction`` (#146).

        Args:
            mac: MAC address of the client.

        Returns:
            The upstream API response with sensitive fields redacted.
        """
        validate_mac(mac, field="mac")
        result = await get_server_context(ctx).clients["network"].list_active_clients()
        clients: list[dict[str, Any]] = result.get("data", [])
        for client in clients:
            if client.get("mac", "").lower() == mac.lower():
                return redact_secrets(client)
        raise UniFiNotFoundError(f"Client with MAC {mac} not found among active clients")

    # ── Write tools ─────────────────────────────────────────────────────

    @mcp.tool(tags={"write", "network"}, annotations={"readOnlyHint": False, "destructiveHint": True})
    @tool_handler(write=True)
    async def unifi_network_block_client(ctx: Context, mac: str) -> dict[str, Any]:
        """Block a client from connecting to the network.

        Args:
            mac: MAC address of the client to block.

        Returns:
            The upstream API response.

        NOTE: not atomic. A ``list_all_clients`` pre-check ensures the MAC is
        known to the controller, then ``cmd/stamgr`` issues the block as a
        separate request. A client that disconnects between the two calls
        will still be blocked once it reconnects. The legacy ``cmd/*`` API
        offers no compare-and-set primitive (#151).
        """
        validate_mac(mac, field="mac")
        return redact_secrets(await get_server_context(ctx).clients["network"].block_client(mac))

    @mcp.tool(tags={"write", "network"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    @tool_handler(write=True)
    async def unifi_network_unblock_client(ctx: Context, mac: str) -> dict[str, Any]:
        """Unblock a previously blocked client.

        Args:
            mac: MAC address of the client to unblock.

        Returns:
            The upstream API response.

        NOTE: not atomic. Same TOCTOU caveat as ``unifi_network_block_client``:
        the pre-check and the ``cmd/stamgr`` POST run as separate requests
        with no compare-and-set primitive (#151).
        """
        validate_mac(mac, field="mac")
        return redact_secrets(await get_server_context(ctx).clients["network"].unblock_client(mac))

    @mcp.tool(tags={"write", "network"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    @tool_handler(write=True)
    async def unifi_network_kick_client(ctx: Context, mac: str) -> dict[str, Any]:
        """Disconnect a client from the network (they may reconnect).

        Args:
            mac: MAC address of the client to disconnect.

        Returns:
            The upstream API response.
        """
        validate_mac(mac, field="mac")
        return redact_secrets(await get_server_context(ctx).clients["network"].kick_client(mac))

    @mcp.tool(tags={"write", "network"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    @tool_handler(write=True)
    async def unifi_network_authorize_guest(ctx: Context, mac: str, minutes: int = 60) -> dict[str, Any]:
        """Authorize a guest client for a specified duration.

        Args:
            mac: MAC address of the guest client.
            minutes: Duration of authorization in minutes (default: 60).
                Bounded to ``1..43200`` (30 days); values outside this range
                raise ``UniFiBadRequestError``.

        Returns:
            The upstream API response.

        NOTE: not atomic. Same TOCTOU caveat as ``unifi_network_block_client``:
        the pre-check and the ``cmd/stamgr`` POST run as separate requests
        with no compare-and-set primitive (#151).
        """
        validate_mac(mac, field="mac")
        if not isinstance(minutes, int) or not (
            _AUTHORIZE_GUEST_MIN_MINUTES <= minutes <= _AUTHORIZE_GUEST_MAX_MINUTES
        ):
            raise UniFiBadRequestError(
                f"minutes must be between {_AUTHORIZE_GUEST_MIN_MINUTES} and "
                f"{_AUTHORIZE_GUEST_MAX_MINUTES} (got {minutes!r})"
            )
        return redact_secrets(await get_server_context(ctx).clients["network"].authorize_guest(mac, minutes=minutes))
