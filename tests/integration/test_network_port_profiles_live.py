"""Live Network API tests: port-profile CRUD round-trip.

Run:
    uv run pytest tests/integration/test_network_port_profiles_live.py -v -m integration

assign_port_profile is NOT covered here — it's disruptive (changes a real
switch port) and lives in test_network_devices_live.py.
"""

from __future__ import annotations

import uuid

import pytest

from tests.integration.conftest import WRITE_GATE_REASON, _writes_enabled

pytestmark = pytest.mark.integration


@pytest.mark.live_write
@pytest.mark.write_gated
@pytest.mark.skipif(not _writes_enabled(), reason=WRITE_GATE_REASON)
async def test_port_profile_crud_roundtrip(
    network_live_client,
    mcptest_prefix,
    test_vlan_id,
    cleanup_register,
):
    suffix = uuid.uuid4().hex[:8]
    name = f"{mcptest_prefix}pp-{suffix}"

    # Minimum from clients/network.py docstring: name, poe_mode, forward.
    # Also include native_networkconf_id to bind to the sandbox VLAN.
    create_payload = {
        "name": name,
        "forward": "native",
        "native_networkconf_id": test_vlan_id,
        "poe_mode": "off",
    }

    created = await network_live_client.create_port_profile(create_payload)
    profile_id = (created.get("data") or [{}])[0].get("_id")
    assert isinstance(profile_id, str), f"create_port_profile missing _id: {created}"
    cleanup_register(network_live_client.delete_port_profile, profile_id)

    read1 = await network_live_client.get_port_profile(profile_id)
    found = next((p for p in read1["data"] if p.get("_id") == profile_id), None)
    assert found is not None
    assert found.get("poe_mode") == "off"

    # UPDATE — toggle poe_mode
    await network_live_client.update_port_profile(profile_id, {"poe_mode": "auto"})

    read2 = await network_live_client.get_port_profile(profile_id)
    found2 = next((p for p in read2["data"] if p.get("_id") == profile_id), None)
    assert found2 is not None
    assert found2.get("poe_mode") == "auto"

    await network_live_client.delete_port_profile(profile_id)
    read3 = await network_live_client.list_port_profiles()
    assert not any(p.get("_id") == profile_id for p in read3["data"])
