# Codebase report remediation issue plan

Reviewed 2026-10-27 against `ae901522d16eedf6cf0ec85e8376f0499f6d8bfb` and the existing, uncommitted sweep changes. Repository: [millsymills-com/unifi-mcp](https://github.com/millsymills-com/unifi-mcp).

Five GitHub issues were filed on 2026-10-27: one to deliver the four fixes already present locally, two for probe cleanup failures, one for logging configuration, and one for optional exception-layer cleanup. The first four address confirmed defects or test gaps; the fifth tracks a confirmed dependency with low current impact. The sections below preserve their planned scope; published issues contain baseline source permalinks and numbered dependency references.

| Plan item | Filed issue | Triage state |
| --- | --- | --- |
| A | [#562 Deliver the validated startup configuration and offline test fixes](https://github.com/millsymills-com/unifi-mcp/issues/562) | `ready-for-agent` |
| B | [#563 Pass resolved raw body logging policy into every API client](https://github.com/millsymills-com/unifi-mcp/issues/563) | `ready-for-agent` |
| C | [#564 Clean up each created probe route before continuing after a failure](https://github.com/millsymills-com/unifi-mcp/issues/564) | `ready-for-agent` |
| D | [#565 Close the archive probe client when its initial alarm read fails](https://github.com/millsymills-com/unifi-mcp/issues/565) | `ready-for-agent` |
| E | [#566 Separate transport exceptions from FastMCP error presentation](https://github.com/millsymills-com/unifi-mcp/issues/566) | `needs-triage` |

Sources: [codebase recon](../codebase-recon-report.md), [Brooks architecture audit](../brooks-audit-report.md), [debt assessment](../brooks-debt-report.md), [health dashboard](../brooks-health-report.md), [test review](../brooks-test-report.md), and [full sweep](../brooks-sweep-report.md).

## Report reconciliation

The six reports describe overlapping snapshots. Deduplicate by cause and use current code to establish status; their scores are not comparable release gates.

| Source finding | Current validation | Planned disposition |
| --- | --- | --- |
| Recon hotspots, fix-message frequency, ownership concentration, and slower commit activity | Historical signals, not demonstrated defects | Use to prioritize server and base-client review; no remediation issue from these metrics alone |
| Architecture explicit-config warning; debt D1; health R2; sweep S1 | `create_server` now captures its configuration in a lifespan closure; two MCP-session regression cases pass | Issue A tracks delivery of the existing local fix |
| Test T5; sweep S2 | Generic create/update cases and network, WLAN, firewall, and route updates now assert decoded payload equality | Issue A tracks delivery of the existing local fix |
| Test T2; sweep S3 | Offline fixture removes case-insensitive `UNIFI_*` variables and suppresses default dotenv loading; conflicting-environment checks pass | Issue A tracks delivery of the existing local fix |
| Test T6; sweep S4 | Explicit offline test job and required gate exist locally; all 16 selected cases pass | Issue A tracks delivery of the existing local fix |
| Architecture logging warning; debt D2; health R3; sweep S5 | Explicit and dotenv settings still disagree with HTTP logging | Issue B |
| Sweep S6 route-probe branch | Read-back failure leaves a route; repeated deletion failures create additional routes | Issue C |
| Sweep S6 archive-probe branch | Initial GET failure bypasses client cleanup | Issue D |
| Architecture dependency suggestion; debt D3; health R5; sweep S7 | Importing `unifi_mcp.clients.network` in a fresh Python process loads FastMCP through `errors.py` | Issue E, low-priority enhancement |

The sweep counts seven distinct findings. Splitting its two probe failures produces eight remediation units; grouping its four completed local fixes into a delivery issue produces five tickets. The health report's earlier test score does not invalidate the later, concrete test findings.

## Existing tracker overlap

The duplicate check covered all 213 issues returned by `gh issue list --state all --limit 300`, the 17 open issues, and the five open PRs on 2026-10-27. No matching open ticket was found for B through E or for delivery of this local sweep.

Immediately before filing, the refreshed tracker still had those 17 open issues and five open PRs, with no duplicate found. Remote `main` remained at the reviewed baseline. Issues #562 through #566 were then created with the labels below, no assignees, and no milestones.

| Existing work | Relationship and filing treatment |
| --- | --- |
| [#148](https://github.com/millsymills-com/unifi-mcp/issues/148), closed | Established error-body redaction and raw DEBUG logging opt-in. Reference from B as historical context; do not reopen or describe the policy mismatch as a new credential disclosure |
| [#513](https://github.com/millsymills-com/unifi-mcp/issues/513) and [PR #559](https://github.com/millsymills-com/unifi-mcp/pull/559), open | Guard documented CI commands against drift. A adds a job and documentation command; coordinate/rebase with the guard tests rather than filing another drift-guard issue. PR #559 changes `tests/unit/test_documented_ci_gates.py` |
| [#271](https://github.com/millsymills-com/unifi-mcp/issues/271), closed | Live-test incident and guardrails. Reference from C for recovery expectations; these standalone probes are a separate path |
| [#543](https://github.com/millsymills-com/unifi-mcp/issues/543) and [PR #560](https://github.com/millsymills-com/unifi-mcp/pull/560), open | Unsupported event reads. D concerns client lifecycle, not discovery of a supported event/archive endpoint |

Refresh this check immediately before filing; reuse an issue if a matching ticket has appeared. Use the repository's [issue tracker conventions](../agents/issue-tracker.md) and [triage labels](../agents/triage-labels.md). All proposed labels below already exist. Each ticket has exactly one category label, `bug` or `enhancement`; priorities belong in the body because the repository has no priority labels.

## Filing and implementation order

1. File A first and link its delivery PR after reviewing the existing diff. Do not reimplement the four fixes or include unrelated working-tree files.
2. File B and C as the first remaining implementation work. B touches public client constructors and server wiring; C prevents probe failures from accumulating controller state. Neither needs the other. Rebase B after A if both modify `server.py`.
3. File D next. Its implementation is independent and small, but failure coverage must precede any live use.
4. File E as `needs-triage`; implement when the compatibility approach is accepted or client reuse makes the dependency worthwhile to remove. Schedule it after B to limit overlapping client changes.

Use one implementation PR per issue, with `Closes #<number>` in its description. Close A only after the fixes are merged and hosted CI passes; close B through D when their failure cases pass and their fixes merge. E remains a tracked enhancement until its dependency and compatibility criteria are met.

Publication used temporary UTF-8 body files and `gh issue create --repo millsymills-com/unifi-mcp --title '<title>' --body-file <file>` with the listed labels, following the user's instruction to file the issues. Returned URLs are recorded above. Issue #563 references #562 for merge order, and #566 references #563. Assignees and milestones remain unset.

Published source links are GitHub permalinks at the reviewed baseline. Issue #562 explicitly identifies the fixes as local proposed changes because the baseline commit does not contain them; add the delivery PR diff when available. The report reconciliation and verification record remain in this plan rather than being copied into every ticket.

## Issue A

**Title:** Deliver the validated startup configuration and offline test fixes

**Labels:** `bug`, `testing`, `ci/cd`, `ready-for-agent`

**Priority:** Medium. Implementation exists locally; merge delivery precedes further server refactoring.

### Problem and current status

At `ae90152`, explicit `create_server(config)` settings govern registration but startup reloads global settings. The same revision has weak Network payload assertions, operator-dependent unit/property configuration, and CI selection that omits existing offline transport/allowlist cases. The full sweep's S1 through S4 fixes are present in the working tree and pass focused verification, but are uncommitted. This issue tracks review and delivery of those fixes, not additional implementation of them.

### Evidence and scope

- [server.py](../../src/unifi_mcp/server.py#L235) now binds startup to the supplied settings; [test_server.py](../../tests/unit/test_server.py#L25) tests both modes through a real FastMCP session with stubbed HTTP and conflicting environment values.
- [test_network_extra.py](../../tests/unit/clients/test_network_extra.py#L130) asserts complete generic create/update JSON; the Network networks, WLAN, firewall, and routing test modules require the requested `enabled=False` value.
- [tests/conftest.py](../../tests/conftest.py#L19) isolates unit/property configuration inputs while leaving integration configuration available.
- [ci.yml](../../.github/workflows/ci.yml#L108) adds the two-file offline job and includes it in `CI Pass`; `CLAUDE.md` and `CONTRIBUTING.md` document the command.

The delivery diff comprises these 11 already modified files. Review and commit those changes explicitly; report files and unrelated local changes do not belong in the implementation PR by default.

### Acceptance criteria

- [ ] Supplied host, site, API key, and readonly/readwrite mode agree between registration and runtime calls even when process settings disagree.
- [ ] Preserve the public `server_lifespan(server)` entry point and normal CLI startup behavior.
- [ ] Generic create/update and the four resource-specific update tests assert decoded payload equality. A scratch mutation that flips the requested boolean makes an affected regression fail.
- [ ] Unit/property defaults are independent of parent `UNIFI_*` settings and default dotenv inputs. Tests can still deliberately set environment variables or pass an explicit dotenv file.
- [ ] CI runs `test_stdio_transport.py` and `test_device_allowlist.py` using explicit paths, and `CI Pass` fails if that job fails. Hardware suites are not selected by the job.
- [ ] Check compatibility with #513 / PR #559 after combining changes; extend its expected documentation coverage if needed without weakening existing checks.
- [ ] Run the full unit/property suite, both offline integration files, Ruff lint/format, ty, workflow lint, and `uv lock --check`; hosted required checks pass after merge.

### Verification already completed

The 352-case focused suite covers server, lifespan, configuration, base client, generic Network CRUD, the four payload assertion modules, error mapping, and shared handlers. Another 88 cases pass with parent mode, host, and port conflicting with test defaults. All 16 offline transport/allowlist cases pass. Full-suite and hosted results reported by the earlier sweep remain historical evidence; attach fresh full-suite and hosted results to the delivery PR.

## Issue B

**Title:** Pass resolved raw body logging policy into every API client

**Labels:** `bug`, `tech-debt`, `ready-for-agent`

**Priority:** Medium. A configured policy is ignored; no new credential disclosure is established.

### Problem and reproduction

[config.py](../../src/unifi_mcp/config.py#L117) declares `unifi_log_raw_bodies`, but [base.py](../../src/unifi_mcp/clients/base.py#L63) reads `UNIFI_LOG_RAW_BODIES` directly on each error response. [Server client construction](../../src/unifi_mcp/server.py#L140) never passes the resolved setting. These authorities disagree:

| Resolved settings | Process environment | Observed DEBUG log from a synthetic JSON error |
| --- | --- | --- |
| Explicit `False` | `true` | Untouched synthetic password marker appears |
| Explicit `True` | `false` | Marker is redacted |
| Dotenv `True` | Variable absent | Marker is redacted |

Reproduce offline by isolating `os.environ`, constructing `UniFiConfig` with the indicated value, constructing `NetworkClient` with a synthetic URL/key, and calling `_extract_error_body(httpx.Response(400, json={"password": "synthetic-body-marker"}))` while capturing the base-client logger at DEBUG. Close the client afterward. No request is required. Existing tests in `tests/unit/clients/test_base.py` opt into logging by changing the environment after client construction, so they currently reinforce the competing policy lifetime.

### Proposed change

Add a keyword-only `log_raw_bodies: bool = False` argument to `BaseUniFiClient`, Network, Network Integration, Protect, and Site Manager constructors. Capture it on the instance and forward `config.unifi_log_raw_bodies` from all four server construction paths. Remove the HTTP layer's environment parser. Standalone callers can opt in explicitly; document that changing the process environment after construction no longer changes an existing client.

### Acceptance criteria

- [ ] All four server-created clients use the same resolved policy, including Site Manager and Network Integration.
- [ ] Constructor, process-environment, and dotenv settings resolve through `UniFiConfig` and produce matching runtime behavior; explicit values win over environment values.
- [ ] A standalone client defaults to redacted logging even if a process variable says `true`; explicit `log_raw_bodies=True` opts into raw DEBUG logging.
- [ ] Environment changes after construction cannot flip an existing client's policy.
- [ ] Both JSON and non-JSON error paths respect the policy. Default logs retain key redaction and configured API-key value scrubbing.
- [ ] Raw logging opt-in affects only DEBUG body logs. Tool-visible errors and WARN messages retain existing redaction, including when raw DEBUG logging is enabled.
- [ ] Existing constructor calls remain valid; update raw-body tests to configure the client rather than mutate global policy after construction. Update the relevant docstrings and `.env.example` explanation.

### Validation and dependencies

Use synthetic response markers and HTTP stubs. Cover all four constructor forwarding paths, conflicting settings, dotenv, safe defaults, and both body formats. Run the client, settings, server/lifespan, logging/redaction, error, and handler suites, then normal offline CI checks. Reference closed #148 for the established redaction contract. A is a merge-order dependency if its server changes are still pending.

## Issue C

**Title:** Clean up each created probe route before continuing after a failure

**Labels:** `bug`, `ready-for-agent`

**Priority:** Medium. Limited to a manually invoked probe, but failures can accumulate controller state.

### Problem and reproduction

In [route_payload_probe.py](../../scripts/route_payload_probe.py#L79), read-back and diagnostic printing occur between creation and deletion. Any exception is reported as a rejected candidate, then the script tries another creation. Cleanup failures follow the same path.

An offline fake `NetworkClient` reproduces both cases by running the existing `main()` with a synthetic API key and patched client constructor:

1. `create_route` returns successive IDs; `get_route("route-1")` raises; later reads succeed; `delete_route` records IDs. The script creates `route-1` and `route-2`, deletes only `route-2`, and returns normally with `route-1` remaining.
2. Reads succeed but every `delete_route` raises. The script creates all three candidate routes, deletes none successfully, and returns normally.

Client closure occurs in both cases; it does not remove the created resources. The probe currently creates disabled routes, which limits immediate traffic impact but still leaves controller configuration behind.

### Proposed change

Track a confirmed route ID immediately after each successful create response and put deletion in a per-route `finally` that covers all read-back and output. Separate a rejected create from a failure after creation. Stop on unresolved cleanup instead of starting another creation. Preserve the primary exception if deletion or client closure also fails, and report the synthetic/probe resource identity needed for operator recovery.

### Acceptance criteria

- [ ] Each successfully identified route is deleted exactly once after normal read-back, read-back failure, output failure, or cancellation; client closure is still attempted.
- [ ] If deletion fails, no later candidate is created. The failure remains visible and identifies the route needing cleanup.
- [ ] If read-back and deletion both fail, retain the original failure and report the cleanup failure without replacing it.
- [ ] A create response without a usable ID is reported as indeterminate rather than clean success. Stop further creates; do not delete an arbitrary route or broaden deletion to all matching names. Report the generated probe name for recovery.
- [ ] Explicit controller rejections can still advance to the next candidate when no resource was created; success still terminates probing after cleanup. A timeout or ambiguous create response stops probing and reports the uncertainty rather than assuming no creation occurred.
- [ ] Add offline tests for success, rejected create, missing ID, failed read-back, failed output, failed deletion, combined failures, and cancellation. Test doubles assert operation order and remaining resource state.

### Validation and boundaries

Add focused tests under `tests/unit/` with the script's constructor patched to a fake; run them through ordinary CI. Verify that a read-back failure deletes the first route before any subsequent create, and that cleanup failure stops the loop. Keep the candidate payloads and disabled state unchanged. Follow #271 recovery expectations for any later operator-run live validation; offline failure injection is sufficient for this remediation's regression checks. This issue does not request live probe execution.

## Issue D

**Title:** Close the archive probe client when its initial alarm read fails

**Labels:** `bug`, `ready-for-agent`

**Priority:** Low. Resource leak in a manually invoked utility.

### Problem and reproduction

[archive_events_probe.py](../../scripts/archive_events_probe.py#L39) constructs a `NetworkClient`, performs its initial GET and alarm formatting, and only then enters the `try/finally` at line 64. Failures during the initial read or formatting skip `client.close()`.

Reproduce offline by patching the script's `NetworkClient` constructor to return a fake whose `get` raises `RuntimeError("synthetic-initial-read-failure")` and whose `close` records invocation. Run `main()` with a synthetic `UNIFI_NETWORK_API` and capture output. The original exception propagates, but `close` is never called.

### Proposed change and acceptance criteria

- [ ] Establish cleanup immediately after client construction, covering the first GET, alarm parsing/formatting, and every candidate operation.
- [ ] Attempt client closure exactly once on success, initial GET failure, malformed alarm data, diagnostic output failure, candidate failure, and cancellation.
- [ ] Preserve the original exception or cancellation if closure also fails; report the secondary cleanup failure.
- [ ] Preserve the existing candidate endpoint/payload list and intended per-candidate continuation behavior.
- [ ] Add offline fake-client tests for these lifecycle paths and run them in the unit suite. No controller access is needed.

Keep this separate from #543 / PR #560: fixing cleanup neither establishes a supported event/archive endpoint nor restores event reads.

## Issue E

**Title:** Separate transport exceptions from FastMCP error presentation

**Labels:** `enhancement`, `tech-debt`, `needs-triage`

**Priority:** Low. Confirmed import coupling; no current runtime failure or standalone reuse blocker is established.

### Evidence and scope

[errors.py](../../src/unifi_mcp/errors.py#L8) imports `fastmcp.exceptions.ToolError` alongside the exception hierarchy. All four API clients, the base client, and the pinning transport import that module. A fresh-process check confirms the dependency:

```bash
.venv/bin/python -c "import sys; import unifi_mcp.clients.network; print('fastmcp' in sys.modules)"
# Current result: True
```

The clients need transport exception types, while [tools/_common.py](../../src/unifi_mcp/tools/_common.py#L10) also needs `handle_client_error`. The package's primary purpose remains serving MCP, so this is a maintenance improvement, not an urgent defect.

### Proposed change

Keep exception definitions framework-independent and move MCP mapping and its formatting helper to a tool-layer adapter. Import that adapter from the shared tool handler. Preserve `from unifi_mcp.errors import handle_client_error` through a thin function that imports the adapter only when called; an eager compatibility re-export would retain the dependency being removed. Review the property tests' private `_classify_error_tag` import and update its home deliberately.

### Acceptance criteria

- [ ] Fresh-process imports of each client and the pinning module do not load FastMCP solely through transport exceptions; importing the legacy mapping function also remains lazy until invocation.
- [ ] Transport exception classes keep their identity, inheritance, `status_code`, and rate-limit metadata. No duplicate hierarchy is introduced.
- [ ] Supported legacy `handle_client_error` imports continue to work and return the same exception mapping behavior as the new adapter.
- [ ] Existing message text, HTTP tags, exception chaining, unexpected-error secrecy, and cancellation/interrupt propagation remain stable.
- [ ] No runtime import cycle is introduced; mapping tests, classification property tests, and shared tool-handler tests pass through both supported entry points where relevant.
- [ ] The focused dependency test uses a fresh interpreter, since pytest's root fixtures already import FastMCP and cannot establish this boundary through the parent process's `sys.modules`.

Review compatibility before moving this ticket to `ready-for-agent`. Implement after B where practical; it is independent of both probe fixes.

## Verification record

All checks below ran against the current working tree on 2026-10-27. Synthetic logging responses contained only test markers. Probe reproductions replaced `NetworkClient` entirely and did not contact controllers.

| Check | Result |
| --- | --- |
| Focused server, lifespan, configuration, base client, Network payload, error, and handler suites | 352 passed in 18.61s |
| Config and server suites with `UNIFI_MODE=readwrite`, `UNIFI_NETWORK_HOST=192.0.2.99`, and `UNIFI_NETWORK_PORT=444` in the parent environment | 88 passed in 4.80s |
| Explicit offline stdio and device-allowlist test files | 16 passed in 7.98s |
| Logging policy reproduction | All three mismatches in B confirmed |
| Probe failure injection | Initial archive GET skipped close; route read-back left one route; repeated deletion failure left three routes |
| Fresh-process client import | FastMCP loaded, confirming E's dependency |

The conflicting-environment run overlaps the focused suite; these numbers are separate runs, not unique coverage totals. This review changed only this plan. Existing source, test, CI, and report changes were left in place. Live hardware checks were not needed to validate these findings; hosted CI remains part of issue A's delivery criteria.
