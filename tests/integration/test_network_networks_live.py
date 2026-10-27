"""Live Network API tests: VLAN CRUD round-trip.

Run:
    uv run pytest tests/integration/test_network_networks_live.py -v -m integration

The default LAN is fetched via the default_lan_id fixture and asserted
NEVER to be the target of an update or delete.
"""

from __future__ import annotations

import uuid

import pytest

from tests.integration.conftest import WRITE_GATE_REASON, _writes_enabled

pytestmark = pytest.mark.integration


@pytest.mark.live_write
@pytest.mark.write_gated
@pytest.mark.skipif(not _writes_enabled(), reason=WRITE_GATE_REASON)
async def test_network_crud_roundtrip(
    network_live_client,
    mcptest_prefix,
    default_lan_id,
    cleanup_register,
):
    suffix = uuid.uuid4().hex[:8]
    name = f"{mcptest_prefix}vlan-{suffix}"

    # Pick the lowest unused VLAN ID in 80-89 (separate range from session sandbox 90-99)
    existing = await network_live_client.list_networks()
    used = {n.get("vlan") for n in existing.get("data", []) if n.get("vlan")}
    chosen_vlan = next((v for v in range(80, 90) if v not in used), None)
    if chosen_vlan is None:
        pytest.skip("VLAN IDs 80-89 fully in use; cannot run CRUD test.")

    # CREATE — vlan_enabled must be True or the controller rejects with VlanUsed
    created = await network_live_client.create_network(
        {
            "name": name,
            "purpose": "corporate",
            "vlan": chosen_vlan,
            "vlan_enabled": True,
            "ip_subnet": f"10.80.{chosen_vlan}.1/24",
            "dhcpd_enabled": False,
        }
    )
    network_id = (created.get("data") or [{}])[0].get("_id")
    assert isinstance(network_id, str), f"create_network missing _id: {created}"
    assert network_id != default_lan_id, "Refusing to test against default LAN."

    cleanup_register(network_live_client.delete_network, network_id)

    # READ-BACK — assert the subnet survived, not just that an _id came back.
    # A wrong field name is dropped silently and still yields an _id, so an
    # existence-only check passes against an unusable network.
    read1 = await network_live_client.get_network(network_id)
    created_net = next((n for n in read1["data"] if n.get("_id") == network_id), None)
    assert created_net is not None
    assert created_net.get("ip_subnet") == f"10.80.{chosen_vlan}.1/24"
    assert created_net.get("vlan") == chosen_vlan

    # UPDATE — change description via attr_no_delete-safe field
    new_name = f"{name}-updated"
    await network_live_client.update_network(network_id, {"name": new_name})

    # READ-BACK after update
    read2 = await network_live_client.get_network(network_id)
    found = next((n for n in read2["data"] if n.get("_id") == network_id), None)
    assert found is not None
    assert found.get("name") == new_name

    # DELETE (assert NOT default lan first)
    assert network_id != default_lan_id
    await network_live_client.delete_network(network_id)

    # CONFIRM-GONE
    read3 = await network_live_client.list_networks()
    assert not any(n.get("_id") == network_id for n in read3["data"])
