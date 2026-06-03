"""Live round-trip verification of Protect accessory PATCH field paths (#330).

The integration-v1 PATCH mappings for lights, chimes, sensors, and viewers
(``src/unifi_mcp/tools/protect/devices.py``) are documented as *unverified
against real hardware*. The API returns ``200`` and silently ignores
unrecognized nested keys, so a wrong path (e.g. ``lightModeSettings.mode`` vs.
an upstream ``lightModeSettings.lightMode``) produces a successful-looking
no-op rather than an error.

Each test here captures the current value at the mapped path, PATCHes a
*different* value, re-reads the device, and asserts the new value actually
landed. A wrong mapping fails that assertion — turning a silent no-op into a
red test. The original value is restored in ``finally``.

Run (against dedicated test hardware):

    LIVE_TEST_PROTECT_WRITES=1 LIVE_TEST_DEVICE_MACS=<accessory-macs> \
        uv run pytest tests/integration/test_protect_accessory_writes_live.py -v -m integration

Gated behind ``LIVE_TEST_PROTECT_WRITES=1`` (mutates a real device) and the
``LIVE_TEST_DEVICE_MACS`` allowlist (never a blind ``records[0]`` pick, per
#271/#330). Skips cleanly when either is absent, or when the chosen device's
GET response omits the field being verified (older/newer firmware varies).
"""

from __future__ import annotations

import logging
import os
from typing import Any

import pytest

from tests.integration.conftest import (
    PROTECT_WRITE_GATE_REASON,
    _normalize_mac,
    _protect_writes_enabled,
    live_test_device_macs,
)
from unifi_mcp.tools.protect.devices import (
    _CHIME_FIELD_PATHS,
    _LIGHT_FIELD_PATHS,
    _SENSOR_FIELD_PATHS,
)

LOG = logging.getLogger(__name__)

pytestmark = pytest.mark.integration

_UNSET = object()


def _nested_get(record: dict[str, Any], path: tuple[str, ...]) -> Any:
    """Follow a field-path tuple into a device record, or ``_UNSET`` if any hop is missing."""
    cursor: Any = record
    for key in path:
        if not isinstance(cursor, dict) or key not in cursor:
            return _UNSET
        cursor = cursor[key]
    return cursor


def _nested_body(path: tuple[str, ...], value: Any) -> dict[str, Any]:
    """Build the nested PATCH body that the named-arg tool would emit for ``path``."""
    body: dict[str, Any] = {}
    cursor = body
    for key in path[:-1]:
        nxt: dict[str, Any] = {}
        cursor[key] = nxt
        cursor = nxt
    cursor[path[-1]] = value
    return body


def _pick_allowlisted(records: list[dict[str, Any]], family: str) -> dict[str, Any]:
    """Return the first record whose MAC is in ``LIVE_TEST_DEVICE_MACS``.

    Skips (never picks ``records[0]``) when the allowlist is empty, the family
    has no adopted devices, or none match — the blind-first-device pick is the
    footgun behind #271/#330.
    """
    allowlist = live_test_device_macs()
    if not allowlist:
        pytest.skip(f"LIVE_TEST_DEVICE_MACS is unset; refusing to pick a {family} write target (#271/#330)")
    if not records:
        pytest.skip(f"No {family} devices adopted on Protect controller")
    for record in records:
        if _normalize_mac(str(record.get("mac", ""))) in allowlist:
            return record
    pytest.skip(f"No adopted {family} matches LIVE_TEST_DEVICE_MACS; refusing to target a non-approved device")


async def _verify_path_roundtrip(
    *,
    device: dict[str, Any],
    path: tuple[str, ...],
    new_value: Any,
    update: Any,
    reread: Any,
    device_id: str,
) -> None:
    """Capture → PATCH ``new_value`` at ``path`` → re-read → assert it landed → restore.

    The assertion is the whole point: a wrong field path PATCHes a key the
    controller ignores (200 + no-op), so the re-read still shows the original
    value and this fails — exactly the silent miss #330 needs surfaced.
    """
    original = _nested_get(device, path)
    if original is _UNSET:
        pytest.skip(f"Device GET omits {'.'.join(path)}; cannot capture original for round-trip on this firmware")
    assert new_value != original, "test bug: new_value must differ from the captured original"

    try:
        await update(device_id, _nested_body(path, new_value))
        refreshed = await reread(device_id)
        observed = _nested_get(refreshed, path)
        assert observed == new_value, (
            f"field path {'.'.join(path)} did not round-trip: set {new_value!r}, "
            f"re-read {observed!r}. The PATCH likely hit a key the controller ignores "
            f"(silent 200 no-op) — the mapping is wrong (#330)."
        )
    finally:
        try:
            await update(device_id, _nested_body(path, original))
        except Exception as exc:
            LOG.warning("Restore of %s on %s failed: %s", ".".join(path), device_id, exc)


def _device_id(record: dict[str, Any]) -> str:
    device_id = record.get("id") or record.get("_id")
    assert isinstance(device_id, str), f"accessory record missing id: {record}"
    return device_id


@pytest.mark.live_write
@pytest.mark.write_gated
@pytest.mark.skipif(not _protect_writes_enabled(), reason=PROTECT_WRITE_GATE_REASON)
class TestAccessoryFieldPaths:
    """Round-trip each accessory family's primary scalar field path against live hardware."""

    async def _reread_factory(self, lister: Any) -> Any:
        async def reread(device_id: str) -> dict[str, Any]:
            for record in await lister():
                if (record.get("id") or record.get("_id")) == device_id:
                    return record
            pytest.fail(f"device {device_id} vanished from listing mid-test")

        return reread

    async def test_chime_volume_path(self, protect_live_client):
        device = _pick_allowlisted(await protect_live_client.list_chimes(), "chime")
        path = _CHIME_FIELD_PATHS["volume"]
        current = _nested_get(device, path)
        new_value = 30 if current != 30 else 40
        await _verify_path_roundtrip(
            device=device,
            path=path,
            new_value=new_value,
            update=protect_live_client.update_chime,
            reread=await self._reread_factory(protect_live_client.list_chimes),
            device_id=_device_id(device),
        )

    async def test_light_led_level_path(self, protect_live_client):
        device = _pick_allowlisted(await protect_live_client.list_lights(), "light")
        path = _LIGHT_FIELD_PATHS["led_level"]
        current = _nested_get(device, path)
        new_value = 3 if current != 3 else 4
        await _verify_path_roundtrip(
            device=device,
            path=path,
            new_value=new_value,
            update=protect_live_client.update_light,
            reread=await self._reread_factory(protect_live_client.list_lights),
            device_id=_device_id(device),
        )

    async def test_light_mode_path(self, protect_live_client):
        device = _pick_allowlisted(await protect_live_client.list_lights(), "light")
        path = _LIGHT_FIELD_PATHS["mode"]
        current = _nested_get(device, path)
        new_value = "off" if current != "off" else "motion"
        await _verify_path_roundtrip(
            device=device,
            path=path,
            new_value=new_value,
            update=protect_live_client.update_light,
            reread=await self._reread_factory(protect_live_client.list_lights),
            device_id=_device_id(device),
        )

    async def test_sensor_motion_enabled_path(self, protect_live_client):
        device = _pick_allowlisted(await protect_live_client.list_sensors(), "sensor")
        path = _SENSOR_FIELD_PATHS["motion_is_enabled"]
        current = _nested_get(device, path)
        new_value = not current if isinstance(current, bool) else True
        await _verify_path_roundtrip(
            device=device,
            path=path,
            new_value=new_value,
            update=protect_live_client.update_sensor,
            reread=await self._reread_factory(protect_live_client.list_sensors),
            device_id=_device_id(device),
        )

    async def test_viewer_liveview_path(self, protect_live_client):
        """Verify the ``liveview`` body shape round-trips on a viewport.

        Needs a *second* liveview id to flip to, supplied via
        ``LIVE_TEST_VIEWER_LIVEVIEW_ID``; setting the current value back to
        itself would not distinguish a correct path from a silent no-op.
        """
        target_liveview = os.environ.get("LIVE_TEST_VIEWER_LIVEVIEW_ID", "").strip()
        if not target_liveview:
            pytest.skip("LIVE_TEST_VIEWER_LIVEVIEW_ID unset; cannot prove liveview path without a distinct id")
        device = _pick_allowlisted(await protect_live_client.list_viewers(), "viewer")
        path = ("liveview",)
        current = _nested_get(device, path)
        if current == target_liveview:
            pytest.skip("LIVE_TEST_VIEWER_LIVEVIEW_ID equals the current liveview; pick a different one")
        await _verify_path_roundtrip(
            device=device,
            path=path,
            new_value=target_liveview,
            update=protect_live_client.update_viewer,
            reread=await self._reread_factory(protect_live_client.list_viewers),
            device_id=_device_id(device),
        )
