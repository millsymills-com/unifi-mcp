# ADR-0001: Destructive write-tool safety conventions

- **Status**: Accepted
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
   Any new write tool that deletes, or performs a full-replacement that can drop
   or detach existing state, MUST require `confirm=True` and SHOULD set
   `destructiveHint: True`.

2. **`unifi_network_reorder_acl_rules` is brought into conformance** (this ADR's
   accompanying change): it now requires `confirm=True`, sets
   `destructiveHint: True`, and keeps the non-empty-list guard. This is safe to
   change now because the tool has not shipped in a tagged release.

3. **Legacy-network deletes are NOT retrofitted in place.** Adding `confirm` to
   them is a breaking interface change; it is deferred to a deliberate,
   versioned change (tracked in #432) rather than applied implicitly here. Until
   then the divergence is intentional and documented: legacy deletes predate the
   convention.

4. **Full-replacement updates** (`unifi_network_update_firewall_zone`,
   `unifi_network_update_dns_policy`) are NOT marked destructive. They are
   intentional modifications whose full-object-PUT footgun (omitted fields are
   dropped) is documented in their docstrings; marking every update destructive
   would dilute the signal. `destructiveHint: True` is reserved for deletes and
   for replacements that drop state without a corresponding new value (reorder).

## Consequences

- New write tools have one clear rule to follow; the next NI write group (traffic
  matching lists, firewall policies) inherits it.
- The legacy/NI delete asymmetry persists until #432's backport lands, but it is
  now a recorded decision rather than silent drift.
- Backporting `confirm` to legacy deletes (#432, option A) remains available as a
  future breaking change with a version bump; this ADR would be updated to mark
  the divergence resolved.
