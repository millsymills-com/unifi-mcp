"""Tests for the Site Manager API client."""

from __future__ import annotations

import httpx
import pytest
import respx

from unifi_mcp.clients.site_manager import SITE_MANAGER_BASE_URL, SiteManagerClient

API_PREFIX = f"{SITE_MANAGER_BASE_URL}/v1/"


@pytest.fixture
def client():
    return SiteManagerClient(
        api_key="test-sm-key",
        timeout=5,
        max_retries=2,
    )


class TestListHosts:
    @respx.mock
    async def test_list_hosts_calls_correct_endpoint(self, client):
        route = respx.get(f"{API_PREFIX}hosts").mock(
            return_value=httpx.Response(200, json={"data": [{"id": "host-1", "name": "UDR Ultra"}]})
        )
        result = await client.list_hosts()
        assert route.called
        assert result == {"data": [{"id": "host-1", "name": "UDR Ultra"}]}

    @respx.mock
    async def test_list_hosts_sends_api_key_header(self, client):
        route = respx.get(f"{API_PREFIX}hosts").mock(return_value=httpx.Response(200, json={"data": []}))
        await client.list_hosts()
        assert route.calls[0].request.headers["X-API-Key"] == "test-sm-key"


class TestListSites:
    @respx.mock
    async def test_list_sites_calls_correct_endpoint(self, client):
        route = respx.get(f"{API_PREFIX}sites").mock(
            return_value=httpx.Response(200, json={"data": [{"id": "site-1", "name": "Default"}]})
        )
        result = await client.list_sites()
        assert route.called
        assert result == {"data": [{"id": "site-1", "name": "Default"}]}


class TestListDevices:
    @respx.mock
    async def test_list_devices_without_host_id(self, client):
        route = respx.get(f"{API_PREFIX}devices").mock(
            return_value=httpx.Response(200, json={"data": [{"id": "dev-1"}]})
        )
        result = await client.list_devices()
        assert route.called
        assert result == {"data": [{"id": "dev-1"}]}
        # No query params when host_id is None
        assert "hostId" not in str(route.calls[0].request.url.params)

    @respx.mock
    async def test_list_devices_with_host_id(self, client):
        route = respx.get(f"{API_PREFIX}devices").mock(
            return_value=httpx.Response(200, json={"data": [{"id": "dev-1", "hostId": "host-1"}]})
        )
        result = await client.list_devices(host_id="host-1")
        assert route.called
        assert result == {"data": [{"id": "dev-1", "hostId": "host-1"}]}
        assert route.calls[0].request.url.params["hostId"] == "host-1"


class TestValidateConnection:
    @respx.mock
    async def test_validate_returns_true_on_success(self, client):
        respx.get(f"{API_PREFIX}hosts").mock(return_value=httpx.Response(200, json={"data": []}))
        result = await client.validate_connection()
        assert result is True

    @respx.mock
    async def test_validate_returns_false_on_failure(self, client):
        respx.get(f"{API_PREFIX}hosts").mock(return_value=httpx.Response(401, text="Unauthorized"))
        result = await client.validate_connection()
        assert result is False


class TestSSLVerification:
    def test_ssl_verification_is_enabled(self, client):
        # Site Manager uses a public cloud API, so SSL must be verified
        verify = client._client._transport._pool._ssl_context
        assert verify is not None


class TestPathPrefix:
    def test_path_prefix_is_v1(self, client):
        assert client._path_prefix == "/v1/"


EA_PREFIX = f"{SITE_MANAGER_BASE_URL}/ea/"


class TestGetHost:
    @respx.mock
    async def test_get_host_calls_correct_endpoint(self, client):
        route = respx.get(f"{API_PREFIX}hosts/host-1").mock(
            return_value=httpx.Response(200, json={"data": {"id": "host-1", "hostName": "UDR"}})
        )
        result = await client.get_host("host-1")
        assert route.called
        assert result == {"data": {"id": "host-1", "hostName": "UDR"}}
        assert route.calls[0].request.headers["X-API-Key"] == "test-sm-key"

    @respx.mock
    async def test_get_host_404_raises_typed_error(self, client):
        from unifi_mcp.errors import UniFiNotFoundError

        respx.get(f"{API_PREFIX}hosts/missing").mock(return_value=httpx.Response(404, json={"message": "not found"}))
        with pytest.raises(UniFiNotFoundError):
            await client.get_host("missing")


class TestGetIspMetrics:
    @respx.mock
    async def test_get_isp_metrics_path_and_no_params(self, client):
        route = respx.get(f"{API_PREFIX}isp-metrics/5m").mock(return_value=httpx.Response(200, json={"data": []}))
        result = await client.get_isp_metrics("5m")
        assert route.called
        assert result == {"data": []}
        assert route.calls[0].request.headers["X-API-Key"] == "test-sm-key"
        assert str(route.calls[0].request.url.params) == ""

    @respx.mock
    async def test_get_isp_metrics_forwards_only_set_params(self, client):
        route = respx.get(f"{API_PREFIX}isp-metrics/1h").mock(return_value=httpx.Response(200, json={"data": []}))
        await client.get_isp_metrics("1h", begin_timestamp="2026-01-01T00:00:00Z", duration="24h")
        params = route.calls[0].request.url.params
        assert params["beginTimestamp"] == "2026-01-01T00:00:00Z"
        assert params["duration"] == "24h"
        assert "endTimestamp" not in str(params)


class TestQueryIspMetrics:
    @respx.mock
    async def test_query_isp_metrics_posts_selector_body(self, client):
        route = respx.post(f"{API_PREFIX}isp-metrics/5m/query").mock(
            return_value=httpx.Response(200, json={"data": [{"metric": 1}]})
        )
        sites = [{"hostId": "h-1", "siteId": "s-1"}]
        result = await client.query_isp_metrics("5m", sites)
        assert route.called
        assert result == {"data": [{"metric": 1}]}
        import json

        assert json.loads(route.calls[0].request.content) == {"sites": sites}


class TestSdwanConfigs:
    @respx.mock
    async def test_list_sdwan_configs_uses_ea_prefix(self, client):
        route = respx.get(f"{EA_PREFIX}sd-wan-configs").mock(
            return_value=httpx.Response(200, json={"data": [{"id": "cfg-1"}]})
        )
        result = await client.list_sdwan_configs()
        assert route.called
        assert result == {"data": [{"id": "cfg-1"}]}
        assert route.calls[0].request.headers["X-API-Key"] == "test-sm-key"

    @respx.mock
    async def test_get_sdwan_config_uses_ea_prefix(self, client):
        route = respx.get(f"{EA_PREFIX}sd-wan-configs/cfg-1").mock(
            return_value=httpx.Response(200, json={"data": {"id": "cfg-1"}})
        )
        result = await client.get_sdwan_config("cfg-1")
        assert route.called
        assert result == {"data": {"id": "cfg-1"}}

    @respx.mock
    async def test_get_sdwan_config_status_uses_ea_prefix(self, client):
        route = respx.get(f"{EA_PREFIX}sd-wan-configs/cfg-1/status").mock(
            return_value=httpx.Response(200, json={"data": {"state": "DEPLOYED"}})
        )
        result = await client.get_sdwan_config_status("cfg-1")
        assert route.called
        assert result == {"data": {"state": "DEPLOYED"}}

    @respx.mock
    async def test_sdwan_config_404_raises_typed_error(self, client):
        from unifi_mcp.errors import UniFiNotFoundError

        respx.get(f"{EA_PREFIX}sd-wan-configs/missing").mock(
            return_value=httpx.Response(404, json={"message": "not found"})
        )
        with pytest.raises(UniFiNotFoundError):
            await client.get_sdwan_config("missing")


class TestEaPrefixRouting:
    """The ``/ea/`` surface must resolve beside ``/v1/``, never under it."""

    def test_ea_url_is_not_under_v1(self, client):
        assert client._url("sd-wan-configs", prefix=client._EA_PREFIX) == "/ea/sd-wan-configs"
        assert client._url("sd-wan-configs/cfg-1", prefix=client._EA_PREFIX) == "/ea/sd-wan-configs/cfg-1"
        assert client._url("sd-wan-configs/cfg-1/status", prefix=client._EA_PREFIX) == "/ea/sd-wan-configs/cfg-1/status"

    def test_v1_methods_still_resolve_under_v1(self, client):
        assert client._url("hosts") == "/v1/hosts"
        assert client._url("isp-metrics/5m") == "/v1/isp-metrics/5m"

    def test_ea_prefix_preserves_leading_slash_gate(self, client):
        from unifi_mcp.errors import UniFiBadRequestError

        with pytest.raises(UniFiBadRequestError):
            client._url("/sd-wan-configs", prefix=client._EA_PREFIX)
        with pytest.raises(UniFiBadRequestError):
            client._url("https://evil.example/x", prefix=client._EA_PREFIX)
