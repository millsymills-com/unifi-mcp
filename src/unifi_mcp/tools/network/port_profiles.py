"""Switch port-profile management tools (2 read + 4 write)."""

from __future__ import annotations

from typing import Any

from fastmcp import Context, FastMCP

from unifi_mcp.errors import UniFiBadRequestError
from unifi_mcp.tools._common import (
    build_named_arg_body,
    get_server_context,
    redact_secrets,
    reject_dangerous_keys,
    tool_handler,
    validate_id,
    validate_mac,
)

# Mirrors the bound in ``tools/network/system.py`` — kept local rather than
# imported so the two tool modules stay independently auditable. See #151.
_PORT_IDX_MIN = 1
_PORT_IDX_MAX = 52

_PORT_PROFILE_FIELD_PATHS: dict[str, tuple[str, ...]] = {
    name: (name,) for name in ("name", "poe_mode", "forward", "native_networkconf_id")
}


def register_port_profile_tools(mcp: FastMCP) -> None:
    """Register port-profile tools (see #93)."""

    # ── Read tools ──────────────────────────────────────────────────────

    @mcp.tool(tags={"network"})
    @tool_handler()
    async def unifi_network_list_port_profiles(ctx: Context) -> dict[str, Any]:
        """List all switch port profiles (VLAN, PoE, storm-control configs).

        Args:
            ctx: FastMCP request context.

        Returns:
            The upstream API response with sensitive fields redacted.
        """
        return redact_secrets(await get_server_context(ctx).clients["network"].list_port_profiles())

    @mcp.tool(tags={"network"})
    @tool_handler()
    async def unifi_network_get_port_profile(ctx: Context, profile_id: str) -> dict[str, Any]:
        """Get a specific switch port profile by id.

        Args:
            profile_id: The port-profile ID (``_id`` from ``list_port_profiles``).

        Returns:
            The upstream API response with sensitive fields redacted.
        """
        validate_id(profile_id, field="profile_id")
        return redact_secrets(await get_server_context(ctx).clients["network"].get_port_profile(profile_id))

    # ── Write tools ─────────────────────────────────────────────────────

    @mcp.tool(tags={"write", "network"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    @tool_handler(write=True)
    async def unifi_network_create_port_profile(
        ctx: Context,
        *,
        name: str,
        poe_mode: str,
        forward: str,
        native_networkconf_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a switch port profile using named fields.

        Args:
            name: Profile name.
            poe_mode: Controller PoE mode, e.g. auto or off.
            forward: Controller forwarding mode, e.g. all, native or customize.
            native_networkconf_id: Legacy network configuration ID; required when forward is native.

        Only these four fields are exposed. Raw ``data`` and explicit
        null-clearing are unsupported; None omits the optional network ID.
        Field support follows the repository's existing port-profile fixture;
        this migration adds no live hardware validation.

        Returns:
            The upstream API response with sensitive fields redacted.
        """
        if native_networkconf_id is not None:
            validate_id(native_networkconf_id, field="native_networkconf_id")
        if forward == "native" and native_networkconf_id is None:
            raise UniFiBadRequestError("native_networkconf_id is required when forward is native")
        body = build_named_arg_body(
            tool_name="unifi_network_create_port_profile",
            field_paths=_PORT_PROFILE_FIELD_PATHS,
            named_values={
                "name": name,
                "poe_mode": poe_mode,
                "forward": forward,
                "native_networkconf_id": native_networkconf_id,
            },
            data=None,
        )
        reject_dangerous_keys(body, tool_name="unifi_network_create_port_profile")
        return redact_secrets(await get_server_context(ctx).clients["network"].create_port_profile(body))

    @mcp.tool(tags={"write", "network"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    @tool_handler(write=True)
    async def unifi_network_update_port_profile(
        ctx: Context,
        profile_id: str,
        *,
        name: str | None = None,
        poe_mode: str | None = None,
        forward: str | None = None,
        native_networkconf_id: str | None = None,
    ) -> dict[str, Any]:
        """Update named switch port-profile fields. Other fields are unchanged.

        Args:
            profile_id: The port-profile ID to update.
            name: Profile name.
            poe_mode: Controller PoE mode, e.g. auto or off.
            forward: Controller forwarding mode, e.g. all, native or customize.
            native_networkconf_id: Legacy network configuration ID.

        At least one non-null named field is required. None omits a field;
        raw ``data``, arbitrary controller keys and explicit null-clearing are
        unsupported. A partial update does not read or resolve existing IDs.

        Returns:
            The upstream API response with sensitive fields redacted.
        """
        validate_id(profile_id, field="profile_id")
        if native_networkconf_id is not None:
            validate_id(native_networkconf_id, field="native_networkconf_id")
        body = build_named_arg_body(
            tool_name="unifi_network_update_port_profile",
            field_paths=_PORT_PROFILE_FIELD_PATHS,
            named_values={
                "name": name,
                "poe_mode": poe_mode,
                "forward": forward,
                "native_networkconf_id": native_networkconf_id,
            },
            data=None,
        )
        reject_dangerous_keys(body, tool_name="unifi_network_update_port_profile")
        return redact_secrets(await get_server_context(ctx).clients["network"].update_port_profile(profile_id, body))

    @mcp.tool(tags={"write", "network"}, annotations={"readOnlyHint": False, "destructiveHint": True})
    @tool_handler(write=True)
    async def unifi_network_delete_port_profile(ctx: Context, profile_id: str, confirm: bool = False) -> dict[str, Any]:
        """Delete a switch port profile.

        Every switch port currently bound to this profile falls back to the
        default profile, which may reset VLAN tagging and PoE mode — treat
        this as destructive on any production site. Pass ``confirm=True`` to
        proceed.

        Args:
            profile_id: The port-profile ID to delete.
            confirm: Must be ``True`` to perform the deletion.

        Returns:
            The upstream API response.

        Raises:
            ToolError: If write mode is disabled, ``profile_id`` is malformed, or
                ``confirm`` is not ``True``.
        """
        validate_id(profile_id, field="profile_id")
        if not confirm:
            raise UniFiBadRequestError("deleting the port profile is irreversible; pass confirm=True")
        return redact_secrets(await get_server_context(ctx).clients["network"].delete_port_profile(profile_id))

    @mcp.tool(tags={"write", "network"}, annotations={"readOnlyHint": False, "destructiveHint": True})
    @tool_handler(write=True)
    async def unifi_network_assign_port_profile(
        ctx: Context, mac: str, port_idx: int, profile_id: str, confirm: bool = False
    ) -> dict[str, Any]:
        """Assign a port profile to a specific switch port.

        Can drop clients on that port if the new profile changes their link
        config. Pass ``confirm=True`` to proceed.

        Args:
            mac: MAC address of the switch.
            port_idx: 1-based port number on the switch. Bounded to ``1..52``;
                values outside this range raise ``UniFiBadRequestError``.
            profile_id: The port-profile ID to apply.
            confirm: Must be ``True`` to apply the profile.

        Returns:
            The upstream API response.

        Raises:
            ToolError: If write mode is disabled, ``mac``/``port_idx``/``profile_id``
                are invalid, or ``confirm`` is not ``True``.

        Note:
            Splices a ``port_overrides`` entry onto the device so the named
            port adopts the profile's VLAN / PoE / storm-control config.
        """
        validate_mac(mac, field="mac")
        validate_id(profile_id, field="profile_id")
        if not isinstance(port_idx, int) or not (_PORT_IDX_MIN <= port_idx <= _PORT_IDX_MAX):
            raise UniFiBadRequestError(
                f"port_idx must be between {_PORT_IDX_MIN} and {_PORT_IDX_MAX} (got {port_idx!r})"
            )
        if not confirm:
            raise UniFiBadRequestError("reassigning the port profile can drop clients; pass confirm=True")
        return redact_secrets(
            await get_server_context(ctx).clients["network"].assign_port_profile(mac, port_idx, profile_id)
        )
