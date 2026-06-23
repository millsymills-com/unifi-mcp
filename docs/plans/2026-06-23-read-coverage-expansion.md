# Read-Only Tool Coverage Expansion — unifi-mcp

> Plan date: 2026-06-23. Execution target: other agents with no extra context.
> All paths are absolute or repo-relative from
> `/Users/mills/Desktop/Projects/mcp-server-dev/unifi-mcp`.

## Goal & scope (read-only; per-API read ceilings; decisions locked)

Maximize per-API **read-only** coverage of each official UniFi API surface. The
user's decisions are locked and not to be revisited:

- **Read tools only.** No write/action/create/update/delete tools. No
  PATCH/PUT/DELETE and no state-mutating POST. A POST that is a pure query
  (the `isp-metrics/{type}/query` selector body) is allowed and counts as a
  read — it is the *only* POST in this plan.
- **Per-API 90% is the aspiration, but read-only physically caps it.** Deliver
  the read ceiling, not 90%. On the write-heavy Network Integration and Protect
  surfaces the ceiling is below 90% because every remaining gap is a write or an
  excluded WS subscription. Site Manager has no documented writes, so its read
  ceiling equals 100%.
- **Network: add a NEW read-only client** for the official Integration API at
  `/proxy/network/integration/v1/` (UUID site ids, `X-API-KEY`). Read/list tools
  first. Do **not** touch the existing legacy `NetworkClient`, its tools, or its
  `{"network"}` tag.

Authoritative gap source: `docs/api-coverage-matrix.md`, rows marked **Gap**.
Only GET / pure-query gaps are in scope.

### Hard conventions (verified in the codebase)

- Tool naming (PROTO-002): `unifi_{api}_{verb}_{entity}`, `snake_case`, always
  `unifi_` prefix. Network Integration tools keep the `unifi_network_` prefix
  (same namespace) but must not collide with existing legacy `unifi_network_*`
  names — verified collision-free below.
- Read tool shape (see `src/unifi_mcp/tools/site_manager/discovery.py`):
  ```python
  @mcp.tool(tags={"<api_tag>"})
  @tool_handler()
  async def unifi_<api>_<verb>_<entity>(ctx: Context, ...) -> dict[str, Any]:
      """Google-style docstring with Args/Returns/Raises."""
      ...validate_id(x, field="x")...
      return redact_secrets(await get_server_context(ctx).clients["<key>"].<method>(...))
  ```
  Read tools take **no** `@tool_handler(write=True)`; they get no `{"write"}`
  tag, so `mcp.disable(tags={"write"})` never hides them.
- Clients subclass `BaseUniFiClient` (`src/unifi_mcp/clients/base.py`), set
  `self._path_prefix`, expose async read methods returning `dict`/`list[dict]`,
  implement `validate_connection()`, and route every agent-controlled path
  segment through `self._segment(id)`. `self.get(path, params=...)` parses JSON;
  `self.get_raw(path, max_bytes=...)` returns bytes.
- `validate_id` (`src/unifi_mcp/tools/_common.py:182`) accepts
  `^[A-Za-z0-9_-]{1,64}$`. A 36-char UUID (hex + hyphen) **passes** this regex,
  so per-tool resource ids (`acl_rule_id`, `zone_id`, …) use `validate_id`. The
  *config-level* site UUID interpolated into the path prefix needs a dedicated
  UUID validator (see Phase 0) — `validate_id`/`_SITE_RE` are wrong for it.
- Namespace membership is classified by **name prefix**
  (`tool.name.startswith(NAMESPACE_PREFIXES[ns])`) in **three** places, verified:
  `tests/unit/test_tool_inventory.py` (`test_per_namespace`,
  `test_per_namespace_read_write_split`) **and** `src/unifi_mcp/_schema.py:149`
  (the schema-matrix renderer, which also iterates a fixed `_SECTIONS` list). The
  doc-count assertions (`TestDocsCiteCanonicalCounts`) additionally hardcode the
  **three** namespaces network/protect/site_manager into format strings. The 28
  Network Integration tools are named `unifi_network_*`, so they are counted in
  the existing **`network`** namespace by every one of these classifiers with no
  change — Phase 0 does **not** introduce a 4th namespace (doing so would require
  editing all three classifiers *and* break the 3-namespace doc strings). The new
  `{"network_integration"}` tag is for graceful-degradation only and is invisible
  to the prefix-based count.

## Coverage targets

Denominators from `docs/api-coverage-matrix.md` (each API enumerates 73 ops for
Network/Protect; Site Manager has 9). Network Integration §3b excludes 1
(`/countries`); Protect excludes 2 WS subscriptions.

| API | baseline covered | read ceiling | new read tools | ceiling note |
|---|---|---|---|---|
| Site Manager | 3/9 = 33% | **9/9 = 100%** | 6 | no documented writes; ceiling = full surface |
| Protect Integration v1 | 13/73 = 18% | **41/73 = 56%** | 28 | remaining 32 = 30 writes + 2 WS (unreachable read-only) |
| Network Integration v1 | 26/72 in-scope = 36% | **54/72 = 75%** | 28 | remaining 18 = all writes (unreachable read-only) |

The 90% per-API aspiration is **provably unattainable read-only** for Protect and
Network Integration: after every GET/pure-query gap is covered, every remaining
operation is a write (`POST`/`PUT`/`PATCH`/`DELETE`) or an excluded WS stream.

### Combined-count reconciliation (CRITICAL for integrators)

Each phase below states its *standalone* delta against today's baseline
(`TOTAL_TOOLS = 85`, reads 38). **No phase accounts for the others.** When more
than one phase has landed, the `_inventory.py` constants and every doc count must
reflect the *cumulative* total, not a single phase's number:

| landed phases | TOTAL_TOOLS | read tools | write tools |
|---|---|---|---|
| baseline | 85 | 38 | 47 |
| + Site Manager (Phase 1) | 91 | 44 | 47 |
| + Protect (Phase 2) | 119 | 72 | 47 |
| + Network Integration (Phase 3) | 147 | 100 | 47 |

`_inventory.py` derives `TOTAL_TOOLS`, `EXPECTED_READ_TOOLS`, and
`EXPECTED_WRITE_TOOLS` automatically from `EXPECTED_NAMESPACE_SPLITS`; only the
per-namespace `read` ints change by hand. Write count never changes (no writes
added). Whichever PR lands second/third must re-derive the doc strings against
the *current* `EXPECTED_*` constants, never a hard-coded "113".

The 28 Network Integration tools fold into the **`network`** namespace (they are
`unifi_network_*`): `EXPECTED_NAMESPACE_SPLITS["network"]["read"]` goes 26 → 54,
so `network` total is 65 → 93 once Phase 3 lands. No new namespace key is added.

---

## Phase 0 — Network Integration client

New `NetworkIntegrationClient`. This phase ships the client + wiring with **zero
tools** (or fold it into the first tool PR — see checklist); it is the
prerequisite for Phase 3. No inventory-classifier refactor is needed — see the
note below.

### Files

- New: `src/unifi_mcp/clients/network_integration.py` —
  `class NetworkIntegrationClient(BaseUniFiClient)`, `_path_prefix =
  "/proxy/network/integration/v1/"`.
- Edit: `src/unifi_mcp/config.py` — new opt-out flag, UUID validator, base-url
  and site properties.
- Edit: `src/unifi_mcp/server.py` — `APIClients` TypedDict entry,
  `TYPE_CHECKING` import, lifespan construction, degradation-loop entry.
- Edit: `src/unifi_mcp/tools/__init__.py` — register branch.
- No `_inventory.py` / `test_tool_inventory.py` / `_schema.py` classifier change:
  the new tools are `unifi_network_*` and count under the existing `network`
  namespace (see the namespace note below). Only the `network.read` int moves,
  and only in the tool-bearing PR (Phase 3).

### Config changes (`config.py`)

No new host/port/key env vars — the Integration API lives on the same UniFi OS
appliance as the legacy controller, reusing `unifi_network_host/port`,
`unifi_network_verify_ssl`, `unifi_network_cert_fingerprint`, and the
`unifi_network_api` key. Add:

- `unifi_network_integration_enabled: bool = True` — explicit opt-out for
  operators on firmware lacking `/integration/v1`, suppressing it without
  dropping legacy Network tools.
- `unifi_network_integration_site: str | None = None` — a UUID site id. When
  unset, the client auto-discovers the default site via `GET /v1/sites` at
  `validate_connection` time and caches it. When set, validate as a UUID and use
  verbatim.
- Property `network_integration_base_url -> str` returning the same value as
  `network_base_url` (the appliance root); the client appends the fixed
  `_path_prefix`.
- Property `network_integration_enabled -> bool` returning
  `self.network_enabled and self.unifi_network_integration_enabled` — gates
  registration only when a Network key exists *and* the operator hasn't opted
  out.
- A UUID validator. Add a module constant and a `field_validator`:
  ```python
  _UUID_RE = re.compile(
      r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
      r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
  )
  ```
  validating `unifi_network_integration_site` when not `None` (empty/blank →
  `None`, mirroring `_validate_fingerprint`). Do **not** reuse `_SITE_RE` (slug
  space) — the integration site id is a different identifier space.

Reuse `unifi_request_timeout`, `unifi_max_retries`. List-tool `offset`/`limit`
params (Phase 3) are bounded by `unifi_max_list_items` / `unifi_max_list_offset`.

### Client (`network_integration.py`)

- Constructor signature mirrors `NetworkClient` but takes `site: str | None`
  (the configured UUID, may be `None`).
- Holds `self._site: str | None` (the configured value) and
  `self._resolved_site: str | None = None` (cached after discovery).
- `validate_connection()`:
  1. `GET v1/sites` (no `_path_prefix` issue — relative path `v1/sites`; note
     `_path_prefix` already ends `.../integration/v1/`, so the per-site paths are
     `sites/{id}/...`; reconcile the prefix vs. the leading `v1/` so the realized
     URL is exactly `/proxy/network/integration/v1/sites`). **Resolve this
     prefix arithmetic against live hardware before coding** — pick either
     `_path_prefix = "/proxy/network/integration/" ` + `"v1/sites"` or
     `_path_prefix = "/proxy/network/integration/v1/"` + `"sites"`. Add a unit
     test asserting the realized URL.
  2. On success, set `_resolved_site` = configured `_site` if set, else the entry
     in the response flagged default (fall back to first). Cache for process
     life.
  3. On `UniFiError`/`httpx.HTTPError` (incl. 404 on old firmware, HTML portal,
     401), stash `self._last_validation_error`, return `False`.
- A private `self._site_path(suffix: str) -> str` helper building
  `sites/{self._segment(resolved)}/{suffix}` so tools never pass a site id.
- ~28 read methods (Phase 3 table). Methods that hit `/v1/<global>` resources
  (`sites`, `pending-devices`, `dpi/...`) do **not** take a site; per-site
  methods use `_site_path`.
- Pagination: list methods accept `offset: int = 0, limit: int = 200` and pass
  them via `params=`.

### Wiring

- `server.py` `APIClients` (line 42): add `network_integration:
  NetworkIntegrationClient` and the `TYPE_CHECKING` import.
- `server.py` `server_lifespan` (after the `config.network_enabled` block, before
  the degradation loop):
  ```python
  if config.network_integration_enabled:
      failures["network_integration"] = await _register_client(
          context, "network_integration",
          NetworkIntegrationClient(
              base_url=config.network_integration_base_url,
              api_key=_require_api_key("network", config.unifi_network_api),
              site=config.unifi_network_integration_site,
              verify_ssl=config.unifi_network_verify_ssl,
              cert_fingerprint=config.unifi_network_cert_fingerprint,
              timeout=config.unifi_request_timeout,
              max_retries=config.unifi_max_retries,
          ),
      )
  ```
  Lazy-import `NetworkIntegrationClient` alongside the other client imports.
- `server.py` degradation loop (line 169 tuple): add
  `("network_integration", config.network_integration_enabled)`. Because the tag
  is `{"network_integration"}` (distinct from `{"network"}`), a 404 on old
  firmware deregisters only the integration tools; legacy Network tools survive.
- `tools/__init__.py` `_register_for_each_api`: add
  ```python
  if config.network_integration_enabled:
      from unifi_mcp.tools.network_integration import register_network_integration_tools
      register_network_integration_tools(mcp)
  ```

### Namespace counting (no classifier refactor)

The 28 integration tools are named `unifi_network_*`, so every name-prefix
classifier already counts them under `network` with no change. Verified
consumers of `NAMESPACE_PREFIXES` (do **not** add a 4th namespace — it would
break all of these):

- `tests/unit/test_tool_inventory.py` — `test_per_namespace` /
  `test_per_namespace_read_write_split` count by `tool.name.startswith(prefix)`.
- `src/unifi_mcp/_schema.py:149` — schema-matrix renderer, `name.startswith(...)`
  over a fixed `_SECTIONS` list (network/protect/site_manager).
- `tests/unit/test_tool_inventory.py::TestDocsCiteCanonicalCounts` — README /
  CLAUDE.md assertion strings hardcode exactly the 3 namespaces.

The only `_inventory.py` edit is bumping
`EXPECTED_NAMESPACE_SPLITS["network"]["read"]` 26 → 54 (in Phase 3, when the
tools land). The `{"network_integration"}` tag is used solely by the lifespan
degradation loop; it is not a counting namespace and the inventory tests never
inspect it.

### validate_connection / graceful degradation

Tag-based, identical to existing APIs: a `False` return from
`validate_connection` causes `server.disable(tags={"network_integration"})` in
the lifespan loop. The `UNIFI_NETWORK_INTEGRATION_ENABLED=false` opt-out skips
registration entirely (no startup WARN).

---

## Phase 1 — Site Manager reads (smallest; 9/9 = 100%; ship first as proof)

Smallest, fully read-cappable surface. No new client, config flag, lifespan, or
`APIClients` wiring — `site_manager_enabled`, `clients["site_manager"]`, the
`{"site_manager"}` tag, and lifespan degradation already exist. Purely additive:
new client methods + two new tool modules.

### Files

- Edit: `src/unifi_mcp/clients/site_manager.py` — 6 read methods.
- New: `src/unifi_mcp/tools/site_manager/metrics.py` —
  `register_site_manager_metrics_tools(mcp)`.
- New: `src/unifi_mcp/tools/site_manager/sdwan.py` —
  `register_site_manager_sdwan_tools(mcp)`.
- Edit: `src/unifi_mcp/tools/site_manager/discovery.py` — add `get_host` tool to
  the existing register fn.
- Edit: `src/unifi_mcp/tools/site_manager/__init__.py` — call the two new
  registrars.

### The one load-bearing decision: `/ea/` path routing (BLOCKING)

`SiteManagerClient._path_prefix = "/v1/"` and `BaseUniFiClient._url`
(`base.py:119`) rejects any leading-`/` or scheme-prefixed path while **always**
prepending `_path_prefix`. So `self.get("ea/sd-wan-configs")` resolves to
`/v1/ea/sd-wan-configs` — **wrong**; `/ea/` sits beside `/v1/`, not under it.

Resolution — add an EA-prefixed code path on the client. Minimal, low-blast-radius
option: a private helper that issues the request with an alternate prefix without
mutating `_path_prefix` or weakening the `_url` traversal gate:

Thread the override as an **explicit parameter** on `_url` and `_request` — not
through `**kwargs`, which `_request` forwards verbatim to
`httpx.AsyncClient.request` (an unknown `_prefix_override=` kwarg there raises
`TypeError`). Concretely:

```python
# base.py
def _url(self, path: str, *, prefix: str | None = None) -> str:
    if not isinstance(path, str) or path.startswith(("/", "http://", "https://")):
        raise UniFiBadRequestError(f"invalid request path: {path!r}")
    return f"{prefix if prefix is not None else self._path_prefix}{path}"

async def _request(self, method, path, *, prefix=None, **kwargs):
    ...  # pass prefix into self._url(path, prefix=prefix); httpx kwargs stay in **kwargs

# site_manager.py
_EA_PREFIX = "/ea/"

async def _get_ea(self, suffix: str, **kwargs) -> Any:
    # suffix is a bare relative path ("sd-wan-configs", "sd-wan-configs/{id}")
    # built from _segment() for any id; never leading-slash / scheme.
    response = await self._request("GET", suffix, prefix=self._EA_PREFIX, **kwargs)
    return self._parse_json(response)
```

Keep the leading-slash / scheme rejection intact for the override path (the
example above preserves it). `get_raw` also calls `_url(path)`; if any EA
endpoint ever needs raw bytes, give it the same keyword. Add a unit test
asserting the realized URL is exactly `/ea/sd-wan-configs` (and
`/ea/sd-wan-configs/{id}` / `.../status`), and a test asserting the `/v1/`
methods still resolve under `/v1/`. Do **not** special-case by string-munging
inside `get`.

### Client methods (`site_manager.py`)

- `get_host(host_id)` → `self.get(f"hosts/{self._segment(host_id)}")`.
- `get_isp_metrics(metric_type, begin_timestamp, end_timestamp, duration)` →
  `self.get(f"isp-metrics/{self._segment(metric_type)}", params=...)` with only
  the non-`None` params populated.
- `query_isp_metrics(metric_type, sites)` →
  `self.post(f"isp-metrics/{self._segment(metric_type)}/query", json={"sites": sites})`.
  This is the only POST in the plan — a pure selector query, mutates nothing.
- `list_sdwan_configs()` → `self._get_ea("sd-wan-configs")`.
- `get_sdwan_config(config_id)` → `self._get_ea(f"sd-wan-configs/{self._segment(config_id)}")`.
- `get_sdwan_config_status(config_id)` →
  `self._get_ea(f"sd-wan-configs/{self._segment(config_id)}/status")`.

### Tool-layer rules

- `metric_type` is interpolated into the path. Do **not** `validate_id` — `"5m"`
  passes the ID regex but an arbitrary value 404s. Validate against an explicit
  `{"5m", "1h"}` allowlist, raising `UniFiBadRequestError` before any HTTP call.
- `validate_id` on `host_id`, `config_id` (get + status).
- Every response passes through `redact_secrets(...)` — host `reportedState`/
  `userData` and SD-WAN configs can carry tokens/PSKs. Do not skip the wrap on
  the EA tools.

### Registration

`tools/site_manager/__init__.py` extends `register_site_manager_tools` to call
the existing discovery registrar plus `register_site_manager_metrics_tools` and
`register_site_manager_sdwan_tools`. All three register under
`tags={"site_manager"}`; existing tag-based degradation covers them.

### Standalone inventory delta

`_inventory.py`: `EXPECTED_NAMESPACE_SPLITS["site_manager"]["read"]` 3 → 9.
`TOTAL_TOOLS` derives 85 → 91; reads 38 → 44 (apply against current constants per
the reconciliation table).

---

## Phase 2 — Protect reads

28 new read tools across 3 new modules under `src/unifi_mcp/tools/protect/`, plus
~28 read methods on the existing `ProtectClient`. No new client/config/lifespan/
`APIClients` wiring — the `protect` key, `{"protect"}` tag, config flag, and
degradation already exist.

### Files

- Edit: `src/unifi_mcp/clients/protect.py` — ~28 read methods under the
  `-- Read methods --` section, each `self.get(...)` + `self._segment(id)` for
  `{id}` params; `get_rtsps_stream` passes `qualities` via `params=`.
- New: `src/unifi_mcp/tools/protect/device_reads.py` —
  `register_protect_device_read_tools(mcp)`. Per-resource `get_{id}` for the 4
  existing list classes (chimes/lights/sensors/viewers) plus list+get for 7 new
  device classes (speakers, sirens, bridges, relays, link-stations, fobs,
  alarm-hubs).
- New: `src/unifi_mcp/tools/protect/liveviews.py` —
  `register_liveview_tools(mcp)`. liveviews list+get; arm-profiles list
  (read-only alarm-manager surface; enable/disable/settings/{id} stay OUT).
- New: `src/unifi_mcp/tools/protect/access.py` —
  `register_protect_access_tools(mcp)`. users list+get, ulp-users list+get,
  meta/info, `cameras/{id}/rtsps-stream` GET, `files/{fileType}` GET.
- Edit: `src/unifi_mcp/tools/protect/__init__.py` — call the three new
  registrars.

### Mandatory redaction

Protect bodies carry credential-bearing fields (rtsps stream URLs/tokens, NVR
`ssoToken`, user/ulp-user identity records). Every tool wraps its response in
`redact_secrets(...)`. This matches existing Protect tools
(`tools/protect/devices.py` already redacts) — it is consistent codebase
behavior, not a Site-Manager-only pattern.

### Validation

Every `{id}` / `{fileType}` param flows through `validate_id` before any HTTP
call. (`fileType` is interpolated into the path; `validate_id` is the correct
traversal gate here.)

### `files/{fileType}` — verify content-type FIRST (design-incomplete)

The spec assumes a JSON metadata response and places `get_file_asset` in
`access.py` with `self.get(...)`. If the endpoint returns **raw bytes**, it must
instead live in `src/unifi_mcp/tools/protect/media.py` using `self.get_raw(...)`
with a max-bytes cap modeled on `unifi_protect_get_snapshot` /
`unifi_max_snapshot_bytes`. **Verify the content-type against live hardware (or
the 7.1.42 OpenAPI mirror) before finalizing** the module placement.

### `cameras/{id}/rtsps-stream` GET

GET only; the POST(create)/DELETE(remove) on this path stay OUT. The GET may 404
or return empty on a camera with no active RTSPS stream — document like
`export_video` (#227); do not fail `validate_connection` on it.

### Registration

`tools/protect/__init__.py` `register_protect_tools` additionally imports and
calls `register_protect_device_read_tools`, `register_liveview_tools`,
`register_protect_access_tools`. No `server.py`/lifespan/`APIClients` change. No
new `validate_connection` (existing `get_nvr` health check stands).

### Standalone inventory delta

`_inventory.py`: `EXPECTED_NAMESPACE_SPLITS["protect"]["read"]` 9 → 37 (write
stays 8). Protect total 17 → 45. Apply against current constants per the
reconciliation table.

---

## Phase 3 — Network Integration read tools

28 read tools in a new `src/unifi_mcp/tools/network_integration/` package,
consuming `NetworkIntegrationClient` from Phase 0. All tagged
`{"network_integration"}`, all under the `unifi_network_` name prefix, none with
`{"write"}`. Tools take **no** `siteId` param — the client injects the resolved,
cached site into per-site paths.

### Files

- New package `src/unifi_mcp/tools/network_integration/` with
  `__init__.py` exporting `register_network_integration_tools(mcp)` that imports
  per-module register fns, plus the modules: `sites.py`, `devices.py`, `dpi.py`,
  `acl.py`, `firewall.py`, `dns.py`, `networks.py`, `hotspot.py`, `traffic.py`,
  `switching.py`, `vpn.py`, `wan.py`, `radius.py`.

### Pagination & caps

List tools accept `offset: int = 0, limit: int = 200`. Bound `offset` by
`config.unifi_max_list_offset` and `limit` by `config.unifi_max_list_items`
before the client call (mirror the existing legacy list-tool caps), so these
tools cannot bypass the safety ceilings. The Integration API returns a paginated
`{data, offset, limit, count, totalCount}` envelope — agents must not assume the
legacy flat `{data:[...]}` shape.

### Redaction decision (OWNER DECISION — resolve before coding)

The convention reserves `redact_secrets` for Site Manager. These 28 tools are
local-controller data, but `radius/profiles` and `vpn/servers` may carry PSKs /
shared keys. **Recommendation:** run at least the RADIUS and VPN responses (and,
defensively, all 28) through `redact_secrets(...)`. Flagged for owner sign-off;
do not ship credential-bearing responses unredacted.

### Standalone inventory delta

Bump `EXPECTED_NAMESPACE_SPLITS["network"]["read"]` 26 → 54 (no new namespace
key; the tools are `unifi_network_*` and count under `network`). `network` total
65 → 93. Apply against current constants per the reconciliation table.

---

## Cross-cutting

For **every** new tool, in lockstep (CI fails otherwise):

1. **`src/unifi_mcp/_inventory.py`** — bump the per-namespace `read` int
   (`site_manager` 3→9, `protect` 9→37, `network` 26→54 for the folded
   integration tools; no new namespace key). `TOTAL_TOOLS`, `EXPECTED_READ_TOOLS`,
   `EXPECTED_WRITE_TOOLS` derive automatically.
2. **`docs/api-coverage-matrix.md`** (hand-maintained snapshot, no generator):
   - §1 Site Manager: flip the 6 Gap rows to Covered with tool names; summary row
     → `9 | 0 | 0 | 9 | 100%`; trailing line → `GA 6/6 (100%); overall 9/9
     (100%)`.
   - §2 Protect: move the 28 GET rows into the Covered table; per-API row Covered
     13 → 41, Gap 58 → 30, 18% → 56%; closing line → `Covered 41/73 ops (56%)`.
     Keep all PATCH/POST actions in the Gap block.
   - §3b Network Integration: flip the 28 GET Gap rows to Covered; Covered 26 →
     54, Gap 46 → 18, 36% → 75%; footer accordingly. `/v1/info` stays covered by
     legacy `unifi_network_get_sysinfo` (no new tool).
   - Header counts (`85 MCP tools` / per-API parenthetical) → the cumulative
     total for the phases that have landed.
3. **`docs/tool-schema-matrix.md`** — regenerate via
   `uv run python scripts/gen_schema_matrix.py` *after* the tools exist
   (machine-asserted by `tests/unit/test_schema_matrix.py`; never hand-edit).
4. **`README.md`** — update the `N tools` headline, the `N MCP tools** covering
   UniFi Network (X), Protect (Y), and Site Manager (Z)` line, the per-API
   breakdown, and the read/write framing. The `47 write tools` line is unchanged
   (no writes added). The exact strings are asserted by
   `tests/unit/test_tool_inventory.py::TestDocsCiteCanonicalCounts`.
5. **`CLAUDE.md`** (unifi-mcp) — update the Architecture tree (add the
   `network_integration` client + `tools/network_integration/` package; new
   `metrics.py`/`sdwan.py` under site_manager; new device_reads/liveviews/access
   under protect) and the per-API tool-count line (asserted by
   `test_claude_md_counts` / `test_claude_md_per_api_splits`).
6. **`tests/unit/test_tool_inventory.py`** — Phase 0 makes it tag-keyed; every
   phase's `EXPECTED_*` bump is auto-asserted against the live registered surface.
7. **`tests/unit/test_schema_matrix.py`** — passes once the matrix is regenerated.
8. **respx unit tests** — one per new client method (exact path, `X-API-Key`
   header, parsed return shape) + an error-path test (404 → typed exception →
   `ToolError` via `tool_handler`) + validate-id/allowlist rejection tests. URL
   tests: assert `/ea/...` is *not* `/v1/ea/...` (Phase 1) and the resolved
   integration `siteId` interpolation (Phase 0/3).
9. **Cassettes** — Network Integration integration tests record VCR-style
   cassettes (`make refresh-cassettes` / `verify-cassettes`). Protect/Site
   Manager unit layers use respx; Site Manager integration optionally records
   cassettes for the 6 endpoints (EA tier is 100 req/min — record once).

---

## Per-tool appendix

### Site Manager (Phase 1)

| tool | http | endpoint | params | client method | module |
|---|---|---|---|---|---|
| `unifi_site_manager_get_host` | GET | `/v1/hosts/{id}` | `host_id` (validate_id) | `get_host` | `site_manager/discovery.py` |
| `unifi_site_manager_get_isp_metrics` | GET | `/v1/isp-metrics/{type}` | `metric_type` (allowlist 5m/1h); `begin_timestamp`/`end_timestamp`/`duration` opt | `get_isp_metrics` | `site_manager/metrics.py` |
| `unifi_site_manager_query_isp_metrics` | POST (pure query) | `/v1/isp-metrics/{type}/query` | `metric_type` (allowlist); `sites: list[dict]` | `query_isp_metrics` | `site_manager/metrics.py` |
| `unifi_site_manager_list_sdwan_configs` | GET | `/ea/sd-wan-configs` | — | `list_sdwan_configs` | `site_manager/sdwan.py` |
| `unifi_site_manager_get_sdwan_config` | GET | `/ea/sd-wan-configs/{id}` | `config_id` (validate_id) | `get_sdwan_config` | `site_manager/sdwan.py` |
| `unifi_site_manager_get_sdwan_config_status` | GET | `/ea/sd-wan-configs/{id}/status` | `config_id` (validate_id) | `get_sdwan_config_status` | `site_manager/sdwan.py` |

### Protect Integration v1 (Phase 2) — endpoints relative to `/proxy/protect/integration/v1/`

| tool | http | endpoint | params | client method | module |
|---|---|---|---|---|---|
| `unifi_protect_get_chime` | GET | `chimes/{id}` | `chime_id` (validate_id) | `get_chime` | `protect/device_reads.py` |
| `unifi_protect_get_light` | GET | `lights/{id}` | `light_id` | `get_light` | `protect/device_reads.py` |
| `unifi_protect_get_sensor` | GET | `sensors/{id}` | `sensor_id` | `get_sensor` | `protect/device_reads.py` |
| `unifi_protect_get_viewer` | GET | `viewers/{id}` | `viewer_id` | `get_viewer` | `protect/device_reads.py` |
| `unifi_protect_list_speakers` | GET | `speakers` | — | `list_speakers` | `protect/device_reads.py` |
| `unifi_protect_get_speaker` | GET | `speakers/{id}` | `speaker_id` | `get_speaker` | `protect/device_reads.py` |
| `unifi_protect_list_sirens` | GET | `sirens` | — | `list_sirens` | `protect/device_reads.py` |
| `unifi_protect_get_siren` | GET | `sirens/{id}` | `siren_id` | `get_siren` | `protect/device_reads.py` |
| `unifi_protect_list_bridges` | GET | `bridges` | — | `list_bridges` | `protect/device_reads.py` |
| `unifi_protect_get_bridge` | GET | `bridges/{id}` | `bridge_id` | `get_bridge` | `protect/device_reads.py` |
| `unifi_protect_list_relays` | GET | `relays` | — | `list_relays` | `protect/device_reads.py` |
| `unifi_protect_get_relay` | GET | `relays/{id}` | `relay_id` | `get_relay` | `protect/device_reads.py` |
| `unifi_protect_list_link_stations` | GET | `link-stations` | — | `list_link_stations` | `protect/device_reads.py` |
| `unifi_protect_get_link_station` | GET | `link-stations/{id}` | `link_station_id` | `get_link_station` | `protect/device_reads.py` |
| `unifi_protect_list_fobs` | GET | `fobs` | — | `list_fobs` | `protect/device_reads.py` |
| `unifi_protect_get_fob` | GET | `fobs/{id}` | `fob_id` | `get_fob` | `protect/device_reads.py` |
| `unifi_protect_list_alarm_hubs` | GET | `alarm-hubs` | — | `list_alarm_hubs` | `protect/device_reads.py` |
| `unifi_protect_get_alarm_hub` | GET | `alarm-hubs/{id}` | `alarm_hub_id` | `get_alarm_hub` | `protect/device_reads.py` |
| `unifi_protect_list_liveviews` | GET | `liveviews` | — | `list_liveviews` | `protect/liveviews.py` |
| `unifi_protect_get_liveview` | GET | `liveviews/{id}` | `liveview_id` | `get_liveview` | `protect/liveviews.py` |
| `unifi_protect_list_arm_profiles` | GET | `arm-profiles` | — | `list_arm_profiles` | `protect/liveviews.py` |
| `unifi_protect_list_users` | GET | `users` | — | `list_users` | `protect/access.py` |
| `unifi_protect_get_user` | GET | `users/{id}` | `user_id` | `get_user` | `protect/access.py` |
| `unifi_protect_list_ulp_users` | GET | `ulp-users` | — | `list_ulp_users` | `protect/access.py` |
| `unifi_protect_get_ulp_user` | GET | `ulp-users/{id}` | `ulp_user_id` | `get_ulp_user` | `protect/access.py` |
| `unifi_protect_get_meta_info` | GET | `meta/info` | — | `get_meta_info` | `protect/access.py` |
| `unifi_protect_get_rtsps_stream` | GET | `cameras/{id}/rtsps-stream` | `camera_id` (validate_id); `qualities: list[str] \| None` | `get_rtsps_stream` | `protect/access.py` |
| `unifi_protect_get_file_asset` | GET | `files/{fileType}` | `file_type` (validate_id) | `get_file_asset` | `protect/access.py` (or `media.py` if bytes) |

### Network Integration v1 (Phase 3) — endpoints relative to `/proxy/network/integration/v1/`; per-site paths get the resolved UUID injected by the client

| tool | http | endpoint | params | client method | module |
|---|---|---|---|---|---|
| `unifi_network_list_sites` | GET | `/v1/sites` | `offset=0`, `limit=200` | `list_sites` | `network_integration/sites.py` |
| `unifi_network_list_pending_devices` | GET | `/v1/pending-devices` | — | `list_pending_devices` | `network_integration/devices.py` |
| `unifi_network_list_dpi_applications` | GET | `/v1/dpi/applications` | `offset`, `limit` | `list_dpi_applications` | `network_integration/dpi.py` |
| `unifi_network_list_dpi_categories` | GET | `/v1/dpi/categories` | `offset`, `limit` | `list_dpi_categories` | `network_integration/dpi.py` |
| `unifi_network_list_device_tags` | GET | `…/device-tags` | — | `list_device_tags` | `network_integration/devices.py` |
| `unifi_network_list_acl_rules` | GET | `…/acl-rules` | `offset`, `limit` | `list_acl_rules` | `network_integration/acl.py` |
| `unifi_network_get_acl_rules_ordering` | GET | `…/acl-rules/ordering` | — | `get_acl_rules_ordering` | `network_integration/acl.py` |
| `unifi_network_get_acl_rule` | GET | `…/acl-rules/{id}` | `acl_rule_id` (validate_id) | `get_acl_rule` | `network_integration/acl.py` |
| `unifi_network_get_firewall_policies_ordering` | GET | `…/firewall/policies/ordering` | — | `get_firewall_policies_ordering` | `network_integration/firewall.py` |
| `unifi_network_list_firewall_zones` | GET | `…/firewall/zones` | `offset`, `limit` | `list_firewall_zones` | `network_integration/firewall.py` |
| `unifi_network_get_firewall_zone` | GET | `…/firewall/zones/{id}` | `zone_id` (validate_id) | `get_firewall_zone` | `network_integration/firewall.py` |
| `unifi_network_list_dns_policies` | GET | `…/dns/policies` | `offset`, `limit` | `list_dns_policies` | `network_integration/dns.py` |
| `unifi_network_get_dns_policy` | GET | `…/dns/policies/{id}` | `dns_policy_id` (validate_id) | `get_dns_policy` | `network_integration/dns.py` |
| `unifi_network_get_network_references` | GET | `…/networks/{id}/references` | `network_id` (validate_id) | `get_network_references` | `network_integration/networks.py` |
| `unifi_network_list_vouchers` | GET | `…/hotspot/vouchers` | `offset`, `limit` | `list_vouchers` | `network_integration/hotspot.py` |
| `unifi_network_get_voucher` | GET | `…/hotspot/vouchers/{id}` | `voucher_id` (validate_id) | `get_voucher` | `network_integration/hotspot.py` |
| `unifi_network_list_traffic_matching_lists` | GET | `…/traffic-matching-lists` | `offset`, `limit` | `list_traffic_matching_lists` | `network_integration/traffic.py` |
| `unifi_network_get_traffic_matching_list` | GET | `…/traffic-matching-lists/{id}` | `list_id` (validate_id) | `get_traffic_matching_list` | `network_integration/traffic.py` |
| `unifi_network_list_lags` | GET | `…/switching/lags` | `offset`, `limit` | `list_lags` | `network_integration/switching.py` |
| `unifi_network_get_lag` | GET | `…/switching/lags/{id}` | `lag_id` (validate_id) | `get_lag` | `network_integration/switching.py` |
| `unifi_network_list_mc_lag_domains` | GET | `…/switching/mc-lag-domains` | `offset`, `limit` | `list_mc_lag_domains` | `network_integration/switching.py` |
| `unifi_network_get_mc_lag_domain` | GET | `…/switching/mc-lag-domains/{id}` | `domain_id` (validate_id) | `get_mc_lag_domain` | `network_integration/switching.py` |
| `unifi_network_list_switch_stacks` | GET | `…/switching/switch-stacks` | `offset`, `limit` | `list_switch_stacks` | `network_integration/switching.py` |
| `unifi_network_get_switch_stack` | GET | `…/switching/switch-stacks/{id}` | `stack_id` (validate_id) | `get_switch_stack` | `network_integration/switching.py` |
| `unifi_network_list_vpn_servers` | GET | `…/vpn/servers` | `offset`, `limit` | `list_vpn_servers` | `network_integration/vpn.py` |
| `unifi_network_list_site_to_site_tunnels` | GET | `…/vpn/site-to-site-tunnels` | `offset`, `limit` | `list_site_to_site_tunnels` | `network_integration/vpn.py` |
| `unifi_network_list_wans` | GET | `…/wans` | `offset`, `limit` | `list_wans` | `network_integration/wan.py` |
| `unifi_network_list_radius_profiles` | GET | `…/radius/profiles` | `offset`, `limit` | `list_radius_profiles` | `network_integration/radius.py` |

Name-collision audit: all 28 names verified collision-free against
`docs/tool-schema-matrix.md`. Deliberate disambiguations from legacy tools:
`list_acl_rules` / `list_firewall_zones` / `list_dns_policies` (vs. legacy
`list_firewall_rules` / `list_firewall_groups`); `get_network_references` (vs.
legacy `get_network`); `list_dpi_applications` / `list_dpi_categories` (vs. legacy
`get_dpi_stats`).

---

## Risks & open questions

1. **`/ea/` routing (Phase 1, BLOCKING).** `SiteManagerClient._path_prefix` is
   fixed `/v1/` and `_url` always prepends it, so the 3 SD-WAN methods cannot be
   plain `self.get()` calls. Needs a `_prefix_override` path + a URL-assertion
   test. Resolve before coding. (Verified against `base.py:119-140`,
   `site_manager.py:25`.)
2. **Inventory namespace counting (Phase 0/3 — RESOLVED, not blocking).**
   `_inventory.py`, `test_tool_inventory.py`, and `_schema.py:149` all classify by
   name prefix, and `TestDocsCiteCanonicalCounts` hardcodes the 3 namespaces.
   Because the integration tools are `unifi_network_*`, they fold into the
   existing `network` namespace (`network.read` 26→54) and every classifier works
   unchanged. Do **not** introduce a `network_integration` counting namespace — it
   would force edits to all three classifiers and break the doc-string asserts.
   The `{"network_integration"}` tag is degradation-only.
3. **siteId resolution (Phase 0).** Auto-discovery adds a `GET /v1/sites`
   round-trip at startup and assumes a single/default site. Multi-site
   controllers silently target the first/default; operators with multiple sites
   must set `UNIFI_NETWORK_INTEGRATION_SITE`. The chosen site is cached for
   process life — a site added after startup needs a restart. Document this.
4. **Firmware availability (Phase 0/3).** `/proxy/network/integration/v1` exists
   only on recent UniFi OS. On old firmware every endpoint 404s,
   `validate_connection` fails, and the `network_integration` tag deregisters
   cleanly — legacy Network tools unaffected. The
   `UNIFI_NETWORK_INTEGRATION_ENABLED=false` opt-out avoids a noisy WARN on
   known-old firmware. Add a lifespan test asserting only the integration tag is
   disabled.
5. **API-key scoping (Phase 0).** Per CLAUDE.md gotcha #131, keys are
   service-scoped. The Integration API is part of the Network service, so the
   existing `UNIFI_NETWORK_API` key *should* authenticate it — confirm on live
   hardware. If it 401s, a separate config var is needed; flag, do not assume.
6. **RADIUS/VPN redaction (Phase 3, OWNER DECISION).** `radius/profiles` and
   `vpn/servers` may carry PSKs/shared keys. Recommend defensive
   `redact_secrets`; resolve before shipping.
7. **`files/{fileType}` bytes-vs-JSON (Phase 2).** If raw bytes, the tool moves
   to `media.py` with `get_raw()` + a max-bytes cap, not `access.py`. Verify
   content-type first.
8. **rtsps-stream GET (Phase 2).** May 404/empty when no stream is active.
   Document like `export_video`; do not fail validation.
9. **Endpoint-shape verification (Phase 2/3).** Path spellings (`link-stations`
   vs `linkstations`, `ulp-users`, isp-metrics param names, the `sites` query
   body schema) are from the matrix + developer.ui.com, not a checked-in mirror.
   Confirm against the pinned OpenAPI mirror before implementing; a wrong path
   404s but the tool stays registered (export_video #227 precedent).
10. **PII exposure (Phase 2).** `users`/`ulp-users` return names/emails/account
    ids. `redact_secrets` masks credential-shaped keys only; confirm the
    denylist covers token/password fields and decide whether identity fields
    warrant exclusion on privacy grounds. Owner decision; do not silently expand
    PII exposure.
11. **Cassette recording on live hardware.** Per `unifi-mcp/CLAUDE.md`, NEVER run
    the full destructive integration sweep in one invocation. These additions are
    read-only (no `LIVE_TEST_WRITES`), so recording GET cassettes is low-risk —
    but still record one TestClass per invocation with a controller health check
    between classes and a ~30s cooldown, per the hardware-safety rules (#271).

---

## Sequenced task checklist (independently shippable PRs)

Order ships smallest-and-lowest-risk first; each PR is independently mergeable and
keeps `_inventory.py` + docs + tests in lockstep (CI gates on drift). Whichever
PR lands second/third re-derives doc counts against the *current* `EXPECTED_*`
constants (see reconciliation table), never a hard-coded number.

**PR 1 — Site Manager reads (Phase 1).** Resolve `/ea/` routing first
(`_prefix_override` + URL test). Add 6 client methods, `metrics.py`, `sdwan.py`,
`get_host` in discovery, registrar wiring. Bump `site_manager.read` 3 → 9. Update
matrix §1, schema matrix (regen), README, CLAUDE.md. respx tests (incl. `/ea/`
URL assertion, metric_type allowlist, redaction). Optional Site Manager
cassettes.

**PR 2 — Protect reads (Phase 2).** Verify `files/{fileType}` content-type first.
Add ~28 client read methods, `device_reads.py`, `liveviews.py`, `access.py`,
registrar wiring. Bump `protect.read` 9 → 37. Update matrix §2, schema matrix,
README, CLAUDE.md. respx tests (paths, error paths, validate_id rejection,
redaction). No cassettes (Protect uses respx).

**PR 3 — Network Integration client (Phase 0).** Add `NetworkIntegrationClient`,
config flag + UUID validator + properties, `server.py`/`tools/__init__.py`
wiring, `tools/network_integration/__init__.py` (empty registrar or first
module), and the `("network_integration", ...)` entry in the lifespan
degradation loop. **No inventory-classifier refactor** — integration tools count
under the `network` namespace by name prefix. No net new tool count if shipped
tool-free; otherwise fold into PR 4. Unit tests for `validate_connection`
(success/site-discovery/explicit-UUID/reject-non-UUID/401-HTML) and the
resolved-URL assertion.

**PR 4 — Network Integration read tools (Phase 3).** Resolve the RADIUS/VPN
redaction decision first. Add the 13 tool modules + 28 client read methods (with
offset/limit caps wired). Set `network_integration.read = 28`. Update matrix §3b,
schema matrix, README, CLAUDE.md. respx tests (siteId injection, header,
pagination caps, error paths). Record Network Integration cassettes per the
one-class-per-invocation hardware-safety protocol. Lifespan test: old-firmware
404 disables only the `network_integration` tag.
