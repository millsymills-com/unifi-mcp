"""Retry/backoff behavior under a real network fault (#315, §2c).

The retry *timing* and decorator config are pinned by deterministic unit tests
with mocked sleeps (#255). What those can't show is the loop behaving on a real
socket against an unreachable endpoint. This module points a client at a
blackhole address and asserts, on the wire, that:

- a GET retries the transient failure and then surfaces a typed ``UniFiError``
  after the budget is exhausted (retry count + final typed error), and
- when the fault manifests as a timeout, a non-idempotent verb does *not*
  retry (the GET/HEAD-only timeout-retry split holds on a real socket).

No live UniFi credentials are required — the target never accepts a connection,
so the request shape and auth are irrelevant. Gated behind
``LIVE_TEST_FAULT_INJECTION=1`` because it does multi-second real socket I/O
with backoff sleeps and has no place in the fast unit suite.

    LIVE_TEST_FAULT_INJECTION=1 uv run pytest \
        tests/integration/test_retry_fault_injection_live.py -v -m integration

The default target is ``192.0.2.1`` (RFC 5737 TEST-NET-1, guaranteed
unrouted). Override with ``LIVE_TEST_BLACKHOLE_TARGET=host[:port]`` to point at
a genuinely blackholed endpoint on your network (e.g. one fronted by
``iptables -j DROP`` / ``tc netem loss 100%``) for a more faithful drop.

Scope: this covers the blackhole/exhaustion case without root. The
``tc netem delay`` latency-injection variant (asserting the same split under
induced latency rather than a full drop) still needs root-level tooling and is
tracked separately on #315.
"""

from __future__ import annotations

import logging
import os

import pytest

from unifi_mcp.clients.network import NetworkClient
from unifi_mcp.errors import UniFiConnectionError, UniFiTimeoutError

BASE_LOGGER = "unifi_mcp.clients.base"
_DEFAULT_TARGET = "192.0.2.1:443"
_MAX_RETRIES = 3
_TIMEOUT_SECONDS = 2

pytestmark = pytest.mark.integration


def _fault_injection_enabled() -> bool:
    return os.environ.get("LIVE_TEST_FAULT_INJECTION", "").strip().lower() in {"1", "true", "yes", "on"}


FAULT_GATE_REASON = "Set LIVE_TEST_FAULT_INJECTION=1 to run real-socket retry tests against a blackhole address"


def _blackhole_base_url() -> str:
    target = os.environ.get("LIVE_TEST_BLACKHOLE_TARGET", "").strip() or _DEFAULT_TARGET
    host, _, port = target.partition(":")
    return f"https://{host}:{port or '443'}"


def _retry_warnings(records: list[logging.LogRecord]) -> list[logging.LogRecord]:
    """Tenacity's ``before_sleep_log`` emits one 'Retrying ...' WARNING per backoff sleep."""
    return [r for r in records if "Retrying" in r.getMessage()]


@pytest.mark.skipif(not _fault_injection_enabled(), reason=FAULT_GATE_REASON)
class TestRetryUnderRealFault:
    """Exercise ``BaseUniFiClient._request``'s retry loop against a live blackhole."""

    def _client(self) -> NetworkClient:
        return NetworkClient(
            base_url=_blackhole_base_url(),
            api_key="unused-no-connection-is-made",
            site="default",
            verify_ssl=False,
            timeout=_TIMEOUT_SECONDS,
            max_retries=_MAX_RETRIES,
        )

    async def test_get_retries_then_surfaces_typed_error(self, caplog):
        """A GET retries the transient fault, then raises a typed error after exhaustion."""
        client = self._client()
        caplog.set_level(logging.WARNING, logger=BASE_LOGGER)
        try:
            with pytest.raises(UniFiConnectionError):
                await client._request("GET", "sites")
        finally:
            await client.close()

        retries = _retry_warnings(caplog.records)
        assert len(retries) == _MAX_RETRIES - 1, (
            f"expected {_MAX_RETRIES - 1} retry sleeps before exhaustion, saw {len(retries)}: "
            f"{[r.getMessage() for r in retries]}"
        )

    async def test_non_idempotent_does_not_retry_on_timeout(self, caplog):
        """A POST must not retry a timeout (the GET/HEAD-only timeout-retry split).

        Only observable when the blackhole yields a timeout; a bare connect
        error is retried for every verb, so we skip rather than assert a split
        that doesn't apply to that fault shape.
        """
        client = self._client()
        caplog.set_level(logging.WARNING, logger=BASE_LOGGER)
        try:
            with pytest.raises(UniFiConnectionError) as exc_info:
                await client._request("POST", "sites")
        finally:
            await client.close()

        if not isinstance(exc_info.value, UniFiTimeoutError):
            pytest.skip(
                "blackhole produced a connect error, not a timeout; the idempotency "
                "split only governs timeouts, so it isn't observable with this fault shape"
            )
        assert _retry_warnings(caplog.records) == [], "non-idempotent POST must not retry a timeout"
