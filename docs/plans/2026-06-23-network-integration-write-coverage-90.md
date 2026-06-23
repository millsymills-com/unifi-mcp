# Implementation Plan — Raise UniFi Network Integration API write coverage 75% → ≥90%

## 0. Goal & coverage math

**Goal:** Add Network Integration (NI) **write** tools to lift §3b coverage from **54/72 (75%)** to **≥65/72 (≥90%)**, ideally **72/72 (100%)**. The denominator is **72** = 73 NI operations minus the 1 excluded `/countries` op. All 18 remaining gaps in `docs/api-coverage-matrix.md` §3b are writes; there are no read gaps.

**Threshold arithmetic (verified):**
- Start: **54/72 = 75.0%**.
- 65/72 = **90.28%** is the first integer numerator that clears 90%. From 54 covered that needs **+11**.
- 72/72 = **100%** needs **+18** (all gaps).

### Endpoint → tool map (the 18 gaps)

| # | Method | Path (per-site suffix) | Proposed tool | Group | Destructive |
|---|--------|------------------------|---------------|-------|-------------|
| 1 | POST | `acl-rules` | `unifi_network_create_acl_rule` | ACL (4) | no |
| 2 | PUT | `acl-rules/{id}` | `unifi_network_update_acl_rule` | ACL | no |
| 3 | DELETE | `acl-rules/{id}` | `unifi_network_delete_acl_rule` | ACL | **yes** |
| 4 | PUT | `acl-rules/ordering` | `unifi_network_reorder_acl_rules` | ACL | no (full-replace) |
| 5 | PUT | `firewall/policies/ordering` | `unifi_network_reorder_firewall_policies` | FW-policies (2) | no (full-replace) |
| 6 | PATCH | `firewall/policies/{id}` | `unifi_network_patch_firewall_policy` | FW-policies | no |
| 7 | POST | `firewall/zones` | `unifi_network_create_firewall_zone` | FW-zones (3) | no |
| 8 | PUT | `firewall/zones/{id}` | `unifi_network_update_firewall_zone` | FW-zones | no (full-replace) |
| 9 | DELETE | `firewall/zones/{id}` | `unifi_network_delete_firewall_zone` | FW-zones | **yes** |
| 10 | POST | `dns/policies` | `unifi_network_create_dns_policy` | DNS (3) | no |
| 11 | PUT | `dns/policies/{id}` | `unifi_network_update_dns_policy` | DNS | no (full-replace) |
| 12 | DELETE | `dns/policies/{id}` | `unifi_network_delete_dns_policy` | DNS | **yes** |
| 13 | POST | `hotspot/vouchers` | `unifi_network_create_vouchers` | Vouchers (3) | no |
| 14 | DELETE | `hotspot/vouchers` (filter) | `unifi_network_delete_vouchers` | Vouchers | **yes (bulk)** |
| 15 | DELETE | `hotspot/vouchers/{id}` | `unifi_network_delete_voucher` | Vouchers | **yes** |
| 16 | POST | `traffic-matching-lists` | `unifi_network_create_traffic_matching_list` | TML (3) | no |
| 17 | PUT | `traffic-matching-lists/{id}` | `unifi_network_update_traffic_matching_list` | TML | no (full-replace) |
| 18 | DELETE | `traffic-matching-lists/{id}` | `unifi_network_delete_traffic_matching_list` | TML | **yes** |

> **No tool-name collisions:** all 18 proposed `unifi_network_*` names are absent from `src/` (verified by name search).

### Group selection — recommend COMPLETE resource groups, no half-written resource

Each group is internally coherent (create/update/delete + ordering belong together). Ship whole groups so the matrix never shows a half-covered resource.

Group sizes: ACL=4, FW-zones=3, DNS=3, Vouchers=3, TML=3, FW-policies=2.

**Provable ≥90% with the recommended set (+13 → 67/72 = 93.1%):**

- **ACL (4) + FW-zones (3) + DNS (3) + Vouchers (3) = +13 → 67/72 = 93.06%.**

This clears 90% with headroom (so a single endpoint slipping a phase still leaves ≥66/72 = 91.7%), and ships only complete groups.

**On the minimum complete-group crossing:** a bare +11 → 65/72 = 90.28% is mathematically sufficient, and the *only* complete-group combination summing to exactly +11 is **FW-policies (2) + DNS (3) + FW-zones (3) + Vouchers (3)**. But that set is forced to include the **FW-policies** group, whose reorder request body and query-param names are **unverified against `10.4.57.json`** (Phase 6 / §7 risks) — so the recommended set deliberately excludes it. With FW-policies excluded, group sizes are {ACL 4, FW-zones 3, DNS 3, Vouchers 3, TML 3} and no subset sums to 11 (the reachable sums straddle it: 10 and 12), so the smallest *FW-policies-free* crossing is **+12 → 66/72 = 91.67%** (any four 3-groups, e.g. FW-zones + DNS + Vouchers + TML). The recommended **+13** adds ACL on top of that for margin while still avoiding the uncertain group.

**Path to 100%:** add the remaining two complete groups — **TML (3) + FW-policies (2) = +5 → 72/72 = 100%.**

**Recommended rollout:** implement all six groups (one PR per group, §7) since the work and bookkeeping are uniform; the 90% line is met after the first four groups land, 100% after all six.

> Coverage facts verified against `docs/api-coverage-matrix.md` §3b: the 18 **Gap** rows are exactly the 18 endpoints above; everything else in §3b is already **Covered**.

---

## Phase 0 — Client write methods on `NetworkIntegrationClient`

**File:** `src/unifi_mcp/clients/network_integration.py`

The client today is read-only (`get`-based). `BaseUniFiClient` already supplies the verb helpers — **no `base.py` change**:
- `post`, `put`, `patch` (deliberately **not** retried — correct for writes), `delete`. All return parsed JSON or `{}` on 204/empty.
- `_segment` percent-encodes one path segment; **every caller-supplied id in a path MUST flow through it** (already the read convention, e.g. `get_acl_rule`).
- `_site_path(suffix)` injects the resolved site UUID as `sites/{siteId}/{suffix}` and raises `UniFiError` if the site is unresolved, so writes are inert until `validate_connection` succeeds.

### 0.1 Module docstring + class docstring

The module header and class docstring say **"Read-only"** — revise both to "Read and write client for the … Integration API" once write methods are added. (The `__init__.py` docstring is handled in §6.)

### 0.2 New methods (mirror legacy `NetworkClient` writes, route through `_site_path`)

Add after the read block. Each returns `dict[str, Any]`.

> **Builtin-shadowing note (BLOCKER fixed):** ruff has `flake8-builtins` (`"A"`) enabled and **A002 (builtin-argument-shadowing) is NOT excused for `src/unifi_mcp/clients/` or `src/unifi_mcp/tools/`** in `[tool.ruff.lint.per-file-ignores]`. A parameter named `filter` therefore fails `uv run ruff check src/ tests/` and violates the zero-warnings policy. The Python identifier is **`voucher_filter`** on both the client method and the tool; the query-string **key stays `filter`** via `params={"filter": voucher_filter}`.

```python
# ── Write methods: ACL ──────────────────────────────────────────────
async def create_acl_rule(self, data: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = await self.post(self._site_path("acl-rules"), json=data)
    return result

async def update_acl_rule(self, acl_rule_id: str, data: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = await self.put(
        self._site_path(f"acl-rules/{self._segment(acl_rule_id)}"), json=data)
    return result

async def delete_acl_rule(self, acl_rule_id: str) -> dict[str, Any]:
    result: dict[str, Any] = await self.delete(self._site_path(f"acl-rules/{self._segment(acl_rule_id)}"))
    return result

async def update_acl_rules_ordering(self, ordered_acl_rule_ids: list[str]) -> dict[str, Any]:
    result: dict[str, Any] = await self.put(
        self._site_path("acl-rules/ordering"), json={"orderedAclRuleIds": ordered_acl_rule_ids})
    return result

# ── Write methods: firewall policies ────────────────────────────────
async def reorder_firewall_policies(
    self, source_firewall_zone_id: str, destination_firewall_zone_id: str,
    before_system_defined: list[str], after_system_defined: list[str],
) -> dict[str, Any]:
    result: dict[str, Any] = await self.put(
        self._site_path("firewall/policies/ordering"),
        params={"sourceFirewallZoneId": source_firewall_zone_id,
                "destinationFirewallZoneId": destination_firewall_zone_id},
        json={"orderedFirewallPolicyIds": {
            "beforeSystemDefined": before_system_defined,
            "afterSystemDefined": after_system_defined}})
    return result

async def patch_firewall_policy(self, firewall_policy_id: str, logging_enabled: bool) -> dict[str, Any]:
    result: dict[str, Any] = await self.patch(
        self._site_path(f"firewall/policies/{self._segment(firewall_policy_id)}"),
        json={"loggingEnabled": logging_enabled})
    return result

# ── Write methods: firewall zones ───────────────────────────────────
async def create_firewall_zone(self, name: str, network_ids: list[str]) -> dict[str, Any]:
    result: dict[str, Any] = await self.post(
        self._site_path("firewall/zones"), json={"name": name, "networkIds": network_ids})
    return result

async def update_firewall_zone(self, zone_id: str, name: str, network_ids: list[str]) -> dict[str, Any]:
    result: dict[str, Any] = await self.put(
        self._site_path(f"firewall/zones/{self._segment(zone_id)}"),
        json={"name": name, "networkIds": network_ids})
    return result

async def delete_firewall_zone(self, zone_id: str) -> dict[str, Any]:
    result: dict[str, Any] = await self.delete(self._site_path(f"firewall/zones/{self._segment(zone_id)}"))
    return result

# ── Write methods: DNS policies ─────────────────────────────────────
async def create_dns_policy(self, data: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = await self.post(self._site_path("dns/policies"), json=data)
    return result

async def update_dns_policy(self, dns_policy_id: str, data: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = await self.put(
        self._site_path(f"dns/policies/{self._segment(dns_policy_id)}"), json=data)
    return result

async def delete_dns_policy(self, dns_policy_id: str) -> dict[str, Any]:
    result: dict[str, Any] = await self.delete(self._site_path(f"dns/policies/{self._segment(dns_policy_id)}"))
    return result

# ── Write methods: hotspot vouchers ─────────────────────────────────
async def create_vouchers(
    self, *, name: str, time_limit_minutes: int, count: int = 1,
    authorized_guest_limit: int | None = None, data_usage_limit_mbytes: int | None = None,
    rx_rate_limit_kbps: int | None = None, tx_rate_limit_kbps: int | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"name": name, "timeLimitMinutes": time_limit_minutes, "count": count}
    optional = {
        "authorizedGuestLimit": authorized_guest_limit,
        "dataUsageLimitMBytes": data_usage_limit_mbytes,
        "rxRateLimitKbps": rx_rate_limit_kbps,
        "txRateLimitKbps": tx_rate_limit_kbps,
    }
    body.update({k: v for k, v in optional.items() if v is not None})
    result: dict[str, Any] = await self.post(self._site_path("hotspot/vouchers"), json=body)
    return result

async def delete_vouchers(self, *, voucher_filter: str) -> dict[str, Any]:
    result: dict[str, Any] = await self.delete(
        self._site_path("hotspot/vouchers"), params={"filter": voucher_filter})
    return result

async def delete_voucher(self, voucher_id: str) -> dict[str, Any]:
    result: dict[str, Any] = await self.delete(self._site_path(f"hotspot/vouchers/{self._segment(voucher_id)}"))
    return result

# ── Write methods: traffic-matching lists ───────────────────────────
async def create_traffic_matching_list(self, data: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = await self.post(self._site_path("traffic-matching-lists"), json=data)
    return result

async def update_traffic_matching_list(self, list_id: str, data: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = await self.put(
        self._site_path(f"traffic-matching-lists/{self._segment(list_id)}"), json=data)
    return result

async def delete_traffic_matching_list(self, list_id: str) -> dict[str, Any]:
    result: dict[str, Any] = await self.delete(
        self._site_path(f"traffic-matching-lists/{self._segment(list_id)}"))
    return result
```

**ID/site handling notes:**
- All path ids (`acl_rule_id`, `zone_id`, `dns_policy_id`, `voucher_id`, `firewall_policy_id`, `list_id`) go through `_segment` in the client and through `validate_id` in the tool layer (§ per-group phases).
- No tool/method takes a `siteId` arg — `_site_path` injects the resolved UUID.
- DELETE/`200`-empty bodies: `base.delete` already normalizes 204/empty to `{}`. Voucher DELETEs are documented to return a JSON body and pass through. **Verify against live/spec** that zone/DNS/TML/ACL DELETE truly return empty 200; if so the client returns `{}` and the tool returns it verbatim — do **not** synthesize `{"deleted": true}`.

---

## Phase 1 — ACL group (+4 → 58/72) *(file: `tools/network_integration/acl.py`)*

**Imports:** extend the `_common` import to add `JsonObject` and `reject_dangerous_keys`:
```python
from unifi_mcp.tools._common import (
    JsonObject, get_server_context, redact_secrets, reject_dangerous_keys, tool_handler, validate_id,
)
```

**Decorator stack (the canonical NI-write stack — mirror legacy `firewall.py` but add `"network_integration"` so the tool BOTH gates on write-mode AND degrades when the NI backend is down):**

```python
@mcp.tool(tags={"write", "network_integration"}, annotations={"readOnlyHint": False, "destructiveHint": False})
@tool_handler(write=True)
async def unifi_network_create_acl_rule(ctx: Context, data: JsonObject) -> dict[str, Any]:
    """Create an L2/L3 ACL rule (Network Integration API).

    The body is a discriminated union on ``type`` (``IPV4`` or ``MAC``). Required
    keys regardless of variant: ``type``, ``enabled``, ``name`` (non-empty),
    ``action`` (``ALLOW``|``BLOCK``). IPV4 rules use IP source/destination
    filters and optional ``protocolFilter`` (``TCP``/``UDP``); MAC rules use MAC
    filters and require ``networkIdFilter``. Do not set the deprecated ``index``
    field — use ``unifi_network_reorder_acl_rules`` for priority.

    Args:
        ctx: FastMCP request context.
        data: Full ACL-rule body matching the controller's "ACL rule update" schema.

    Returns:
        The created rule (server-assigned ``id``), with sensitive fields redacted.

    Raises:
        ToolError: If write mode is disabled, ``data`` contains a denylisted key,
            or the controller rejects the body.
    """
    reject_dangerous_keys(data, tool_name="unifi_network_create_acl_rule")
    return redact_secrets(await get_server_context(ctx).clients["network_integration"].create_acl_rule(data))
```

`unifi_network_update_acl_rule(ctx, acl_rule_id: str, data: JsonObject)` — body order: `validate_id(acl_rule_id, field="acl_rule_id")` **first**, then `reject_dangerous_keys(data, ...)`, then call `update_acl_rule(acl_rule_id, data)`, wrap in `redact_secrets`. Docstring notes the body schema is identical to create; only user-defined rules are editable.

`unifi_network_delete_acl_rule(ctx, acl_rule_id: str, confirm: bool = False)` — **destructive**, `annotations={"readOnlyHint": False, "destructiveHint": True}`. Body: `validate_id(...)`, then `if not confirm: raise UniFiBadRequestError("delete is irreversible; pass confirm=True")` (the error funnel maps it to `ToolError`). Then call `delete_acl_rule`. Docstring `Raises:` documents the `confirm` guard.

`unifi_network_reorder_acl_rules(ctx, ordered_acl_rule_ids: list[str])` — non-destructive but **full-replacement**: omitting an id rewrites site-wide ACL priority. `destructiveHint=False`. Validate each id via `validate_id` in a loop (`field="ordered_acl_rule_ids"`). Call `update_acl_rules_ordering(ordered_acl_rule_ids)`. **Docstring MUST warn**: "Pass the COMPLETE current id set; any omitted rule loses its enforcement position." Pairs with read `unifi_network_get_acl_rules_ordering`.

> **Uncertain (verify against live/spec, do NOT invent):** inner shapes of `IP ACL rule endpoint`, `MAC ACL rule endpoint`, `IntegrationAclRuleDevicesFilterDto`. Tool forwards `data` verbatim — no field synthesis. Docstring lists only the confirmed parent fields above.

---

## Phase 2 — DNS-policies group (+3) *(file: `tools/network_integration/dns.py`)*

Same imports addition (`JsonObject`, `reject_dangerous_keys`).

- `unifi_network_create_dns_policy(ctx, data: JsonObject)` — `destructiveHint=False`. `reject_dangerous_keys` → `create_dns_policy(data)` → `redact_secrets`. Docstring: body is a discriminated union on `type` (`A_RECORD`/`AAAA_RECORD`/`CNAME_RECORD`/`MX_RECORD`/`TXT_RECORD`/`SRV_RECORD`/`FORWARD_DOMAIN`); `type` and `enabled` always required; per-type required fields differ. **`ttlSeconds` applies only to A/AAAA/CNAME** (CNAME max 604800; A/AAAA max 86400); MX/TXT/SRV/FORWARD_DOMAIN have no `ttlSeconds`.
- `unifi_network_update_dns_policy(ctx, dns_policy_id: str, data: JsonObject)` — `validate_id(dns_policy_id, field="dns_policy_id")` first, then `reject_dangerous_keys`, then `update_dns_policy`. Full-object PUT (send every required field for the chosen `type`).
- `unifi_network_delete_dns_policy(ctx, dns_policy_id: str, confirm: bool = False)` — **destructive** (`destructiveHint=True`), `validate_id` → confirm guard → `delete_dns_policy`.

> DELETE returns 200 with no body — see Phase 0 empty-body note.

---

## Phase 3 — Firewall-zones group (+3) *(file: `tools/network_integration/firewall.py`)*

Imports: this is **named-scalar** (not raw `data`), so you do **not** need `JsonObject`/`reject_dangerous_keys` for create/update — keep `validate_id`. (`network_ids` is a body array of plain strings; do not run `validate_id` on its items — the spec types items as plain `string`, not uuid.)

- `unifi_network_create_firewall_zone(ctx, name: str, network_ids: list[str])` — `destructiveHint=False`. Call `create_firewall_zone(name, network_ids)` → `redact_secrets`. Docstring: `metadata` is response-only and must not be supplied; some system-defined zones may reject a rename (controller-side, surfaced as a 4xx via the error funnel — not pre-validated).
- `unifi_network_update_firewall_zone(ctx, zone_id: str, name: str, network_ids: list[str])` — `validate_id(zone_id, field="zone_id")`, then `update_firewall_zone(...)`. **Full-replace**: an incomplete `network_ids` silently detaches networks — state this in the docstring.
- `unifi_network_delete_firewall_zone(ctx, zone_id: str, confirm: bool = False)` — **destructive** (`destructiveHint=True`): deleting a zone unlinks it from referencing firewall policies. `validate_id` → confirm guard → `delete_firewall_zone`.

---

## Phase 4 — Hotspot-vouchers group (+3) *(file: `tools/network_integration/hotspot.py`)*

Named-scalar create; delete-by-filter and delete-by-id.

- `unifi_network_create_vouchers(ctx, *, name: str, time_limit_minutes: int, count: int = 1, authorized_guest_limit: int | None = None, data_usage_limit_mbytes: int | None = None, rx_rate_limit_kbps: int | None = None, tx_rate_limit_kbps: int | None = None)` — `destructiveHint=False`. **All args after `ctx` are keyword-only (bare `*`)**, so the positional-param count is 1, satisfying the global `≤5 positional params` norm with zero ambiguity (PLR0913 is globally ignored, so this is a standards choice, not a CI gate). Calls client `create_vouchers(...)` (client builds the body, omitting `None`). Docstring lists verbatim bounds: `count` 1–1000, `time_limit_minutes` 1–1000000, `data_usage_limit_mbytes` 1–1048576, `rx/tx_rate_limit_kbps` 2–100000. Do **not** add invented fields.
- `unifi_network_delete_vouchers(ctx, voucher_filter: str, confirm: bool = False)` — **destructive, BULK** (`destructiveHint=True`). The identifier is `voucher_filter` (NOT `filter` — see Phase 0 A002 note); the client passes it through as the `filter` query-string key. The API only requires the param be present, not narrow. Tool MUST: reject blank/whitespace `voucher_filter` (raise `UniFiBadRequestError`) AND require `confirm=True`. Then `delete_vouchers(voucher_filter=voucher_filter)`. Returns the API's deletion-count body verbatim. Docstring strongly warns a broad filter mass-deletes vouchers.
- `unifi_network_delete_voucher(ctx, voucher_id: str, confirm: bool = False)` — **destructive** single id (`destructiveHint=True`). `validate_id(voucher_id, field="voucher_id")` (mirrors `unifi_network_get_voucher`) → confirm guard → `delete_voucher`.

> The `filter` expression grammar is **uncertain** (spec gives no description) — treat as opaque string; do not validate its contents beyond non-blank. **Verify against live/spec.**

**Phases 1–4 together = +13 → 67/72 = 93.1% (≥90% met).**

---

## Phase 5 — Traffic-matching-lists group (+3 → 70/72) *(file: `tools/network_integration/traffic.py`)*

Named-scalar `name`/`list_type`/`items`; tool assembles the body dict. (Add `JsonObject`/`reject_dangerous_keys` to imports.)

- `unifi_network_create_traffic_matching_list(ctx, name: str, list_type: str, items: list[dict[str, Any]])` — `destructiveHint=False`. Build `data = {"name": name, "type": list_type, "items": items}`, run `reject_dangerous_keys(data, tool_name=...)` (items are dicts), call `create_traffic_matching_list(data)`. Docstring: `list_type` ∈ `PORTS`|`IPV4_ADDRESSES`|`IPV6_ADDRESSES`; each `items` element carries its own discriminator `type` + `value`/`start`/`stop`.
- `unifi_network_update_traffic_matching_list(ctx, list_id: str, name: str, list_type: str, items: list[dict[str, Any]])` — `validate_id(list_id, field="list_id")` first, then build body + `reject_dangerous_keys` + `update_traffic_matching_list(list_id, data)`. Full-replace.
- `unifi_network_delete_traffic_matching_list(ctx, list_id: str, confirm: bool = False)` — **destructive** (`destructiveHint=True`): a list still referenced by a firewall policy/rule may orphan that rule. `validate_id` → confirm guard → `delete_traffic_matching_list`.

> Item element `type` enums (`PORT_NUMBER`/`PORT_NUMBER_RANGE`; v4 `IP_ADDRESS`/`SUBNET`/`IP_ADDRESS_RANGE`; **v6 has NO range variant**) are nested discriminators the tool does NOT validate (no-Pydantic convention). **Verify against live/spec** — base variant DTOs mark `required:[items,name]` but `type` must still be sent (it is the discriminator).

---

## Phase 6 — Firewall-policies group (+2 → 72/72 = 100%) *(file: `tools/network_integration/firewall.py`)*

- `unifi_network_reorder_firewall_policies(ctx, source_firewall_zone_id: str, destination_firewall_zone_id: str, before_system_defined: list[str], after_system_defined: list[str])` — `destructiveHint=False` (full-replace, reversible). `validate_id` both zone ids (`field="source_firewall_zone_id"` / `"destination_firewall_zone_id"`) and each id in both arrays. The two zone ids are **query params**; the body holds `{orderedFirewallPolicyIds: {beforeSystemDefined, afterSystemDefined}}` (client handles this split). **Both arrays are required even if empty** — pass `[]` explicitly. Docstring: full-replace of ordering for that zone pair.

  > **UNCERTAIN — verify before shipping (do NOT present as settled):** the nested body shape `{"orderedFirewallPolicyIds": {"beforeSystemDefined": [...], "afterSystemDefined": [...]}}` AND the two query-param names `sourceFirewallZoneId`/`destinationFirewallZoneId` are **not yet confirmed** against the pinned `10.4.57.json` spec. Gate shipping Phase 6 on confirming this body nesting and the param names against `10.4.57.json` (and/or a live PUT). If the spec differs, adjust both the client method (`reorder_firewall_policies`, Phase 0) and this tool. See §7 Risks.

- `unifi_network_patch_firewall_policy(ctx, firewall_policy_id: str, logging_enabled: bool)` — `destructiveHint=False`. `validate_id(firewall_policy_id, field="firewall_policy_id")` → `patch_firewall_policy(firewall_policy_id, logging_enabled)`. **In spec v10.4.57 the PATCH schema exposes ONLY `loggingEnabled`** — do NOT add `action`/`enabled`/`name` patch args (no-speculative-features; widen only if a future pinned spec widens). `logging_enabled` is a required bool (empty-body PATCH may be rejected).

---

## 4. Gating & registration

**No new modules** — every write tool lands inside an existing `register_*_tools` function (e.g. `register_acl_tools`), which `register_network_integration_tools` already calls. New tools are auto-discovered; **no `__init__.py` import/call change** is needed.

**Three independent gates (defense-in-depth), all satisfied by the decorator stack above:**

1. **Registration tag gate (PROTO-005/006).** `register_all_tools` (`tools/__init__.py:48`) runs `if not config.writes_enabled: mcp.disable(tags={"write"})` (`:56-57`). Carrying `"write"` in `mcp.tool(tags=…)` means the tool is **hidden in readonly mode by default** (`UNIFI_MODE` defaults to readonly; `config.writes_enabled` is True only when `UNIFI_MODE=readwrite`).
2. **In-handler runtime gate.** `@tool_handler(write=True)` injects `if write and not …writes_enabled: raise UniFiReadOnlyError` **before** the body — blocks even a force-exposed tool. Because the gate fires before the body, `confirm`/`validate_id` are never reached in readonly mode, so the existing readonly-defense test (§5.3) passes for these tools automatically.
3. **NI graceful-degradation gate.** `server_lifespan` calls `server.disable(tags={"network_integration"})` (`server.py:195`) when NI `validate_connection` fails.

`mcp.disable(tags=…)` disables a tool carrying **any** listed tag, so `{"write", "network_integration"}` is hidden when **either** write-mode is off **or** the NI backend failed validation — exactly the intended union. **No `server.py`/`config.py` edits required**; `config.network_integration_enabled` does not gate on writes — write-mode is purely the tag/handler gates. The NI client is already built in the lifespan (reusing the Network key).

**Per-tool `confirm` guard** is an additional, tool-local affordance layered on top of the three gates for the 6 destructive ops (delete ACL/DNS/zone/voucher(s)/TML). There is no shared confirm helper today (`_common.py` has only `validate_id`); introduce the inline pattern `if not confirm: raise UniFiBadRequestError(...)` — keep it consistent across the delete tools.

---

## 5. Tests

The repo uses **respx** for client/HTTP tests and **AsyncMock** for tool-layer tests. **No VCR/cassettes in unit tests**; cassettes belong only to `tests/integration/` against live hardware.

### 5.1 Client tests — `tests/unit/clients/test_network_integration.py`
Reuse `BASE_URL`/`PREFIX`/`SITE_UUID`, `_make_client`, the `client` fixture pre-setting `_resolved_site`. For each write method add a respx route (mirror legacy write-client tests `tests/unit/tools/test_network_firewall.py:80-108`):
- `respx.post/put/patch/delete` on `f"{PREFIX}sites/{SITE_UUID}/<suffix>"`; assert `route.called`, assert the realized URL injects the site UUID, assert body bytes (`b"\"name\"" in route.calls[0].request.content`), assert query params for `reorder_firewall_policies` (`sourceFirewallZoneId`/`destinationFirewallZoneId`) and `delete_vouchers` (`filter` — note the **client arg is `voucher_filter`** but the realized query key is `filter`).
- **Edge:** assert DELETE returns `{}` on a 204/empty body; assert PATCH route is hit exactly once (non-retried).

### 5.2 Tool-layer tests — `tests/unit/tools/test_network_integration_tools.py`
Use `_Lifespan`/`_config`/`_ctx`/`server`/`_call` helpers. **Writes require readwrite** — set `unifi_mode=UniFiMode.READWRITE` in a write-specific `_config` variant (the default helper is READONLY; the `@tool_handler(write=True)` gate otherwise raises). Per group add:
- **Happy path:** AsyncMock client returns a dict; assert the client method is awaited with the right args and the response is returned (redacted).
- **`validate_id` rejection** (mirror `TestValidateIdRejection`) for every id-bearing write (`../escape` → `ToolError`).
- **`reject_dangerous_keys` rejection** for the raw-`data` tools (ACL/DNS/TML) — feed a denylisted key (e.g. `roles`) and assert `ToolError` (denylist contract: `tests/unit/tools/test_dangerous_key_denylist.py`).
- **Error funnel** 404 → `ToolError` (mirror `TestErrorFunnel`).
- **`confirm` guard:** each delete tool with `confirm=False` raises and does NOT call the client; with `confirm=True` it calls.
- **Bulk-delete blank-filter guard:** `unifi_network_delete_vouchers(voucher_filter="  ", confirm=True)` raises; client not called.

### 5.3 Hard-coded count assertions to update (will fail until fixed)
- `tests/unit/tools/test_network_integration_tools.py:65` — `assert len(ni) == 28`. This is inside `class TestAllTaggedNetworkIntegration.test_every_tool_tagged_and_not_write`, which currently asserts **every** NI tool is read-only (`:68` `assert "write" not in set(t.tags)` inside a per-tool loop). Once writes are added this **fails on the first write tool**, so the test must be **structurally restructured, not just count-bumped**:
  - Replace the single `len(ni) == 28` + per-tool `"write" not in tags` loop with two scoped checks: (a) NI **read** tools (`"network_integration" in tags and "write" not in tags`) count == 28 and each is `unifi_network_*`; (b) NI **write** tools (`"network_integration" in tags and "write" in tags`) count == N (N=18 at 100%) and each is `unifi_network_*`. Remove/scope the blanket `"write" not in tags` assertion to the read subset only.
- `tests/unit/test_tool_inventory.py` — asserts live surface vs `_inventory.py` constants (passes once §6.1 is updated) and asserts the doc count strings (see §6.3 for the **exact** asserted literals).
- `tests/unit/test_schema_matrix.py:53-58` — byte-for-byte vs the generated matrix; fails until regenerated (§6.5).
- `tests/unit/tools/test_writes_enabled_defense.py` auto-discovers all `{"write"}` tools and parametrizes the readonly-gate test; the new NI writes are picked up automatically and MUST pass. Required-arg placeholders are auto-filled (object→`{}`); the gate fires before body validation. The `_WRITE_TOOLS_FLOOR=40` only needs raising if you want a tighter floor (optional).

### 5.4 Live-integration SAFETY protocol (per CLAUDE.md `## Live Integration Tests`)
Live writes target real hardware and have **bricked a UCG Ultra** (#271). Enforce:
- **One `TestClass` per pytest invocation**, never the whole file in one run when `LIVE_TEST_WRITES=1`/`LIVE_TEST_DESTRUCTIVE=1`.
- **Health check between classes:** `curl -skf -o /dev/null -w '%{http_code}\n' "https://${UNIFI_NETWORK_HOST}/proxy/network/integration/v1/sites"` must return 200; **~30s cooldown** between classes; stop the sweep and triage if a class hangs or the health check fails.
- New destructive NI writes (delete zone/DNS/ACL/voucher(s)/TML) must run create→delete **roundtrips** that capture-then-restore, never delete pre-existing operator resources. Gate destructive cases behind `LIVE_TEST_WRITES`/`LIVE_TEST_DESTRUCTIVE` and `pytest.skip` when unset.
- Add live cases as **separate `TestClass`es** (e.g. `TestNiAclWriteRoundtrips`, `TestNiVoucherDestructive`) in `tests/integration/test_all_tools_live.py`, one class per invocation. Voucher bulk-delete: only ever delete vouchers created by the test (filter scoped to the test's note), never an operator filter.
- Protect-style device allowlists do not apply (these are Network resources), but the same capture/restore discipline does. See `docs/agents/live-test-safety.md`.

---

## 6. Bookkeeping (all keyed off the canonical inventory; numbers below assume the FULL +18 at 100% — scale to +13 if shipping only Phases 1–4)

### 6.1 `src/unifi_mcp/_inventory.py` — THE source of truth
Only the network **write** number changes (NI reads already counted as network reads; NI writes go in the write slot):
- `EXPECTED_NAMESPACE_SPLITS["network"]` `{"read": 54, "write": 39}` → **`"write": 57`** (39 + 18). At the +13 milestone use `52`.
- Everything else derives automatically: network total 93→**111**, `EXPECTED_WRITE_TOOLS` 47→**65**, `TOTAL_TOOLS` 147→**165**, `EXPECTED_READ_TOOLS` stays **100**.

### 6.2 `README.md`
- "147 tools" → "**165 tools**".
- "147 MCP tools** covering UniFi Network (93)…" → "**165 MCP tools** covering UniFi Network (111)…".
- "47 write tools" → "**65 write tools**".

### 6.3 `CLAUDE.md` — EXACT asserted literals (free-text substring match across the whole file)
`tests/unit/test_tool_inventory.py` matches these as **substrings anywhere in the file**, so the format strings are load-bearing. Reproduce them verbatim:

- `test_claude_md_counts` (`:97-100`) requires the file to contain, anywhere: `65 write tools`, `(111 total)` (network total), and `(45 total` (protect total, unchanged).
- `test_claude_md_per_api_splits` (`:102-107`) requires the **exact** form `{read} read + {write} write tools ({total} total` per namespace — for network that is the literal `54 read + 57 write tools (111 total`. A missed/misspelled split string is **fatal**; the generic format is `N read + M write tools (T total`.

Concrete edits:
- `CLAUDE.md:40` `# exposes the 47 write tools` → `# exposes the 65 write tools`. (Stray remaining `47 write tools` elsewhere is harmless to the assertion — but find/replace all for cleanliness.)
- `CLAUDE.md:85` `Network 54 read + 39 write tools (93 total)` → `Network 54 read + 57 write tools (111 total)`. **This exact substring `54 read + 57 write tools (111 total` is the load-bearing one.**
- The "47 write tools stay readonly-gated" narrative → `65 write tools`.
- Architecture-block NI tree comment (NI subdir) "28 read" → "28 read + 18 write".
- The §3b-related narrative describing the NI 28-read split should note the read/write split.

> Confirm after editing: `grep -F '54 read + 57 write tools (111 total' CLAUDE.md` and `grep -F '65 write tools' CLAUDE.md` and `grep -F '(111 total)' CLAUDE.md` and `grep -F '(45 total' CLAUDE.md` all return a hit.

### 6.4 `src/unifi_mcp/tools/network_integration/__init__.py`
Docstring currently says "28 read-only tools … none is tagged `{"write"}`" — **revise** to "28 read tools + 18 write tools; write tools tagged `{"write", "network_integration"}`."

### 6.5 `docs/tool-schema-matrix.md` — MACHINE-GENERATED, do NOT hand-edit
Regenerate: `uv run python scripts/gen_schema_matrix.py`. Header counts ("147 MCP tools** (100 read, 47 write)", the Counts table "Network API | 54 | 39 | 93", "**All** | **100** | **47** | **147**") are part of the rendered output and update on regen. `tests/unit/test_schema_matrix.py` fails byte-for-byte until regenerated.

### 6.6 `docs/api-coverage-matrix.md` — hand-maintained (not count-asserted)
- Header "147 MCP tools" / "Network 93" → 165 / 111.
- §3b intro "28 read tools … tagged `{"network_integration"}`" → read/write split.
- Flip the 18 **Gap** rows to **Covered** with the new tool name (e.g. `POST …/acl-rules` → `unifi_network_create_acl_rule`).
- Update the §1 summary coverage percentages to ≥90% / 100%.

---

## 7. Verification, rollout & risk

### Commands (run per phase before each PR)
```bash
uv sync --extra dev
uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/
uv run ty check src/unifi_mcp/
uv run pytest tests/unit/ -v -m "not integration"
uv run python scripts/gen_schema_matrix.py     # regenerate after tool count changes
uv run bandit -r src/unifi_mcp/ -c pyproject.toml
uv run pre-commit run --all-files
# self-audit against canonical standards
cd ~/Desktop/Projects/consistency-check && uv run consistency-check audit --repo unifi-mcp
```

> **Lint gate note:** the `voucher_filter` rename (Phase 0/Phase 4) is what keeps `ruff check` green — A002 (builtin-argument-shadowing) is enabled and **not excused** for `src/unifi_mcp/clients/` or `src/unifi_mcp/tools/`. Naming the param `filter` would fail the lint gate and the zero-warnings policy.

### PR splitting — one PR per resource group (6 PRs)
Recommended order (each PR includes its client methods, tools, unit tests, and a partial bookkeeping bump):
1. **ACL** (+4 → 58) 2. **DNS** (+3 → 61) 3. **FW-zones** (+3 → 64) 4. **Vouchers** (+3 → 67, **crosses 90%**) 5. **TML** (+3 → 70) 6. **FW-policies** (+2 → 72, 100%).

Because `_inventory.py` and the doc count-strings are asserted, **each PR must bump the counts for the tools it adds** (e.g. PR-1 sets network write to 43) and regenerate `tool-schema-matrix.md`, so every PR lands green. Per-PR bumps are required — gating all count changes to a final PR makes intermediate PRs fail the inventory test. Per the workspace PR-session rule: author and merge in **separate sessions**; do not `gh pr merge` in the session that ran `gh pr create`.

### Risks / call-outs
- **Uncertain (verify against live/spec before shipping — do NOT invent):**
  - ACL filter / device-filter inner shapes (Phase 1).
  - DNS per-type fields beyond the confirmed list (Phase 2).
  - **Firewall-policy reorder (Phase 6): the nested request body `{"orderedFirewallPolicyIds": {"beforeSystemDefined": [...], "afterSystemDefined": [...]}}` AND the query-param names `sourceFirewallZoneId`/`destinationFirewallZoneId`** are unconfirmed against `10.4.57.json` — gate Phase 6 on confirming both.
  - TML item discriminators, esp. v6 having no range variant (Phase 5).
  - Voucher `filter` grammar — opaque string, non-blank only (Phase 4).
  - Firewall-policy PATCH being `loggingEnabled`-only (Phase 6).

  Raw-`data` tools forward verbatim, so the controller is the validator — surface its 4xx via the existing error funnel rather than pre-validating.
- **Full-replace footguns:** ACL reorder, firewall-policy reorder, firewall-zone PUT, DNS PUT, TML PUT all replace rather than merge — docstrings must say "send the complete object/id set." Reorders can silently drop a rule/policy from enforcement order.
- **Destructive ops** (6 deletes) carry `destructiveHint=True` + a `confirm=True` guard on top of the three write gates; bulk voucher delete additionally rejects a blank filter.
- **PATCH non-idempotency:** `base.patch` is never retried (correct) — a lost response surfaces, never silently re-sends.
- **Live hardware:** follow §5.4 strictly (one class/invocation, health check, 30s cooldown) — #271 bricked a UCG Ultra under a destructive sweep.
- The NI client docstrings (module + class + `__init__.py`) still say "read-only"; flipping them is part of the change, not optional.
