# Live integration write-test safety

The live integration suite (`tests/integration/`, marked `@pytest.mark.integration`)
mutates a real UniFi controller. A sustained write sweep has bricked production
hardware before — on 2026-05-21 the destructive sweep corrupted a UCG Ultra
on-disk and required a factory reset (#271). The rules below exist to keep that
from recurring. This doc complements the "Live Integration Tests — Hardware
Safety" section in the repo-root `CLAUDE.md`.

## Device-MAC allowlist (`LIVE_TEST_DEVICE_MACS`)

Protect **write** tests target only devices the operator has explicitly
approved. The old behavior picked `cameras[0]` — "whatever device is first" —
which is the footgun behind #271.

- **Env var**: `LIVE_TEST_DEVICE_MACS`, comma-separated MACs.
- **Format**: any common separator/case is accepted. `E438830FD628`,
  `e4:38:83:0f:d6:28`, and `e4-38-83-0f-d6-28` all normalize to the same
  12-hex-digit key. Unparseable entries (not exactly 12 hex digits) are
  dropped. Parsing lives in `tests/integration/conftest.py`
  (`_normalize_mac`, `live_test_device_macs`).
- **Resolution**: `_allowlisted_camera_id(client)` (in
  `test_all_tools_live.py`) and `_pick_test_camera_id(...)` (in
  `test_protect_writes_live.py`) list cameras, filter to the allowlist, and
  return the first match.
- **Skip semantics**: if the allowlist is empty (var unset) or no adopted
  camera matches, the write test `pytest.skip`s — it never errors, and never
  falls back to a non-approved device.
- **Read-only** Protect tests may keep using `_first_protect_camera_id`
  (first adopted camera). Only writes are allowlist-gated.

Example:

```bash
export LIVE_TEST_DEVICE_MACS=E438830FD628   # the approved G3 Flex
```

## Capture → write → read-back → restore

Every reversible camera/accessory write roundtrip must:

1. Read the field's **original** value first (skip if it can't be captured).
2. Write the new value.
3. Assert the read-back where the API echoes the field.
4. Restore the original in a `finally` so the test leaves config unchanged.

Apply to reversible fields only — e.g. `osdSettings.isNameEnabled`,
`ledSettings.isEnabled`, `name`, `recordingSettings.mode`,
`lightDeviceSettings.ledLevel`, chime `volume`, sensor
`motionSettings.isEnabled`. Never weaken an existing restore.

## Run protocol (one class per invocation)

Do **not** run the whole suite in one invocation when writes/destructive gates
are on. Cumulative state churn compounds and the controller cannot
self-recover. Required pattern: one `TestClass` per pytest invocation, a
controller health check between classes, and a ~30s cooldown.

```bash
uv run pytest tests/integration/test_all_tools_live.py::TestProtectWriteRoundtrips -v -m integration
# verify the controller is responsive before continuing:
curl -skf -o /dev/null -w '%{http_code}\n' "https://${UNIFI_NETWORK_HOST}/proxy/network/integration/v1/sites"
sleep 30
uv run pytest tests/integration/test_all_tools_live.py::TestProtectAccessoryWriteRoundtrips -v -m integration
```

If the health check fails or a class hangs, stop the sweep and triage before
continuing. See #271 for incident details.

## Missing hardware (#330 parked)

The maintainer's only Protect device is one camera: a **G3 Flex,
MAC `E438830FD628`** (`featureFlags.smartDetectTypes=[]`, no AI). Several
Protect accessory write tools and the AI smart-detection roundtrip cannot be
exercised — and their PATCH field paths cannot be verified — without one of
each device below. **#330 is parked pending this hardware.**

| Capability under test            | Tool                                  | Device needed                  | Why the G3 Flex can't cover it          |
| -------------------------------- | ------------------------------------- | ------------------------------ | --------------------------------------- |
| Light PATCH (`ledLevel`, `mode`) | `unifi_protect_update_light` / `set_light_mode` | UP-FloodLight (light)          | no light adopted                        |
| Chime PATCH (`volume`)           | `unifi_protect_update_chime`          | UP-Chime (chime)               | no chime adopted                        |
| Sensor PATCH (`motionSettings`)  | `unifi_protect_update_sensor`         | UP-Sense (sensor)              | no sensor adopted                       |
| Viewer PATCH (`liveview`)        | `unifi_protect_set_viewer_liveview`   | UniFi Protect Viewport (viewer)| no viewer adopted                       |
| Smart detection (`person`)       | `unifi_protect_set_smart_detection`   | AI-capable camera (G4/G5)      | G3 Flex has `smartDetectTypes=[]`, no AI |

Until that hardware lands, those tests `pytest.skip` cleanly (no adopted
device of the type, or no AI support), so the suite stays green on the
current bench.
