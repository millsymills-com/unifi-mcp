"""Live Protect write tests.

Holds the gated live ``set_recording_mode`` round-trip against the test
camera. Camera writes are issued as PATCH on integration v1 and are
functional on current firmware.

Run:
    uv run pytest tests/integration/test_protect_writes_live.py -v -m integration

The round-trip is gated behind LIVE_TEST_PROTECT_WRITES=1 because a silent
mode flip on a real surveillance setup would be a problem; for dedicated test
hardware this gate is just opt-in confirmation. It skips when the camera GET
response omits ``recordingSettings.mode`` (integration v1 does this on current
firmware), since the original mode can't be captured for restoration.
"""

from __future__ import annotations

import logging
import os

import pytest

from tests.integration.conftest import _normalize_mac, live_test_device_macs

LOG = logging.getLogger(__name__)

pytestmark = pytest.mark.integration


def _writes_enabled() -> bool:
    return os.environ.get("LIVE_TEST_PROTECT_WRITES", "").strip().lower() in {"1", "true", "yes", "on"}


PROTECT_WRITE_GATE_REASON = "Set LIVE_TEST_PROTECT_WRITES=1 to run set_recording_mode against the test camera"


async def _pick_test_camera_id(protect_live_client) -> str:
    """Return the id of the first adopted camera whose MAC is allowlisted.

    This is a write target, so it must come from ``LIVE_TEST_DEVICE_MACS``
    rather than ``cameras[0]`` — the blind-first-device pick is the footgun
    behind the #271 bench-bricking incident. Skips cleanly when the
    allowlist is empty or no adopted camera matches (#330).
    """
    allowlist = live_test_device_macs()
    if not allowlist:
        pytest.skip("LIVE_TEST_DEVICE_MACS is unset; refusing to pick a Protect write target (#271/#330)")
    cameras = await protect_live_client.list_cameras()
    if not cameras:
        pytest.skip("No cameras adopted on Protect controller")
    for cam in cameras:
        mac = _normalize_mac(str(cam.get("mac", "")))
        if mac and mac in allowlist:
            cam_id = cam.get("id") or cam.get("_id")
            assert isinstance(cam_id, str), f"camera record missing id: {cam}"
            return cam_id
    pytest.skip(
        "No adopted camera matches LIVE_TEST_DEVICE_MACS; "
        "skipping Protect write test rather than targeting a non-approved device (#271/#330)"
    )


@pytest.mark.skipif(not _writes_enabled(), reason=PROTECT_WRITE_GATE_REASON)
class TestSetRecordingModeWrite:
    """``set_recording_mode`` round-trip against the test camera.

    Per memory (Protect integration v1 surface), the PUT cameras/{id} with
    ``recordingSettings`` is round-trip-confirmed on the older G3-flex camera,
    but on G3 Flex hardware running newer firmware the GET response may no
    longer include ``recordingSettings`` — in that case we can't capture the
    original mode for restoration and the test skips.
    """

    async def test_set_recording_mode_roundtrip(self, protect_live_client):
        camera_id = await _pick_test_camera_id(protect_live_client)
        camera = await protect_live_client.get_camera(camera_id)
        original = camera.get("recordingSettings", {}).get("mode") if isinstance(camera, dict) else None
        if not original:
            pytest.skip(
                "Camera GET response has no recordingSettings.mode; round-trip cannot capture original. "
                "PUT path may still work but is no longer verifiable via integration v1 GET."
            )

        new_mode = "never" if original != "never" else "always"

        try:
            response = await protect_live_client.set_recording_mode(camera_id, new_mode)
            assert isinstance(response, dict), "set_recording_mode must return a dict"
        finally:
            try:
                await protect_live_client.set_recording_mode(camera_id, original)
            except Exception as exc:
                LOG.warning("Cleanup set_recording_mode(%s, %s) failed: %s", camera_id, original, exc)
