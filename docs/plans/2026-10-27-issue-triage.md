# Repository issue triage, 2026-10-27

Reviewed all 22 open issues and five existing open PRs against main at `ae901522d16eedf6cf0ec85e8376f0499f6d8bfb`. Existing local changes were preserved. New work uses isolated worktrees under `/private/tmp` and one PR per issue.

Every triaged issue now has exactly one category (`bug` or `enhancement`) and a triage role, except the three completed issues closed during this review. Existing topic labels were retained.

| Issue | Disposition | Reason / next action |
| --- | --- | --- |
| [#562](https://github.com/millsymills-com/unifi-mcp/issues/562) | Selected, medium priority | Deliver the existing configuration/startup, payload assertions, offline isolation, and CI changes in [PR #567](https://github.com/millsymills-com/unifi-mcp/pull/567). Includes a new guard for the offline CI job. |
| [#564](https://github.com/millsymills-com/unifi-mcp/issues/564) | Selected, medium priority | Prevent probe resources accumulating after read/output/deletion failure. [PR #569](https://github.com/millsymills-com/unifi-mcp/pull/569) stops uncertain creation, identifies recovery resources, and preserves primary errors. |
| [#565](https://github.com/millsymills-com/unifi-mcp/issues/565) | Selected, low priority | Independent client lifecycle fix in [PR #568](https://github.com/millsymills-com/unifi-mcp/pull/568), with initial-read, formatting/output, cancellation, and closure-failure coverage. |
| [#563](https://github.com/millsymills-com/unifi-mcp/issues/563) | Ready for agent, medium priority | Next runtime correctness fix. Use resolved settings for all four clients; implement after #567 to reduce overlapping server edits. No new credential disclosure is established. |
| [#566](https://github.com/millsymills-com/unifi-mcp/issues/566) | Needs triage, low priority | Optional layering cleanup. Retain lazy compatibility imports and fresh-process tests; schedule after #563. No current runtime failure justifies prioritizing it over the selected fixes. |
| [#543](https://github.com/millsymills-com/unifi-mcp/issues/543) | Existing PR | [#560](https://github.com/millsymills-com/unifi-mcp/pull/560) has passing checks and uses the explicitly permitted unsupported-status resolution. Keep open until merged. |
| [#537](https://github.com/millsymills-com/unifi-mcp/issues/537) | Ready for human | Operator must rotate the exposed VPN configuration, replace it on the controller, and reconnect existing MCP servers. The code fix is already on main; do not close without operator confirmation. |
| [#529](https://github.com/millsymills-com/unifi-mcp/issues/529) | Existing PR | [#558](https://github.com/millsymills-com/unifi-mcp/pull/558) has passing checks. Keep open until merged. |
| [#522](https://github.com/millsymills-com/unifi-mcp/issues/522) | Existing PR | [#561](https://github.com/millsymills-com/unifi-mcp/pull/561) has passing checks and documents the guest-network limitation, an allowed issue resolution. Keep open until merged. |
| [#514](https://github.com/millsymills-com/unifi-mcp/issues/514) | Existing PR | [#557](https://github.com/millsymills-com/unifi-mcp/pull/557) has passing checks. Keep open until merged. |
| [#513](https://github.com/millsymills-com/unifi-mcp/issues/513) | Existing PR | [#559](https://github.com/millsymills-com/unifi-mcp/pull/559) has passing checks. Its 27 tests also pass with #567; combined validation includes both. |
| [#511](https://github.com/millsymills-com/unifi-mcp/issues/511) | Needs triage | Separate remaining prose fixes from the unresolved punctuation policy; coordinate CLAUDE.md work with #478 and avoid reopening already-fixed accuracy issues. |
| [#500](https://github.com/millsymills-com/unifi-mcp/issues/500) | Needs triage | Breaking tool-schema migration needs per-resource field allowlists and small release/PR groups. Existing write gates remain the authorization boundary. |
| [#499](https://github.com/millsymills-com/unifi-mcp/issues/499) | Needs info | Needs sanitized evidence from integration-v1 camera responses to determine whether bare aliases are present. No live call or new leak claim was made. |
| [#494](https://github.com/millsymills-com/unifi-mcp/issues/494) | Needs triage, epic | Split its rollout into endpoint-family PRs and reconcile with #500/#499. Preserve the explicit physical-actuation exclusions and existing confirmation conventions. |
| [#483](https://github.com/millsymills-com/unifi-mcp/issues/483) | Needs info | Settle the requested install-UI configuration split and release/tag policy before implementation. Acceptance needs a real host install and a published release. |
| [#480](https://github.com/millsymills-com/unifi-mcp/issues/480) | Ready for agent | Four API families, default-all behavior, and composition with mode gating are specified. Keep independent of startup/client validation behavior. |
| [#479](https://github.com/millsymills-com/unifi-mcp/issues/479) | Needs triage | Inventory the affected allowlists and split enum changes from the broad parameter-documentation migration before implementation. Preserve runtime guards. |
| [#478](https://github.com/millsymills-com/unifi-mcp/issues/478) | Needs info | Its shared-conventions prerequisite is not established by current workspace guidance; command removal must also coordinate with #559's drift guard. Hardware safety and gotchas must survive unchanged in substance. |
| [#477](https://github.com/millsymills-com/unifi-mcp/issues/477) | Closed, completed | #488 fixes both stdio annotations and the three pinning suppressions. Current ty 0.0.89 passes on src/ and tests/. |
| [#476](https://github.com/millsymills-com/unifi-mcp/issues/476) | Closed, completed | #488 updates the expected FastMCP validation exception. The coercion tests pass with locked FastMCP 4.1.4. |
| [#469](https://github.com/millsymills-com/unifi-mcp/issues/469) | Closed, completed | Main locks click 8.4.2, mcp 2.3.0, FastMCP 4.1.4; #488 landed the associated annotation/exception fixes. Current pip-audit finds no known vulnerabilities. |

The selected work delivers an existing correctness fix and two independent resource-cleanup defects with reproducible offline failures. Larger API/schema/release projects remain queued with explicit next steps. No live probe or hardware test was run, no release was published, and no PR was merged.

| PR | Local validation |
| --- | --- |
| #567 | 1,635 unit/property tests, 95.71% coverage; 16 offline integration tests; 88 conflicting-environment config/server cases; 27 compatibility tests from #559; boolean-flip mutation rejected; lockfile, Ruff, ty, actionlint pass. |
| #568 | 1,640 unit/property tests, 95.70% coverage; 10 focused lifecycle regressions; 16 offline integration tests; regressions fail against original code; lockfile, Ruff including script, ty, pip-audit pass. |
| #569 | 1,653 unit/property tests, 95.70% coverage; 23 focused state/order regressions; 16 offline integration tests; regressions fail against original code; lockfile, Ruff including script, ty pass. |

Combined merge compatibility: all three PRs plus #559 apply cleanly and pass 1,695 unit/property tests with 95.71% coverage, all 16 explicit offline integration tests, lockfile verification, Ruff lint/format (including both changed scripts), ty, and actionlint.

Final hosted readiness verified at **2026-10-28 05:31:17 UTC** (2026-10-27 22:31:17 America/Los_Angeles): all three PRs are non-draft, `MERGEABLE`, and `CLEAN` against main `ae901522d16eedf6cf0ec85e8376f0499f6d8bfb`. Every required check, including the full hosted test suite and `CI Pass`, passed. Optional cron/manual-only security audit jobs were skipped as expected; the CI dependency audit passed. Semgrep and GitGuardian checks passed. Commit signatures are verified, and no inline review comments were outstanding.

| PR | Verified head | Result |
| --- | --- | --- |
| [#567](https://github.com/millsymills-com/unifi-mcp/pull/567) | `265fbd522707e40229d446f2676a4b86dbf5db31` | Ready for merge; new offline transport job also passes. |
| [#568](https://github.com/millsymills-com/unifi-mcp/pull/568) | `8a163f38e741efd175abde90fade22b8ca652119` | Ready for merge. |
| [#569](https://github.com/millsymills-com/unifi-mcp/pull/569) | `57cf67665b9115a1acd1490c7e253c4f8a9910d3` | Ready for merge. |

No PR was merged. The original tracked working-tree diff was compared byte-for-byte with the initial patch and remains unchanged. This triage note is the only new file added to the primary checkout during this task; the implementation commits are in their isolated worktrees. GitHub's strict base-update requirement means the remaining PRs may need updating after any PR merges; the combined validation above establishes compatibility with these changes and #559.
