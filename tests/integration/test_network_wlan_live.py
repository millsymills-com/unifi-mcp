"""Live Network API tests: WLAN CRUD round-trip.

Depends on the session-scoped test_vlan_id fixture.
Run:
    uv run pytest tests/integration/test_network_wlan_live.py -v -m integration
"""

from __future__ import annotations

import os
import uuid

import pytest

pytestmark = pytest.mark.integration


def _writes_enabled() -> bool:
    return os.environ.get("UNIFI_MODE", "readonly").lower() == "readwrite" and os.environ.get(
        "LIVE_TEST_WRITES", ""
    ).strip() in {"1", "true", "yes"}


WRITE_GATE_REASON = "Set UNIFI_MODE=readwrite and LIVE_TEST_WRITES=1 to run write tests"


@pytest.mark.live_write
@pytest.mark.write_gated
@pytest.mark.skipif(not _writes_enabled(), reason=WRITE_GATE_REASON)
async def test_wlan_crud_roundtrip(
    network_live_client,
    mcptest_prefix,
    test_vlan_id,
    cleanup_register,
):
    suffix = uuid.uuid4().hex[:8]
    ssid = f"{mcptest_prefix}wlan-{suffix}"
    initial_passphrase = "InitialPass123!"  # noqa: S105
    updated_passphrase = "UpdatedPass456!"  # noqa: S105

    # Resolve an AP group ID — controller rejects (api.err.ApGroupMissing) without one.
    # Pull from the first existing WLAN rather than hard-coding an environment variable.
    existing_wlans = await network_live_client.list_wlans()
    first_wlan = next(iter(existing_wlans.get("data", [])), None)
    ap_group_ids = first_wlan.get("ap_group_ids", []) if first_wlan else []
    if not ap_group_ids:
        pytest.skip("No AP group IDs found on existing WLANs; cannot create test WLAN.")

    # CREATE — minimal payload from the MCP tool layer; adjust if controller demands more
    create_payload = {
        "name": ssid,
        "security": "wpapsk",
        "wpa_mode": "wpa2",
        "x_passphrase": initial_passphrase,
        "enabled": True,
        # Required by controller: api.err.ApGroupMissing without this field
        "ap_group_ids": ap_group_ids,
    }
    # Bind to sandbox VLAN so the WLAN is isolated from the default LAN
    create_payload["networkconf_id"] = test_vlan_id

    try:
        created = await network_live_client.create_wlan(create_payload)
    except Exception as exc:
        if "TooManyWirelessNetwork" in str(exc):
            pytest.skip(
                f"Controller at WLAN capacity ({len(existing_wlans.get('data', []))} WLANs); "
                "remove one before running this test."
            )
        raise
    wlan_id = (created.get("data") or [{}])[0].get("_id")
    assert isinstance(wlan_id, str), f"create_wlan missing _id: {created}"
    cleanup_register(network_live_client.delete_wlan, wlan_id)

    # READ-BACK
    read1 = await network_live_client.get_wlan(wlan_id)
    found = next((w for w in read1["data"] if w.get("_id") == wlan_id), None)
    assert found is not None
    assert found.get("name") == ssid

    # UPDATE — change passphrase
    await network_live_client.update_wlan(wlan_id, {"x_passphrase": updated_passphrase})

    # READ-BACK after update — passphrase is often redacted in responses, so
    # assert the WLAN still exists with the same _id (round-trip semantics).
    read2 = await network_live_client.get_wlan(wlan_id)
    found2 = next((w for w in read2["data"] if w.get("_id") == wlan_id), None)
    assert found2 is not None

    # DELETE
    await network_live_client.delete_wlan(wlan_id)

    # CONFIRM-GONE
    read3 = await network_live_client.list_wlans()
    assert not any(w.get("_id") == wlan_id for w in read3["data"])
