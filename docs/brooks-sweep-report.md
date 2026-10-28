# Brooks-Lint — Full Sweep Report

**Mode:** Full Sweep<br>
**Scope:** Entire repository, 192 tracked files at sweep start; reviewed 2026-10-27.<br>
**Health Score:** Estimated 69/100 before → 89/100 after (balanced).<br>
**Trend:** First Full Sweep run.

Four distinct findings were fixed. Three findings remain for human review; none is Critical. No `.brooks-lint.yaml` was present, so default risks and the three-round non-critical cap applied.

## Dimension Summary

| Dimension | Scanned | Safe Applied | Extended Applied | Reverted | Residual |
|-----------|---------|--------------|------------------|----------|----------|
| Review (R1–R6) | 56 production + 4 script Python files | 0 | 1 | 0 | 3 |
| Test (T1–T6) | 81 test modules, fixtures, CI selection | 5 | 2 | 0 | 0 |
| Debt | Repository-wide accumulation and policy ownership | 2 | 0 | 0 | 1 overlapping |
| Audit | 56 production modules and runtime import graph | 0 | 0 | 0 | 1 overlapping |

Applied columns count fix-log actions, not independent findings. Five local assertion edits address one T5 finding; two documentation edits support the CI fix. Debt's logging-policy item and Audit's framework-coupling item overlap Review and are counted once in totals and scoring.

Static inventory, function/import analysis, and risk-pattern triage covered every tracked Python file. Detailed implementation reading concentrated on settings, startup, transport, shared policies, resource/test families across the four API surfaces, and all four operator scripts. Metadata and documentation were inspected for test commands, intended boundaries, and drift; image assets were inventoried only. This is a maintenance sweep, not an exhaustive verification of every upstream wire contract.

## Findings Fixed

### S1 · R2 — Constructor configuration did not reach startup

**Symptom:** `create_server(config)` registered tools from its argument but attached a lifespan that independently called `get_config()`. Injected hosts, keys, and mode could disagree with runtime clients and write policy.<br>
**Source:** *The Pragmatic Programmer* — Orthogonality; *Working Effectively with Legacy Code* — The Seam Model.<br>
**Consequence:** Programmatic users could discover tools whose matching clients were absent or configured differently.<br>
**Remedy:** Bind the selected configuration into the server's lifespan. Share initialization through a private context manager while preserving the existing public `server_lifespan(server)` entry point and signatures. Two regression cases use real FastMCP sessions and HTTP stubs to verify the injected host, site, API key, read/write visibility, and successful runtime calls despite conflicting environment settings.<br>
**Outcome:** Applied, Extended-Safe; full suite passed before and after.

### S2 · T5 — Update tests accepted incorrect payload values

**Symptom:** Generic Network CRUD tests asserted call count or key presence; network, WLAN, firewall, and route update cases accepted an `enabled` key without requiring `False`.<br>
**Source:** *How Google Tests Software* — Change versus line coverage; *The Art of Unit Testing* — Test completeness.<br>
**Consequence:** An update that enabled a resource when asked to disable it could pass these tests.<br>
**Remedy:** Decode request JSON and assert complete payload equality. Strengthen generic create assertions too.<br>
**Outcome:** Applied as five Safe local test edits. Existing parameterization covers five update and five create operations; focused verification passed 104 cases after the final variants were corrected.

### S3 · T2 — Unit/property tests inherited operator settings

**Symptom:** `_env_file=None` did not suppress process environment settings, and the shared fixture cleared only the settings cache. Defaults could depend on the developer's `UNIFI_*` values.<br>
**Source:** *xUnit Test Patterns* — Erratic Test; *The Art of Unit Testing* — Test isolation.<br>
**Consequence:** Legitimate local controller configuration could change offline test outcomes without a code change.<br>
**Remedy:** Add a fixture restricted to unit/property paths that temporarily clears case-insensitive `UNIFI_*` environment names and disables default dotenv loading. Individual tests can still set environment variables or explicit dotenv inputs. Live integration configuration remains available.<br>
**Outcome:** Applied, Extended-Safe; all 1,632 unit/property cases passed with conflicting mode, host, and port supplied by the parent process.

### S4 · T6 — Existing offline tests were omitted from CI

**Symptom:** CI selected only unit/property directories, omitting ten allowlist and six simulated stdio cases under `tests/integration/`.<br>
**Source:** *How Google Tests Software* — Risk-based test distribution.<br>
**Consequence:** Changes could merge without exercising existing process-boundary, cancellation, concurrency, tool-visibility, or allowlist checks.<br>
**Remedy:** Add a five-minute `offline-transport` job selecting exactly those two files and require it in `CI Pass`. Update contributor/agent commands. Explicit paths preserve the existing markers and avoid collecting hardware tests.<br>
**Outcome:** Applied, Extended-Safe, with two supporting Safe documentation edits. All 16 selected cases passed; workflow lint passed. Hosted execution awaits CI.

## Iteration History

- Round 1: mixed, seven distinct findings diagnosed across Review → Test → Debt → Audit; four fixed, three classified Residual. Baseline: 1,630 passing cases. Review verification: 1,632 passing cases. Test verification: 1,632 passing cases with conflicting environment settings, plus 16 offline transport/allowlist cases.
- Round 2: non-critical refinement of S2; re-scan of modified files, same-module peers, and static consumers found firewall/route manifestations of the same weak assertion. Both fixed; 104 affected cases passed. No new distinct finding.
- Round 3: clean for eligible changes; final diff, imports, type/lint/format checks, and direct consumers revealed no additional actionable finding. The three intentionally deferred residuals remain outside the automatic fix queue.
- Stopped at: no further eligible fixes; no outstanding Critical findings. Non-critical iteration cap was not exhausted. No verification-driven reverts or retired findings.

## Fix Log

| # | File | Approximate lines | Risk | Outcome | Change |
|---|------|-------------------|------|---------|--------|
| 1 | `src/unifi_mcp/server.py`; `tests/unit/test_server.py` | 104–124, 235–253; 25–55 | R2 | applied | Bind settings to startup; verify both modes through MCP sessions |
| 2 | `tests/unit/clients/test_network_extra.py` | 130–152 | T5 | applied | Assert complete generic create/update payloads |
| 3 | `tests/unit/tools/test_network_networks.py` | 70–74 | T5 | applied | Require the requested false value |
| 4 | `tests/unit/tools/test_network_wlan.py` | 90–95 | T5 | applied | Replace permissive alternative assertion |
| 5 | `tests/conftest.py` | 19–28 | T2 | applied | Isolate offline configuration inputs |
| 6 | `.github/workflows/ci.yml` | 108–167 | T6 | applied | Require simulated transport and allowlist checks |
| 7 | `CLAUDE.md` | 23–31, 142 | T6 support | applied | Document offline job and five-job gate |
| 8 | `CONTRIBUTING.md` | 33 | T6 support | applied | Include offline checks in contributor commands |
| 9 | `tests/unit/tools/test_network_firewall.py` | 88–94 | T5 | applied | Require the requested false value |
| 10 | `tests/unit/tools/test_network_routing.py` | 69–74 | T5 | applied | Require the requested false value |

## Health Score Delta

Before: **69/100** → After: **89/100**, estimated against this sweep's seven distinct findings. Before: six Warnings and one Suggestion. After: two Warnings and one Suggestion. Balanced deductions: 5 per Warning and 1 per Suggestion. No overlapping dimension finding is counted twice. Re-run `/brooks-health` for its mode-specific recalculation.

## Residual Items (3 not applied)

### Warning · S5 · R3 — HTTP logging policy has two authorities

**Location:** `src/unifi_mcp/config.py:117`; `src/unifi_mcp/clients/base.py:63` and `:220`; server client construction.<br>
**Symptom:** Settings declare `unifi_log_raw_bodies`, but HTTP error logging separately parses the process environment on every response. The selected constructor/dotenv value never reaches the clients.<br>
**Source:** *The Pragmatic Programmer* — DRY; *A Philosophy of Software Design* — Information Leakage.<br>
**Consequence:** One logging policy has inconsistent parsers and lifetimes; explicit or dotenv settings can disagree with runtime behavior. This finding does not establish credential disclosure.<br>
**Remedy:** Pass a resolved logging-policy value through the base and concrete client constructors, retaining a safe default for standalone callers. Test explicit, environment, and dotenv configuration at that seam.<br>
**Not applied because:** The straightforward remedy alters public client constructor signatures across six source files. This exceeds the sweep's automatic fix criteria. Debt priority: Pain 2 × Spread 2 = 4, Warning.

### Warning · S6 · R1 — Probe cleanup does not cover failures

**Location:** `scripts/archive_events_probe.py:39` and `:64`; `scripts/route_payload_probe.py:82`–`:95`.<br>
**Symptom:** The archive probe's initial HTTP request runs before its closing `finally`. The route probe creates a route, then performs read-back and printing before deletion; failures in those steps are caught as a rejected candidate and can start another creation attempt without deleting the first route.<br>
**Source:** *Code Complete* — Defensive programming and error-handling discipline; *Refactoring* — Long Method with mixed lifecycle and diagnostic responsibilities.<br>
**Consequence:** Diagnostic failure can leak an HTTP client or leave a disabled test route behind. The impact is limited to manually invoked operator probes.<br>
**Remedy:** Cover all post-construction work with client cleanup, and put deletion of each successfully identified route in a per-route `finally`. Preserve the original error if cleanup also fails. Add offline failure-injection coverage before changing this live-mutating utility.<br>
**Not applied because:** Neither probe has automated behavior coverage; route cleanup changes live-controller mutation/recovery behavior. No probe or live hardware test was executed.

### Suggestion · S7 · R5 — Transport exceptions import presentation machinery

**Location:** `src/unifi_mcp/errors.py:8` and `:107`; imports from clients and pinning transport.<br>
**Symptom:** The module defining transport exceptions also imports FastMCP's `ToolError` and implements presentation mapping.<br>
**Source:** *Clean Architecture* — Dependency Inversion and separation of presentation details.<br>
**Consequence:** Reusing the HTTP clients also loads framework coupling. Impact is small in a package whose primary purpose is MCP.<br>
**Remedy:** Move presentation mapping into a tool-layer adapter while retaining supported public imports through compatibility handling.<br>
**Not applied because:** Cross-module structural change and public-import compatibility need design review. Debt priority: Pain 1 × Spread 3 = 3, Suggestion.

## Coverage and Tradeoffs

- R1: Long tool registrars mostly contain independent, named handlers; linear registration size alone is not a finding. Probe cleanup is the concrete mixed-responsibility issue.
- R2/R3: Configuration ownership is the meaningful change-coupling issue. Similar wrappers for different upstream contexts and separate request/stream lifecycles are not automatically duplicated knowledge.
- R4/R6: Raw payload dictionaries and thin adapters are documented decisions. No new domain-object or plugin framework was introduced without an invariant that requires it.
- R5: Static runtime imports, including lazy imports and excluding `TYPE_CHECKING` branches, contain no cycles. Registrar/server fan-out is intentional composition. Dynamic import behavior and third-party internals are outside this graph.
- T1/T3/T4: The reviewed assertions, fixtures, and doubles generally have clear purposes. Local setup duplication, coherent multi-assert tests, and HTTP/client interaction checks do not independently justify consolidation or mock-abuse findings.
- T5/T6: Coverage remains useful but is not proof of correctness. Shared error, boundary, cancellation, and write-gate tests complement happy-path dispatch tests. No blanket test scaffold was added to inflate percentages.

## Verification

- Baseline: `.venv/bin/pytest tests/unit/ tests/property/ -q --cov=unifi_mcp ... -m 'not integration'` — **1,630 passed**, **95.70%** combined coverage.
- After Review: full unit/property suite — **1,632 passed**.
- After Test: same suite with `UNIFI_MODE=readwrite`, `UNIFI_NETWORK_HOST=192.0.2.99`, and `UNIFI_NETWORK_PORT=1234` — **1,632 passed**, **95.71%** combined coverage, **438/450 branches covered (97.33%)**.
- The environment-stress run initially hit a sandbox `PermissionError` binding a local TLS fixture socket. The identical command passed after approved escalation; no code was reverted for that environment failure.
- `.venv/bin/pytest tests/integration/test_stdio_transport.py tests/integration/test_device_allowlist.py -q` — **16 passed** using simulated local services.
- After Round 2 assertion edits: affected Network client/tool tests — **104 passed**. This targeted run supplements the preceding full suite; these cases overlap the full-suite count.
- Final Ruff lint, Ruff format (145 files), `ty check src/ tests/`, and `git diff --check` — passed. `actionlint -verbose` — zero workflow errors; its optional Python-snippet check was unavailable because `pyflakes` is not installed.
- No dependencies changed. No live controller calls, hardware tests, commits, pushes, or amendments were performed. Existing audit reports were preserved; history received one appended Full Sweep entry.

## Summary

- Total distinct findings detected: **7**.
- Fixed this sweep: **4** (10 logged actions, including supporting documentation).
- Residual needing human review: **3**.
- Unresolvable after three failed attempts: **0**.
- Critical findings: **0**.

The runtime now uses the selected server settings, offline tests control their configuration inputs, and CI includes the existing simulated transport checks. Address the residual logging seam before the smaller framework-coupling cleanup; characterize the operator probes before changing their mutation recovery.

## Scope File List

The following is the exact tracked-file list captured before edits. Pre-existing untracked reports were used as leads, then relevant claims were checked against current code; they were not overwritten.

```text
.devcontainer/devcontainer.json
.editorconfig
.env.example
.github/CODEOWNERS
.github/ISSUE_TEMPLATE/bug_report.yml
.github/ISSUE_TEMPLATE/feature_request.yml
.github/PULL_REQUEST_TEMPLATE.md
.github/dependabot.yml
.github/workflows/ci.yml
.github/workflows/security.yml
.gitignore
.pre-commit-config.yaml
CHANGELOG.md
CLAUDE.md
CONTEXT.md
CONTRIBUTING.md
LICENSE
README.md
SECURITY.md
docs/adr/0000-template.md
docs/adr/0001-destructive-write-tool-conventions.md
docs/agents/domain.md
docs/agents/issue-tracker.md
docs/agents/live-test-safety.md
docs/agents/triage-labels.md
docs/api-coverage-matrix.md
docs/assets/favicon-16.png
docs/assets/favicon-32.png
docs/assets/favicon.ico
docs/assets/logo-256.png
docs/assets/logo-transparent.svg
docs/assets/logo.svg
docs/plans/2026-04-16-001-feat-unifi-mcp-server-plan.md
docs/plans/2026-06-23-network-integration-write-coverage-90.md
docs/plans/2026-06-23-read-coverage-expansion.md
docs/plans/2026-08-10-coverage-completion.md
docs/tool-schema-matrix.md
pyproject.toml
scripts/archive_events_probe.py
scripts/gen_schema_matrix.py
scripts/live_test_discovery.py
scripts/route_payload_probe.py
src/unifi_mcp/__init__.py
src/unifi_mcp/__main__.py
src/unifi_mcp/_inventory.py
src/unifi_mcp/_logging.py
src/unifi_mcp/_redaction.py
src/unifi_mcp/_schema.py
src/unifi_mcp/clients/__init__.py
src/unifi_mcp/clients/_pinning.py
src/unifi_mcp/clients/base.py
src/unifi_mcp/clients/network.py
src/unifi_mcp/clients/network_integration.py
src/unifi_mcp/clients/protect.py
src/unifi_mcp/clients/site_manager.py
src/unifi_mcp/config.py
src/unifi_mcp/errors.py
src/unifi_mcp/py.typed
src/unifi_mcp/server.py
src/unifi_mcp/tools/__init__.py
src/unifi_mcp/tools/_common.py
src/unifi_mcp/tools/network/__init__.py
src/unifi_mcp/tools/network/clients.py
src/unifi_mcp/tools/network/devices.py
src/unifi_mcp/tools/network/firewall.py
src/unifi_mcp/tools/network/networks.py
src/unifi_mcp/tools/network/port_forward.py
src/unifi_mcp/tools/network/port_profiles.py
src/unifi_mcp/tools/network/routing.py
src/unifi_mcp/tools/network/stats.py
src/unifi_mcp/tools/network/system.py
src/unifi_mcp/tools/network/wlan.py
src/unifi_mcp/tools/network_integration/__init__.py
src/unifi_mcp/tools/network_integration/_common.py
src/unifi_mcp/tools/network_integration/acl.py
src/unifi_mcp/tools/network_integration/devices.py
src/unifi_mcp/tools/network_integration/dns.py
src/unifi_mcp/tools/network_integration/dpi.py
src/unifi_mcp/tools/network_integration/firewall.py
src/unifi_mcp/tools/network_integration/hotspot.py
src/unifi_mcp/tools/network_integration/networks.py
src/unifi_mcp/tools/network_integration/radius.py
src/unifi_mcp/tools/network_integration/sites.py
src/unifi_mcp/tools/network_integration/switching.py
src/unifi_mcp/tools/network_integration/traffic.py
src/unifi_mcp/tools/network_integration/vpn.py
src/unifi_mcp/tools/network_integration/wan.py
src/unifi_mcp/tools/protect/__init__.py
src/unifi_mcp/tools/protect/access.py
src/unifi_mcp/tools/protect/cameras.py
src/unifi_mcp/tools/protect/device_reads.py
src/unifi_mcp/tools/protect/devices.py
src/unifi_mcp/tools/protect/liveviews.py
src/unifi_mcp/tools/protect/media.py
src/unifi_mcp/tools/protect/nvr.py
src/unifi_mcp/tools/site_manager/__init__.py
src/unifi_mcp/tools/site_manager/discovery.py
src/unifi_mcp/tools/site_manager/metrics.py
src/unifi_mcp/tools/site_manager/sdwan.py
tests/__init__.py
tests/conftest.py
tests/fixtures/network_responses.json
tests/fixtures/protect_responses.json
tests/fixtures/site_manager_responses.json
tests/integration/__init__.py
tests/integration/conftest.py
tests/integration/test_all_tools_live.py
tests/integration/test_device_allowlist.py
tests/integration/test_network_clients_live.py
tests/integration/test_network_device_lifecycle_live.py
tests/integration/test_network_device_ops_live.py
tests/integration/test_network_firewall_live.py
tests/integration/test_network_live.py
tests/integration/test_network_networks_live.py
tests/integration/test_network_port_forward_live.py
tests/integration/test_network_port_profiles_live.py
tests/integration/test_network_routes_live.py
tests/integration/test_network_update_settings_live.py
tests/integration/test_network_wlan_live.py
tests/integration/test_protect_accessory_writes_live.py
tests/integration/test_protect_live.py
tests/integration/test_protect_writes_live.py
tests/integration/test_public_tls_verify_ssl_live.py
tests/integration/test_retry_fault_injection_live.py
tests/integration/test_site_manager_live.py
tests/integration/test_stdio_transport.py
tests/property/__init__.py
tests/property/test_errors_classify.py
tests/property/test_path_validators.py
tests/unit/__init__.py
tests/unit/clients/__init__.py
tests/unit/clients/test_base.py
tests/unit/clients/test_cancellation.py
tests/unit/clients/test_network.py
tests/unit/clients/test_network_extra.py
tests/unit/clients/test_network_integration.py
tests/unit/clients/test_path_traversal.py
tests/unit/clients/test_pinning.py
tests/unit/clients/test_protect.py
tests/unit/clients/test_protect_extra.py
tests/unit/clients/test_protect_reads.py
tests/unit/clients/test_retry_timing.py
tests/unit/clients/test_site_manager.py
tests/unit/clients/test_ssl_verification.py
tests/unit/clients/test_url_contracts.py
tests/unit/test_audit_inventory.py
tests/unit/test_config.py
tests/unit/test_errors.py
tests/unit/test_live_write_abort_hook.py
tests/unit/test_logging.py
tests/unit/test_redaction.py
tests/unit/test_schema_matrix.py
tests/unit/test_server.py
tests/unit/test_server_lifespan.py
tests/unit/test_tool_inventory.py
tests/unit/test_touched_devices.py
tests/unit/test_version.py
tests/unit/tools/__init__.py
tests/unit/tools/test_concurrent_tool_calls.py
tests/unit/tools/test_confirm_gate.py
tests/unit/tools/test_dangerous_key_denylist.py
tests/unit/tools/test_handler_bodies.py
tests/unit/tools/test_handler_bodies_full.py
tests/unit/tools/test_handler_error_paths.py
tests/unit/tools/test_input_bounds.py
tests/unit/tools/test_list_bounds.py
tests/unit/tools/test_network_clients.py
tests/unit/tools/test_network_devices.py
tests/unit/tools/test_network_firewall.py
tests/unit/tools/test_network_integration_tools.py
tests/unit/tools/test_network_networks.py
tests/unit/tools/test_network_port_forward.py
tests/unit/tools/test_network_port_profiles.py
tests/unit/tools/test_network_routing.py
tests/unit/tools/test_network_stats.py
tests/unit/tools/test_network_system.py
tests/unit/tools/test_network_update_settings_named_args.py
tests/unit/tools/test_network_wlan.py
tests/unit/tools/test_path_segment_validators.py
tests/unit/tools/test_protect_cameras.py
tests/unit/tools/test_protect_devices.py
tests/unit/tools/test_protect_media.py
tests/unit/tools/test_protect_named_args.py
tests/unit/tools/test_protect_nvr.py
tests/unit/tools/test_protect_reads.py
tests/unit/tools/test_redaction_at_tool_layer.py
tests/unit/tools/test_site_manager.py
tests/unit/tools/test_site_manager_reads.py
tests/unit/tools/test_tool_handler.py
tests/unit/tools/test_validator_rollout.py
tests/unit/tools/test_writes_enabled_defense.py
uv.lock
```
