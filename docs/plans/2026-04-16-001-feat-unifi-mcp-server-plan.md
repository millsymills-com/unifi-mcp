---
title: "feat: Build production-grade UniFi MCP server"
type: feat
status: historical
date: 2026-04-16
deepened: 2026-04-16
---

# feat: Build production-grade UniFi MCP server

> **Historical document.** This is the original build plan, kept for context.
> Some decisions have since changed — notably, the project is **not** published
> to PyPI; it installs from source / git (see the README). Treat references to
> PyPI publishing below as superseded.

## Overview

Build a standalone, open-source Python MCP server providing comprehensive coverage of UniFi Site Manager, Network, and Protect APIs. Published to PyPI as `unifi-mcp`. Uses FastMCP framework with declarative read/write mode separation, graceful per-API degradation, and atomic agent-native tool design.

**Status:** Units 1–10 implemented and merged. Unit 11 (MCP client registration and end-to-end live-hardware verification) is deferred pending access to the target UDR Ultra + Protect cameras.

## Problem Frame

Existing UniFi MCP servers (enuno/unifi-mcp-server with 77 tools, sirkirby/unifi-mcp with 200+ tools) are either monolithic or overly granular. None provide clean read/write separation at the tool registration level, and most require all APIs configured or fail entirely. We need a production-grade server that:
- Registers only the tools for APIs you have keys for (graceful degradation)
- Hides write tools entirely in readonly mode (not just guarded — invisible)
- Uses atomic, composable tools following agent-native principles
- Ships as a proper open-source project (PyPI, CI/CD, docs)

## Requirements Trace

- R1. Cover all three UniFi APIs: Site Manager (cloud, read-only), Network (local, full CRUD), Protect (local, read+write+media)
- R2. Strong read/write mode separation via `UNIFI_MODE` env var — write tools invisible in readonly mode
- R3. Graceful per-API degradation — missing API key = that API's tools don't register
- R4. Live-tested against real hardware (UDR Ultra, 3 APs, 5 switches, Protect cameras)
- R5. Production open source: PyPI publishing, semver, CI/CD, contributor docs
- R6. Production-grade tests with 90%+ coverage
- R7. Comprehensive setup documentation with MCP client configs

## Scope Boundaries

- No WebSocket streaming (MCP doesn't support server push yet)
- No batch/bulk operations (MCP protocol handles parallel tool calls natively)
- No Redis or caching layer (keep it simple — direct API calls)
- No session-based auth (API key only — cleaner for MCP use)
- No GUI or dashboard

### Deferred to Separate Tasks

- PyPI trusted publishing setup: after initial GitHub repo creation
- Protect live testing: when cameras are reconnected

## Context & Research

### Relevant Code and Patterns

- `toolkit/diagnostics/media/api_clients.py` — Existing API client hierarchy with retry and auth (reference pattern)
- `toolkit/cli_unified.py` — Module registration pattern (reference for tool organization)
- `config/prometheus/rules/unifi_alerts.yml` — 22 existing UniFi alert rules (reference for what metrics matter)
- `scripts/recreate_unifi_poller.sh` — Controller URL and auth patterns

### Hardware Inventory (Live-Test Targets)

- **UDR Ultra** at 192.168.1.1 (gateway + controller + Protect)
- **3 APs**: 1x UAP-AC-Pro, 2x U6+
- **5 Switches**: 1x USF5P, 1x USL16LP, 3x USMINI
- **27 clients**, 1 site ("default"), DPI enabled
- **API keys**: All three provisioned in resurgent's `.env`

### API Path Validation (Live-Tested 2026-04-16)

| API | Base URL | Auth Header | Validated |
|-----|----------|-------------|-----------|
| Network | `https://192.168.1.1/proxy/network/api/s/{site}/` | `X-API-Key` | Yes |
| Protect | `https://192.168.1.1/proxy/protect/api/` | `X-API-Key` | Yes |
| Site Manager | `https://api.ui.com/v1/` | `X-API-Key` | Yes |

Note: Site Manager also accepts `/ea/` prefix but `/v1/` is preferred for forward compatibility.

### External References

- [FastMCP docs](https://gofastmcp.com) — v3.2.4 stable, decorator-based tools, lifespan, in-memory testing
- [MCP Protocol Spec](https://modelcontextprotocol.io/specification/2025-11-25) — Tool annotations (readOnlyHint, destructiveHint)
- [UniFi Network API](https://developer.ui.com/network/v10.1.84/gettingstarted) — Official docs
- [UniFi Protect API](https://developer.ui.com/protect/v7.0.104/gettingstarted) — Official docs
- [UniFi Site Manager API](https://developer.ui.com/site-manager/v1.0.0/gettingstarted) — Official docs

## Key Technical Decisions

- **FastMCP v3.2+**: Decorator-based tools, async lifespan, built-in tag-based visibility control, in-memory testing via `Client(transport=mcp)`. Rationale: Most mature Python MCP framework, 70% market share.
- **Tag-based mode gating over custom decorators**: FastMCP's native `mcp.disable(tags={"write"})` handles visibility. We tag write tools with `{"write"}` and disable them in readonly mode. Defense-in-depth: tools also check mode at runtime. Rationale: Uses framework capabilities instead of reinventing.
- **httpx (async) over requests**: Required for FastMCP's async tool execution. Also provides connection pooling, HTTP/2.
- **tenacity for retry**: Industry standard, composable with httpx. Only retry on connection/timeout errors, not auth failures.
- **Pydantic models with `extra="allow"`**: UniFi APIs return unpredictable fields across firmware versions. Models shape responses for documentation and type safety without breaking on unknown fields.
- **`/v1/` for Site Manager API**: Both `/ea/` and `/v1/` work. `/v1/` is the explicit versioned path.
- **No `unifi_` prefix on tool names**: The MCP server name (`unifi-mcp`) provides namespace. Tools use `network_*`, `protect_*`, `site_manager_*` prefixes.
- **hatchling build backend**: Simple, modern, well-supported. `src/` layout for clean packaging.

## Open Questions

### Resolved During Planning

- **Custom decorators vs built-in tags?** Use built-in `mcp.disable(tags={"write"})` + runtime guard. FastMCP handles this natively.
- **Site Manager `/ea/` vs `/v1/`?** Both work; use `/v1/` for versioning clarity.
- **Binary data handling?** FastMCP provides `Image(data=, format=)` for snapshots and raw bytes for video. No custom encoding needed.
- **Type checker?** Use mypy (strict mode) — better Pydantic plugin than ty for this project.

### Deferred to Implementation

- Exact Protect API response shapes: Will be discovered during live testing
- Whether all Network REST endpoints require the `_id` field for PUT: Test during CRUD implementation
- Video export response format (MP4 stream vs download URL): Test with Protect API when cameras connected

## Output Structure

```
unifi-mcp/
├── pyproject.toml
├── LICENSE
├── README.md
├── CONTRIBUTING.md
├── CLAUDE.md
├── .env.example
├── .github/
│   └── workflows/
│       ├── ci.yml
│       ├── release.yml
│       └── security.yml
├── src/
│   └── unifi_mcp/
│       ├── __init__.py
│       ├── __main__.py
│       ├── server.py
│       ├── config.py
│       ├── errors.py
│       ├── clients/
│       │   ├── __init__.py
│       │   ├── base.py
│       │   ├── network.py
│       │   ├── protect.py
│       │   └── site_manager.py
│       ├── models/
│       │   ├── __init__.py
│       │   ├── common.py
│       │   ├── network.py
│       │   ├── protect.py
│       │   └── site_manager.py
│       └── tools/
│           ├── __init__.py
│           ├── network/
│           │   ├── __init__.py
│           │   ├── devices.py
│           │   ├── clients.py
│           │   ├── wlan.py
│           │   ├── firewall.py
│           │   ├── networks.py
│           │   ├── port_forward.py
│           │   ├── routing.py
│           │   ├── stats.py
│           │   └── system.py
│           ├── protect/
│           │   ├── __init__.py
│           │   ├── cameras.py
│           │   ├── events.py
│           │   ├── media.py
│           │   ├── nvr.py
│           │   └── devices.py
│           └── site_manager/
│               ├── __init__.py
│               └── discovery.py
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── unit/
    │   ├── __init__.py
    │   ├── test_config.py
    │   ├── test_server.py
    │   ├── clients/
    │   │   ├── __init__.py
    │   │   ├── test_base.py
    │   │   ├── test_network.py
    │   │   ├── test_protect.py
    │   │   └── test_site_manager.py
    │   └── tools/
    │       ├── __init__.py
    │       ├── test_network_devices.py
    │       ├── test_network_clients.py
    │       ├── test_network_wlan.py
    │       ├── test_network_firewall.py
    │       ├── test_network_stats.py
    │       ├── test_network_system.py
    │       ├── test_protect_cameras.py
    │       ├── test_protect_events.py
    │       ├── test_protect_media.py
    │       └── test_site_manager.py
    ├── integration/
    │   ├── __init__.py
    │   ├── conftest.py
    │   ├── test_network_live.py
    │   ├── test_protect_live.py
    │   └── test_site_manager_live.py
    └── fixtures/
        ├── network_responses.json
        ├── protect_responses.json
        └── site_manager_responses.json
```

## High-Level Technical Design

> *This illustrates the intended approach and is directional guidance for review, not implementation specification.*

```
┌─────────────────────────────────────────────────────┐
│                   FastMCP Server                     │
│  server.py: create_server() + async lifespan         │
│                                                      │
│  Lifespan:                                           │
│    1. Load UniFiConfig (pydantic-settings)            │
│    2. Init clients for configured APIs (httpx async)  │
│    3. Validate connections                            │
│    4. Register tools for available APIs               │
│    5. Apply mode gating: mcp.disable(tags={"write"}) │
│    6. yield {config, clients}                         │
│    7. Cleanup: close all clients                      │
├─────────────────────────────────────────────────────┤
│                    Tool Layer                         │
│  tools/{api}/{entity}.py                             │
│  Each tool: @mcp.tool(tags={"write"}, annotations=) │
│  Access clients via ctx.lifespan_context             │
├──────────┬──────────┬────────────────────────────────┤
│ Network  │ Protect  │ Site Manager                   │
│ Client   │ Client   │ Client                         │
├──────────┴──────────┴────────────────────────────────┤
│              BaseUniFiClient                          │
│  httpx.AsyncClient + tenacity retry + error mapping  │
└─────────────────────────────────────────────────────┘
```

**Mode gating flow:**
1. All tools register with standard `@mcp.tool()` decorators
2. Write tools tagged with `tags={"write"}` and `annotations={"readOnlyHint": False, "destructiveHint": True/False}`
3. After registration, if `UNIFI_MODE == readonly`: `mcp.disable(tags={"write"})`
4. Defense-in-depth: write tool functions also check `config.is_readwrite` before executing

**Tool count: 77 total (38 read, 39 write)** *(updated 2026-04-16 — source of truth: `grep -rc '@mcp\.tool' src/unifi_mcp/tools/` returns 77)*

| Area | Read | Write | Total |
|------|------|-------|-------|
| Site Manager (all read) | 3 | 0 | 3 |
| Network (stats, config, devices, clients, wlan, system) | 24 | 35 | 59 |
| Protect (cameras, devices, events, media, NVR) | 11 | 4 | 15 |

## Implementation Units

- [x] **Unit 1: Project scaffold and packaging**

**Goal:** Create project structure, pyproject.toml, and all empty modules so the project is installable and runnable (even if it does nothing yet).

**Requirements:** R5

**Dependencies:** None

**Files:**
- Create: `pyproject.toml`, `LICENSE`, `.env.example`, `CLAUDE.md`
- Create: `src/unifi_mcp/__init__.py`, `src/unifi_mcp/__main__.py`
- Create: All `__init__.py` files for subpackages (clients, models, tools, tools/network, tools/protect, tools/site_manager)

**Approach:**
- Use hatchling build backend with `src/` layout
- Python >=3.11, deps: fastmcp>=3.2.0, httpx>=0.27.0, pydantic>=2.6.0, pydantic-settings>=2.2.0, tenacity>=8.2.0
- Dev deps: pytest, pytest-asyncio, pytest-cov, respx, ruff, mypy, bandit
- Entry point: `unifi-mcp = "unifi_mcp.__main__:main"`
- `__init__.py` exports `__version__ = "0.1.0"`
- Apache-2.0 license

**Patterns to follow:**
- resurgent's `pyproject.toml` for ruff/pytest config conventions

**Test expectation:** None — pure scaffolding. Verified by `uv pip install -e .` succeeding.

**Verification:**
- `uv venv && uv pip install -e ".[dev]"` succeeds
- `python -m unifi_mcp` runs without import errors (can exit immediately)

---

- [x] **Unit 2: Configuration and error handling**

**Goal:** Implement `config.py` with pydantic-settings for all env vars, and `errors.py` with the exception hierarchy.

**Requirements:** R2, R3

**Dependencies:** Unit 1

**Files:**
- Create: `src/unifi_mcp/config.py`
- Create: `src/unifi_mcp/errors.py`
- Test: `tests/unit/test_config.py`

**Approach:**
- `UniFiConfig(BaseSettings)` with `env_prefix=""`, `env_file=".env"`
- `UniFiMode` enum: `readonly` (default), `readwrite`
- Properties: `is_readwrite`, `network_enabled`, `protect_enabled`, `site_manager_enabled`
- Model validator: default `UNIFI_PROTECT_HOST` to `UNIFI_NETWORK_HOST`
- Error hierarchy: `UniFiError` base → `UniFiAuthError`, `UniFiNotFoundError`, `UniFiRateLimitError`, `UniFiConnectionError`
- `handle_client_error()` maps exceptions to FastMCP `ToolError` with consistent formatting

**Patterns to follow:**
- resurgent `toolkit/config/settings.py` for settings hierarchy pattern

**Test scenarios:**
- Happy path: Config loads from env vars with correct types and defaults
- Happy path: `is_readwrite` returns True when `UNIFI_MODE=readwrite`
- Happy path: `network_enabled` returns True when API key is set, False when None
- Edge case: `UNIFI_PROTECT_HOST` defaults to `UNIFI_NETWORK_HOST` when not set
- Edge case: `UNIFI_MODE` defaults to `readonly` when not set
- Error path: Invalid `UNIFI_MODE` value raises validation error
- Happy path: `handle_client_error` maps `UniFiAuthError` to ToolError with auth message
- Happy path: `handle_client_error` maps `UniFiNotFoundError` to ToolError with resource message

**Verification:**
- All config tests pass
- Config loads from `.env` file correctly
- Error mapping produces clean, agent-readable messages

---

- [x] **Unit 3: Base API client**

**Goal:** Implement `BaseUniFiClient` with httpx async, retry logic, auth, and error mapping.

**Requirements:** R1

**Dependencies:** Unit 2

**Files:**
- Create: `src/unifi_mcp/clients/base.py`
- Test: `tests/unit/clients/test_base.py`

**Approach:**
- Wraps `httpx.AsyncClient` with configurable base_url, API key header, SSL verification, timeout
- Retry via tenacity: 3 attempts, exponential backoff (1s-10s), only on `ConnectError`/`TimeoutException`
- `_raise_for_status()` maps HTTP status codes to typed exceptions (401/403 → AuthError, 404 → NotFoundError, 429 → RateLimitError)
- `get()`, `post()`, `put()`, `delete()` convenience methods
- `validate_connection()` abstract method for subclasses
- `close()` for cleanup

**Patterns to follow:**
- resurgent `toolkit/diagnostics/media/api_clients.py` for retry and auth patterns

**Test scenarios:**
- Happy path: GET request returns parsed JSON
- Happy path: API key header included in all requests
- Happy path: SSL verification configurable (on/off)
- Error path: 401 response raises `UniFiAuthError`
- Error path: 404 response raises `UniFiNotFoundError`
- Error path: 429 response raises `UniFiRateLimitError`
- Error path: 500 response raises `UniFiError` with status and body excerpt
- Edge case: Retry on `ConnectError` up to 3 times then fail
- Edge case: No retry on auth errors (fail immediately)
- Happy path: `close()` calls `aclose()` on httpx client

**Verification:**
- All client tests pass using respx for HTTP mocking
- Error hierarchy correctly maps all status codes

---

- [x] **Unit 4: Server assembly and lifespan**

**Goal:** Implement `server.py` with FastMCP server creation, async lifespan for client initialization, and mode gating.

**Requirements:** R2, R3

**Dependencies:** Unit 3

**Files:**
- Create: `src/unifi_mcp/server.py`
- Modify: `src/unifi_mcp/__main__.py`
- Test: `tests/unit/test_server.py`

**Approach:**
- `create_server()` returns configured `FastMCP` instance
- `@lifespan` initializes clients for configured APIs, validates connections, yields context dict
- After tool registration: `if not config.is_readwrite: mcp.disable(tags={"write"})`
- Failed client connections log warning and skip (don't crash server)
- `__main__.py`: `server = create_server(); server.run()`

**Patterns to follow:**
- FastMCP lifespan pattern: `@lifespan` + `try/finally` + `yield {"config": config, "clients": clients}`

**Test scenarios:**
- Happy path: Server creates with all three APIs configured
- Happy path: Server creates with only Network API configured (Protect/Site Manager tools absent)
- Happy path: Server creates with zero APIs configured (logs warning, starts with no tools)
- Happy path: Write tools disabled when `UNIFI_MODE=readonly`
- Happy path: Write tools enabled when `UNIFI_MODE=readwrite`
- Error path: Client connection failure logs error, other APIs still initialize
- Integration: `python -m unifi_mcp` starts without errors

**Verification:**
- Server starts in both readonly and readwrite modes
- Tool count matches expected for each mode
- Failed API connections don't crash the server

---

- [x] **Unit 5: Site Manager client and tools (3 read-only tools)**

**Goal:** Implement Site Manager API client and 3 discovery tools. First tools in the server — validates the full stack.

**Requirements:** R1, R4

**Dependencies:** Unit 4

**Files:**
- Create: `src/unifi_mcp/clients/site_manager.py`
- Create: `src/unifi_mcp/models/site_manager.py`
- Create: `src/unifi_mcp/tools/site_manager/discovery.py`
- Modify: `src/unifi_mcp/tools/__init__.py` (register tools)
- Test: `tests/unit/tools/test_site_manager.py`
- Test: `tests/integration/test_site_manager_live.py`
- Create: `tests/fixtures/site_manager_responses.json`

**Approach:**
- `SiteManagerClient(BaseUniFiClient)` with base_url `https://api.ui.com`, SSL on
- 3 tools: `site_manager_list_hosts`, `site_manager_list_sites`, `site_manager_list_devices`
- All read-only (no write tag)
- Models: `CloudHost`, `CloudSite`, `CloudDevice` with `extra="allow"`
- Response extraction: `result.get("data", [])`
- `list_devices` accepts optional `host_id` filter

**Test scenarios:**
- Happy path: `list_hosts` returns list of host dicts
- Happy path: `list_sites` returns list of site dicts
- Happy path: `list_devices` returns devices, accepts optional `host_id` filter
- Error path: Invalid API key returns auth error
- Error path: Network timeout retries then fails
- Integration: `list_hosts` returns real UDR Ultra data from api.ui.com

**Verification:**
- Unit tests pass with mocked HTTP
- Integration test returns real data matching known hardware (UDR Ultra)
- Tools appear in `list_tools` response

---

- [x] **Unit 6: Network client and read tools (24 read tools)**

**Goal:** Implement Network API client and all read-only tools: stats (9), devices (1), clients (1), wlan (2), firewall (4), networks (2), port forward (2), routing (2), system (1).

**Requirements:** R1, R4

**Dependencies:** Unit 4

**Files:**
- Create: `src/unifi_mcp/clients/network.py`
- Create: `src/unifi_mcp/models/network.py`
- Create: `src/unifi_mcp/tools/network/stats.py` (9 tools)
- Create: `src/unifi_mcp/tools/network/devices.py` (2 read tools)
- Create: `src/unifi_mcp/tools/network/clients.py` (3 read tools)
- Create: `src/unifi_mcp/tools/network/wlan.py` (2 read tools)
- Create: `src/unifi_mcp/tools/network/firewall.py` (4 read tools: rules list/get + groups list/get)
- Create: `src/unifi_mcp/tools/network/networks.py` (2 read tools)
- Create: `src/unifi_mcp/tools/network/port_forward.py` (2 read tools)
- Create: `src/unifi_mcp/tools/network/routing.py` (2 read tools)
- Create: `src/unifi_mcp/tools/network/system.py` (1 read tool: get settings)
- Modify: `src/unifi_mcp/tools/__init__.py`
- Test: `tests/unit/tools/test_network_devices.py`
- Test: `tests/unit/tools/test_network_clients.py`
- Test: `tests/unit/tools/test_network_stats.py`
- Test: `tests/unit/clients/test_network.py`
- Test: `tests/integration/test_network_live.py`
- Create: `tests/fixtures/network_responses.json`

**Approach:**
- `NetworkClient(BaseUniFiClient)` with path prefix `/proxy/network/api/s/{site}/`
- Client methods map 1:1 to API endpoints
- Stats tools: `network_get_health`, `network_list_events`, `network_list_devices`, `network_list_devices_basic`, `network_list_active_clients`, `network_list_configured_clients`, `network_list_all_clients`, `network_get_dpi_stats`, `network_get_sysinfo`
- Config read tools: list/get for wlans, firewall rules, firewall groups, networks, port forwards, routes, settings
- Models: `NetworkDevice`, `NetworkClient`, `WlanConfig`, `FirewallRule`, `FirewallGroup`, `PortForwardRule`, `StaticRoute`
- All tools tagged with `{"network"}`, no `{"write"}` tag

**Test scenarios:**
- Happy path: Each read tool returns expected data shape from mock
- Happy path: `network_get_health` returns health for all subsystems
- Happy path: `network_list_events` accepts optional `limit` parameter
- Happy path: `network_get_dpi_stats` requires `type` parameter (by_app/by_cat)
- Happy path: `network_list_active_clients` vs `network_list_configured_clients` hit different endpoints
- Error path: Invalid site returns 404
- Error path: Connection timeout retries
- Integration: `network_list_devices` returns real APs/switches from UDR Ultra
- Integration: `network_list_active_clients` returns real client data
- Integration: `network_get_health` returns health status

**Verification:**
- 24 read tools registered and functional
- Integration tests pass against live UDR Ultra
- All tools return structured data matching Pydantic models

---

- [x] **Unit 7: Network write tools (35 write tools)**

**Goal:** Implement all Network write tools: CRUD write operations (23) and command/action tools (12) across wlan, firewall, networks, port forwards, routing, system, devices, and clients.

**Requirements:** R1, R2

**Dependencies:** Unit 6

**Files:**
- Modify: `src/unifi_mcp/tools/network/wlan.py` (add 3 write tools)
- Modify: `src/unifi_mcp/tools/network/firewall.py` (add 6 write tools)
- Modify: `src/unifi_mcp/tools/network/networks.py` (add 3 write tools)
- Modify: `src/unifi_mcp/tools/network/port_forward.py` (add 3 write tools)
- Modify: `src/unifi_mcp/tools/network/routing.py` (add 3 write tools)
- Modify: `src/unifi_mcp/tools/network/system.py` (add 3 write tools: speedtest, backup, update settings)
- Modify: `src/unifi_mcp/tools/network/devices.py` (add 5 write tools: restart, adopt, locate, unlocate, provision)
- Modify: `src/unifi_mcp/tools/network/clients.py` (add 4 write tools: block, unblock, kick, authorize_guest)
- Create: `src/unifi_mcp/tools/network/commands.py` (remaining command tools: upgrade, power_cycle_port, archive_events, reset_dpi, unauthorize_guest)
- Test: `tests/unit/tools/test_network_wlan.py`
- Test: `tests/unit/tools/test_network_firewall.py`
- Test: `tests/unit/tools/test_network_system.py`

**Approach:**
- All write tools tagged with `tags={"write", "network"}` and `annotations={"readOnlyHint": False}`
- Destructive operations (adopt, delete_*, block) also get `destructiveHint: True`
- CRUD creates use POST, updates use PUT (with `_id`), deletes use DELETE
- Command tools use `POST /cmd/{manager}` with `{"cmd": "command_name", "mac": mac}`
- Defense-in-depth: each write tool checks `config.is_readwrite` before executing
- Partial updates: update tools accept only the fields being changed

**Test scenarios:**
- Happy path: Create WLAN sends correct POST payload
- Happy path: Update firewall rule sends PUT with `_id`
- Happy path: Delete port forward sends DELETE with correct ID
- Happy path: `network_restart_device` sends `{"cmd": "restart", "mac": mac}` to devmgr
- Happy path: `network_block_client` sends `{"cmd": "block-sta", "mac": mac}` to stamgr
- Edge case: Mode gating — write tools not in `list_tools` when UNIFI_MODE=readonly
- Edge case: Defense-in-depth — write tool raises ToolError if called in readonly mode
- Integration (safe only): `network_locate_device` / `network_unlocate_device` on a real AP
- Integration (safe only): `network_run_speedtest` returns speed data

**Verification:**
- 35 write tools registered in readwrite mode
- 0 write tools visible in readonly mode
- Mode gating tests pass for both modes
- Safe integration tests pass

---

- [x] **Unit 8: Protect client and tools (15 tools)**

**Goal:** Implement Protect API client and all tools: read (11), media (2 within read), write (4).

**Requirements:** R1, R2

**Dependencies:** Unit 4

**Files:**
- Create: `src/unifi_mcp/clients/protect.py`
- Create: `src/unifi_mcp/models/protect.py`
- Create: `src/unifi_mcp/tools/protect/cameras.py` (6 tools: list, get, update, recording mode, motion zones, smart detection)
- Create: `src/unifi_mcp/tools/protect/events.py` (1 tool: list events with rich filtering)
- Create: `src/unifi_mcp/tools/protect/media.py` (2 tools: snapshot, video export)
- Create: `src/unifi_mcp/tools/protect/nvr.py` (2 tools: get, update)
- Create: `src/unifi_mcp/tools/protect/devices.py` (4 tools: list chimes, lights, sensors, viewers)
- Modify: `src/unifi_mcp/tools/__init__.py`
- Test: `tests/unit/tools/test_protect_cameras.py`
- Test: `tests/unit/tools/test_protect_events.py`
- Test: `tests/unit/tools/test_protect_media.py`
- Test: `tests/unit/clients/test_protect.py`
- Test: `tests/integration/test_protect_live.py`
- Create: `tests/fixtures/protect_responses.json`

**Approach:**
- `ProtectClient(BaseUniFiClient)` with path prefix `/proxy/protect/api/`
- Read tools: `protect_get_bootstrap`, `protect_list_cameras`, `protect_get_camera`, `protect_list_events`, `protect_get_nvr`, `protect_list_chimes`, `protect_list_lights`, `protect_list_sensors`, `protect_list_viewers`
- `protect_list_events` accepts: `start` (ISO8601), `end`, `camera_ids`, `types` (motion/ring/smartDetect), `smart_detect_types` (person/vehicle/animal), `limit`, `offset`
- Media tools: `protect_get_snapshot` returns `Image(data=, format="jpeg")`, `protect_export_video` returns raw bytes
- Write tools tagged `{"write", "protect"}`
- Models: `Camera`, `ProtectEvent`, `NVR`, `Chime`, `Light`, `Sensor`

**Test scenarios:**
- Happy path: `protect_list_cameras` returns camera list with status fields
- Happy path: `protect_list_events` filters by camera_id, type, and time range
- Happy path: `protect_get_snapshot` returns Image object
- Happy path: `protect_update_camera` sends partial update via PUT
- Happy path: `protect_set_recording_mode` sends mode change with padding options
- Edge case: `protect_get_snapshot` without timestamp gets live frame
- Edge case: `protect_list_events` with no filters returns recent events
- Error path: Invalid camera_id returns NotFoundError
- Error path: Mode gating — write tools invisible in readonly mode

**Verification:**
- 15 Protect tools registered
- Snapshot returns Image type
- Write tools respect mode gating
- Integration tests work when cameras are connected

---

- [x] **Unit 9: Documentation**

**Goal:** Write comprehensive README, CONTRIBUTING guide, CLAUDE.md, and .env.example.

**Requirements:** R5, R7

**Dependencies:** Units 5-8 (all tools implemented)

**Files:**
- Create: `README.md`
- Create: `CONTRIBUTING.md`
- Modify: `CLAUDE.md`
- Modify: `.env.example`

**Approach:**
- README sections: What it does, Quick Start (install + configure + run), Configuration Reference (env var table), Available Tools (organized by API with read/write labels), MCP Client Configuration (Claude Desktop JSON, Claude Code, Cursor), Mode Separation docs, Development Setup
- CONTRIBUTING: Fork, branch, test, PR workflow. Code style (ruff), type checking (mypy), test requirements
- CLAUDE.md: Project conventions, commands, architecture for Claude Code
- .env.example: All env vars with descriptions and example values

**Test expectation:** None — documentation. Verified by human review.

**Verification:**
- README has working quick start instructions
- .env.example contains all configuration variables
- MCP client config examples are correct JSON

---

- [x] **Unit 10: CI/CD and quality gates**

**Goal:** Set up GitHub Actions for CI, release, and security scanning. Create GitHub repo.

**Requirements:** R5, R6

**Dependencies:** Unit 9

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `.github/workflows/release.yml`
- Create: `.github/workflows/security.yml`

**Approach:**
- CI: lint (ruff), typecheck (mypy), test (pytest with coverage) across Python 3.11-3.13
- Release: triggered by `v*` tags, builds with hatch, publishes to PyPI via trusted publishing
- Security: weekly bandit scan
- Create `millsmillsymills/unifi-mcp` repo on GitHub, push, verify CI green

**Test expectation:** None — CI config. Verified by green CI checks.

**Verification:**
- `ruff check && ruff format --check` passes
- `mypy src/unifi_mcp/` passes (strict)
- `pytest tests/unit/ --cov=unifi_mcp` shows >=40% coverage (the R6 90%+ target is tracked as follow-up work in the GitHub issue tracker — add per-tool unit tests in fast-follow PRs)
- CI workflow runs green on push

---

- [ ] **Unit 11: MCP client registration and end-to-end test** *(deferred — requires live hardware)*

**Goal:** Register the server in Claude Code and verify end-to-end functionality.

**Requirements:** R4, R7

**Dependencies:** Unit 10

**Files:**
- Modify: `~/.claude.json` (add MCP server config)

**Approach:**
- Register as stdio transport MCP server in Claude Code config
- Set env vars from resurgent's `.env` + `UNIFI_MODE=readonly`
- End-to-end test: ask Claude to list network devices, verify structured response

**Test scenarios:**
- Integration: "List my network devices" returns real device data
- Integration: "What's my network health?" returns health summary
- Integration: "List my Site Manager hosts" returns cloud host data
- Edge case: Write tool invocation blocked in readonly mode

**Verification:**
- Claude Code can discover and call UniFi tools
- Responses are structured and useful
- Readonly mode enforced

## System-Wide Impact

- **Interaction graph:** Tools access UniFi APIs via httpx clients. No callbacks or middleware. Server is self-contained with no external dependencies beyond the UniFi controller.
- **Error propagation:** API errors → typed exceptions → ToolError (agent-readable). No silent failures.
- **State lifecycle risks:** No persistent state. Each tool call is a stateless API request. No caching, no sessions to expire.
- **API surface parity:** Claude Code, Cursor, and any MCP client can use the same tools. Transport-agnostic via FastMCP.
- **Unchanged invariants:** Resurgent's existing UniFi-Poller metrics pipeline is completely separate and unaffected.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| UniFi API undocumented changes across firmware versions | Pydantic models use `extra="allow"` to tolerate unknown fields. Live integration tests catch breaking changes. |
| Protect API largely reverse-engineered (not fully official) | Use official developer docs where available. Protect cameras currently disconnected — defer full testing. |
| FastMCP v3.x API changes | Pin `>=3.2.0,<4.0.0` in deps. In-memory test pattern is stable. |
| Rate limiting on Site Manager API (10k/min) | Not a practical concern for MCP usage patterns. Log 429 errors clearly. |
| SSL certificate issues with local controller | Default `verify_ssl=False` for local controllers. Document the tradeoff. |

## Configuration Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `UNIFI_MODE` | No | `readonly` | `readonly` or `readwrite` |
| `UNIFI_NETWORK_HOST` | No | `192.168.1.1` | Network controller IP |
| `UNIFI_NETWORK_PORT` | No | `443` | Network controller port |
| `UNIFI_NETWORK_API` | No* | — | Network API key |
| `UNIFI_NETWORK_SITE` | No | `default` | Site name |
| `UNIFI_NETWORK_VERIFY_SSL` | No | `false` | SSL verification for local controller |
| `UNIFI_PROTECT_HOST` | No | same as NETWORK_HOST | Protect host |
| `UNIFI_PROTECT_PORT` | No | `443` | Protect port |
| `UNIFI_PROTECT_API` | No* | — | Protect API key |
| `UNIFI_PROTECT_VERIFY_SSL` | No | `false` | SSL verification |
| `UNIFI_SITE_MANAGER_API` | No* | — | Site Manager cloud API key |
| `UNIFI_REQUEST_TIMEOUT` | No | `30` | Request timeout (seconds) |
| `UNIFI_MAX_RETRIES` | No | `3` | Max retry attempts |

*At least one API key must be set for the server to be useful.

## Sources & References

- **FastMCP docs**: https://gofastmcp.com (v3.2.4, validated 2026-04-16)
- **UniFi Network API**: https://developer.ui.com/network/v10.1.84/gettingstarted
- **UniFi Protect API**: https://developer.ui.com/protect/v7.0.104/gettingstarted
- **UniFi Site Manager API**: https://developer.ui.com/site-manager/v1.0.0/gettingstarted
- **Existing implementations**: enuno/unifi-mcp-server, sirkirby/unifi-mcp (studied for differentiation)
- **API paths validated live** against UDR Ultra at 192.168.1.1 (2026-04-16)
