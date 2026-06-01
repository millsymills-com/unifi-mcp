# Protect integration v1 write-schema notes (Task 4 spike)

**Date:** 2026-05-29
**Controller probed:** Protect host `192.168.1.220` (read-only GETs via `ProtectClient`).
**Method:** `GET /proxy/protect/integration/v1/{cameras,lights,chimes,sensors,viewers,nvrs}` — no writes issued.

## Inventory found on the test controller

| Resource | Count | Notes |
|---|---|---|
| cameras | 1 | `smartDetectSettings` populated (`audioTypes`, `objectTypes`); **`recordingSettings` read back as empty `{}`** |
| lights | 0 | none present |
| chimes | 0 | none present |
| sensors | 0 | none present |
| viewers | 0 | none present |

**Consequence:** there is no live accessory device on this controller, so the exact
PATCH body field names could **not** be confirmed against real data. The field
paths below are the documented official-API defaults (unconfirmed against this
hardware). Task 9's accessory write roundtrips will `pytest.skip(...)` here
(count == 0) and must not hard-fail.

### Finding: integration v1 returns some settings sub-objects empty on read

The single camera's `recordingSettings` came back as `{}` even though the camera
records — matching the uiprotect discussion #442 observation that the official
integration v1 API omits fields the private API populates (there reported for
chime `ringSettings`). This is a **read-back** gap, not necessarily a write gap:
a PATCH that sets `recordingSettings.mode` may still be accepted.

**Action for Task 9:** the un-xfailed `test_recording_mode_roundtrip` reads the
original mode to restore it. Because the read can yield an empty
`recordingSettings`, the test must default the "original" mode when absent
(e.g. fall back to `"always"`) and assert on the PATCH call succeeding rather
than requiring the new mode to echo back in a subsequent read. Do not assume
read-back reflects the written value.

## Field paths used by Tasks 5–8 (documented official-API defaults, unconfirmed)

These feed the `_LIGHT_/_CHIME_/_SENSOR_FIELD_PATHS` allowlists and the
named-arg → body mapping. If a controller with these devices later confirms
different names, update the allowlists, the tool docstrings, the unit-test
expected bodies, and the Task 9 readbacks together.

- **Light** (`PATCH lights/{id}`):
  - `led_level` → `lightDeviceSettings.ledLevel` (int 1–6)
  - `pir_duration` → `lightDeviceSettings.pirDuration` (ms)
  - `pir_sensitivity` → `lightDeviceSettings.pirSensitivity` (0–100)
  - `mode` → `lightModeSettings.mode` (`"off" | "motion" | "always"`)
- **Chime** (`PATCH chimes/{id}`):
  - `volume` → `volume` (int 0–100)
  - `repeat_times` → `repeatTimes` (int)
- **Sensor** (`PATCH sensors/{id}`):
  - `mount_type` → `mountType` (str)
  - `motion_is_enabled` → `motionSettings.isEnabled` (bool)
  - `light_is_enabled` → `lightSettings.isEnabled` (bool)
- **Viewer** (`PATCH viewers/{id}`):
  - `liveview_id` → `liveview` (str — a liveview id)

## Camera writes (Task 2, already shipped)

Confirmed the read endpoints respond and the resource paths are correct. Camera
PATCH bodies remain:
- recording mode → `{"recordingSettings": {"mode": ...}}` (+ optional `prePaddingSecs`/`postPaddingSecs`)
- smart detection → `{"smartDetectSettings": {"objectTypes": [...]}}` (controller exposes `objectTypes` and `audioTypes`)
