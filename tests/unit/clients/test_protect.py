"""Tests for the Protect API client."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from unifi_mcp.clients.protect import ProtectClient

BASE_URL = "https://10.0.0.1:443"
API_PREFIX = f"{BASE_URL}/proxy/protect/integration/v1/"

FIXTURES = json.loads(
    (Path(__file__).resolve().parent.parent.parent / "fixtures" / "protect_responses.json").read_text()
)


@pytest.fixture
def client():
    return ProtectClient(
        base_url=BASE_URL,
        api_key="test-protect-key",
        timeout=5,
        max_retries=2,
    )


class TestListCameras:
    @respx.mock
    async def test_list_cameras_calls_correct_endpoint(self, client):
        route = respx.get(f"{API_PREFIX}cameras").mock(return_value=httpx.Response(200, json=FIXTURES["cameras"]))
        result = await client.list_cameras()
        assert route.called
        assert result == FIXTURES["cameras"]


class TestGetCamera:
    @respx.mock
    async def test_get_camera_calls_correct_endpoint(self, client):
        route = respx.get(f"{API_PREFIX}cameras/cam-1").mock(
            return_value=httpx.Response(200, json=FIXTURES["cameras"][0])
        )
        result = await client.get_camera("cam-1")
        assert route.called
        assert result["id"] == "cam-1"
        assert result["name"] == "Front Door"


class TestGetSnapshot:
    @respx.mock
    async def test_get_snapshot_returns_bytes(self, client):
        snapshot_data = b"\xff\xd8\xff\xe0fake-jpeg-data"
        route = respx.get(f"{API_PREFIX}cameras/cam-1/snapshot").mock(
            return_value=httpx.Response(200, content=snapshot_data)
        )
        result = await client.get_snapshot("cam-1")
        assert route.called
        assert result == snapshot_data

    @respx.mock
    async def test_get_snapshot_with_timestamp_passes_ts_param(self, client):
        snapshot_data = b"\xff\xd8\xff\xe0fake-jpeg-data"
        route = respx.get(f"{API_PREFIX}cameras/cam-1/snapshot").mock(
            return_value=httpx.Response(200, content=snapshot_data)
        )
        result = await client.get_snapshot("cam-1", timestamp=1700000000000)
        assert route.called
        request = route.calls[0].request
        assert "ts=1700000000000" in str(request.url)
        assert result == snapshot_data

    @respx.mock
    async def test_get_snapshot_under_max_bytes_returns_full_body(self, client):
        """Snapshot under the cap streams through and returns complete bytes."""
        snapshot_data = b"\xff\xd8\xff\xe0fake-jpeg-data"
        respx.get(f"{API_PREFIX}cameras/cam-1/snapshot").mock(return_value=httpx.Response(200, content=snapshot_data))
        result = await client.get_snapshot("cam-1", max_bytes=1024)
        assert result == snapshot_data

    @respx.mock
    async def test_get_snapshot_over_max_bytes_raises(self, client):
        """Snapshot exceeding the cap aborts mid-stream with UniFiError."""
        from unifi_mcp.errors import UniFiError

        oversized = b"x" * 2000
        respx.get(f"{API_PREFIX}cameras/cam-1/snapshot").mock(return_value=httpx.Response(200, content=oversized))
        with pytest.raises(UniFiError, match="exceeded max_bytes=1024"):
            await client.get_snapshot("cam-1", max_bytes=1024)


class TestUpdateCamera:
    @respx.mock
    async def test_update_camera_sends_patch(self, client):
        payload = {"name": "Back Yard"}
        route = respx.patch(f"{API_PREFIX}cameras/cam-1").mock(
            return_value=httpx.Response(200, json={"id": "cam-1", "name": "Back Yard"})
        )
        result = await client.update_camera("cam-1", payload)
        assert route.called
        request_body = json.loads(route.calls[0].request.content)
        assert request_body == payload
        assert result["name"] == "Back Yard"


class TestSetRecordingMode:
    @respx.mock
    async def test_set_recording_mode_sends_correct_payload(self, client):
        route = respx.patch(f"{API_PREFIX}cameras/cam-1").mock(return_value=httpx.Response(200, json={"id": "cam-1"}))
        await client.set_recording_mode("cam-1", "motion", pre_padding=5, post_padding=10)
        assert route.called
        request_body = json.loads(route.calls[0].request.content)
        assert request_body == {
            "recordingSettings": {
                "mode": "motion",
                "prePaddingSecs": 5,
                "postPaddingSecs": 10,
            }
        }

    @respx.mock
    async def test_set_recording_mode_always_sends_correct_payload(self, client):
        route = respx.patch(f"{API_PREFIX}cameras/cam-1").mock(return_value=httpx.Response(200, json={"id": "cam-1"}))
        await client.set_recording_mode("cam-1", "always")
        assert route.called
        request_body = json.loads(route.calls[0].request.content)
        assert request_body == {"recordingSettings": {"mode": "always"}}


class TestSetSmartDetection:
    @respx.mock
    async def test_set_smart_detection_sends_correct_payload(self, client):
        route = respx.patch(f"{API_PREFIX}cameras/cam-1").mock(return_value=httpx.Response(200, json={"id": "cam-1"}))
        await client.set_smart_detection("cam-1", ["person"])
        assert route.called
        request_body = json.loads(route.calls[0].request.content)
        assert request_body == {"smartDetectSettings": {"objectTypes": ["person"]}}


class TestGetNvr:
    @respx.mock
    async def test_get_nvr_calls_correct_endpoint(self, client):
        route = respx.get(f"{API_PREFIX}nvrs").mock(return_value=httpx.Response(200, json=FIXTURES["nvr"]))
        result = await client.get_nvr()
        assert route.called
        assert result == FIXTURES["nvr"]


class TestUpdateChime:
    @respx.mock
    async def test_update_chime_sends_patch(self, client):
        payload = {"volume": 75}
        route = respx.patch(f"{API_PREFIX}chimes/ch1").mock(
            return_value=httpx.Response(200, json={"id": "ch1", **payload})
        )
        result = await client.update_chime("ch1", payload)
        assert route.called
        request_body = json.loads(route.calls[0].request.content)
        assert request_body == payload
        assert result["id"] == "ch1"


class TestUpdateLight:
    @respx.mock
    async def test_update_light_sends_patch(self, client):
        payload = {"lightModeSettings": {"mode": "motion"}}
        route = respx.patch(f"{API_PREFIX}lights/l1").mock(
            return_value=httpx.Response(200, json={"id": "l1", **payload})
        )
        result = await client.update_light("l1", payload)
        assert route.called
        request_body = json.loads(route.calls[0].request.content)
        assert request_body == payload
        assert result["id"] == "l1"


class TestUpdateSensor:
    @respx.mock
    async def test_update_sensor_sends_patch(self, client):
        payload = {"mountType": "door"}
        route = respx.patch(f"{API_PREFIX}sensors/s1").mock(
            return_value=httpx.Response(200, json={"id": "s1", **payload})
        )
        result = await client.update_sensor("s1", payload)
        assert route.called
        request_body = json.loads(route.calls[0].request.content)
        assert request_body == payload
        assert result["id"] == "s1"


class TestValidateConnection:
    @respx.mock
    async def test_validate_returns_true_on_success(self, client):
        respx.get(f"{API_PREFIX}nvrs").mock(return_value=httpx.Response(200, json=FIXTURES["nvr"]))
        result = await client.validate_connection()
        assert result is True

    @respx.mock
    async def test_validate_returns_false_on_failure(self, client):
        respx.get(f"{API_PREFIX}nvrs").mock(side_effect=httpx.ConnectError("Connection refused"))
        result = await client.validate_connection()
        assert result is False

    @respx.mock
    async def test_validate_stashes_exception_on_failure(self, client):
        """When validate_connection catches an error and returns False, the
        exception is stashed on _last_validation_error so the server
        lifespan can surface the failure class in its WARN log (#104).
        """
        from unifi_mcp.errors import UniFiConnectionError

        respx.get(f"{API_PREFIX}nvrs").mock(side_effect=httpx.ConnectError("refused"))
        assert await client.validate_connection() is False
        assert isinstance(client._last_validation_error, UniFiConnectionError)

    @respx.mock
    async def test_validate_clears_stashed_exception_on_success(self, client):
        """A successful validate after a prior failure must clear the
        stashed exception so stale errors don't leak into later WARN logs.
        """
        # First call fails and stashes the exception.
        respx.get(f"{API_PREFIX}nvrs").mock(side_effect=httpx.ConnectError("refused"))
        await client.validate_connection()
        assert client._last_validation_error is not None

        # Reset and simulate success.
        respx.reset()
        respx.get(f"{API_PREFIX}nvrs").mock(return_value=httpx.Response(200, json=FIXTURES["nvr"]))
        assert await client.validate_connection() is True
        assert client._last_validation_error is None
