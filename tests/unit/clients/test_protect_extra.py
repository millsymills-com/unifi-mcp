"""Per-method coverage for ProtectClient methods not covered in test_protect.py (#72)."""

from __future__ import annotations

import httpx
import pytest
import respx

from unifi_mcp.clients.protect import ProtectClient

BASE_URL = "https://10.0.0.1:443"
API_PREFIX = f"{BASE_URL}/proxy/protect/integration/v1/"


@pytest.fixture
def client() -> ProtectClient:
    return ProtectClient(base_url=BASE_URL, api_key="test-key", timeout=5, max_retries=1)


class TestReadMethods:
    @respx.mock
    async def test_list_chimes(self, client):
        respx.get(f"{API_PREFIX}chimes").mock(return_value=httpx.Response(200, json=[{"id": "chime-1"}]))
        assert await client.list_chimes() == [{"id": "chime-1"}]

    @respx.mock
    async def test_list_lights(self, client):
        respx.get(f"{API_PREFIX}lights").mock(return_value=httpx.Response(200, json=[{"id": "light-1"}]))
        assert await client.list_lights() == [{"id": "light-1"}]

    @respx.mock
    async def test_list_sensors(self, client):
        respx.get(f"{API_PREFIX}sensors").mock(return_value=httpx.Response(200, json=[{"id": "sensor-1"}]))
        assert await client.list_sensors() == [{"id": "sensor-1"}]

    @respx.mock
    async def test_list_viewers(self, client):
        respx.get(f"{API_PREFIX}viewers").mock(return_value=httpx.Response(200, json=[{"id": "viewer-1"}]))
        assert await client.list_viewers() == [{"id": "viewer-1"}]


class TestWriteMethods:
    @respx.mock
    async def test_set_smart_detection_patches_smart_settings(self, client):
        route = respx.patch(f"{API_PREFIX}cameras/cam-1").mock(return_value=httpx.Response(200, json={}))
        await client.set_smart_detection("cam-1", ["person", "vehicle"])
        body = route.calls[0].request.content
        assert b"smartDetectSettings" in body
        assert b"person" in body
        assert b"vehicle" in body

    @respx.mock
    async def test_set_recording_mode_pre_padding_only(self, client):
        # Exercise the pre_padding branch when post_padding is None.
        route = respx.patch(f"{API_PREFIX}cameras/cam-1").mock(return_value=httpx.Response(200, json={}))
        await client.set_recording_mode("cam-1", "motion", pre_padding=7)
        body = route.calls[0].request.content
        assert b"prePaddingSecs" in body
        assert b"postPaddingSecs" not in body

    @respx.mock
    async def test_set_recording_mode_post_padding_only(self, client):
        route = respx.patch(f"{API_PREFIX}cameras/cam-1").mock(return_value=httpx.Response(200, json={}))
        await client.set_recording_mode("cam-1", "motion", post_padding=11)
        body = route.calls[0].request.content
        assert b"postPaddingSecs" in body
        assert b"prePaddingSecs" not in body
