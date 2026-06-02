# Design: v1 read-only runbook prompts

**Date:** 2026-06-01
**Status:** Approved design, pending implementation plan
**Scope:** v1 — read-only diagnostic and reporting runbooks for UniFi admins, delivered as MCP prompts.

## Problem

The server today exposes only MCP **tools** — no prompts, no resources. An AI
agent driving `unifi-mcp` on behalf of a UniFi admin has to invent the
diagnostic sequence for common tasks ("why can't this client connect?",
"is my WAN degraded?") from scratch every time. There are no operational
runbooks; all of `docs/` is dev/agent-facing (ADRs, plans, test safety).

MCP **prompts** are the purpose-built primitive for shipping agent-initiated,
parameterized workflows. We use none. That is the gap this design closes.

## Goal

Ship four read-only **runbook prompts** that encode the diagnostic/reporting
procedure for the most common admin tasks: the agent invokes a prompt, receives
an ordered procedure naming the exact existing tools to call and how to
interpret each result, then executes against the already-safe read tools.

## Non-goals (deferred to v2, per product decision)

- Audit/review prompts (firewall posture, exposed port-forwards, rogue clients).
- Provisioning prompts (write-gated: create WLAN/VLAN/port-forward).
- Hybrid markdown→resource source-of-truth pattern.
- Multi-site parameters.
- Client-slow / client-to-client reachability runbooks.

## Architecture

New package mirroring `tools/`:

```
src/unifi_mcp/prompts/
├── __init__.py     # register_all_prompts(mcp, config)
└── network.py      # 4 prompt fns + per-prompt REFERENCED_TOOLS frozensets
```

`create_server` calls `register_all_prompts(server, config)` immediately after
`register_all_tools(server, config)`.

All four v1 runbooks depend on the Network API, so they register **only when
`config.network_enabled`** — the same graceful-degradation rule tools follow.
They are tagged `{"network", "runbook"}`.

### Why the `network` tag is intentional

The server lifespan disables a configured-but-unreachable API's components via
`server.disable(tags={api_name})` (`server.py`, `api_name="network"`). Verified
empirically: `disable(tags={"network"})` removes prompts from `list_prompts()`,
not just tools. This is **desirable** — if the Network API fails startup
validation, its runbooks should disappear too rather than instruct the agent to
call tools that will raise at call time. The shared tag wires runbook
degradation to API health for free.

### What a runbook prompt is

A FastMCP `@mcp.prompt` returning **procedure text** (a `str`, which FastMCP
delivers as a single `user`-role message). It does **not** call the API itself —
all I/O stays in the existing, already-safe read tools. The text states:

1. The goal.
2. Ordered diagnostic steps.
3. The existing tools to call **by name**.
4. How to interpret results and branch to a conclusion.
5. A fixed "report back" output shape so the agent's answer to the admin is
   consistent.

Prompt parameters interpolate into the text. Each prompt module declares a
`REFERENCED_TOOLS: frozenset[str]` and builds its text to include exactly those
names — this declaration (not prose-parsing) is what the drift guard checks.

No write tag, no `UNIFI_MODE` gating: these are read-only guidance.

## Procedure-authoring rules (baked into every runbook)

These exist because the underlying tools have constraints that naive procedure
text would misrepresent, misleading the agent:

1. **`unifi_network_list_events` is a site-wide alarm log taking only `limit`**
   (verified: `(ctx, limit=100)`). It has no server-side per-entity filter.
   Procedures MUST instruct: fetch N events, then **filter client-side** by
   MAC/keyword. Never imply the tool filters by client/device/WAN.
2. **MAC-only tools require resolution first.** `unifi_network_get_client` and
   `unifi_network_get_device` take a strict `mac` (verified). When a runbook
   accepts a name-or-MAC argument, the procedure MUST spell out the resolve
   step: call `list_active_clients` / `list_devices`, match by name, extract the
   MAC, then call the MAC-only tool. Do not direct the agent to pass a hostname
   to a MAC-only tool.
3. **Single-site scope.** Each procedure states it covers the configured site
   only, so the agent does not imply completeness to a multi-site operator.

## The four runbooks

| Prompt | Args | Tool chain |
|---|---|---|
| `unifi_network_troubleshoot_client` | `client: str` (MAC or name) | resolve → `unifi_network_get_client` → identify AP/uplink → `unifi_network_get_health` → `unifi_network_list_events` + client-side filter → conclusion (roaming, DHCP, band, blocked, AP down) |
| `unifi_network_troubleshoot_device` | `device: str` (MAC or name) | resolve → `unifi_network_get_device` / `unifi_network_list_devices` → state & uplink → `unifi_network_list_events` + filter → `unifi_network_get_health` → conclusion (adoption, uplink, PoE/power, firmware, offline) |
| `unifi_network_troubleshoot_wan` | *(none)* | `unifi_network_get_health` (WAN subsystem) → `unifi_network_list_devices` (gateway state) → `unifi_network_list_events` + filter → `unifi_network_get_sysinfo` → conclusion (ISP outage, gateway, DNS, degraded) |
| `unifi_network_report_health` | *(none)* | `unifi_network_get_health` + `unifi_network_get_sysinfo` → `unifi_network_list_devices` (status/firmware) → `unifi_network_list_active_clients` (counts) → `unifi_network_list_events` (recent notable) → structured digest |

All seven referenced tool names are verified to exist in `src/unifi_mcp/tools/`.

### Naming

Prompts follow the tool convention `unifi_network_{verb}_{entity}` so they read
consistently alongside tools in a client's combined list, and so v2 prompts for
other APIs (`unifi_protect_*`, `unifi_site_manager_*`) disambiguate structurally.

### Note on `unifi_network_report_health`

This is an aggregation runbook (assemble a digest) rather than a branching
diagnostic. It carries less unique value than the three troubleshoot runbooks —
a capable agent can assemble a similar digest unaided — but it is retained as a
deliberate v1 inclusion for the common "how's my network?" ask.

## Testing — `tests/unit/prompts/`

Pure-text; no HTTP, no cassettes. Verified feasible against FastMCP 3.3.1
(`list_prompts()`, `render_prompt(name, args)` returning
`messages[].content.text`).

1. **Arg interpolation.** Render each parameterized prompt with a sample value;
   assert the value appears in `messages[].content.text`. (FastMCP populates
   `.arguments` from the function signature, so the assertion must be on
   *rendered text*, not the argument list.)
2. **Drift guard (bidirectional).** For each prompt:
   - `REFERENCED_TOOLS ⊆ {names in the server's registered tool set}` — catches
     a runbook naming a tool that was renamed/removed.
   - every `unifi_network_*` token in the rendered text is in
     `REFERENCED_TOOLS` — catches typos and undeclared references.
   - *Known limitation:* the guard validates tool-name presence, not that the
     procedure passes correct arguments (e.g. a MAC where a MAC is required).
     The procedure-authoring rules mitigate this; tests do not enforce it.
3. **Gating + leak guard.** `register_all_prompts` registers nothing when
   `network_enabled=False`; additionally, a server built with
   `network_enabled=False` exposes zero prompts via `list_prompts()` (catches a
   prompt registered outside `register_all_prompts`).

## Risks

- **Procedure rot.** Static text can direct the agent to suboptimal tool chains
  after new tools land; the drift guard detects deletions, not better
  alternatives. Accepted for v1; revisit if churn is high.
- **User-role delivery.** Procedure arrives as a user turn, which some clients
  follow less strictly than a system instruction. `task=True` is available but
  is YAGNI for v1.
