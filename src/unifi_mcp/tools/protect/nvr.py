"""Protect NVR tools (1 read)."""

from __future__ import annotations

from typing import Any

from fastmcp import Context, FastMCP

from unifi_mcp.errors import handle_client_error
from unifi_mcp.tools._common import get_server_context, redact_secrets


def register_nvr_tools(mcp: FastMCP) -> None:
    """Register NVR tools."""

    @mcp.tool(tags={"protect"})
    async def unifi_protect_get_nvr(ctx: Context) -> dict[str, Any]:
        """Get NVR (Network Video Recorder) status and configuration.

        ``ssoToken`` and other credential fields are redacted before the
        response leaves this tool — see ``unifi_mcp._redaction`` (#146).

        Args:
            ctx: FastMCP request context.

        Returns:
            The upstream API response with sensitive fields redacted.
        """
        try:
            context = get_server_context(ctx)
            return redact_secrets(await context.clients["protect"].get_nvr())
        except Exception as e:
            handle_client_error(e)
