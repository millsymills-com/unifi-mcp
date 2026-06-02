# Project Context

Domain glossary and core concepts for `unifi-mcp`. Producer skills (e.g. `/grill-with-docs`) extend this lazily as new terms are resolved.

## What this project is

Production-grade Python MCP server bridging UniFi Site Manager, Network, and Protect APIs to MCP-speaking clients. Installed from source via `uv sync`; not published to PyPI. Built on FastMCP.

## Glossary

- **API client**: an `httpx.AsyncClient` wrapper for one upstream service, subclassing `BaseUniFiClient` (`src/unifi_mcp/clients/`). Owns auth headers, `tenacity` retry, and error mapping. Responses pass through as raw `dict[str, Any]`; there is no Pydantic validation layer between clients and tools.
- **Dangerous-key denylist**: a guard (`reject_dangerous_keys`) that rejects request bodies touching auth, callback, or escalation fields (`super_*`, `radius_*`, `mac_filter_*`, `*_url`, `*_command`, admin role flags) before they reach the controller.
- **Graceful degradation**: per-API startup behavior; only services with configured keys register their tools; a service that fails `validate_connection` deregisters its tools with a single WARN line rather than aborting the server. See `config.network_enabled` / `config.protect_enabled`.
- **MCP tool**: a FastMCP-decorated async function exposed to MCP clients (`src/unifi_mcp/tools/`). Named `unifi_{api}_{verb}_{entity}`; every name starts with `unifi_` (PROTO-002).
- **Mode gating**: the readonly/readwrite split. Write tools are disabled unless `config.writes_enabled` (true when `UNIFI_MODE=readwrite`), enforced both declaratively (`mcp.disable(tags={"write"})`) and at runtime in the tool handler.
- **Named-arg body builder**: `build_named_arg_body`, which maps a tool's allowlisted scalar kwargs to their dotted destinations in the outgoing request body. The named-arg surface *is* the write allowlist; fields not listed cannot be set via that tool.
- **Read tool**: a tool with no `write` tag; available in both readonly and readwrite mode.
- **Redaction**: scrubbing of secret-shaped fields (tokens, keys, passwords, `super_*` callbacks) from responses via `redact_secrets` before they leave a tool. See `src/unifi_mcp/_redaction.py`.
- **Service-scoped API key**: a UniFi OS API key issued under one service. A Network-scoped key returns 401 against `/proxy/protect/...`; `UNIFI_NETWORK_API` and `UNIFI_PROTECT_API` must be issued under their respective services (#131).
- **Write tool**: a tool tagged `{"write"}` and annotated `readOnlyHint=False`, gated behind mode gating. Tools that change controller state.

## Core concepts

### Mode gating (readonly vs readwrite)

The server defaults to readonly. `UNIFI_MODE=readwrite` sets `config.writes_enabled`, which both keeps `{"write"}`-tagged tools registered and lets the shared tool handler run them. Read tools are always available. This is defense-in-depth: the declarative `mcp.disable(tags={"write"})` and the runtime handler check both have to agree before a write executes.

### Graceful per-API degradation

Each upstream (Site Manager, Network, Protect) is independent. A service registers its tools only when its key is configured and its connection validates at startup; otherwise it deregisters with a WARN line and the rest of the server runs normally. On split deployments, Protect needs `UNIFI_PROTECT_HOST` set explicitly; the default inherits `UNIFI_NETWORK_HOST` and fails validation (#107).

### Named-arg write allowlist

Write tools that edit structured settings expose explicit scalar kwargs instead of a free-form payload. `build_named_arg_body` resolves those kwargs to nested body paths; anything not in the per-tool field-path map cannot be set. This keeps the writable surface small and auditable rather than relying on a denylist alone.

### Retry / error-mapping pipeline

Clients retry transient failures with `tenacity` (3 attempts, exponential backoff), then map upstream API errors to typed exceptions, which the tool handler converts to `ToolError` with agent-readable messages. Responses are redacted on the way out.
