"""Live Network API tests. Require a reachable UniFi controller + UNIFI_NETWORK_API.

Run manually:

    uv run pytest tests/integration/test_network_live.py -v -m integration

Each test skips individually if the ``network_live_client`` fixture can't be built.
"""

from __future__ import annotations

import pytest

from unifi_mcp.errors import UniFiUnsupportedError

pytestmark = pytest.mark.integration


async def test_validate_connection(network_live_client):
    assert await network_live_client.validate_connection() is True


async def test_get_health_returns_subsystems(network_live_client):
    result = await network_live_client.get_health()
    assert "data" in result
    subsystems = {entry.get("subsystem") for entry in result["data"]}
    # The UniFi health endpoint reliably returns at least WAN + LAN.
    assert "wan" in subsystems
    assert "lan" in subsystems


async def test_list_devices_returns_list(network_live_client):
    result = await network_live_client.list_devices()
    assert "data" in result
    assert isinstance(result["data"], list)


async def test_list_active_clients_returns_list(network_live_client):
    result = await network_live_client.list_active_clients()
    assert "data" in result
    assert isinstance(result["data"], list)


async def test_get_sysinfo_has_version(network_live_client):
    result = await network_live_client.get_sysinfo()
    assert "data" in result
    data = result["data"]
    assert data, "Expected at least one sysinfo entry"
    assert any("version" in entry for entry in data)


async def test_list_events_returns_shape(network_live_client):
    # Some controllers reject legacy alarm reads with 400 or 404 (#543).
    try:
        result = await network_live_client.list_events(limit=1)
    except UniFiUnsupportedError as exc:
        pytest.skip(str(exc))
    assert "data" in result
    assert isinstance(result["data"], list)


async def test_list_devices_basic_returns_list(network_live_client):
    result = await network_live_client.list_devices_basic()
    assert "data" in result
    assert isinstance(result["data"], list)


async def test_list_configured_clients_returns_list(network_live_client):
    result = await network_live_client.list_configured_clients()
    assert "data" in result
    assert isinstance(result["data"], list)


async def test_list_all_clients_returns_list(network_live_client):
    result = await network_live_client.list_all_clients()
    assert "data" in result
    assert isinstance(result["data"], list)


async def test_get_dpi_stats_returns_shape(network_live_client):
    result = await network_live_client.get_dpi_stats()
    assert "data" in result
    assert isinstance(result["data"], list)


async def test_active_clients_lookup_by_mac(network_live_client):
    """Smoke test for the read pattern that unifi_network_get_client uses internally:
    list_active_clients() then filter by MAC."""
    actives = await network_live_client.list_active_clients()
    if not actives.get("data"):
        pytest.skip("No active clients to exercise lookup-by-mac pattern.")
    sample = actives["data"][0]
    mac = sample.get("mac")
    assert mac, "active client missing mac"
    found = next(
        (c for c in actives["data"] if c.get("mac", "").lower() == mac.lower()),
        None,
    )
    assert found is not None
    assert found.get("mac", "").lower() == mac.lower()


async def test_target_device_present_in_list(network_live_client, test_target_mac):
    """Smoke test for the read pattern that unifi_network_get_device uses internally:
    list_devices() then filter by MAC. Asserts the configured test target is
    discoverable so that disruptive tests in later tasks won't NEEDS_CONTEXT."""
    devices = await network_live_client.list_devices()
    found = next(
        (d for d in devices.get("data", []) if d.get("mac", "").lower() == test_target_mac),
        None,
    )
    assert found is not None, f"test_target_mac {test_target_mac} not in list_devices"
    assert found.get("mac", "").lower() == test_target_mac


async def test_list_firewall_rules_returns_list(network_live_client):
    result = await network_live_client.list_firewall_rules()
    assert "data" in result
    assert isinstance(result["data"], list)


async def test_get_firewall_rule_returns_doc(network_live_client):
    rules = await network_live_client.list_firewall_rules()
    if not rules.get("data"):
        pytest.skip("No firewall rules configured; cannot exercise get_firewall_rule.")
    rule_id = rules["data"][0]["_id"]
    result = await network_live_client.get_firewall_rule(rule_id)
    assert "data" in result
    assert any(r.get("_id") == rule_id for r in result["data"])


async def test_list_firewall_groups_returns_list(network_live_client):
    result = await network_live_client.list_firewall_groups()
    assert "data" in result
    assert isinstance(result["data"], list)


async def test_get_firewall_group_returns_doc(network_live_client):
    groups = await network_live_client.list_firewall_groups()
    if not groups.get("data"):
        pytest.skip("No firewall groups configured; cannot exercise get_firewall_group.")
    group_id = groups["data"][0]["_id"]
    result = await network_live_client.get_firewall_group(group_id)
    assert "data" in result
    assert any(g.get("_id") == group_id for g in result["data"])


async def test_list_networks_returns_list(network_live_client):
    result = await network_live_client.list_networks()
    assert "data" in result
    assert isinstance(result["data"], list)


async def test_get_network_lookup_pattern(network_live_client):
    networks = await network_live_client.list_networks()
    if not networks.get("data"):
        pytest.skip("No networks configured; cannot exercise get_network.")
    network_id = networks["data"][0]["_id"]
    result = await network_live_client.get_network(network_id)
    assert "data" in result
    assert any(n.get("_id") == network_id for n in result["data"])


async def test_list_port_forwards_returns_list(network_live_client):
    result = await network_live_client.list_port_forwards()
    assert "data" in result
    assert isinstance(result["data"], list)


async def test_get_port_forward_returns_doc(network_live_client):
    port_forwards = await network_live_client.list_port_forwards()
    if not port_forwards.get("data"):
        pytest.skip("No port forwarding rules configured; cannot exercise get_port_forward.")
    pf_id = port_forwards["data"][0]["_id"]
    result = await network_live_client.get_port_forward(pf_id)
    assert "data" in result
    assert any(pf.get("_id") == pf_id for pf in result["data"])


async def test_list_port_profiles_returns_list(network_live_client):
    result = await network_live_client.list_port_profiles()
    assert "data" in result
    assert isinstance(result["data"], list)


async def test_get_port_profile_returns_doc(network_live_client):
    profiles = await network_live_client.list_port_profiles()
    if not profiles.get("data"):
        pytest.skip("No port profiles configured; cannot exercise get_port_profile.")
    profile_id = profiles["data"][0]["_id"]
    result = await network_live_client.get_port_profile(profile_id)
    assert "data" in result
    assert any(p.get("_id") == profile_id for p in result["data"])


async def test_list_routes_returns_list(network_live_client):
    result = await network_live_client.list_routes()
    assert "data" in result
    assert isinstance(result["data"], list)


async def test_get_route_returns_doc(network_live_client):
    routes = await network_live_client.list_routes()
    if not routes.get("data"):
        pytest.skip("No static routes configured; cannot exercise get_route.")
    route_id = routes["data"][0]["_id"]
    result = await network_live_client.get_route(route_id)
    assert "data" in result
    assert any(r.get("_id") == route_id for r in result["data"])


async def test_list_wlans_returns_list(network_live_client):
    result = await network_live_client.list_wlans()
    assert "data" in result
    assert isinstance(result["data"], list)


async def test_get_wlan_returns_doc(network_live_client):
    wlans = await network_live_client.list_wlans()
    if not wlans.get("data"):
        pytest.skip("No WLANs configured; cannot exercise get_wlan.")
    wlan_id = wlans["data"][0]["_id"]
    result = await network_live_client.get_wlan(wlan_id)
    assert "data" in result
    assert any(w.get("_id") == wlan_id for w in result["data"])
