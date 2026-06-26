"""Live Network API tests: static route CRUD round-trip.

Run:
    uv run pytest tests/integration/test_network_routes_live.py -v -m integration

Created route is enabled=False to a non-overlapping CIDR so even if cleanup
fails, the route is inert.
"""

from __future__ import annotations

import uuid

import pytest

from tests.integration.conftest import WRITE_GATE_REASON, _writes_enabled

pytestmark = pytest.mark.integration


@pytest.mark.live_write
@pytest.mark.write_gated
@pytest.mark.skipif(not _writes_enabled(), reason=WRITE_GATE_REASON)
async def test_route_crud_roundtrip(
    network_live_client,
    mcptest_prefix,
    cleanup_register,
):
    suffix = uuid.uuid4().hex[:8]
    name = f"{mcptest_prefix}route-{suffix}"

    create_payload = {
        "name": name,
        "type": "static-route",
        "enabled": False,
        "static-route_network": "192.0.2.0/24",
        "static-route_distance": 1,
        "static-route_type": "nexthop-route",
        "static-route_nexthop": "192.0.2.1",
    }

    created = await network_live_client.create_route(create_payload)
    route_id = (created.get("data") or [{}])[0].get("_id")
    assert isinstance(route_id, str), f"create_route missing _id: {created}"
    cleanup_register(network_live_client.delete_route, route_id)

    read1 = await network_live_client.get_route(route_id)
    found = next((r for r in read1["data"] if r.get("_id") == route_id), None)
    assert found is not None
    assert found.get("name") == name
    assert found.get("enabled") is False

    new_name = f"{name}-updated"
    await network_live_client.update_route(route_id, {"name": new_name})

    read2 = await network_live_client.get_route(route_id)
    found2 = next((r for r in read2["data"] if r.get("_id") == route_id), None)
    assert found2 is not None
    assert found2.get("name") == new_name

    read3 = await network_live_client.list_routes()
    assert any(r.get("_id") == route_id for r in read3["data"])
