"""Live Network API tests: port-forward CRUD round-trip.

Run:
    uv run pytest tests/integration/test_network_port_forward_live.py -v -m integration

Created port-forward is enabled=False so even if cleanup fails, the rule is inert.
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
async def test_port_forward_crud_roundtrip(
    network_live_client,
    mcptest_prefix,
    cleanup_register,
):
    suffix = uuid.uuid4().hex[:8]
    name = f"{mcptest_prefix}pf-{suffix}"

    create_payload = {
        "name": name,
        "proto": "tcp",
        "dst_port": "60099",
        "fwd": "10.99.99.10",
        "fwd_port": "8080",
        "enabled": False,
    }

    created = await network_live_client.create_port_forward(create_payload)
    pf_id = (created.get("data") or [{}])[0].get("_id")
    assert isinstance(pf_id, str), f"create_port_forward missing _id: {created}"
    cleanup_register(network_live_client.delete_port_forward, pf_id)

    read1 = await network_live_client.get_port_forward(pf_id)
    found = next((p for p in read1["data"] if p.get("_id") == pf_id), None)
    assert found is not None
    assert found.get("enabled") is False

    new_name = f"{name}-updated"
    await network_live_client.update_port_forward(pf_id, {"name": new_name})

    read2 = await network_live_client.get_port_forward(pf_id)
    found2 = next((p for p in read2["data"] if p.get("_id") == pf_id), None)
    assert found2 is not None
    assert found2.get("name") == new_name

    await network_live_client.delete_port_forward(pf_id)
    read3 = await network_live_client.list_port_forwards()
    assert not any(p.get("_id") == pf_id for p in read3["data"])
