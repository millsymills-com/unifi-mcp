"""Live round-trip for ``unifi_network_update_settings`` named-arg paths (#211).

PR #208 (issue #202) introduced named scalar args for ``update_settings``.
The original mappings shipped against ``respx`` mocks only — live testing
on the UCG Ultra surfaced three issues that the named-arg surface now
reflects (see PR for #211 for the full evidence):

1. The bare ``PUT /rest/setting`` rejects multi-section bodies (HTTP 500).
   Correct shape is ``PUT /rest/setting/<section_key>`` with the section's
   partial body; the client now dispatches one PUT per top-level section.
2. ``locale.timezone`` and ``country.code`` are locked behind the
   integration API key — controller responds ``api.err.NoEdit``. The
   corresponding named args (``locale_timezone``, ``country_code``) were
   never functional and have been dropped from the tool signature.
3. ``ntp.ntp_server_1`` and ``ntp.ntp_server_2`` round-trip cleanly, as
   does ``mgmt.led_enabled``.

Surviving named args this test exercises:

* ``ntp_server_1``     → ``PUT /rest/setting/ntp`` with ``ntp_server_1``
* ``ntp_server_2``     → ``PUT /rest/setting/ntp`` with ``ntp_server_2``
* ``mgmt_led_enabled`` → ``PUT /rest/setting/mgmt`` with ``led_enabled``

Run manually::

    UNIFI_MODE=readwrite LIVE_TEST_WRITES=1 \\
        uv run pytest tests/integration/test_network_update_settings_live.py -v -m integration

Each parametrized case reads the current value for its field, picks the
alternate from a fixed two-value cycle, writes it through the tool layer,
re-reads, asserts the read-back matches, then restores the original value
in ``finally`` so a mid-test failure leaves the controller as it was found.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import pytest
from fastmcp import Client

from unifi_mcp.server import create_server

pytestmark = pytest.mark.integration

LOG = logging.getLogger(__name__)


def _writes_enabled() -> bool:
    return os.environ.get("UNIFI_MODE", "readonly").lower() == "readwrite" and os.environ.get(
        "LIVE_TEST_WRITES", ""
    ).strip() in {"1", "true", "yes"}


WRITE_GATE_REASON = "Set UNIFI_MODE=readwrite and LIVE_TEST_WRITES=1 to run write tests"


@pytest.fixture
async def live_client():
    """A FastMCP ``Client`` connected to a server built from real env config."""
    if not os.environ.get("UNIFI_NETWORK_API"):
        pytest.skip("UNIFI_NETWORK_API not set; skipping live update_settings test")
    server = create_server()
    async with Client(server) as client:
        yield client


async def _invoke(client: Client, name: str, args: dict[str, Any] | None = None) -> Any:
    result = await client.call_tool(name, args or {})
    return getattr(result, "structured_content", None) or getattr(result, "data", None) or result


def _extract_section(settings: Any, section_key: str) -> dict[str, Any]:
    """Pull the ``key == section_key`` document from a ``get_settings`` response.

    ``GET /rest/setting`` returns ``{"data": [<section doc>, ...]}`` where each
    section is identified by its ``key`` field. Some firmwares wrap the list
    under ``result`` instead when surfaced through fastmcp's structured-content.
    """
    container: list[dict[str, Any]] | None = None
    if isinstance(settings, dict):
        for key in ("data", "result"):
            value = settings.get(key)
            if isinstance(value, list):
                container = value
                break
    elif isinstance(settings, list):
        container = settings
    if container is None:
        pytest.fail(f"Unexpected get_settings shape: {type(settings).__name__} {settings!r}")
    for section in container:
        if isinstance(section, dict) and section.get("key") == section_key:
            return section
    pytest.fail(f"Settings response had no section with key={section_key!r}; available keys: {_keys(container)}")


def _keys(sections: list[dict[str, Any]]) -> list[str]:
    return [s.get("key", "?") for s in sections if isinstance(s, dict)]


_FIELD_CASES: tuple[tuple[str, str, str, Any, Any], ...] = (
    ("ntp_server_1", "ntp", "ntp_server_1", "0.pool.ntp.org", "time.google.com"),
    ("ntp_server_2", "ntp", "ntp_server_2", "1.pool.ntp.org", "time.cloudflare.com"),
    ("mgmt_led_enabled", "mgmt", "led_enabled", True, False),
)


@pytest.mark.live_write
@pytest.mark.write_gated
@pytest.mark.skipif(not _writes_enabled(), reason=WRITE_GATE_REASON)
class TestUpdateSettingsRoundTrip:
    """Round-trip every named scalar through the live controller.

    Each iteration: read → flip-to-alternate → write → wait → read-back →
    assert → restore-in-finally. The restore is best-effort: failures are
    logged as WARNING so they don't shadow an assertion failure from the
    body of the test.
    """

    @pytest.mark.parametrize(
        ("named_arg", "section_key", "field", "option_a", "option_b"),
        _FIELD_CASES,
        ids=[case[0] for case in _FIELD_CASES],
    )
    async def test_named_arg_round_trips(
        self,
        live_client: Client,
        named_arg: str,
        section_key: str,
        field: str,
        option_a: Any,
        option_b: Any,
    ) -> None:
        before = await _invoke(live_client, "unifi_network_get_settings")
        section = _extract_section(before, section_key)
        original = section.get(field)
        target = option_b if original == option_a else option_a
        LOG.warning(
            "update_settings round-trip: arg=%s path=%s.%s original=%r target=%r",
            named_arg,
            section_key,
            field,
            original,
            target,
        )

        try:
            applied = await _invoke(live_client, "unifi_network_update_settings", {named_arg: target})
            LOG.warning("update_settings(%s=%r) response: %r", named_arg, target, applied)

            await asyncio.sleep(2)

            after = await _invoke(live_client, "unifi_network_get_settings")
            after_value = _extract_section(after, section_key).get(field)
            assert after_value == target, (
                f"Read-back mismatch for {section_key}.{field}: set {target!r}, read back {after_value!r}"
            )
        finally:
            if original is not None:
                try:
                    await _invoke(live_client, "unifi_network_update_settings", {named_arg: original})
                except Exception as exc:
                    LOG.warning(
                        "Failed to restore %s.%s to original %r: %s",
                        section_key,
                        field,
                        original,
                        exc,
                    )
