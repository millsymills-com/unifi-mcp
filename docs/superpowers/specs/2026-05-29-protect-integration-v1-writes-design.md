# Protect write support via integration v1 PATCH

**Date:** 2026-05-29
**Status:** Approved design
**Branch:** `feat/protect-integration-v1-writes`

## Problem

All four Protect write tools are pinned `xfail` in the live suite: they `PUT`
to `/proxy/protect/integration/v1/...` and get `404 Entity 'endpoint' not
found` (#237, #139). The repo concluded Protect writes are unsupported on the
integration API and treated the legacy cookie-session API as the only write
path.

That conclusion was wrong. The official Protect integration v1 API **does**
support writes — via **PATCH**, authenticated with the **same `X-API-Key`** the
server already sends. The 404s are a verb mismatch: `ProtectClient` calls
`self.put(...)`, and `BaseUniFiClient` exposes no `patch()` method, so writes
were never issued as PATCH.

Confirmed against the official developer portal endpoint pages:

- `PATCH /v1/cameras/{id}` — developer.ui.com/protect/v5.3.38/patch-v1camerasid
- `PATCH /v1/chimes/{id}` — developer.ui.com/protect/v6.2.87/patch-v1chimesid
- `PATCH /v1/viewers/{id}` — developer.ui.com/protect/v6.2.87/patch-v1viewersid
- `PATCH /v1/lights/{id}`, `PATCH /v1/sensors/{id}` — same family

One genuine gap: **the NVR resource is GET-only** on integration v1 (no
`PATCH /v1/nvrs/{id}`).

## Goal

Unlock the Protect write surface through the supported, already-authenticated
integration v1 API. No new credentials, no cookie/CSRF session, no dual-auth
refactor.

Deliver working writes for: camera settings (incl. recording mode and smart
detection), lights, chimes, sensors, and viewers. Remove the NVR write tool as
unsupported upstream.

## Non-goals

- No cookie-session / `/api/auth/login` / CSRF transport. Explicitly rejected:
  the integration API covers every in-scope write, so the legacy path would add
  username/password credentials and a parallel auth stack for no remaining
  benefit (the only thing it would add — NVR writes — is being dropped).
- No move of Protect **reads** off integration v1; they already work.
- No POST action endpoints (camera PTZ, chime play-test). Out of scope for this
  round; can be added later on the same transport.
- No Network or Site Manager changes.

## Approach

### 1. `patch()` on the base client

Add `BaseUniFiClient.patch(path, **kwargs)`, mirroring the existing `put()`:

```python
async def patch(self, path: str, **kwargs: Any) -> Any:
    """HTTP PATCH, returns parsed JSON."""
    response = await self._request("PATCH", path, **kwargs)
    if response.status_code == 204 or not response.content:
        return {}
    return self._parse_json(response)
```

`_request` already classifies PATCH as a non-idempotent method: it is excluded
from the GET/HEAD transient-retry set, so a PATCH whose response is lost is not
silently re-sent. No changes to retry, error mapping, redaction, or the 429
fence are needed — PATCH inherits all of it.

### 2. Camera writes: PUT → PATCH

`ProtectClient.update_camera`, `set_recording_mode`, and `set_smart_detection`
switch from `self.put(...)` to `self.patch(...)`. Paths and bodies are
unchanged pending the verification spike (below); only the verb changes. This
fixes three of the four pinned xfails natively.

### 3. Remove the NVR write tool

Integration v1 has no NVR write. Per "no phantom features / replace, don't
deprecate":

- Delete `ProtectClient.update_nvr` (and its `TODO(#43)` PUT-vs-PUT note).
- Delete the `unifi_protect_update_nvr` tool.
- Replace its strict-`xfail` live test with the removal (the tool no longer
  exists, so there is nothing to xfail). `get_nvr` read support stays.

This drops the Protect write count's NVR entry; the remaining three camera
writes plus the new accessory writes are the delivered surface.

### 4. Accessory write client methods + tools

New `ProtectClient` methods, each a thin PATCH to its resource:

| Method | Endpoint | Body (subset, pending spike) |
|---|---|---|
| `update_light(id, data)` | `PATCH lights/{id}` | `lightDeviceSettings`, `lightModeSettings` |
| `update_chime(id, data)` | `PATCH chimes/{id}` | `volume`, `ringSettings` |
| `update_sensor(id, data)` | `PATCH sensors/{id}` | `mountType`, sensitivity/alarm toggles |
| `update_viewer(id, data)` | `PATCH viewers/{id}` | `liveview` (liveview id) |

New tools (tagged `{"write"}`, `readOnlyHint=False`, `unifi_` prefix per
PROTO-002):

- `unifi_protect_update_light` — generic light config patch
- `unifi_protect_set_light_mode` — convenience wrapper for on/off + mode
- `unifi_protect_update_chime` — volume / ringtone / repeat
- `unifi_protect_update_sensor` — sensitivity / mount / alarm toggles
- `unifi_protect_set_viewer_liveview` — assign a liveview to a viewer

Tool argument shapes follow the existing camera write tools (explicit typed
params that the method assembles into the PATCH body, not a raw passthrough
dict), so the agent gets validated, discoverable parameters.

### 5. Verification spike — step 0 of implementation

The official integration v1 schema differs from the reverse-engineered private
API (e.g. uiprotect discussion #442 reports the official chime `ringSettings`
returns empty where the private API returns a populated object). Before writing
any PATCH body, confirm exact field names **read-only** against live hardware:

For each device type present on the test controller, `GET /v1/{type}/{id}`,
record the settings sub-objects and field names, and pin the PATCH body shape
to what the controller actually returns. Only then implement the write methods.

If a device type is absent on the hardware, its write method is still
implemented to the documented schema but its live roundtrip test is skipped
(not xfailed) with a clear "no <type> on test controller" reason.

## Mode gating & degradation

Unchanged from today's model. Write tools are tagged `{"write"}`, disabled in
readonly mode via `mcp.disable(tags={"write"})`, and re-checked against
`config.writes_enabled` at runtime. No new config, no new credentials, so there
is no new degradation path: if Protect is reachable with its API key, the
writes register exactly like the read tools already do.

## Error handling

PATCH flows through the same `_raise_for_status` mapping as every other verb. A
404 on a write now means the resource id is wrong (not a verb mismatch); a 400
surfaces the controller's validation message via `_extract_error_body`. No
new error types.

## Testing

**Unit (respx):**
- `patch()` returns parsed JSON; 204/empty body → `{}`.
- Each camera write issues `PATCH` (not `PUT`) to the expected path with the
  expected body.
- Each new accessory write issues the expected PATCH path + body.
- A PATCH that times out is **not** retried (non-idempotent), matching `put()`.

**Integration (live, `@pytest.mark.integration`):**
- Flip the three camera-write strict-xfails (`set_recording_mode`,
  `set_smart_detection`, `update_camera`) to real assertions.
- Remove the `update_nvr` xfail along with the tool.
- Add accessory write roundtrips (light, chime, sensor, viewer), each:
  read original settings → PATCH a change → assert applied → PATCH back to the
  original value (restore teardown).
- All write roundtrips gated behind `UNIFI_MODE=readwrite` + `LIVE_TEST_WRITES=1`.
- Per #271, accessory writes live in their own `TestClass` so the suite is run
  one class per invocation with a controller health check between classes.

**Docs:**
- Update `CLAUDE.md` Protect tool counts (9 read + writes; NVR write removed,
  accessory writes added) and the architecture tree.
- `CHANGELOG.md` entry: Protect writes now functional via integration v1 PATCH;
  `unifi_protect_update_nvr` removed (unsupported upstream).

## Risks

- **Schema drift across Protect versions.** The verification spike pins bodies
  to the live controller; tests catch regressions if a field is renamed. The
  spike result should note the controller's Protect version.
- **Per-version feature availability.** Some accessory settings depend on the
  Protect version (the portal flags per-feature minimum versions). Writes to a
  field the controller doesn't support return 400 with a controller message,
  surfaced cleanly — not a silent failure.
- **NVR-write removal is a (pre-1.0) breaking change.** Acceptable at 0.3.0
  alpha; recorded in CHANGELOG. The tool never worked, so no real capability is
  lost.
