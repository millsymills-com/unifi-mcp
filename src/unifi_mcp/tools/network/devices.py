"""Network device management tools (2 read + 5 write)."""

from __future__ import annotations

from typing import Any

from fastmcp import Context, FastMCP

from unifi_mcp.errors import UniFiNotFoundError
from unifi_mcp.tools._common import get_server_context, redact_secrets, tool_handler, validate_mac


def register_device_tools(mcp: FastMCP) -> None:
    """Register network device tools."""

    # ── Read tools ──────────────────────────────────────────────────────

    @mcp.tool(tags={"network"})
    @tool_handler()
    async def unifi_network_get_device(ctx: Context, mac: str) -> dict[str, Any]:
        """Get detailed info for a specific network device by MAC address.

        Args:
            mac: MAC address of the device (e.g., "aa:bb:cc:dd:ee:ff").

        Returns:
            The upstream API response.
        """
        validate_mac(mac, field="mac")
        result = await get_server_context(ctx).clients["network"].list_devices()
        devices: list[dict[str, Any]] = result.get("data", [])
        for device in devices:
            if device.get("mac", "").lower() == mac.lower():
                return redact_secrets(device)
        raise UniFiNotFoundError(f"Device with MAC {mac} not found")

    # ── Write tools ─────────────────────────────────────────────────────

    @mcp.tool(tags={"write", "network"}, annotations={"readOnlyHint": False, "destructiveHint": True})
    @tool_handler(write=True)
    async def unifi_network_restart_device(ctx: Context, mac: str) -> dict[str, Any]:
        """Restart an adopted network device.

        Args:
            mac: MAC address of the device to restart.

        Returns:
            The upstream API response.
        """
        validate_mac(mac, field="mac")
        return redact_secrets(await get_server_context(ctx).clients["network"].restart_device(mac))

    @mcp.tool(tags={"write", "network"}, annotations={"readOnlyHint": False, "destructiveHint": True})
    @tool_handler(write=True)
    async def unifi_network_adopt_device(ctx: Context, mac: str) -> dict[str, Any]:
        """Adopt a new device into the network.

        Args:
            mac: MAC address of the device to adopt.

        Returns:
            The upstream API response.

        NOTE: not atomic. A ``list_devices`` pre-check runs before the
        ``cmd/devmgr`` adopt POST so already-adopted devices surface a typed
        ``UniFiDeviceAlreadyAdoptedError`` (#93). A concurrent adopt between
        the two calls can still produce that error after the parallel adopt
        succeeded — agents should treat it as a soft "already done", not a
        hard failure. The legacy ``cmd/*`` API has no compare-and-set
        primitive (#151).
        """
        validate_mac(mac, field="mac")
        return redact_secrets(await get_server_context(ctx).clients["network"].adopt_device(mac))

    @mcp.tool(tags={"write", "network"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    @tool_handler(write=True)
    async def unifi_network_locate_device(ctx: Context, mac: str) -> dict[str, Any]:
        """Enable the locate LED on a device (makes it blink for identification).

        Args:
            mac: MAC address of the device.

        Returns:
            The upstream API response.
        """
        validate_mac(mac, field="mac")
        return redact_secrets(await get_server_context(ctx).clients["network"].locate_device(mac))

    @mcp.tool(tags={"write", "network"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    @tool_handler(write=True)
    async def unifi_network_unlocate_device(ctx: Context, mac: str) -> dict[str, Any]:
        """Disable the locate LED on a device (stop blinking).

        Args:
            mac: MAC address of the device.

        Returns:
            The upstream API response.
        """
        validate_mac(mac, field="mac")
        return redact_secrets(await get_server_context(ctx).clients["network"].unlocate_device(mac))

    @mcp.tool(tags={"write", "network"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    @tool_handler(write=True)
    async def unifi_network_provision_device(ctx: Context, mac: str) -> dict[str, Any]:
        """Force re-provision a device (push current configuration).

        Args:
            mac: MAC address of the device.

        Returns:
            The upstream API response.
        """
        validate_mac(mac, field="mac")
        return redact_secrets(await get_server_context(ctx).clients["network"].provision_device(mac))

    @mcp.tool(tags={"write", "network"}, annotations={"readOnlyHint": False, "destructiveHint": True})
    @tool_handler(write=True)
    async def unifi_network_forget_device(ctx: Context, mac: str) -> dict[str, Any]:
        """Forget (unadopt) a previously-adopted device.

        The device reverts to the unadopted state and can be re-adopted later.
        Any in-flight clients on that device lose connectivity during the
        transition, so this is marked destructive.

        Args:
            mac: MAC address of the adopted device.

        Returns:
            The upstream API response.

        NOTE: not atomic. A ``list_devices`` pre-check runs before the
        ``cmd/sitemgr`` forget POST, so a concurrent forget/re-adopt between
        them races; the legacy ``cmd/*`` API has no compare-and-set
        primitive (#151).
        """
        validate_mac(mac, field="mac")
        return redact_secrets(await get_server_context(ctx).clients["network"].forget_device(mac))
