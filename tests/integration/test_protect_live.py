"""Live Protect API tests. Require a reachable NVR + UNIFI_PROTECT_API.

Run manually:

    uv run pytest tests/integration/test_protect_live.py -v -m integration
"""

from __future__ import annotations

import time

import httpx
import pytest

from unifi_mcp.errors import UniFiError

pytestmark = pytest.mark.integration


async def test_validate_connection(protect_live_client):
    assert await protect_live_client.validate_connection() is True


async def test_get_nvr_returns_identifier(protect_live_client):
    nvr = await protect_live_client.get_nvr()
    # NVR payload always carries at least one of these top-level identifiers.
    assert any(key in nvr for key in ("id", "mac", "name"))


async def test_list_cameras_returns_list(protect_live_client):
    cameras = await protect_live_client.list_cameras()
    assert isinstance(cameras, list)


async def test_get_snapshot_returns_jpeg(protect_live_client):
    cameras = await protect_live_client.list_cameras()
    if not cameras:
        pytest.skip("No cameras connected to the NVR")
    camera_id = cameras[0].get("id")
    assert camera_id, "First camera entry missing id"
    snapshot = await protect_live_client.get_snapshot(camera_id, max_bytes=50 * 1024 * 1024)
    # JPEG magic bytes.
    assert snapshot.startswith(b"\xff\xd8\xff"), "Snapshot is not a JPEG"
    assert len(snapshot) > 1024, "Snapshot suspiciously small"


@pytest.mark.xfail(
    strict=True,
    reason="#227 — GET cameras/{id}/video/export 404s on Protect integration v1 (endpoint not exposed)",
)
async def test_export_video_returns_data(protect_live_client):
    """Export a 5-second window from ~30s ago. Asserts non-empty bytes; size
    sanity check guards against the controller returning an empty/0-byte
    response on a brand-new camera with no recordings yet (treat that as a
    skip, not a fail — the test is about the export endpoint, not retention).
    """
    cameras = await protect_live_client.list_cameras()
    if not cameras:
        pytest.skip("No cameras connected to the NVR")
    camera_id = cameras[0].get("id")
    assert camera_id, "First camera entry missing id"

    end_ms = int(time.time() * 1000) - 5_000
    start_ms = end_ms - 5_000

    data = await protect_live_client.export_video(camera_id, start=start_ms, end=end_ms, max_bytes=500 * 1024 * 1024)
    assert isinstance(data, bytes), f"Expected bytes, got {type(data).__name__}"
    if len(data) == 0:
        pytest.skip("Export returned 0 bytes — likely no recording yet for the new camera")
    assert len(data) > 1024, f"Export suspiciously small: {len(data)} bytes"


async def test_export_video_reversed_window_raises(protect_live_client):
    """A reversed time window (start > end) should fail at the API rather than
    silently returning an empty/garbage clip. Accept either a UniFiError
    (mapped 4xx) or an httpx.HTTPError (raw timeout/transport) — the test is
    that the failure surfaces, not its precise class.
    """
    cameras = await protect_live_client.list_cameras()
    if not cameras:
        pytest.skip("No cameras connected to the NVR")
    camera_id = cameras[0].get("id")
    assert camera_id, "First camera entry missing id"

    now_ms = int(time.time() * 1000)
    with pytest.raises((UniFiError, httpx.HTTPError)):
        await protect_live_client.export_video(
            camera_id, start=now_ms, end=now_ms - 60_000, max_bytes=500 * 1024 * 1024
        )
