"""verify_ssl=True against a publicly-trusted root cert (#316, §3c).

Every TLS case that can be minted in-test is already covered hardware-free
(self-signed two-tier, three-tier chain building, out-of-order presentation —
#250/#310/#313/#314). The one case that cannot be reproduced locally is a leaf
issued by a **publicly-trusted root already in the default trust store** — a
real ACME/Let's Encrypt cert. Such a cert can't be minted for ``127.0.0.1``, so
this is inherently live-only.

This test points a client at a controller (or fronting proxy) served by a real
publicly-rooted cert, with ``verify_ssl=True`` and **no** custom CA bundle, and
confirms httpx completes the handshake against the default trust store and a
read tool call goes through.

    UNIFI_LIVE_PUBLIC_TLS_URL=https://unifi.example.com \
    UNIFI_LIVE_PUBLIC_TLS_API=<key> \
        uv run pytest tests/integration/test_public_tls_verify_ssl_live.py -v -m integration

Skips cleanly when the URL (or an API key) is not configured — there is no way
to synthesize a publicly-rooted cert for a loopback address.
"""

from __future__ import annotations

import logging
import os

import pytest

from unifi_mcp.clients.network import NetworkClient
from unifi_mcp.errors import UniFiAuthError, UniFiBadRequestError, UniFiNotFoundError

LOG = logging.getLogger(__name__)

pytestmark = pytest.mark.integration

# App-level errors that still prove the TLS handshake completed and the request
# reached the controller — i.e. verify_ssl=True validated the public cert. A
# cert-verification failure surfaces as UniFiConnectionError instead, which is
# deliberately NOT caught here so it fails the test.
_TLS_REACHED_APP = (UniFiAuthError, UniFiNotFoundError, UniFiBadRequestError)


def _public_tls_url() -> str:
    return os.environ.get("UNIFI_LIVE_PUBLIC_TLS_URL", "").strip()


def _public_tls_api_key() -> str:
    return os.environ.get("UNIFI_LIVE_PUBLIC_TLS_API", "").strip() or os.environ.get("UNIFI_NETWORK_API", "").strip()


@pytest.mark.skipif(
    not _public_tls_url(),
    reason="Set UNIFI_LIVE_PUBLIC_TLS_URL to a controller served by a publicly-rooted TLS cert",
)
class TestPublicTlsVerifySsl:
    """verify_ssl=True must validate a real public cert via the default trust store."""

    async def test_read_succeeds_over_public_cert(self):
        api_key = _public_tls_api_key()
        if not api_key:
            pytest.skip("No API key (UNIFI_LIVE_PUBLIC_TLS_API / UNIFI_NETWORK_API); cannot issue a tool call")

        client = NetworkClient(
            base_url=_public_tls_url(),
            api_key=api_key,
            site=os.environ.get("UNIFI_NETWORK_SITE", "default"),
            verify_ssl=True,
            timeout=int(os.environ.get("UNIFI_REQUEST_TIMEOUT", "30")),
            max_retries=int(os.environ.get("UNIFI_MAX_RETRIES", "3")),
        )
        try:
            # A UniFiConnectionError (cert verification failure) propagates and
            # fails the test — that is the regression this guards against.
            try:
                result = await client.list_devices()
            except _TLS_REACHED_APP as exc:
                LOG.warning("TLS handshake validated the public cert; app returned %s", type(exc).__name__)
                return
            assert isinstance(result, dict), "list_devices over a public cert must return a dict on success"
        finally:
            await client.close()
