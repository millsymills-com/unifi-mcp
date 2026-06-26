"""Live Network API tests: firewall rule + group CRUD round-trips.

Run:
    uv run pytest tests/integration/test_network_firewall_live.py -v -m integration
"""

from __future__ import annotations

import uuid

import pytest

from tests.integration.conftest import WRITE_GATE_REASON, _writes_enabled

pytestmark = pytest.mark.integration


@pytest.mark.live_write
@pytest.mark.write_gated
@pytest.mark.skipif(not _writes_enabled(), reason=WRITE_GATE_REASON)
async def test_firewall_rule_crud_roundtrip(
    network_live_client,
    mcptest_prefix,
    cleanup_register,
):
    suffix = uuid.uuid4().hex[:8]
    name = f"{mcptest_prefix}fw-rule-{suffix}"

    # NOTE: rest/firewallrule rejects partial payloads with FirewallRuleFieldsRequired
    # (issue #90). Provide the full required field set.
    create_payload = {
        "name": name,
        "ruleset": "LAN_IN",
        "rule_index": 20000,
        "action": "drop",
        "protocol": "all",
        "src_address": "192.0.2.0/24",
        "dst_address": "192.0.2.0/24",
        "enabled": True,
        "logging": False,
        "state_new": True,
        "state_established": True,
        "state_invalid": True,
        "state_related": True,
        "icmp_typename": "",
        "ipsec": "",
        "src_firewallgroup_ids": [],
        "dst_firewallgroup_ids": [],
    }

    created = await network_live_client.create_firewall_rule(create_payload)
    rule_id = (created.get("data") or [{}])[0].get("_id")
    assert isinstance(rule_id, str), f"create_firewall_rule missing _id: {created}"
    cleanup_register(network_live_client.delete_firewall_rule, rule_id)

    read1 = await network_live_client.get_firewall_rule(rule_id)
    found = next((r for r in read1["data"] if r.get("_id") == rule_id), None)
    assert found is not None
    assert found.get("action") == "drop"

    await network_live_client.update_firewall_rule(rule_id, {"action": "reject"})

    read2 = await network_live_client.get_firewall_rule(rule_id)
    found2 = next((r for r in read2["data"] if r.get("_id") == rule_id), None)
    assert found2 is not None
    assert found2.get("action") == "reject"

    await network_live_client.delete_firewall_rule(rule_id)
    read3 = await network_live_client.list_firewall_rules()
    assert not any(r.get("_id") == rule_id for r in read3["data"])


@pytest.mark.live_write
@pytest.mark.write_gated
@pytest.mark.skipif(not _writes_enabled(), reason=WRITE_GATE_REASON)
async def test_firewall_group_crud_roundtrip(
    network_live_client,
    mcptest_prefix,
    cleanup_register,
):
    suffix = uuid.uuid4().hex[:8]
    name = f"{mcptest_prefix}fw-grp-{suffix}"

    created = await network_live_client.create_firewall_group(
        {
            "name": name,
            "group_type": "address-group",
            "group_members": ["192.0.2.10", "192.0.2.11"],
        }
    )
    group_id = (created.get("data") or [{}])[0].get("_id")
    assert isinstance(group_id, str), f"create_firewall_group missing _id: {created}"
    cleanup_register(network_live_client.delete_firewall_group, group_id)

    read1 = await network_live_client.get_firewall_group(group_id)
    found = next((g for g in read1["data"] if g.get("_id") == group_id), None)
    assert found is not None
    assert set(found.get("group_members") or []) >= {"192.0.2.10", "192.0.2.11"}

    await network_live_client.update_firewall_group(
        group_id,
        {"name": name, "group_type": "address-group", "group_members": ["192.0.2.10", "192.0.2.11", "192.0.2.12"]},
    )

    read2 = await network_live_client.get_firewall_group(group_id)
    found2 = next((g for g in read2["data"] if g.get("_id") == group_id), None)
    assert found2 is not None
    assert "192.0.2.12" in (found2.get("group_members") or [])

    await network_live_client.delete_firewall_group(group_id)
    read3 = await network_live_client.list_firewall_groups()
    assert not any(g.get("_id") == group_id for g in read3["data"])
