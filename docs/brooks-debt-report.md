# Brooks-Lint Review

**Mode:** Tech Debt Assessment<br>
**Scope:** Entire repository at `ae90152`, reviewed 2026-10-27. Static function and runtime-import analysis covered all 56 production Python files (8,507 lines); implementation reading sampled configuration, startup, HTTP transport, shared policies, and tools across all four API surfaces. Tests, scripts, history, and design documents were sampled.<br>
**Health Score:** 89/100 — balanced: 100 − (2 warnings × 5) − (1 suggestion × 1).<br>
**Trend:** First run — no trend data for Tech Debt Assessment.

The highest-value refactoring is to give configuration one owner from tool registration through client startup and logging.

## Findings

All six risks were scanned before prioritization. The complete finding set is D1 (R2), D2 (R3), and D3 (R5), grouped below by risk within severity. Pain scores are provisional estimates based on reproducible behavior and code structure, not measured developer effort or reports of avoidance. Spread counts affected source modules; priority and severity are separate measures.

### 🟡 Warning

**D1 · R2 Change Propagation — Configuration injection stops before startup**

**Symptom:** [server.py:229](../src/unifi_mcp/server.py#L229) accepts explicit configuration and uses it for tool registration, but [server.py:115](../src/unifi_mcp/server.py#L115) independently calls global `get_config()` during startup. An offline reproduction supplied a Site Manager key to `create_server`, then patched the global loader to return settings with no enabled APIs. Nine tools remained visible, the runtime context had zero clients, and the supplied configuration was not used. Existing tests separately exercise registration and the lifespan; they do not establish agreement when the supplied and global settings differ.

**Source:** *The Pragmatic Programmer* — Orthogonality; *Working Effectively with Legacy Code* — The Seam Model.

**Consequence:** A configuration change through the explicit constructor seam does not reliably control runtime hosts, keys, or mode. Callers and tests must also coordinate global settings. Ordinary CLI startup normally uses the same cached settings, limiting the common-case impact.

**Remedy:** Bind the selected settings into a lifespan factory or closure in `create_server`. Build clients and `ServerContext` from that object. Add a regression that starts a server with explicit settings differing from the global loader and checks tool visibility, client construction, and write-policy agreement.

**Priority:** Pain 2 × Spread 2 = **4 — Scheduled debt**. Affects server composition, tool registration, and shared runtime policy. **Intent:** [accidental]; no documented reason for accepting two authorities at this seam.

**D2 · R3 Knowledge Duplication — Raw-body logging has two authorities**

**Symptom:** [config.py:117](../src/unifi_mcp/config.py#L117) declares `unifi_log_raw_bodies`, but [clients/base.py:63](../src/unifi_mcp/clients/base.py#L63) separately parses `UNIFI_LOG_RAW_BODIES` from the process environment on each error response. Client construction never receives the resolved settings value. An offline reproduction returned `True` from explicit settings and `False` from the HTTP helper in the same process.

**Source:** *The Pragmatic Programmer* — DRY; *A Philosophy of Software Design* — Information Hiding and Leakage.

**Consequence:** Constructor and dotenv settings do not govern this HTTP behavior. Maintainers must reconcile two parsers and two configuration lifetimes for one logging policy. Environment mutation can change logging independently of cached settings. This is confirmed policy inconsistency; the reproduction does not establish disclosure of credentials.

**Remedy:** Add an explicit client logging-policy argument with a safe default. Pass the resolved setting from the server through client constructors and remove the HTTP-layer environment lookup. Verify constructor, environment, and dotenv configuration resolve to the same runtime policy, preserving standalone client construction.

**Priority:** Pain 2 × Spread 2 = **4 — Scheduled debt**. Ownership spans settings, server composition, and the base HTTP client. **Intent:** [accidental] for prioritization. The helper documents a deliberate convenience for standalone clients, but no payback plan for the competing setting authority is visible.

### 🟢 Suggestion

**D3 · R5 Dependency Disorder — Transport exception imports load FastMCP**

**Symptom:** [errors.py:8](../src/unifi_mcp/errors.py#L8) imports FastMCP's `ToolError` alongside transport exception definitions. The base client, all four concrete clients, and certificate-pinning transport import this module. Presentation mapping and transport exception vocabulary share one dependency boundary.

**Source:** *Clean Architecture* — Dependency Inversion and separation of policy from presentation details.

**Consequence:** Reusing the HTTP clients or changing MCP error presentation carries framework coupling into transport code. The impact is currently small: this package is an MCP server, and isolated HTTP tests remain practical.

**Remedy:** Keep transport exception types framework-independent and move `handle_client_error` and its formatting helper into a tool-layer adapter. Update the shared handler import and preserve any supported public import path during migration.

**Priority:** Pain 1 × Spread 3 = **3 — Monitored debt**. The import dependency reaches more than five client/transport modules, but no active upgrade blockage is demonstrated. **Intent:** [accidental]; no documented payback plan found.

## Debt Summary

| Risk | Findings | Avg Priority | Classification | Intent |
|------|---------:|-------------:|----------------|--------|
| Cognitive Overload | 0 | — | No finding | — |
| Change Propagation | 1 | 4.0 | Scheduled | [accidental] |
| Knowledge Duplication | 1 | 4.0 | Scheduled | [accidental] |
| Accidental Complexity | 0 | — | No finding | — |
| Dependency Disorder | 1 | 3.0 | Monitored | [accidental] |
| Domain Model Distortion | 0 | — | No finding | — |

**Recommended focus:** D1 first, then D2, within the quarter. Both establish explicit configuration ownership. Consider D3 when next changing exception mapping or reusing the clients. No finding scores 7–9, so this assessment does not justify sprint-critical refactoring.

## Coverage and tradeoffs

- **R1:** The largest non-registrar function is the 123-line lifespan, including comments and documentation. Its client-construction branches are linear and cohesive. Nested tool registrars are long because they register independently named tools. Neither length alone warrants a cognitive-overload finding.
- **R2:** Configuration ownership is the concrete propagation issue. Normal feature additions across a tool, its API adapter, tests, and generated documentation are coordinated work within a feature boundary.
- **R3:** `_inventory.py`, inventory tests, and the schema renderer provide explicit authorities and drift guards. Similar endpoint wrappers across different upstream APIs do not necessarily duplicate decisions. Streaming and buffered HTTP paths share rate-limit handling while retaining different response lifecycles.
- **R4:** No sampled speculative subsystem or unnecessary framework was established. Sixteen tools across nine files accept `data`, including raw upstream ACL/DNS rule payloads and backward-compatible update paths. Their existence alone does not demonstrate avoidable complexity. The denylist-to-named-argument transition is documented in shared helpers and issue references.
- **R5:** Static imports, including lazy imports and excluding `TYPE_CHECKING` branches, contain no runtime cycles. Registration and server fan-out are composition responsibilities. This scan does not resolve arbitrary dynamic imports.
- **R6:** Raw response dictionaries and thin API adapters are explicit design choices in `CLAUDE.md` and `CONTEXT.md`. No rich domain model is required without a specific invariant to own. The destructive-write convention has an ADR and a server-wide invariant test.

The earlier architecture report was consulted as supporting evidence; D1 and D2 were independently reproduced for this assessment. These findings overlap that report and should not be counted as additional distinct debt in a combined backlog. This assessment does not certify every handler or upstream wire contract.

## Validation

Offline reproductions used synthetic settings with environment and dotenv input isolated; the startup reproduction enabled no runtime clients and made no controller requests. Focused tests passed: **237 passed in 24.21s** across server, lifespan, settings, base client, inventory, and schema-matrix suites. The passing suite and reproductions together establish a coverage gap around explicit-versus-global settings. No production code was changed.

## Summary

Schedule configuration ownership work first: bind startup to the supplied settings, then pass logging policy explicitly into clients. Existing shared helpers, drift checks, and documented API boundaries support localized refactoring; the evidence does not call for a repository-wide redesign.
