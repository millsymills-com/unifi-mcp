"""MCP tool definitions for UniFi APIs.

``register_all_tools`` is the single entry point used by
``server.create_server``: it registers every configured API's tools, then
hides the write-tagged ones unless ``UNIFI_MODE=readwrite`` (PROTO-005 /
PROTO-006).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from unifi_mcp.config import UniFiConfig

logger = logging.getLogger(__name__)


def _register_for_each_api(mcp: FastMCP, config: UniFiConfig) -> None:
    if config.network_enabled:
        from unifi_mcp.tools.network import register_network_tools

        register_network_tools(mcp)
        logger.info("Registered Network tools")

    if config.protect_enabled:
        from unifi_mcp.tools.protect import register_protect_tools

        register_protect_tools(mcp)
        logger.info("Registered Protect tools")

    if config.site_manager_enabled:
        from unifi_mcp.tools.site_manager import register_site_manager_tools

        register_site_manager_tools(mcp)
        logger.info("Registered Site Manager tools")


def register_all_tools(mcp: FastMCP, config: UniFiConfig) -> None:
    """Register every configured API's tools, hiding writes in readonly mode.

    Write-tagged tools are disabled unless ``config.writes_enabled`` (the
    explicit ``UNIFI_MODE=readwrite`` opt-in of PROTO-005 / PROTO-006), so the
    served tool list is mutation-free by default.
    """
    _register_for_each_api(mcp, config)
    if not config.writes_enabled:
        mcp.disable(tags={"write"})
