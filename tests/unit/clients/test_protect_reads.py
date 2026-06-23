"""Tests for the Protect client read methods added in #407 (Phase 2)."""

from __future__ import annotations

import httpx
import pytest
import respx

from unifi_mcp.clients.protect import ProtectClient
from unifi_mcp.errors import UniFiNotFoundError

BASE_URL = "https://10.0.0.1:443"
API_PREFIX = f"{BASE_URL}/proxy/protect/integration/v1/"


@pytest.fixture
def client() -> ProtectClient:
    return ProtectClient(base_url=BASE_URL, api_key="test-protect-key", timeout=5, max_retries=1)


_GET_BY_ID = [
    ("get_chime", ("ch1",), "chimes/ch1", {"id": "ch1"}),
    ("get_light", ("l1",), "lights/l1", {"id": "l1"}),
    ("get_sensor", ("s1",), "sensors/s1", {"id": "s1"}),
    ("get_viewer", ("v1",), "viewers/v1", {"id": "v1"}),
    ("get_speaker", ("sp1",), "speakers/sp1", {"id": "sp1"}),
    ("get_siren", ("si1",), "sirens/si1", {"id": "si1"}),
    ("get_bridge", ("b1",), "bridges/b1", {"id": "b1"}),
    ("get_relay", ("r1",), "relays/r1", {"id": "r1"}),
    ("get_link_station", ("ls1",), "link-stations/ls1", {"id": "ls1"}),
    ("get_fob", ("f1",), "fobs/f1", {"id": "f1"}),
    ("get_alarm_hub", ("ah1",), "alarm-hubs/ah1", {"id": "ah1"}),
    ("get_liveview", ("lv1",), "liveviews/lv1", {"id": "lv1"}),
    ("get_user", ("u1",), "users/u1", {"id": "u1"}),
    ("get_ulp_user", ("uu1",), "ulp-users/uu1", {"id": "uu1"}),
    ("get_meta_info", (), "meta/info", {"version": "7.1.42"}),
    ("get_file_asset", ("logo",), "files/logo", {"type": "logo"}),
]

_LISTS = [
    ("list_speakers", "speakers"),
    ("list_sirens", "sirens"),
    ("list_bridges", "bridges"),
    ("list_relays", "relays"),
    ("list_link_stations", "link-stations"),
    ("list_fobs", "fobs"),
    ("list_alarm_hubs", "alarm-hubs"),
    ("list_liveviews", "liveviews"),
    ("list_arm_profiles", "arm-profiles"),
    ("list_users", "users"),
    ("list_ulp_users", "ulp-users"),
]


class TestReadEndpointsAndShape:
    @pytest.mark.parametrize(("method_name", "args", "endpoint", "payload"), _GET_BY_ID)
    @respx.mock
    async def test_get_endpoint(self, client, method_name, args, endpoint, payload):
        route = respx.get(f"{API_PREFIX}{endpoint}").mock(return_value=httpx.Response(200, json=payload))
        result = await getattr(client, method_name)(*args)
        assert route.called
        assert result == payload

    @pytest.mark.parametrize(("method_name", "endpoint"), _LISTS)
    @respx.mock
    async def test_list_endpoint(self, client, method_name, endpoint):
        payload = [{"id": "dev-1"}, {"id": "dev-2"}]
        route = respx.get(f"{API_PREFIX}{endpoint}").mock(return_value=httpx.Response(200, json=payload))
        result = await getattr(client, method_name)()
        assert route.called
        assert result == payload


class TestApiKeyHeader:
    @respx.mock
    async def test_get_user_sends_api_key_header(self, client):
        route = respx.get(f"{API_PREFIX}users/u1").mock(return_value=httpx.Response(200, json={"id": "u1"}))
        await client.get_user("u1")
        assert route.calls[0].request.headers["X-API-Key"] == "test-protect-key"


class TestRtspsStream:
    @respx.mock
    async def test_rtsps_stream_no_qualities(self, client):
        route = respx.get(f"{API_PREFIX}cameras/cam-1/rtsps-stream").mock(
            return_value=httpx.Response(200, json={"high": "rtsps://x"})
        )
        result = await client.get_rtsps_stream("cam-1")
        assert route.called
        assert "qualities" not in str(route.calls[0].request.url)
        assert result == {"high": "rtsps://x"}

    @respx.mock
    async def test_rtsps_stream_passes_qualities_param(self, client):
        route = respx.get(f"{API_PREFIX}cameras/cam-1/rtsps-stream").mock(
            return_value=httpx.Response(200, json={"high": "rtsps://x"})
        )
        await client.get_rtsps_stream("cam-1", qualities=["high", "medium"])
        url = str(route.calls[0].request.url)
        assert "qualities=high" in url
        assert "qualities=medium" in url

    @respx.mock
    async def test_rtsps_stream_404_raises_not_found(self, client):
        """A camera with no active stream returns 404 → typed exception."""
        respx.get(f"{API_PREFIX}cameras/cam-1/rtsps-stream").mock(return_value=httpx.Response(404, json={}))
        with pytest.raises(UniFiNotFoundError):
            await client.get_rtsps_stream("cam-1")


class TestErrorPath:
    @respx.mock
    async def test_get_chime_404_raises_not_found(self, client):
        respx.get(f"{API_PREFIX}chimes/missing").mock(return_value=httpx.Response(404, json={}))
        with pytest.raises(UniFiNotFoundError):
            await client.get_chime("missing")
