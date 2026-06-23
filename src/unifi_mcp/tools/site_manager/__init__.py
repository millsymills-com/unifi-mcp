"""Site Manager API tools."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastmcp import FastMCP


def register_site_manager_tools(mcp: FastMCP) -> None:
    """Register all Site Manager API tools on the server."""
    from unifi_mcp.tools.site_manager.discovery import (
        register_site_manager_tools as _register_discovery,
    )
    from unifi_mcp.tools.site_manager.metrics import register_site_manager_metrics_tools
    from unifi_mcp.tools.site_manager.sdwan import register_site_manager_sdwan_tools

    _register_discovery(mcp)
    register_site_manager_metrics_tools(mcp)
    register_site_manager_sdwan_tools(mcp)
