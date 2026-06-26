"""Regression tests for path-traversal hardening (#145).

These tests pin the contract that agent-controlled IDs cannot escape the
client's ``_path_prefix`` via ``../`` segments, query-string injection,
or other URL-syntax tricks. The ``BaseUniFiClient._segment`` helper rejects
or percent-encodes such values before they reach ``httpx``.
"""

from __future__ import annotations

import httpx
import pytest
import respx
from pydantic import ValidationError

from unifi_mcp.clients.network import NetworkClient
from unifi_mcp.clients.protect import ProtectClient
from unifi_mcp.config import UniFiConfig
from unifi_mcp.errors import UniFiBadRequestError

BASE_URL = "https://10.0.0.1:443"
SITE = "default"
NETWORK_PREFIX = f"/proxy/network/api/s/{SITE}/"
PROTECT_PREFIX = "/proxy/protect/integration/v1/"


@pytest.fixture
def network_client():
    return NetworkClient(
        base_url=BASE_URL,
        api_key="test-net-key",
        site=SITE,
        timeout=5,
        max_retries=1,
    )


@pytest.fixture
def protect_client():
    return ProtectClient(
        base_url=BASE_URL,
        api_key="test-prot-key",
        timeout=5,
        max_retries=1,
    )


class TestNetworkPathTraversal:
    async def test_get_wlan_traversal_rejected(self, network_client):
        """Traversal payload from issue #145 must raise before any HTTP call."""
        traversal = "../../../../proxy/protect/integration/v1/cameras"
        with respx.mock(assert_all_called=False) as router:
            router.route().mock(return_value=httpx.Response(200, json={}))
            with pytest.raises(UniFiBadRequestError):
                await network_client.get_wlan(traversal)
            assert len(router.calls) == 0, "no HTTP request should leave the client"

    async def test_get_wlan_query_injection_rejected(self, network_client):
        """``?`` is percent-encoded so it can't open a new query string."""
        with respx.mock(assert_all_called=False) as router:
            router.route().mock(return_value=httpx.Response(200, json={}))
            # `_segment` quotes `?` -> `%3F` and `=` -> `%3D` so the upstream
            # sees one literal segment instead of a path + query split.
            await network_client.get_wlan("abc?foo=bar")
            assert len(router.calls) == 1
            raw_path = router.calls[0].request.url.raw_path.decode("ascii")
            assert raw_path.startswith(NETWORK_PREFIX), raw_path
            assert raw_path.endswith("rest/wlanconf/abc%3Ffoo%3Dbar"), raw_path
            # No new query component was created.
            assert router.calls[0].request.url.query == b"", router.calls[0].request.url

    async def test_get_wlan_slash_rejected(self, network_client):
        """Embedded ``/`` would create a new path segment — rejected."""
        with respx.mock(assert_all_called=False) as router:
            router.route().mock(return_value=httpx.Response(200, json={}))
            with pytest.raises(UniFiBadRequestError):
                await network_client.get_wlan("abc/def")
            assert len(router.calls) == 0

    async def test_get_wlan_empty_rejected(self, network_client):
        with respx.mock(assert_all_called=False) as router:
            router.route().mock(return_value=httpx.Response(200, json={}))
            with pytest.raises(UniFiBadRequestError):
                await network_client.get_wlan("")
            assert len(router.calls) == 0

    async def test_update_wlan_traversal_rejected(self, network_client):
        with respx.mock(assert_all_called=False) as router:
            router.route().mock(return_value=httpx.Response(200, json={}))
            with pytest.raises(UniFiBadRequestError):
                await network_client.update_wlan("../foo", {"name": "x"})
            assert len(router.calls) == 0

    async def test_delete_network_traversal_rejected(self, network_client):
        with respx.mock(assert_all_called=False) as router:
            router.route().mock(return_value=httpx.Response(200, json={}))
            with pytest.raises(UniFiBadRequestError):
                await network_client.delete_network("..")
            assert len(router.calls) == 0


class TestProtectPathTraversal:
    async def test_get_camera_traversal_rejected(self, protect_client):
        with respx.mock(assert_all_called=False) as router:
            router.route().mock(return_value=httpx.Response(200, json={}))
            with pytest.raises(UniFiBadRequestError):
                await protect_client.get_camera("../../api/nvr")
            assert len(router.calls) == 0

    async def test_update_camera_traversal_rejected(self, protect_client):
        """Issue #145's worked example: ``update_camera`` traversal payload."""
        with respx.mock(assert_all_called=False) as router:
            router.route().mock(return_value=httpx.Response(200, json={}))
            with pytest.raises(UniFiBadRequestError):
                await protect_client.update_camera("../../api/nvr", {"name": "x"})
            assert len(router.calls) == 0

    async def test_get_snapshot_path_stays_within_prefix(self, protect_client):
        """Even a benign ID is encoded; no path-prefix escape possible."""
        with respx.mock(assert_all_called=False) as router:
            router.route().mock(return_value=httpx.Response(200, content=b"jpegbytes"))
            await protect_client.get_snapshot("cam1", max_bytes=1024)
            assert len(router.calls) == 1
            raw_path = router.calls[0].request.url.raw_path.decode("ascii")
            assert raw_path.startswith(PROTECT_PREFIX), raw_path
            assert raw_path == f"{PROTECT_PREFIX}cameras/cam1/snapshot", raw_path


class TestPercentEncodedTraversal:
    """Pre-encoded ``%2e%2e`` payloads must not decode back to ``..`` upstream.

    ``_segment`` escapes the literal ``%`` to ``%25``, so a payload like
    ``%2e%2e`` reaches the server as ``%252e%252e`` (a literal seven-char
    segment containing the characters ``%``, ``2``, ``e``, ``%``, ``2``,
    ``e``) and cannot be path-decoded into ``..``.
    """

    async def test_percent_encoded_dotdot_is_double_encoded(self, network_client):
        with respx.mock(assert_all_called=False) as router:
            router.route().mock(return_value=httpx.Response(200, json={}))
            await network_client.get_wlan("%2e%2e")
            assert len(router.calls) == 1
            raw_path = router.calls[0].request.url.raw_path.decode("ascii")
            assert raw_path == f"{NETWORK_PREFIX}rest/wlanconf/%252e%252e", raw_path

    async def test_percent_encoded_slash_is_double_encoded(self, network_client):
        with respx.mock(assert_all_called=False) as router:
            router.route().mock(return_value=httpx.Response(200, json={}))
            await network_client.get_wlan("foo%2Fbar")
            assert len(router.calls) == 1
            raw_path = router.calls[0].request.url.raw_path.decode("ascii")
            assert raw_path == f"{NETWORK_PREFIX}rest/wlanconf/foo%252Fbar", raw_path

    async def test_nul_byte_rejected(self, network_client):
        with respx.mock(assert_all_called=False) as router:
            router.route().mock(return_value=httpx.Response(200, json={}))
            with pytest.raises(UniFiBadRequestError):
                await network_client.get_wlan("abc\x00def")
            assert len(router.calls) == 0

    async def test_newline_rejected(self, network_client):
        with respx.mock(assert_all_called=False) as router:
            router.route().mock(return_value=httpx.Response(200, json={}))
            with pytest.raises(UniFiBadRequestError):
                await network_client.get_wlan("abc\ndef")
            assert len(router.calls) == 0


class TestSiteConfigValidation:
    def test_bad_site_with_slash_rejected(self):
        with pytest.raises(ValidationError, match="invalid unifi_network_site"):
            UniFiConfig(_env_file=None, unifi_network_site="bad/site")

    def test_bad_site_with_traversal_rejected(self):
        with pytest.raises(ValidationError, match="invalid unifi_network_site"):
            UniFiConfig(_env_file=None, unifi_network_site="..")

    def test_bad_site_with_query_char_rejected(self):
        with pytest.raises(ValidationError, match="invalid unifi_network_site"):
            UniFiConfig(_env_file=None, unifi_network_site="default?evil=1")

    def test_empty_site_rejected(self):
        with pytest.raises(ValidationError, match="invalid unifi_network_site"):
            UniFiConfig(_env_file=None, unifi_network_site="")

    def test_valid_site_accepted(self):
        config = UniFiConfig(_env_file=None, unifi_network_site="my-site_1")
        assert config.unifi_network_site == "my-site_1"
