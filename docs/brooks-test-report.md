# Brooks-Lint Review

**Mode:** Test Quality Review<br>
**Scope:** All 81 test files mapped; representative tests and production paths reviewed at `ae90152`.<br>
**Health Score:** **85/100** — three warnings, balanced scoring.<br>
**Trend:** First run — no trend data.<br>
**Review date:** 2026-10-27

The suite provides strong coverage, with three concrete gaps in assertion strength, environment isolation, and CI selection.

**Test Suite Map**

```text
                              Files   Test functions*
Unit, including allowlist        60               937
Property                          2                 8
Live integration                 18               105
Subprocess transport              1                 6

* Before parametrization; classified by actual behavior.
```

Coverage spans configuration, clients, tool handlers, validation, redaction, lifecycle, and transport. No broad untested production area emerged from the review.

## Findings

### 🟡 Warning

**T5: Coverage Illusion — write assertions accept incorrect values**

**Symptom:** Several Network update tests check only for an `enabled` key or an HTTP call. For example, [test_network_networks.py:69](../tests/unit/tools/test_network_networks.py#L69) checks key presence, while [test_network_extra.py:146](../tests/unit/clients/test_network_extra.py#L146) checks request count. An in-memory mutation that inverted `update_network`’s requested boolean left both affected cases passing.

**Source:** *How Google Tests Software* — change versus line coverage; *The Art of Unit Testing* — test completeness.

**Consequence:** A regression that enables a network when asked to disable it can pass these offline checks despite high coverage.

**Remedy:** Decode the request JSON and assert its complete expected payload, including `enabled=False`, across the parameterized update cases.

**T2: Test Brittleness — configuration tests inherit operator settings**

**Symptom:** [test_readonly_is_default](../tests/unit/test_config.py#L44) passes normally but fails with `UNIFI_MODE=readwrite`. `_env_file=None` disables dotenv loading while leaving process environment settings active; the shared fixture clears the configuration cache without clearing those settings.

**Source:** *xUnit Test Patterns* — Erratic Test; *The Art of Unit Testing* — test isolation.

**Consequence:** Developers’ legitimate controller settings can change test outcomes without a code change.

**Remedy:** Clear application environment variables in unit/property fixtures before each test, allowing environment-specific cases to set their inputs explicitly.

**T6: Architecture Mismatch — CI excludes useful offline tests**

**Symptom:** [CI](../.github/workflows/ci.yml#L90) selects only `tests/unit/` and `tests/property/`. This excludes ten offline allowlist cases and six simulated stdio cases covering handshake, mode gating, cancellation, concurrency, and tool-list stability. The stdio module also carries the hardware-oriented `integration` marker.

**Source:** *How Google Tests Software* — risk-based test distribution.

**Consequence:** Transport regressions and allowlist-parser changes can merge without exercising their existing tests.

**Remedy:** Move allowlist tests into the unit directory and give simulated transport tests a separate CI job and marker.

## Summary

Strengthen write-payload assertions first, then isolate configuration inputs and include the existing offline tests in CI. No strong evidence justified findings for obscurity, duplication, mock abuse, or excessive suite runtime.

Validation: **1,630 unit/property cases passed in 85.83 seconds**, with **95.70% combined coverage** and **97.33% branch coverage**. The ten allowlist cases and six simulated stdio cases also passed; live hardware tests were not run. Production and test code were unchanged; the score was appended to [.brooks-lint-history.json](../.brooks-lint-history.json).
