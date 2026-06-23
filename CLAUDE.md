# CLAUDE.md — Project Intelligence for unifi-mcp

## Project Overview

Production-grade Python MCP server for UniFi Site Manager, Network, and Protect APIs. Distributed as the `unifi-mcp` package (not yet on PyPI — install from source via `uv sync`). Uses FastMCP framework with declarative read/write mode separation and graceful per-API degradation.

## Commands

```bash
# Install (development)
uv sync --extra dev

# Lint
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/

# Type check
uv run ty check src/unifi_mcp/

# Test (unit only, excludes integration)
uv run pytest tests/unit/ -v

# Test with coverage
uv run pytest tests/unit/ --cov=unifi_mcp --cov-report=term-missing -m "not integration"

# Integration tests (requires live UniFi hardware)
uv run pytest tests/integration/ -v -m integration

# Security scan
uv run bandit -r src/unifi_mcp/ -c pyproject.toml

# Pre-commit hooks
uv run pre-commit run --all-files

# Build package
uv build

# Run the server (after `uv sync`)
uv run unifi-mcp                       # readonly mode (default, safe)
UNIFI_MODE=readwrite uv run unifi-mcp  # exposes the 47 write tools
```

## Live Integration Tests — Hardware Safety

**NEVER** run `uv run pytest tests/integration/` as a single invocation when `LIVE_TEST_WRITES=1` and `LIVE_TEST_DESTRUCTIVE=1` are set. Cumulative config-state churn across the full destructive sweep has bricked production hardware: on 2026-05-21 it corrupted a UCG Ultra on-disk and required a factory reset (#271). Partial-create pins (#257, #258, etc.) compound under sustained load and the controller cannot self-recover.

Required pattern: one TestClass per pytest invocation, with a controller health check between classes, and ~30s cooldown to let the controller settle.

```bash
uv run pytest tests/integration/test_all_tools_live.py::TestWriteRoundtrips -v -m integration
# verify controller responsive before continuing, e.g.:
curl -skf -o /dev/null -w '%{http_code}\n' "https://${UNIFI_NETWORK_HOST}/proxy/network/integration/v1/sites"
sleep 30
uv run pytest tests/integration/test_all_tools_live.py::TestDestructive -v -m integration
```

If the health check fails or any class hangs, stop the sweep and triage before continuing. See #271 for incident details.

Protect **write** tests target only devices the operator approves via `LIVE_TEST_DEVICE_MACS` (comma-separated MACs, any separator/case) and `pytest.skip` when the allowlist is empty or no live camera matches — never `cameras[0]`. Full allowlist + capture/restore + run-protocol rules: `docs/agents/live-test-safety.md`.

## Architecture

```
src/unifi_mcp/
├── __init__.py          # Package root, exports __version__
├── __main__.py          # Entry point: creates and runs server
├── _logging.py          # Structured logging setup
├── server.py            # FastMCP server creation + lifespan
├── config.py            # Pydantic settings (env vars, including UNIFI_MODE)
├── errors.py            # Exception hierarchy + error mapping
├── clients/             # API clients (httpx async)
│   ├── base.py          # BaseUniFiClient with retry/auth/error mapping
│   ├── network.py       # Network API client
│   ├── protect.py       # Protect API client
│   └── site_manager.py  # Site Manager API client
└── tools/               # MCP tool definitions
    ├── network/         # 26 read + 39 write tools (65 total)
    ├── protect/         # 9 read + 8 write tools (17 total, includes 2 media read tools)
    └── site_manager/    # 9 read-only tools (discovery.py + metrics.py + sdwan.py)
```

## Conventions

- **Python >=3.13**, strict `ty` type checks, ruff for lint+format
- **Line length**: 120 characters
- **Tool naming**: `unifi_{api}_{verb}_{entity}` (e.g., `unifi_network_list_devices`, `unifi_protect_get_snapshot`). Every tool starts with `unifi_` per PROTO-002.
- **Write tools**: Tagged with `{"write"}`, annotated with `readOnlyHint=False`. Disabled in readonly mode via `mcp.disable(tags={"write"})`
- **Defense-in-depth**: Write tools also check `config.writes_enabled` at runtime
- **Clients**: Use `httpx.AsyncClient` with `tenacity` retry (3 attempts, exponential backoff). API responses flow through as `dict[str, Any]` — there is no Pydantic validation layer between clients and tools.
- **Error mapping**: API errors -> typed exceptions -> `ToolError` with agent-readable messages
- **Tests**: Use `respx` for HTTP mocking, `pytest-asyncio` for async tests
- **No print statements**: Use `logging` module (enforced by ruff T20 rule)

## Key Patterns

### Mode Gating
```python
# Tools tagged with {"write"} are disabled in readonly mode
@mcp.tool(tags={"write"}, annotations={"readOnlyHint": False})
async def unifi_network_create_wlan(...): ...

# In server lifespan:
if not config.writes_enabled:
    mcp.disable(tags={"write"})
```

### Graceful Degradation
```python
# Only register tools for APIs with configured keys
if config.network_enabled:
    register_network_tools(mcp)
if config.protect_enabled:
    register_protect_tools(mcp)
```

## Gotchas

- **Protect host must be set on split deployments (#107)**: If Protect runs on a separate UCK/NVR from the gateway, `UNIFI_PROTECT_HOST` must be set explicitly. The default inherits `UNIFI_NETWORK_HOST`, `validate_connection` fails at startup, and every Protect tool deregisters with a single WARN line.
- **API keys are service-scoped (#131)**: A Network-scoped key returns 401 on `/proxy/protect/...`. `UNIFI_NETWORK_API` and `UNIFI_PROTECT_API` must be issued under their respective services in UniFi OS.
- **No Pydantic validation layer between clients and tools**: An earlier `src/unifi_mcp/models/` layer was abandoned; clients pass raw `dict[str, Any]` straight to tools. Don't reintroduce one without a clear motivating constraint.

## CI/CD

- **CI**: Runs on push to main and PRs. Lint (ruff), typecheck (ty), and test (pytest) all on Python 3.13
- **Security**: Weekly Bandit scans + dependency review on PRs
- **Dependabot**: Weekly updates for Python deps and GitHub Actions
- **Release**: No automated release pipeline yet — `uv build` produces a wheel locally; PyPI publishing is not wired up

## Canonical MCP standards

Authoritative source: `~/Desktop/Projects/consistency-check/docs/standards/`. This repo is graded against `mcp.md` + the language-specific file (`python.md` for Python repos, `go.md` for Go) + `mcp-protocol.md`.

Run the audit:

```bash
cd ~/Desktop/Projects/consistency-check
uv run consistency-check audit --repo $(basename "$PWD")
```

## Agent skills

### Issue tracker

GitHub issues at `millsymills-com/unifi-mcp` via `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default canonical roles (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`) plus `bug`/`enhancement` category labels. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` + `docs/adr/` at repo root. See `docs/agents/domain.md`.
