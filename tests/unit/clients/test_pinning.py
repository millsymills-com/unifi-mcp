"""Tests for the certificate-pinning transport.

These tests don't exercise a real TLS handshake — they construct an
``httpx.Response`` whose ``network_stream`` extension is a stub that returns
a controlled ``ssl_object``. That's enough to verify the pin comparison
logic without standing up a live HTTPS server.
"""

from __future__ import annotations

import hashlib
import ssl
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest

from unifi_mcp.clients._pinning import (
    CertPinningTransport,
    build_pinning_ssl_context,
    fingerprint_of,
)
from unifi_mcp.errors import UniFiAuthError

# Deterministic fake DER bytes — content doesn't matter, only its hash.
_FAKE_DER = b"\x30\x82\x01\x00fake-cert-bytes-for-testing"
_FAKE_FP = hashlib.sha256(_FAKE_DER).hexdigest()


class _FakeSSLObject:
    def __init__(self, der: bytes | None) -> None:
        self._der = der

    def getpeercert(self, binary_form: bool = False) -> bytes | None:
        assert binary_form is True
        return self._der


class _FakeNetworkStream:
    def __init__(self, ssl_object: object | None) -> None:
        self._ssl_object = ssl_object

    def get_extra_info(self, info: str) -> object | None:
        if info == "ssl_object":
            return self._ssl_object
        return None


def _make_response(ssl_object: object | None) -> httpx.Response:
    """Build an httpx.Response carrying a stubbed ``network_stream`` extension."""
    return httpx.Response(
        status_code=200,
        extensions={"network_stream": _FakeNetworkStream(ssl_object)},
    )


class TestBuildPinningSSLContext:
    def test_disables_hostname_and_chain_verification(self):
        ctx = build_pinning_ssl_context()
        assert ctx.check_hostname is False
        assert ctx.verify_mode == ssl.CERT_NONE


class TestFingerprintOf:
    def test_canonical_hex(self):
        assert fingerprint_of(_FAKE_DER) == _FAKE_FP
        assert len(fingerprint_of(_FAKE_DER)) == 64


class TestVerifyPin:
    """``_verify_pin`` is the only post-handshake logic worth unit-testing."""

    def test_passes_on_matching_pin(self):
        transport = CertPinningTransport(expected_fingerprint=_FAKE_FP)
        response = _make_response(_FakeSSLObject(_FAKE_DER))
        # No exception = pass.
        transport._verify_pin(response)

    def test_accepts_uppercase_pin_input(self):
        """The transport normalizes the configured pin to lowercase."""
        transport = CertPinningTransport(expected_fingerprint=_FAKE_FP.upper())
        response = _make_response(_FakeSSLObject(_FAKE_DER))
        transport._verify_pin(response)

    def test_raises_on_mismatch(self):
        bad_pin = "b" * 64
        transport = CertPinningTransport(expected_fingerprint=bad_pin)
        response = _make_response(_FakeSSLObject(_FAKE_DER))
        with pytest.raises(UniFiAuthError) as exc:
            transport._verify_pin(response)
        assert "pin mismatch" in str(exc.value)
        assert bad_pin in str(exc.value)
        assert _FAKE_FP in str(exc.value)

    def test_raises_when_no_ssl_object(self):
        transport = CertPinningTransport(expected_fingerprint=_FAKE_FP)
        response = _make_response(None)
        with pytest.raises(UniFiAuthError, match="no ssl_object"):
            transport._verify_pin(response)

    def test_raises_when_peer_cert_empty(self):
        transport = CertPinningTransport(expected_fingerprint=_FAKE_FP)
        response = _make_response(_FakeSSLObject(b""))
        with pytest.raises(UniFiAuthError, match="no certificate"):
            transport._verify_pin(response)


class TestCertPinningTransportHandlesRequests:
    """End-to-end: ``handle_async_request`` should call ``_verify_pin``."""

    async def test_handle_async_request_invokes_verification(self, monkeypatch):
        transport = CertPinningTransport(expected_fingerprint=_FAKE_FP)

        async def fake_super(self_: Any, request: httpx.Request) -> httpx.Response:
            return _make_response(_FakeSSLObject(_FAKE_DER))

        monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", fake_super)
        request = httpx.Request("GET", "https://example.invalid/")
        response = await transport.handle_async_request(request)
        assert response.status_code == 200

    async def test_handle_async_request_propagates_mismatch(self, monkeypatch):
        transport = CertPinningTransport(expected_fingerprint="c" * 64)

        async def fake_super(self_: Any, request: httpx.Request) -> httpx.Response:
            return _make_response(_FakeSSLObject(_FAKE_DER))

        monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", fake_super)
        request = httpx.Request("GET", "https://example.invalid/")
        with pytest.raises(UniFiAuthError, match="pin mismatch"):
            await transport.handle_async_request(request)


class TestTeardownOnMismatch:
    """#189: pin mismatch must close the response and evict the pool entry.

    Cert pinning runs *after* the TLS handshake and request send, so the API
    key has already been written by the time the pin check fires. Tearing the
    suspect connection down deterministically prevents reuse.
    """

    async def test_mismatch_closes_response(self, monkeypatch):
        transport = CertPinningTransport(expected_fingerprint="c" * 64)
        response = _make_response(_FakeSSLObject(_FAKE_DER))
        response.aclose = AsyncMock()  # ty: ignore[invalid-assignment]

        async def fake_super(self_: Any, request: httpx.Request) -> httpx.Response:
            return response

        monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", fake_super)
        request = httpx.Request("GET", "https://example.invalid/")
        with pytest.raises(UniFiAuthError, match="pin mismatch"):
            await transport.handle_async_request(request)
        response.aclose.assert_awaited_once()

    async def test_mismatch_evicts_matching_pool_connection(self, monkeypatch):
        transport = CertPinningTransport(expected_fingerprint="c" * 64)
        response = _make_response(_FakeSSLObject(_FAKE_DER))

        class _FakeOrigin:
            host = b"example.invalid"
            port = 443

        class _FakeConn:
            def __init__(self) -> None:
                self._origin = _FakeOrigin()
                self.aclose = AsyncMock()

        matching = _FakeConn()

        # A non-matching connection for a different host should NOT be touched.
        class _OtherOrigin:
            host = b"other.invalid"
            port = 443

        non_matching = _FakeConn()
        non_matching._origin = _OtherOrigin()  # ty: ignore[invalid-assignment]

        class _FakePool:
            def __init__(self, conns: list[_FakeConn]) -> None:
                self.connections = conns

        transport._pool = _FakePool([matching, non_matching])  # ty: ignore[invalid-assignment]

        async def fake_super(self_: Any, request: httpx.Request) -> httpx.Response:
            return response

        monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", fake_super)
        request = httpx.Request("GET", "https://example.invalid/")
        with pytest.raises(UniFiAuthError, match="pin mismatch"):
            await transport.handle_async_request(request)
        matching.aclose.assert_awaited_once()
        non_matching.aclose.assert_not_awaited()

    async def test_mismatch_without_pool_still_raises(self, monkeypatch):
        """When the transport exposes no connection pool, teardown closes only
        the response and lets the original error through unchanged."""
        transport = CertPinningTransport(expected_fingerprint="c" * 64)
        transport._pool = None  # ty: ignore[invalid-assignment]
        response = _make_response(_FakeSSLObject(_FAKE_DER))
        response.aclose = AsyncMock()  # ty: ignore[invalid-assignment]

        async def fake_super(self_: Any, request: httpx.Request) -> httpx.Response:
            return response

        monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", fake_super)
        request = httpx.Request("GET", "https://example.invalid/")
        with pytest.raises(UniFiAuthError, match="pin mismatch"):
            await transport.handle_async_request(request)
        response.aclose.assert_awaited_once()

    async def test_mismatch_when_pool_connections_raise(self, monkeypatch):
        """If enumerating the pool's connections raises, teardown swallows it
        and the original ``UniFiAuthError`` reaches the caller."""
        transport = CertPinningTransport(expected_fingerprint="c" * 64)
        response = _make_response(_FakeSSLObject(_FAKE_DER))

        class _ExplodingPool:
            @property
            def connections(self) -> list[object]:
                raise RuntimeError("pool snapshot unavailable")

        transport._pool = _ExplodingPool()  # ty: ignore[invalid-assignment]

        async def fake_super(self_: Any, request: httpx.Request) -> httpx.Response:
            return response

        monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", fake_super)
        request = httpx.Request("GET", "https://example.invalid/")
        with pytest.raises(UniFiAuthError, match="pin mismatch"):
            await transport.handle_async_request(request)

    async def test_mismatch_skips_connection_without_origin(self, monkeypatch):
        """A pooled connection with no ``_origin`` is skipped, not closed —
        we can't confirm it serves the suspect origin, so leave it alone."""
        transport = CertPinningTransport(expected_fingerprint="c" * 64)
        response = _make_response(_FakeSSLObject(_FAKE_DER))

        class _OriginlessConn:
            def __init__(self) -> None:
                self._origin = None
                self.aclose = AsyncMock()

        originless = _OriginlessConn()

        class _FakePool:
            def __init__(self, conns: list[object]) -> None:
                self.connections = conns

        transport._pool = _FakePool([originless])  # ty: ignore[invalid-assignment]

        async def fake_super(self_: Any, request: httpx.Request) -> httpx.Response:
            return response

        monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", fake_super)
        request = httpx.Request("GET", "https://example.invalid/")
        with pytest.raises(UniFiAuthError, match="pin mismatch"):
            await transport.handle_async_request(request)
        originless.aclose.assert_not_awaited()

    async def test_success_path_does_not_teardown(self, monkeypatch):
        transport = CertPinningTransport(expected_fingerprint=_FAKE_FP)
        response = _make_response(_FakeSSLObject(_FAKE_DER))
        response.aclose = AsyncMock()  # ty: ignore[invalid-assignment]

        async def fake_super(self_: Any, request: httpx.Request) -> httpx.Response:
            return response

        monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", fake_super)
        request = httpx.Request("GET", "https://example.invalid/")
        result = await transport.handle_async_request(request)
        assert result is response
        response.aclose.assert_not_awaited()


class TestClientIntegration:
    """Pinning should be wired into ``NetworkClient`` / ``ProtectClient``."""

    def test_network_client_uses_pinning_transport_when_fingerprint_set(self):
        from unifi_mcp.clients.network import NetworkClient

        client = NetworkClient(
            base_url="https://10.0.0.1:443",
            api_key="k",
            cert_fingerprint=_FAKE_FP,
        )
        # The underlying transport on the AsyncClient should be ours.
        assert isinstance(client._client._transport, CertPinningTransport)

    def test_protect_client_uses_pinning_transport_when_fingerprint_set(self):
        from unifi_mcp.clients.protect import ProtectClient

        client = ProtectClient(
            base_url="https://10.0.0.1:443",
            api_key="k",
            cert_fingerprint=_FAKE_FP,
        )
        assert isinstance(client._client._transport, CertPinningTransport)

    def test_no_pinning_transport_when_fingerprint_absent(self):
        from unifi_mcp.clients.network import NetworkClient

        client = NetworkClient(
            base_url="https://10.0.0.1:443",
            api_key="k",
        )
        assert not isinstance(client._client._transport, CertPinningTransport)
