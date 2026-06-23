"""Network Integration network-reference read tool."""

from __future__ import annotations

from typing import Any

from fastmcp import Context, FastMCP

from unifi_mcp.tools._common import get_server_context, redact_secrets, tool_handler, validate_id


def register_networks_tools(mcp: FastMCP) -> None:
    """Register the Network Integration network-reference tool."""

    @mcp.tool(tags={"network_integration"})
    @tool_handler()
    async def unifi_network_get_network_references(ctx: Context, network_id: str) -> dict[str, Any]:
        """Get dependency references for a network (Network Integration API).

        Distinct from the legacy ``unifi_network_get_network`` (which returns the
        network config); this returns what other objects depend on it.

        Args:
            ctx: FastMCP request context.
            network_id: The network id.

        Returns:
            The upstream API response with sensitive fields redacted.

        Raises:
            ToolError: If ``network_id`` is malformed.
        """
        validate_id(network_id, field="network_id")
        return redact_secrets(
            await get_server_context(ctx).clients["network_integration"].get_network_references(network_id)
        )
