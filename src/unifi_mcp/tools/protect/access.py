"""Protect access/identity and metadata read tools (7 read).

Protect users, ULP users, application metadata, the camera RTSPS stream
descriptor, and device-asset files.
"""

from __future__ import annotations

from typing import Any

from fastmcp import Context, FastMCP

from unifi_mcp.tools._common import get_server_context, redact_secrets, tool_handler, validate_id


def register_protect_access_tools(mcp: FastMCP) -> None:
    """Register Protect access, metadata, and asset read tools."""

    @mcp.tool(tags={"protect"})
    @tool_handler()
    async def unifi_protect_list_users(ctx: Context) -> list[dict[str, Any]]:
        """List all Protect users.

        User records carry identity fields (names, emails, account ids).
        Credential-shaped keys are redacted, but identity fields are returned
        as-is — treat the response as PII.

        Args:
            ctx: FastMCP request context.

        Returns:
            The upstream API response with sensitive fields redacted.
        """
        return redact_secrets(await get_server_context(ctx).clients["protect"].list_users())

    @mcp.tool(tags={"protect"})
    @tool_handler()
    async def unifi_protect_get_user(ctx: Context, user_id: str) -> dict[str, Any]:
        """Get detailed info for a specific Protect user.

        User records carry identity fields (names, emails, account ids).
        Credential-shaped keys are redacted, but identity fields are returned
        as-is — treat the response as PII.

        Args:
            user_id: The Protect user ID.

        Returns:
            The upstream API response with sensitive fields redacted.
        """
        validate_id(user_id, field="user_id")
        return redact_secrets(await get_server_context(ctx).clients["protect"].get_user(user_id))

    @mcp.tool(tags={"protect"})
    @tool_handler()
    async def unifi_protect_list_ulp_users(ctx: Context) -> list[dict[str, Any]]:
        """List all UniFi Local Portal (ULP) users.

        ULP records carry identity fields. Credential-shaped keys are redacted,
        but identity fields are returned as-is — treat the response as PII.

        Args:
            ctx: FastMCP request context.

        Returns:
            The upstream API response with sensitive fields redacted.
        """
        return redact_secrets(await get_server_context(ctx).clients["protect"].list_ulp_users())

    @mcp.tool(tags={"protect"})
    @tool_handler()
    async def unifi_protect_get_ulp_user(ctx: Context, ulp_user_id: str) -> dict[str, Any]:
        """Get detailed info for a specific ULP user.

        ULP records carry identity fields. Credential-shaped keys are redacted,
        but identity fields are returned as-is — treat the response as PII.

        Args:
            ulp_user_id: The ULP user ID.

        Returns:
            The upstream API response with sensitive fields redacted.
        """
        validate_id(ulp_user_id, field="ulp_user_id")
        return redact_secrets(await get_server_context(ctx).clients["protect"].get_ulp_user(ulp_user_id))

    @mcp.tool(tags={"protect"})
    @tool_handler()
    async def unifi_protect_get_meta_info(ctx: Context) -> dict[str, Any]:
        """Get Protect application metadata (version, capabilities).

        Args:
            ctx: FastMCP request context.

        Returns:
            The upstream API response with sensitive fields redacted.
        """
        return redact_secrets(await get_server_context(ctx).clients["protect"].get_meta_info())

    @mcp.tool(tags={"protect"})
    @tool_handler()
    async def unifi_protect_get_rtsps_stream(
        ctx: Context, camera_id: str, qualities: list[str] | None = None
    ) -> dict[str, Any]:
        """Get the RTSPS stream descriptor(s) for a camera.

        The stream URLs carry the bearer credential in their path alias
        (``rtsps://host:7441/<alias>``), so each is redacted by stream-URL
        shape before the response leaves this tool (#455).

        Args:
            camera_id: The camera ID.
            qualities: Optional stream qualities to request (e.g.
                ["high", "medium"]); omit for the controller default set.

        Returns:
            The upstream API response with sensitive fields redacted.

        Note:
            A camera with no active RTSPS stream may return ``HTTP 404`` or an
            empty body; tolerate both (same precedent as
            ``unifi_protect_export_video``, #227). The tool stays registered
            either way.
        """
        validate_id(camera_id, field="camera_id")
        return redact_secrets(
            await get_server_context(ctx).clients["protect"].get_rtsps_stream(camera_id, qualities=qualities)
        )

    @mcp.tool(tags={"protect"})
    @tool_handler()
    async def unifi_protect_get_file_asset(ctx: Context, file_type: str) -> dict[str, Any]:
        """Get a Protect device-asset descriptor for a file type.

        Args:
            file_type: The file/asset type segment.

        Returns:
            The upstream API response with sensitive fields redacted.

        Note:
            The ``files/{fileType}`` content-type is unverified against live
            hardware. This tool assumes JSON metadata. If the endpoint serves
            raw bytes, it should move to ``media.py`` with a byte cap modeled
            on ``unifi_protect_get_snapshot`` (#407).
        """
        validate_id(file_type, field="file_type")
        return redact_secrets(await get_server_context(ctx).clients["protect"].get_file_asset(file_type))
