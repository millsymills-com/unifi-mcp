"""Protect API tools."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastmcp import FastMCP


def register_protect_tools(mcp: FastMCP) -> None:
    """Register all Protect API tools on the server."""
    from unifi_mcp.tools.protect.access import register_protect_access_tools
    from unifi_mcp.tools.protect.cameras import register_camera_tools
    from unifi_mcp.tools.protect.device_reads import register_protect_device_read_tools
    from unifi_mcp.tools.protect.devices import register_protect_device_tools
    from unifi_mcp.tools.protect.liveviews import register_liveview_tools
    from unifi_mcp.tools.protect.media import register_media_tools
    from unifi_mcp.tools.protect.nvr import register_nvr_tools

    register_camera_tools(mcp)
    register_media_tools(mcp)
    register_nvr_tools(mcp)
    register_protect_device_tools(mcp)
    register_protect_device_read_tools(mcp)
    register_liveview_tools(mcp)
    register_protect_access_tools(mcp)
