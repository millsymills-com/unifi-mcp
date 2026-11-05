# Legacy firewall-rule update migration

`unifi_network_update_firewall_rule` accepts named fields instead of raw `data`.
`rule_id` is still required; at least one other non-null argument is required.
Each name maps to the same outgoing legacy key:

- name, ruleset, action, enabled, protocol
- src_address, dst_address, rule_index, logging
- state_new, state_established, state_invalid, state_related
- icmp_typename, ipsec
- src_firewallgroup_ids, dst_firewallgroup_ids

For example, replace `data={"enabled": False}` with `enabled=False`. False,
zero, empty strings and empty group-ID lists are sent explicitly. None omits a
field and leaves the prior partial-update behavior intact. Empty match lists
can broaden matching; use them only when that is the intended policy change.
Explicit null-clearing and arbitrary controller keys are no longer exposed.

The allowlist follows the existing full-payload fixtures in
`tests/integration/test_all_tools_live.py::TestWriteRoundtrips.test_firewall_rule_crud`
and `tests/integration/test_network_firewall_live.py`, including the additional
fields recorded in #90. This is repository evidence, not a complete official
legacy schema or new hardware validation. Ordering, connection-state flags,
controller vocabularies and rule semantics are never inferred. The controller
still validates these values; no new ordering range or action enum is assumed.
FastMCP retains normal scalar coercion. Group IDs are validated as IDs, and []
explicitly requests an empty list.

The client still performs the same PUT with only the supplied fields. No GET,
read/merge cycle or default field injection is added. Fixed endpoint routing,
readonly registration/runtime gates, dangerous-key defense, response redaction
and delete confirmation remain intact. Create's existing raw-data interface
remains pending its separate #500 migration. No live tests or service changes
were run for this update.
