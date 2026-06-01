# Protect writes via integration v1 PATCH — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Protect write tools work by issuing PATCH (not PUT) against the integration v1 API with the existing X-API-Key, add light/chime/sensor/viewer writes, and remove the unsupported NVR write.

**Architecture:** Add a `patch()` verb to `BaseUniFiClient` (reusing all existing retry/error/redaction machinery), switch the three camera writes from PUT to PATCH, delete `update_nvr` (integration v1 is GET-only for NVR), and add four accessory write client methods + tools following the established `build_named_arg_body` allowlist pattern (#202). A read-only schema spike against live hardware pins the PATCH body field names before the live write tests run.

**Tech Stack:** Python 3.13, httpx async, FastMCP, respx (unit HTTP mocking), pytest-asyncio, `uv` for everything.

**Design:** `docs/superpowers/specs/2026-05-29-protect-integration-v1-writes-design.md`

**Branch:** `feat/protect-integration-v1-writes` (already created)

**Conventions reminder:**
- Lint/format: `uv run ruff check src/ tests/` and `uv run ruff format src/ tests/`
- Types: `uv run ty check src/unifi_mcp/`
- Unit tests: `uv run pytest tests/unit/ -v`
- Line length 120; tool names `unifi_{api}_{verb}_{entity}`; write tools tagged `{"write", "protect"}` with `annotations={"readOnlyHint": False, "destructiveHint": False}`.

---

### Task 1: Add `patch()` to the base client

**Files:**
- Modify: `src/unifi_mcp/clients/base.py` (add method next to `put()`)
- Test: `tests/unit/clients/test_base.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/clients/test_base.py` (follow the existing respx style in that file — reuse whatever concrete `BaseUniFiClient` subclass/fixture the other tests use; the snippet below assumes a `make_client()` helper returning a client with `_path_prefix=""` and base_url `https://ctrl`):

```python
@pytest.mark.asyncio
@respx.mock
async def test_patch_returns_parsed_json():
    client = make_client()
    route = respx.patch("https://ctrl/widgets/abc").mock(
        return_value=httpx.Response(200, json={"id": "abc", "name": "new"})
    )
    result = await client.patch("widgets/abc", json={"name": "new"})
    assert route.called
    assert route.calls.last.request.method == "PATCH"
    assert result == {"id": "abc", "name": "new"}
    await client.close()


@pytest.mark.asyncio
@respx.mock
async def test_patch_empty_body_returns_empty_dict():
    client = make_client()
    respx.patch("https://ctrl/widgets/abc").mock(return_value=httpx.Response(204))
    result = await client.patch("widgets/abc", json={"name": "new"})
    assert result == {}
    await client.close()


@pytest.mark.asyncio
@respx.mock
async def test_patch_timeout_not_retried():
    client = make_client()
    route = respx.patch("https://ctrl/widgets/abc").mock(side_effect=httpx.TimeoutException("boom"))
    with pytest.raises(UniFiTimeoutError):
        await client.patch("widgets/abc", json={"name": "new"})
    assert route.call_count == 1  # non-idempotent: no transient retry
    await client.close()
```

If `test_base.py` has no `make_client()` helper, mirror the construction used by the existing `test_put_*` tests in that file and import `UniFiTimeoutError` from `unifi_mcp.errors` and `httpx`/`respx`/`pytest` as the file already does.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/clients/test_base.py -k patch -v`
Expected: FAIL — `AttributeError: 'BaseUniFiClient' object has no attribute 'patch'`

- [ ] **Step 3: Add the `patch()` method**

In `src/unifi_mcp/clients/base.py`, directly after the `put()` method, add:

```python
    async def patch(self, path: str, **kwargs: Any) -> Any:
        """HTTP PATCH, returns parsed JSON.

        PATCH is non-idempotent, so ``_request`` does not retry it on a lost
        response (only GET/HEAD are retried on timeout) — a partially applied
        write is never silently re-sent.
        """
        response = await self._request("PATCH", path, **kwargs)
        if response.status_code == 204 or not response.content:
            return {}
        return self._parse_json(response)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/clients/test_base.py -k patch -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/unifi_mcp/clients/base.py tests/unit/clients/test_base.py
git commit -m "feat(clients): add PATCH verb to base client"
```

---

### Task 2: Switch camera writes from PUT to PATCH

**Files:**
- Modify: `src/unifi_mcp/clients/protect.py` (3 methods: `update_camera`, `set_recording_mode`, `set_smart_detection`)
- Test: `tests/unit/clients/test_protect.py`

- [ ] **Step 1: Write/adjust the failing test**

In `tests/unit/clients/test_protect.py`, add (or modify the existing camera-write tests so they assert the PATCH method). Mirror the file's existing respx setup for `ProtectClient` (base url + `/proxy/protect/integration/v1/` prefix):

```python
@pytest.mark.asyncio
@respx.mock
async def test_set_recording_mode_uses_patch(protect_client):
    route = respx.patch(
        "https://protect.local/proxy/protect/integration/v1/cameras/cam1"
    ).mock(return_value=httpx.Response(200, json={"id": "cam1"}))
    await protect_client.set_recording_mode("cam1", "always")
    assert route.called
    req = route.calls.last.request
    assert req.method == "PATCH"
    assert json.loads(req.content) == {"recordingSettings": {"mode": "always"}}


@pytest.mark.asyncio
@respx.mock
async def test_update_camera_uses_patch(protect_client):
    route = respx.patch(
        "https://protect.local/proxy/protect/integration/v1/cameras/cam1"
    ).mock(return_value=httpx.Response(200, json={"id": "cam1"}))
    await protect_client.update_camera("cam1", {"name": "Front"})
    assert route.calls.last.request.method == "PATCH"


@pytest.mark.asyncio
@respx.mock
async def test_set_smart_detection_uses_patch(protect_client):
    route = respx.patch(
        "https://protect.local/proxy/protect/integration/v1/cameras/cam1"
    ).mock(return_value=httpx.Response(200, json={"id": "cam1"}))
    await protect_client.set_smart_detection("cam1", ["person"])
    assert route.calls.last.request.method == "PATCH"
    assert json.loads(route.calls.last.request.content) == {
        "smartDetectSettings": {"objectTypes": ["person"]}
    }
```

Use whatever the file's existing `protect_client` fixture host is (the snippet assumes `protect.local`); match it. Any existing camera-write tests that assert `respx.put(...)` must be updated to `respx.patch(...)`.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/clients/test_protect.py -k "patch" -v`
Expected: FAIL — routes not called because the client still issues PUT.

- [ ] **Step 3: Switch the three methods to PATCH**

In `src/unifi_mcp/clients/protect.py`, in `update_camera`, `set_recording_mode`, and `set_smart_detection`, change each `await self.put(...)` to `await self.patch(...)`. No path or body changes. Example for `update_camera`:

```python
    async def update_camera(self, camera_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update camera settings."""
        result: dict[str, Any] = await self.patch(f"cameras/{self._segment(camera_id)}", json=data)
        return result
```

Apply the same `put` → `patch` change in `set_recording_mode` and `set_smart_detection`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/clients/test_protect.py -v`
Expected: PASS (all camera-write tests now assert PATCH)

- [ ] **Step 5: Remove the stale "endpoint missing" notes**

The `Note:` paragraphs in `unifi_protect_update_camera` and `unifi_protect_set_smart_detection` docstrings (`src/unifi_mcp/tools/protect/cameras.py`) claim the endpoint 404s on integration v1. That is no longer true. Delete both `Note:` blocks (the paragraph starting "The underlying endpoint is missing from Protect integration v1 …").

- [ ] **Step 6: Run tool unit tests + lint**

Run: `uv run pytest tests/unit/tools/test_protect_cameras.py -v && uv run ruff check src/ tests/`
Expected: PASS, no lint errors.

- [ ] **Step 7: Commit**

```bash
git add src/unifi_mcp/clients/protect.py src/unifi_mcp/tools/protect/cameras.py tests/unit/clients/test_protect.py
git commit -m "fix(protect): issue camera writes as PATCH on integration v1 (#139, #237)"
```

---

### Task 3: Remove the unsupported NVR write

Integration v1 exposes no `PATCH /v1/nvrs/{id}`; NVR is GET-only. Remove the write tool and its client method entirely (replace, don't deprecate). `get_nvr` read support stays.

**Files:**
- Modify: `src/unifi_mcp/tools/protect/nvr.py` (delete the write tool, the allowlist, now-unused imports)
- Modify: `src/unifi_mcp/clients/protect.py` (delete `update_nvr`)
- Modify: `tests/unit/tools/test_protect_nvr.py`, `tests/unit/tools/test_protect_named_args.py` (delete update_nvr tests)
- Modify: `tests/unit/clients/test_protect.py` (delete any `update_nvr` client test)

- [ ] **Step 1: Find every reference**

Run: `rg -n "update_nvr" src/ tests/`
Expected: references in `clients/protect.py`, `tools/protect/nvr.py`, the three unit test files above, and `tests/integration/test_all_tools_live.py` (handled in Task 9). Note each.

- [ ] **Step 2: Delete the tool**

In `src/unifi_mcp/tools/protect/nvr.py`:
- Delete the entire `unifi_protect_update_nvr` function.
- Delete the `_NVR_FIELD_PATHS` dict.
- Reduce imports to only what `unifi_protect_get_nvr` needs:

```python
from __future__ import annotations

from typing import Any

from fastmcp import Context, FastMCP

from unifi_mcp.errors import handle_client_error
from unifi_mcp.tools._common import get_server_context, redact_secrets
```

- Update the module docstring: `"""Protect NVR tools (1 read)."""`

- [ ] **Step 3: Delete the client method**

In `src/unifi_mcp/clients/protect.py`, delete the entire `update_nvr` method (including its `TODO(#43)` comment).

- [ ] **Step 4: Delete the unit tests**

Delete every test referencing `unifi_protect_update_nvr` / `update_nvr` in `tests/unit/tools/test_protect_nvr.py`, `tests/unit/tools/test_protect_named_args.py`, and `tests/unit/clients/test_protect.py`. Keep the `get_nvr` read tests. If `test_protect_nvr.py` is left with no tests, delete the file.

- [ ] **Step 5: Run the suite + verify no dangling references**

Run: `rg -n "update_nvr" src/ tests/unit/ ; uv run pytest tests/unit/ -q`
Expected: no matches under `src/` or `tests/unit/`; all unit tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/unifi_mcp/tools/protect/nvr.py src/unifi_mcp/clients/protect.py tests/unit/
git commit -m "feat(protect)!: remove update_nvr — unsupported on integration v1"
```

---

### Task 4: Schema spike — pin accessory PATCH field names

The official integration v1 settings schema can differ from the reverse-engineered private API (uiprotect discussion #442 reports the official chime `ringSettings` returns empty). Confirm the real field names **read-only** before writing any PATCH body. This task changes no source code; it produces a notes file the next tasks consume.

**Files:**
- Create: `docs/superpowers/specs/2026-05-29-protect-v1-write-schema-notes.md`

- [ ] **Step 1: If live hardware is available, capture real settings shapes**

With a configured `.env` (Protect API key, `UNIFI_MODE` can stay readonly — these are reads), run a one-off probe per device type. Example for lights (repeat for chimes/sensors/viewers):

```bash
uv run python - <<'PY'
import anyio, json
from unifi_mcp.config import get_config
from unifi_mcp.clients.protect import ProtectClient
cfg = get_config()
async def main():
    c = ProtectClient(cfg.protect_base_url, cfg.unifi_protect_api.get_secret_value(),
                      verify_ssl=cfg.unifi_protect_verify_ssl,
                      cert_fingerprint=cfg.unifi_protect_cert_fingerprint)
    for kind in ("lights", "chimes", "sensors", "viewers"):
        try:
            items = await c.get(kind)
            print(kind, json.dumps(items[:1], indent=2)[:2000])
        except Exception as e:
            print(kind, "ERR", e)
    await c.close()
anyio.run(main)
PY
```

Record, for each device type, the exact settings sub-object names and the scalar field names (e.g. `lightDeviceSettings.ledLevel`, `lightModeSettings.mode`, `volume`, `mountType`, `liveview`). Note the controller's Protect version.

- [ ] **Step 2: If no hardware, use the documented defaults**

If no controller is reachable, record the documented official-API defaults below and mark them "unconfirmed — live test will validate." These are the field paths Tasks 5–8 use:

- Light: `lightDeviceSettings.ledLevel` (int 1–6), `lightDeviceSettings.pirDuration` (ms), `lightDeviceSettings.pirSensitivity` (0–100), `lightModeSettings.mode` (`"off"|"motion"|"always"`)
- Chime: `volume` (int 0–100), `repeatTimes` (int)
- Sensor: `mountType` (str), `motionSettings.isEnabled` (bool), `lightSettings.isEnabled` (bool)
- Viewer: `liveview` (str — a liveview id)

- [ ] **Step 3: Write the notes file**

Create `docs/superpowers/specs/2026-05-29-protect-v1-write-schema-notes.md` with a section per device type listing the confirmed (or documented-default) field paths and the Protect version probed. Tasks 5–8 reference this file; if Step 1 found names differing from Step 2's defaults, **use the Step 1 names** in those tasks.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-05-29-protect-v1-write-schema-notes.md
git commit -m "docs: pin Protect v1 accessory write schema field names"
```

---

### Task 5: Light write client method + tools

**Files:**
- Modify: `src/unifi_mcp/clients/protect.py` (add `update_light`)
- Modify: `src/unifi_mcp/tools/protect/devices.py` (add two write tools + allowlist)
- Test: `tests/unit/clients/test_protect.py`, `tests/unit/tools/test_protect_devices.py`

> Field paths below match Task 4 Step 2 defaults. If Task 4 Step 1 confirmed different names, substitute them in the `_LIGHT_FIELD_PATHS` dict and the test bodies.

- [ ] **Step 1: Write the failing client test**

Add to `tests/unit/clients/test_protect.py`:

```python
@pytest.mark.asyncio
@respx.mock
async def test_update_light_uses_patch(protect_client):
    route = respx.patch(
        "https://protect.local/proxy/protect/integration/v1/lights/l1"
    ).mock(return_value=httpx.Response(200, json={"id": "l1"}))
    await protect_client.update_light("l1", {"lightModeSettings": {"mode": "motion"}})
    req = route.calls.last.request
    assert req.method == "PATCH"
    assert json.loads(req.content) == {"lightModeSettings": {"mode": "motion"}}
```

- [ ] **Step 2: Run it — expect failure**

Run: `uv run pytest tests/unit/clients/test_protect.py -k update_light -v`
Expected: FAIL — `ProtectClient` has no `update_light`.

- [ ] **Step 3: Add the client method**

In `src/unifi_mcp/clients/protect.py`, in the write-methods section:

```python
    async def update_light(self, light_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update light settings."""
        result: dict[str, Any] = await self.patch(f"lights/{self._segment(light_id)}", json=data)
        return result
```

- [ ] **Step 4: Run client test — expect pass**

Run: `uv run pytest tests/unit/clients/test_protect.py -k update_light -v`
Expected: PASS

- [ ] **Step 5: Write the failing tool test**

Add to `tests/unit/tools/test_protect_devices.py` (follow the file's existing pattern for invoking a registered tool against a fake context; mirror how `test_protect_cameras.py` exercises `unifi_protect_set_recording_mode` — same `get_server_context`/fake-client harness). Two tools: a generic `update_light` and a `set_light_mode` convenience wrapper.

```python
@pytest.mark.asyncio
async def test_update_light_builds_body_and_calls_client(readwrite_protect_tool_ctx):
    ctx, fake_client = readwrite_protect_tool_ctx
    await call_tool("unifi_protect_update_light", ctx, light_id="l1", led_level=6, mode="motion")
    fake_client.update_light.assert_awaited_once_with(
        "l1", {"lightDeviceSettings": {"ledLevel": 6}, "lightModeSettings": {"mode": "motion"}}
    )


@pytest.mark.asyncio
async def test_set_light_mode_builds_mode_body(readwrite_protect_tool_ctx):
    ctx, fake_client = readwrite_protect_tool_ctx
    await call_tool("unifi_protect_set_light_mode", ctx, light_id="l1", mode="always")
    fake_client.update_light.assert_awaited_once_with("l1", {"lightModeSettings": {"mode": "always"}})


@pytest.mark.asyncio
async def test_update_light_readonly_rejected(readonly_protect_tool_ctx):
    ctx, _ = readonly_protect_tool_ctx
    with pytest.raises(UniFiReadOnlyError):
        await call_tool("unifi_protect_update_light", ctx, light_id="l1", mode="motion")
```

Replace `readwrite_protect_tool_ctx` / `readonly_protect_tool_ctx` / `call_tool` with the actual fixtures and invocation helper used elsewhere in `tests/unit/tools/`. If none exists, build the fake context the same way `test_protect_cameras.py` does (a `ServerContext` with `clients={"protect": AsyncMock()}` and a `config` whose `writes_enabled` is True/False).

- [ ] **Step 6: Run tool test — expect failure**

Run: `uv run pytest tests/unit/tools/test_protect_devices.py -k light -v`
Expected: FAIL — tools not registered.

- [ ] **Step 7: Add the tools + allowlist**

In `src/unifi_mcp/tools/protect/devices.py`, add imports and the allowlist near the top:

```python
from unifi_mcp.errors import UniFiReadOnlyError, handle_client_error
from unifi_mcp.tools._common import (
    JsonObject,
    build_named_arg_body,
    get_server_context,
    redact_secrets,
    reject_dangerous_keys,
    validate_id,
)

_LIGHT_FIELD_PATHS: dict[str, tuple[str, ...]] = {
    "led_level": ("lightDeviceSettings", "ledLevel"),
    "pir_duration": ("lightDeviceSettings", "pirDuration"),
    "pir_sensitivity": ("lightDeviceSettings", "pirSensitivity"),
    "mode": ("lightModeSettings", "mode"),
}
```

Inside `register_protect_device_tools`, add:

```python
    @mcp.tool(tags={"write", "protect"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    async def unifi_protect_update_light(
        ctx: Context,
        light_id: str,
        *,
        led_level: int | None = None,
        pir_duration: int | None = None,
        pir_sensitivity: int | None = None,
        mode: str | None = None,
        data: JsonObject | None = None,
    ) -> dict[str, Any]:
        """Update Protect light settings using named scalar args.

        Pass only the fields to change.

        Args:
            light_id: The light device ID.
            led_level: LED brightness level, 1–6 (``lightDeviceSettings.ledLevel``).
            pir_duration: Motion light on-duration in ms (``lightDeviceSettings.pirDuration``).
            pir_sensitivity: PIR sensitivity 0–100 (``lightDeviceSettings.pirSensitivity``).
            mode: Light mode — "off", "motion", or "always" (``lightModeSettings.mode``).
            data: DEPRECATED raw settings dict; cannot be combined with named args.

        Returns:
            The upstream API response.
        """
        try:
            validate_id(light_id, field="light_id")
            context = get_server_context(ctx)
            if not context.config.writes_enabled:
                raise UniFiReadOnlyError("Cannot update light in read-only mode")
            body = build_named_arg_body(
                tool_name="unifi_protect_update_light",
                field_paths=_LIGHT_FIELD_PATHS,
                named_values={
                    "led_level": led_level,
                    "pir_duration": pir_duration,
                    "pir_sensitivity": pir_sensitivity,
                    "mode": mode,
                },
                data=data,
            )
            reject_dangerous_keys(body, tool_name="unifi_protect_update_light")
            return await context.clients["protect"].update_light(light_id, body)
        except Exception as e:
            handle_client_error(e)

    @mcp.tool(tags={"write", "protect"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    async def unifi_protect_set_light_mode(ctx: Context, light_id: str, mode: str) -> dict[str, Any]:
        """Set a Protect light's mode.

        Args:
            light_id: The light device ID.
            mode: Light mode — "off", "motion", or "always".

        Returns:
            The upstream API response.
        """
        try:
            validate_id(light_id, field="light_id")
            context = get_server_context(ctx)
            if not context.config.writes_enabled:
                raise UniFiReadOnlyError("Cannot set light mode in read-only mode")
            return await context.clients["protect"].update_light(light_id, {"lightModeSettings": {"mode": mode}})
        except Exception as e:
            handle_client_error(e)
```

Update the module docstring to `"""Protect accessory device tools — chimes, lights, sensors, viewers (4 read + writes)."""`.

- [ ] **Step 8: Run tool tests + client tests — expect pass**

Run: `uv run pytest tests/unit/tools/test_protect_devices.py tests/unit/clients/test_protect.py -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add src/unifi_mcp/clients/protect.py src/unifi_mcp/tools/protect/devices.py tests/unit/
git commit -m "feat(protect): add light write tools via integration v1 PATCH"
```

---

### Task 6: Chime write client method + tool

**Files:**
- Modify: `src/unifi_mcp/clients/protect.py` (add `update_chime`)
- Modify: `src/unifi_mcp/tools/protect/devices.py` (add `unifi_protect_update_chime` + allowlist)
- Test: `tests/unit/clients/test_protect.py`, `tests/unit/tools/test_protect_devices.py`

- [ ] **Step 1: Write failing client test**

```python
@pytest.mark.asyncio
@respx.mock
async def test_update_chime_uses_patch(protect_client):
    route = respx.patch(
        "https://protect.local/proxy/protect/integration/v1/chimes/ch1"
    ).mock(return_value=httpx.Response(200, json={"id": "ch1"}))
    await protect_client.update_chime("ch1", {"volume": 75})
    assert route.calls.last.request.method == "PATCH"
    assert json.loads(route.calls.last.request.content) == {"volume": 75}
```

- [ ] **Step 2: Run — expect fail**

Run: `uv run pytest tests/unit/clients/test_protect.py -k update_chime -v` → FAIL

- [ ] **Step 3: Add client method**

```python
    async def update_chime(self, chime_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update chime settings."""
        result: dict[str, Any] = await self.patch(f"chimes/{self._segment(chime_id)}", json=data)
        return result
```

- [ ] **Step 4: Run — expect pass**

Run: `uv run pytest tests/unit/clients/test_protect.py -k update_chime -v` → PASS

- [ ] **Step 5: Write failing tool test**

```python
@pytest.mark.asyncio
async def test_update_chime_builds_body(readwrite_protect_tool_ctx):
    ctx, fake_client = readwrite_protect_tool_ctx
    await call_tool("unifi_protect_update_chime", ctx, chime_id="ch1", volume=75, repeat_times=2)
    fake_client.update_chime.assert_awaited_once_with("ch1", {"volume": 75, "repeatTimes": 2})
```

- [ ] **Step 6: Run — expect fail**

Run: `uv run pytest tests/unit/tools/test_protect_devices.py -k chime -v` → FAIL

- [ ] **Step 7: Add the allowlist + tool**

Add allowlist near the light one:

```python
_CHIME_FIELD_PATHS: dict[str, tuple[str, ...]] = {
    "volume": ("volume",),
    "repeat_times": ("repeatTimes",),
}
```

Add inside `register_protect_device_tools`:

```python
    @mcp.tool(tags={"write", "protect"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    async def unifi_protect_update_chime(
        ctx: Context,
        chime_id: str,
        *,
        volume: int | None = None,
        repeat_times: int | None = None,
        data: JsonObject | None = None,
    ) -> dict[str, Any]:
        """Update Protect chime settings using named scalar args.

        Args:
            chime_id: The chime device ID.
            volume: Chime volume, 0–100 (``volume``).
            repeat_times: Number of times to repeat the ring (``repeatTimes``).
            data: DEPRECATED raw settings dict; cannot be combined with named args.

        Returns:
            The upstream API response.
        """
        try:
            validate_id(chime_id, field="chime_id")
            context = get_server_context(ctx)
            if not context.config.writes_enabled:
                raise UniFiReadOnlyError("Cannot update chime in read-only mode")
            body = build_named_arg_body(
                tool_name="unifi_protect_update_chime",
                field_paths=_CHIME_FIELD_PATHS,
                named_values={"volume": volume, "repeat_times": repeat_times},
                data=data,
            )
            reject_dangerous_keys(body, tool_name="unifi_protect_update_chime")
            return await context.clients["protect"].update_chime(chime_id, body)
        except Exception as e:
            handle_client_error(e)
```

- [ ] **Step 8: Run — expect pass**

Run: `uv run pytest tests/unit/tools/test_protect_devices.py tests/unit/clients/test_protect.py -k chime -v` → PASS

- [ ] **Step 9: Commit**

```bash
git add src/unifi_mcp/clients/protect.py src/unifi_mcp/tools/protect/devices.py tests/unit/
git commit -m "feat(protect): add chime write tool via integration v1 PATCH"
```

---

### Task 7: Sensor write client method + tool

**Files:**
- Modify: `src/unifi_mcp/clients/protect.py` (add `update_sensor`)
- Modify: `src/unifi_mcp/tools/protect/devices.py` (add `unifi_protect_update_sensor` + allowlist)
- Test: `tests/unit/clients/test_protect.py`, `tests/unit/tools/test_protect_devices.py`

- [ ] **Step 1: Write failing client test**

```python
@pytest.mark.asyncio
@respx.mock
async def test_update_sensor_uses_patch(protect_client):
    route = respx.patch(
        "https://protect.local/proxy/protect/integration/v1/sensors/s1"
    ).mock(return_value=httpx.Response(200, json={"id": "s1"}))
    await protect_client.update_sensor("s1", {"mountType": "door"})
    assert route.calls.last.request.method == "PATCH"
    assert json.loads(route.calls.last.request.content) == {"mountType": "door"}
```

- [ ] **Step 2: Run — expect fail.** `uv run pytest tests/unit/clients/test_protect.py -k update_sensor -v`

- [ ] **Step 3: Add client method**

```python
    async def update_sensor(self, sensor_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update sensor settings."""
        result: dict[str, Any] = await self.patch(f"sensors/{self._segment(sensor_id)}", json=data)
        return result
```

- [ ] **Step 4: Run — expect pass.** `uv run pytest tests/unit/clients/test_protect.py -k update_sensor -v`

- [ ] **Step 5: Write failing tool test**

```python
@pytest.mark.asyncio
async def test_update_sensor_builds_body(readwrite_protect_tool_ctx):
    ctx, fake_client = readwrite_protect_tool_ctx
    await call_tool(
        "unifi_protect_update_sensor", ctx, sensor_id="s1", mount_type="door", motion_is_enabled=True
    )
    fake_client.update_sensor.assert_awaited_once_with(
        "s1", {"mountType": "door", "motionSettings": {"isEnabled": True}}
    )
```

- [ ] **Step 6: Run — expect fail.** `uv run pytest tests/unit/tools/test_protect_devices.py -k sensor -v`

- [ ] **Step 7: Add the allowlist + tool**

```python
_SENSOR_FIELD_PATHS: dict[str, tuple[str, ...]] = {
    "mount_type": ("mountType",),
    "motion_is_enabled": ("motionSettings", "isEnabled"),
    "light_is_enabled": ("lightSettings", "isEnabled"),
}
```

```python
    @mcp.tool(tags={"write", "protect"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    async def unifi_protect_update_sensor(
        ctx: Context,
        sensor_id: str,
        *,
        mount_type: str | None = None,
        motion_is_enabled: bool | None = None,
        light_is_enabled: bool | None = None,
        data: JsonObject | None = None,
    ) -> dict[str, Any]:
        """Update Protect sensor settings using named scalar args.

        Args:
            sensor_id: The sensor device ID.
            mount_type: Physical mount type, e.g. "door", "window", "garage" (``mountType``).
            motion_is_enabled: Enable motion detection (``motionSettings.isEnabled``).
            light_is_enabled: Enable the light/lux sensor reporting (``lightSettings.isEnabled``).
            data: DEPRECATED raw settings dict; cannot be combined with named args.

        Returns:
            The upstream API response.
        """
        try:
            validate_id(sensor_id, field="sensor_id")
            context = get_server_context(ctx)
            if not context.config.writes_enabled:
                raise UniFiReadOnlyError("Cannot update sensor in read-only mode")
            body = build_named_arg_body(
                tool_name="unifi_protect_update_sensor",
                field_paths=_SENSOR_FIELD_PATHS,
                named_values={
                    "mount_type": mount_type,
                    "motion_is_enabled": motion_is_enabled,
                    "light_is_enabled": light_is_enabled,
                },
                data=data,
            )
            reject_dangerous_keys(body, tool_name="unifi_protect_update_sensor")
            return await context.clients["protect"].update_sensor(sensor_id, body)
        except Exception as e:
            handle_client_error(e)
```

- [ ] **Step 8: Run — expect pass.** `uv run pytest tests/unit/tools/test_protect_devices.py tests/unit/clients/test_protect.py -k sensor -v`

- [ ] **Step 9: Commit**

```bash
git add src/unifi_mcp/clients/protect.py src/unifi_mcp/tools/protect/devices.py tests/unit/
git commit -m "feat(protect): add sensor write tool via integration v1 PATCH"
```

---

### Task 8: Viewer write client method + tool

**Files:**
- Modify: `src/unifi_mcp/clients/protect.py` (add `update_viewer`)
- Modify: `src/unifi_mcp/tools/protect/devices.py` (add `unifi_protect_set_viewer_liveview`)
- Test: `tests/unit/clients/test_protect.py`, `tests/unit/tools/test_protect_devices.py`

- [ ] **Step 1: Write failing client test**

```python
@pytest.mark.asyncio
@respx.mock
async def test_update_viewer_uses_patch(protect_client):
    route = respx.patch(
        "https://protect.local/proxy/protect/integration/v1/viewers/v1"
    ).mock(return_value=httpx.Response(200, json={"id": "v1"}))
    await protect_client.update_viewer("v1", {"liveview": "lv1"})
    assert route.calls.last.request.method == "PATCH"
    assert json.loads(route.calls.last.request.content) == {"liveview": "lv1"}
```

- [ ] **Step 2: Run — expect fail.** `uv run pytest tests/unit/clients/test_protect.py -k update_viewer -v`

- [ ] **Step 3: Add client method**

```python
    async def update_viewer(self, viewer_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update viewer settings."""
        result: dict[str, Any] = await self.patch(f"viewers/{self._segment(viewer_id)}", json=data)
        return result
```

- [ ] **Step 4: Run — expect pass.** `uv run pytest tests/unit/clients/test_protect.py -k update_viewer -v`

- [ ] **Step 5: Write failing tool test**

The viewer's `liveview` value is itself a UniFi id, so the tool validates it with `validate_id`.

```python
@pytest.mark.asyncio
async def test_set_viewer_liveview_builds_body(readwrite_protect_tool_ctx):
    ctx, fake_client = readwrite_protect_tool_ctx
    await call_tool("unifi_protect_set_viewer_liveview", ctx, viewer_id="v1", liveview_id="lv1")
    fake_client.update_viewer.assert_awaited_once_with("v1", {"liveview": "lv1"})


@pytest.mark.asyncio
async def test_set_viewer_liveview_rejects_bad_id(readwrite_protect_tool_ctx):
    ctx, _ = readwrite_protect_tool_ctx
    with pytest.raises(UniFiBadRequestError):
        await call_tool("unifi_protect_set_viewer_liveview", ctx, viewer_id="v1", liveview_id="../x")
```

Import `UniFiBadRequestError` from `unifi_mcp.errors` in the test if not already.

- [ ] **Step 6: Run — expect fail.** `uv run pytest tests/unit/tools/test_protect_devices.py -k viewer -v`

- [ ] **Step 7: Add the tool**

```python
    @mcp.tool(tags={"write", "protect"}, annotations={"readOnlyHint": False, "destructiveHint": False})
    async def unifi_protect_set_viewer_liveview(ctx: Context, viewer_id: str, liveview_id: str) -> dict[str, Any]:
        """Assign a liveview to a Protect viewer (Viewport).

        Args:
            viewer_id: The viewer device ID.
            liveview_id: The liveview ID to display on this viewer.

        Returns:
            The upstream API response.
        """
        try:
            validate_id(viewer_id, field="viewer_id")
            validate_id(liveview_id, field="liveview_id")
            context = get_server_context(ctx)
            if not context.config.writes_enabled:
                raise UniFiReadOnlyError("Cannot set viewer liveview in read-only mode")
            return await context.clients["protect"].update_viewer(viewer_id, {"liveview": liveview_id})
        except Exception as e:
            handle_client_error(e)
```

- [ ] **Step 8: Run — expect pass.** `uv run pytest tests/unit/tools/test_protect_devices.py tests/unit/clients/test_protect.py -k viewer -v`

- [ ] **Step 9: Full unit suite + lint + types**

Run:
```bash
uv run pytest tests/unit/ -q
uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/
uv run ty check src/unifi_mcp/
```
Expected: all green.

- [ ] **Step 10: Commit**

```bash
git add src/unifi_mcp/clients/protect.py src/unifi_mcp/tools/protect/devices.py tests/unit/
git commit -m "feat(protect): add viewer liveview write tool via integration v1 PATCH"
```

---

### Task 9: Live integration tests

Flip the camera-write xfails to real assertions, drop the NVR-write tests, and add accessory write roundtrips. Per `CLAUDE.md` / #271, write roundtrips run gated and one TestClass per invocation — never the whole destructive sweep at once.

**Files:**
- Modify: `tests/integration/test_all_tools_live.py`

- [ ] **Step 1: Update the xfail map**

In `tests/integration/test_all_tools_live.py`, edit `XFAIL_PROTECT_WRITE_TOOLS` (around line 138): remove the `unifi_protect_set_recording_mode`, `unifi_protect_set_smart_detection`, `unifi_protect_update_camera`, and `unifi_protect_update_nvr` entries. If the dict becomes empty and is unused elsewhere (`rg -n XFAIL_PROTECT_WRITE_TOOLS`), delete it and the preceding `#` comment block.

- [ ] **Step 2: Un-xfail the three camera roundtrips**

In `TestProtectWriteRoundtrips` (around line 1073), remove the `@pytest.mark.xfail(...)` decorators from `test_recording_mode_roundtrip`, `test_smart_detection_roundtrip`, and `test_update_camera_roundtrip`. The bodies already read → write → assert → restore; they now must pass for real.

- [ ] **Step 3: Delete the NVR-write tests**

Delete `test_update_nvr_roundtrip` (in `TestProtectWriteRoundtrips`, ~line 1235) and `test_update_nvr_unknown_field` (in `TestProtectWriteNegatives`, ~line 1323). Update the `TestProtectWriteRoundtrips` docstring that mentions "(or the NVR for update_nvr)".

- [ ] **Step 4: Add accessory write roundtrips**

Add a new class after `TestProtectWriteNegatives`. Each test lists the device type, skips cleanly if none present, then read → write a change → assert → restore. Match the file's existing helpers (`live_client`, `artifacts`, and the tool-invocation helper used by the other roundtrips — mirror `test_recording_mode_roundtrip`'s exact call style).

```python
class TestProtectAccessoryWriteRoundtrips:
    """Read→write→restore roundtrips for light/chime/sensor/viewer writes.

    Gated behind UNIFI_MODE=readwrite + LIVE_TEST_WRITES=1. Run as its own
    invocation per CLAUDE.md #271 hardware-safety guidance.
    """

    async def test_light_mode_roundtrip(self, live_client, artifacts):
        lights = await live_client.call("unifi_protect_list_lights")
        if not lights:
            pytest.skip("no Protect lights on test controller")
        light_id = lights[0]["id"]
        original = lights[0].get("lightModeSettings", {}).get("mode", "motion")
        target = "always" if original != "always" else "motion"
        try:
            applied = await live_client.call("unifi_protect_set_light_mode", light_id=light_id, mode=target)
            artifacts.dump("light_mode_applied", {"target": target, "response": applied})
            after = await live_client.call("unifi_protect_get_... ", )  # see note
        finally:
            await live_client.call("unifi_protect_set_light_mode", light_id=light_id, mode=original)
```

Note: there is no `get_light` read tool — read back via `unifi_protect_list_lights` and find the matching `id`. Implement the readback as a list-filter:

```python
        after_lights = await live_client.call("unifi_protect_list_lights")
        after_mode = next(l["lightModeSettings"]["mode"] for l in after_lights if l["id"] == light_id)
        assert after_mode == target
```

Add analogous `test_chime_volume_roundtrip` (list_chimes → `unifi_protect_update_chime` volume → readback via list_chimes → restore), `test_sensor_mount_roundtrip` (list_sensors → `unifi_protect_update_sensor` → restore), and `test_viewer_liveview_roundtrip` (list_viewers; needs an existing liveview id from the NVR/bootstrap — if none discoverable, `pytest.skip("no liveview available")`). Each follows the same try/finally restore shape.

- [ ] **Step 5: Collection-only check (no hardware needed)**

Run: `uv run pytest tests/integration/test_all_tools_live.py --collect-only -q`
Expected: collection succeeds (no import/syntax errors), the new class and tests are listed, and no `update_nvr` tests remain.

- [ ] **Step 6: Lint**

Run: `uv run ruff check tests/ && uv run ruff format --check tests/`
Expected: clean.

- [ ] **Step 7: (If hardware available) run the new class in isolation**

Per CLAUDE.md, run ONLY this class, then health-check:
```bash
UNIFI_MODE=readwrite LIVE_TEST_WRITES=1 \
  uv run pytest tests/integration/test_all_tools_live.py::TestProtectAccessoryWriteRoundtrips -v -m integration
curl -skf -o /dev/null -w '%{http_code}\n' "https://${UNIFI_PROTECT_HOST}/proxy/protect/integration/v1/cameras"
```
Expected: pass or clean skips; controller responsive. Do NOT run the full integration file in one invocation.

- [ ] **Step 8: Commit**

```bash
git add tests/integration/test_all_tools_live.py
git commit -m "test(protect): live-verify integration v1 writes; drop NVR-write tests"
```

---

### Task 10: Docs + changelog

**Files:**
- Modify: `CLAUDE.md` (Protect tool counts + architecture tree)
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Update CLAUDE.md counts**

In `src/unifi_mcp/`’s tree comment and the prose, update the Protect line. New Protect surface: 9 read + 8 write (3 camera + light×2 + chime + sensor + viewer) = 17 tools; NVR write removed. Find the current line:

```
└── protect/             # 9 read + 4 write tools (13 total, includes 2 media read tools)
```

Replace with:

```
└── protect/             # 9 read + 8 write tools (17 total, includes 2 media read tools)
```

Also update any other count in `CLAUDE.md` that says Protect "9 read + 4 write" or total tool counts (search: `rg -n "9 read|4 write|protect" CLAUDE.md`). Total tools become 81 − 4 + 8 = 85 across the three APIs; adjust the Architecture section if it states a global total.

- [ ] **Step 2: Add a CHANGELOG entry**

In `CHANGELOG.md`, under a new Unreleased/next-version section (match the file's "Keep a Changelog" format):

```markdown
### Added
- Protect light, chime, sensor, and viewer write tools (`unifi_protect_update_light`,
  `unifi_protect_set_light_mode`, `unifi_protect_update_chime`,
  `unifi_protect_update_sensor`, `unifi_protect_set_viewer_liveview`).

### Fixed
- Protect camera writes (`unifi_protect_update_camera`, `set_recording_mode`,
  `set_smart_detection`) now work: they issue PATCH on the integration v1 API
  instead of an unsupported PUT (#139, #237).

### Removed
- `unifi_protect_update_nvr`: the integration v1 API is GET-only for the NVR,
  so the tool could never succeed.
```

- [ ] **Step 3: Verify docs reference reality**

Run: `rg -n "update_nvr" . -g '!docs/superpowers/**'`
Expected: no remaining references in source, tests, or top-level docs (design/plan files may still mention it as removed — that's fine).

- [ ] **Step 4: Final full check**

Run:
```bash
uv run pytest tests/unit/ -q
uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/
uv run ty check src/unifi_mcp/
```
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md CHANGELOG.md
git commit -m "docs: record Protect integration v1 write support and NVR-write removal"
```

---

## Self-Review notes

- **Spec coverage:** patch() (Task 1), camera PUT→PATCH (Task 2), NVR-write removal (Task 3), schema spike (Task 4), light/chime/sensor/viewer writes (Tasks 5–8), live tests incl. xfail flips + accessory roundtrips (Task 9), docs/CLAUDE.md/CHANGELOG (Task 10). All spec sections mapped.
- **Type consistency:** client methods `update_light/update_chime/update_sensor/update_viewer` are defined in Tasks 5–8 and referenced by the same names in their tools and tests. Field-path allowlists (`_LIGHT_/_CHIME_/_SENSOR_FIELD_PATHS`) are defined where used.
- **Open dependency:** Tasks 5–8 field paths depend on Task 4's confirmed schema. If the spike (Task 4 Step 1) yields different field names than the documented defaults, substitute them consistently in the allowlist, the client/tool, the unit-test expected bodies, and the live readback in Task 9.
