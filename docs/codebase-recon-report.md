# Codebase Recon Report

Analysis date: 2026-10-27. Based on local Git history through `ae90152`.

## Repo Vitals

2026-04-16 to 2026-10-27 | **291 commits** | **8 branch refs** | Analysis window: **all time**

## 1. Code Hotspots

| Changes | File |
|---:|---|
| 64 | `pyproject.toml` |
| 47 | `uv.lock` |
| 31 | `README.md` |
| 29 | `CLAUDE.md` |
| 27 | `tests/integration/test_all_tools_live.py` |
| 27 | `src/unifi_mcp/clients/base.py` |
| 21 | `tests/unit/clients/test_base.py` |
| 21 | `.github/workflows/security.yml` |
| 19 | `src/unifi_mcp/tools/network/system.py` |
| 19 | `src/unifi_mcp/server.py` |

## 2. Bug Magnets

Counts reflect commits whose messages match `fix`, `bug`, or `broken`; they are signals, not confirmed defect counts.

| Commits | File |
|---:|---|
| 20 | `src/unifi_mcp/clients/base.py` |
| 16 | `tests/unit/clients/test_base.py` |
| 16 | `tests/integration/test_all_tools_live.py` |
| 12 | `src/unifi_mcp/clients/network.py` |
| 12 | `README.md` |
| 11 | `src/unifi_mcp/config.py` |
| 10 | `tests/integration/conftest.py` |
| 10 | `src/unifi_mcp/server.py` |
| 10 | `CLAUDE.md` |
| 9 | `tests/unit/test_config.py` |

## 3. High-Risk Files

These appear in both lists. Andrew Mills is the sole recorded contributor to each.

| File | Hotspot rank | Bug magnet rank |
|---|---:|---:|
| `README.md` | 3 | 5 |
| `CLAUDE.md` | 4 | 9 |
| `tests/integration/test_all_tools_live.py` | 5 | 3 |
| `src/unifi_mcp/clients/base.py` | 6 | 1 |
| `tests/unit/clients/test_base.py` | 7 | 2 |
| `src/unifi_mcp/server.py` | 10 | 8 |

The strongest runtime review target is `clients/base.py`: 20 of its 27 changes accompany matching bug-fix messages. Documentation and tests may change alongside fixes without causing them.

## 4. Bus Factor

| Commits | Contributor |
|---:|---|
| 234 | Andrew Mills |
| 56 | dependabot[bot] |
| 1 | Andy Mills |

Active in the last three months: **2 of 3 author names (67%)**, comprising Andrew Mills and Dependabot.

The ratio passes the skill's 30% threshold, but human ownership is concentrated in Andrew Mills. "Andy Mills" may be an alias; identities were not merged.

## 5. Team Momentum

| Month | Commits |
|---|---:|
| April 2026 | 77 |
| May | 94 |
| June | 82 |
| July | 5 |
| August | 13 |
| September | 0 |
| October, through the 27th | 20 |

**Trend: declining, with substantial monthly volatility.** Using completed months, July–September averaged **6 commits/month**, versus **84.3** in April–June—a **93% decrease**. October shows renewed activity, though the month is incomplete.

## 6. Firefighting Frequency

No commit subjects matched `revert`, `hotfix`, `emergency`, or `rollback`.

Rate: **0 of 291 commits (0%)**. This measures commit wording, not incident history.

## 7. Recently Added Files

With an all-time window, all top entries were added once; this ranking is tied and does not imply recency.

| Additions | File |
|---:|---|
| 1 | `uv.lock` |
| 1 | `tests/unit/tools/test_writes_enabled_defense.py` |
| 1 | `tests/unit/tools/test_validator_rollout.py` |
| 1 | `tests/unit/tools/test_tool_handler.py` |
| 1 | `tests/unit/tools/test_site_manager_reads.py` |
| 1 | `tests/unit/tools/test_site_manager.py` |
| 1 | `tests/unit/tools/test_redaction_at_tool_layer.py` |
| 1 | `tests/unit/tools/test_protect_reads.py` |
| 1 | `tests/unit/tools/test_protect_nvr.py` |
| 1 | `tests/unit/tools/test_protect_named_args.py` |

The latest addition-bearing commit introduced `docs/plans/2026-08-10-coverage-completion.md` on August 11.

## 8. Recommendations

- **Start reading:** `src/unifi_mcp/clients/base.py`, its unit tests, and `tests/integration/test_all_tools_live.py`.
- **Talk to:** Andrew Mills about the shared client behavior and recurring fixes.
- **Watch out:** concentrated human ownership and the sharp slowdown after June. These history signals warrant investigation; they do not establish code quality problems.
