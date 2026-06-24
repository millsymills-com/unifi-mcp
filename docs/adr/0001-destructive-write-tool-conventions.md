# ADR-0001: Destructive write-tool safety conventions

- **Status**: Accepted (legacy backport completed 2026-06-24, see Update)
- **Date**: 2026-06-23

## Context

The Network Integration (NI) write tools added in #424/#428/#429/#430 introduced
two safety patterns that the pre-existing legacy-network write tools do not share,
creating an inconsistency across the two write surfaces (surfaced as #431 and #432):

1. **`confirm` gate on destructive tools.** Every NI delete
   (`unifi_network_delete_acl_rule`, `…_dns_policy`, `…_firewall_zone`,
   `…_voucher`, `…_vouchers`) requires `confirm=True` and raises
   `UniFiBadRequestError` otherwise. The legacy-network deletes
   (`unifi_network_delete_firewall_rule`, `…_network`, `…_port_forward`,
   `…_port_profile`, `…_wlan`, routing deletes, etc.) take no `confirm` argument.

2. **Full-replacement writes.** `unifi_network_reorder_acl_rules` is a
   full-replacement PUT: any rule id omitted from the list silently loses its
   enforcement position. It originally carried `destructiveHint: False` and no
   `confirm` gate, while a single-rule delete — lower blast radius — carried both.

Adding a required `confirm` argument to the already-shipped legacy deletes is a
breaking change to those tools' contracts (an agent that calls them today would
start erroring), so it cannot be done silently.

## Decision

1. **`confirm=True` is the standard for destructive write tools going forward.**
   Any write tool marked `destructiveHint: True` MUST require `confirm=True` and
   raise `UniFiBadRequestError` otherwise. The two are now a single invariant —
   `destructiveHint: True` iff a `confirm` boolean parameter exists — asserted
   server-wide by `tests/unit/tools/test_confirm_gate.py`. This applies to
   deletes, to full-replacements that drop or detach state, and to disruptive
   operations (device restart/adopt/forget/upgrade, port power-cycle, DPI reset,
   port-profile assignment, client block).

2. **`unifi_network_reorder_acl_rules` is brought into conformance** (this ADR's
   accompanying change): it now requires `confirm=True`, sets
   `destructiveHint: True`, and keeps the non-empty-list guard. This is safe to
   change now because the tool has not shipped in a tagged release.

3. **Legacy-network destructive tools are retrofitted (see Update).** Originally
   this ADR deferred the change as a breaking interface change tracked in #432.
   That backport has since landed: all 15 `destructiveHint: True` legacy-network
   tools now carry the `confirm` gate, shipped as the breaking `0.4.0` release.

4. **Full-replacement updates** (`unifi_network_update_firewall_zone`,
   `unifi_network_update_dns_policy`) are NOT marked destructive. They are
   intentional modifications whose full-object-PUT footgun (omitted fields are
   dropped) is documented in their docstrings; marking every update destructive
   would dilute the signal. `destructiveHint: True` is reserved for deletes and
   for replacements that drop state without a corresponding new value (reorder).

## Consequences

- New write tools have one clear rule to follow; the next NI write group (traffic
  matching lists, firewall policies) inherits it.
- The legacy/NI delete asymmetry is resolved: the gate is uniform across both
  write surfaces and enforced by a single invariant test.

## Update (2026-06-24)

The legacy backport in decision 3 landed. `confirm=True` was added to all 15
`destructiveHint: True` legacy-network tools — the 7 deletes plus
`restart_device`, `adopt_device`, `forget_device`, `upgrade_device`,
`power_cycle_port`, `reset_dpi`, `assign_port_profile`, and `block_client`. This
is a breaking change to those tool contracts, shipped as `0.4.0` (#432).

The convention from decision 1 was widened in the process: rather than gating only
deletes and state-dropping replacements, the gate now tracks `destructiveHint`
exactly, so the rule is a single testable biconditional with no fuzzy boundary.
`tests/unit/tools/test_confirm_gate.py` fails if any future tool sets
`destructiveHint: True` without a `confirm` parameter, or vice versa.
