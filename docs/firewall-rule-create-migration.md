# Legacy firewall-rule creation migration

`unifi_network_create_firewall_rule` accepts named fields instead of raw `data`,
using the same 17-field allowlist as
[firewall updates](firewall-rule-update-migration.md). Each named value maps to
the identically spelled outgoing controller key. Raw bodies, arbitrary keys and
explicit null-clearing are unsupported.

`name` and `ruleset` remain required. The existing `action="drop"`,
`enabled=True` and `protocol="all"` defaults remain unchanged. Every added field
is optional/None by default: `rule_index`, `logging`, four `state_*` flags,
`icmp_typename`, `ipsec`, and the two group-ID lists. Source/destination
addresses keep their existing None defaults. None omits an optional field;
False, zero, empty strings and [] are sent explicitly. Group IDs are validated.
FastMCP retains normal scalar coercion.

A minimum Python call is not necessarily a valid controller request. #90 records
modern controllers rejecting incomplete bodies. Supply the explicit ordering,
flags and selectors required by your controller. The tool does not choose an
index, guess connection-state flags, query existing rules, or widen its
allowlist when the controller asks for another field. Controller vocabularies,
ordering ranges and rule semantics remain controller-validated.

The full-payload fixture in
`tests/integration/test_all_tools_live.py::TestWriteRoundtrips.test_firewall_rule_crud`
now passes its complete dictionary as named tool arguments. It supplies a
`rule_index`, all state/logging flags, explicit selectors and group-ID lists;
this is an example field set from repository evidence, not a complete official
legacy schema or a claim of fresh hardware validation. Replace `data=payload`
with named arguments matching these fields. The update and cleanup behavior
remain covered by the offline real-handler roundtrip tests.

Runtime/declarative write gates, dangerous-key defense, response redaction and
delete confirmation remain intact. No live tests, device writes, controller
queries or service changes were run for this migration. #500 remains open for
the remaining resource interfaces, and the held WLAN change remains separate.
