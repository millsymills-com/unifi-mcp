"""Network Integration API read and write tools (#409, #423).

28 read tools plus the write tools over the official
``/proxy/network/integration/v1/`` surface, consuming
:class:`~unifi_mcp.clients.network_integration.NetworkIntegrationClient`. Every
tool is named ``unifi_network_*`` (folding into the existing ``network``
counting namespace). Read tools are tagged ``{"network_integration"}``; write
tools are tagged ``{"write", "network_integration"}`` so they are hidden in
readonly mode and degrade with the NI backend.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastmcp import FastMCP


def register_network_integration_tools(mcp: FastMCP) -> None:
    """Register every Network Integration read tool on the given server."""
    from unifi_mcp.tools.network_integration.acl import register_acl_tools
    from unifi_mcp.tools.network_integration.devices import register_devices_tools
    from unifi_mcp.tools.network_integration.dns import register_dns_tools
    from unifi_mcp.tools.network_integration.dpi import register_dpi_tools
    from unifi_mcp.tools.network_integration.firewall import register_firewall_tools
    from unifi_mcp.tools.network_integration.hotspot import register_hotspot_tools
    from unifi_mcp.tools.network_integration.networks import register_networks_tools
    from unifi_mcp.tools.network_integration.radius import register_radius_tools
    from unifi_mcp.tools.network_integration.sites import register_sites_tools
    from unifi_mcp.tools.network_integration.switching import register_switching_tools
    from unifi_mcp.tools.network_integration.traffic import register_traffic_tools
    from unifi_mcp.tools.network_integration.vpn import register_vpn_tools
    from unifi_mcp.tools.network_integration.wan import register_wan_tools

    register_sites_tools(mcp)
    register_devices_tools(mcp)
    register_dpi_tools(mcp)
    register_acl_tools(mcp)
    register_firewall_tools(mcp)
    register_dns_tools(mcp)
    register_networks_tools(mcp)
    register_hotspot_tools(mcp)
    register_traffic_tools(mcp)
    register_switching_tools(mcp)
    register_vpn_tools(mcp)
    register_wan_tools(mcp)
    register_radius_tools(mcp)
