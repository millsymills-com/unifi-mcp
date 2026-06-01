"""Tests for the base UniFi API client."""

import asyncio
import logging
import urllib.parse

import httpx
import pytest
import respx

from unifi_mcp.clients.base import _MIN_SCRUBBABLE_SECRET_LEN, BaseUniFiClient
from unifi_mcp.errors import (
    UniFiAuthError,
    UniFiBadRequestError,
    UniFiConnectionError,
    UniFiError,
    UniFiNotFoundError,
    UniFiRateLimitError,
    UniFiServerError,
    UniFiTimeoutError,
)

BASE_URL = "https://10.0.0.1:443"


class _ConcreteClient(BaseUniFiClient):
    """Minimal concrete subclass so the abstract base can be instantiated in tests."""

    async def validate_connection(self) -> bool:
        return True


@pytest.fixture
def client():
    return _ConcreteClient(
        base_url=BASE_URL,
        api_key="test-api-key",
        verify_ssl=False,
        timeout=5,
        max_retries=2,
    )


class TestGetRequest:
    @respx.mock
    async def test_get_returns_json(self, client):
        respx.get(f"{BASE_URL}/test").mock(return_value=httpx.Response(200, json={"data": [{"id": "1"}]}))
        result = await client.get("test")
        assert result == {"data": [{"id": "1"}]}

    @respx.mock
    async def test_api_key_header_included(self, client):
        route = respx.get(f"{BASE_URL}/test").mock(return_value=httpx.Response(200, json={}))
        await client.get("test")
        assert route.calls[0].request.headers["X-API-Key"] == "test-api-key"


class TestPostRequest:
    @respx.mock
    async def test_post_returns_json(self, client):
        respx.post(f"{BASE_URL}/test").mock(return_value=httpx.Response(200, json={"meta": {"rc": "ok"}}))
        result = await client.post("test", json={"name": "foo"})
        assert result == {"meta": {"rc": "ok"}}

    @respx.mock
    async def test_post_204_returns_empty_dict(self, client):
        respx.post(f"{BASE_URL}/test").mock(return_value=httpx.Response(204))
        result = await client.post("test")
        assert result == {}


class TestPutRequest:
    @respx.mock
    async def test_put_returns_json(self, client):
        respx.put(f"{BASE_URL}/test/123").mock(return_value=httpx.Response(200, json={"data": [{"_id": "123"}]}))
        result = await client.put("test/123", json={"name": "updated"})
        assert result == {"data": [{"_id": "123"}]}

    @respx.mock
    async def test_put_204_returns_empty_dict(self, client):
        respx.put(f"{BASE_URL}/test/123").mock(return_value=httpx.Response(204))
        result = await client.put("test/123", json={"name": "updated"})
        assert result == {}

    @respx.mock
    async def test_put_empty_body_returns_empty_dict(self, client):
        respx.put(f"{BASE_URL}/test/123").mock(return_value=httpx.Response(200, content=b""))
        result = await client.put("test/123", json={})
        assert result == {}


class TestDeleteRequest:
    @respx.mock
    async def test_delete_204_returns_empty_dict(self, client):
        respx.delete(f"{BASE_URL}/test/123").mock(return_value=httpx.Response(204))
        result = await client.delete("test/123")
        assert result == {}

    @respx.mock
    async def test_delete_returns_json_body_when_present(self, client):
        respx.delete(f"{BASE_URL}/test/123").mock(return_value=httpx.Response(200, json={"meta": {"rc": "ok"}}))
        result = await client.delete("test/123")
        assert result == {"meta": {"rc": "ok"}}


class TestErrorMapping:
    @respx.mock
    async def test_401_raises_auth_error(self, client):
        respx.get(f"{BASE_URL}/test").mock(return_value=httpx.Response(401, text="Unauthorized"))
        with pytest.raises(UniFiAuthError, match="401"):
            await client.get("test")

    @respx.mock
    async def test_403_raises_auth_error(self, client):
        respx.get(f"{BASE_URL}/test").mock(return_value=httpx.Response(403, text="Forbidden"))
        with pytest.raises(UniFiAuthError, match="403"):
            await client.get("test")

    @respx.mock
    async def test_404_raises_not_found(self, client):
        respx.get(f"{BASE_URL}/test").mock(return_value=httpx.Response(404, text="Not Found"))
        with pytest.raises(UniFiNotFoundError, match="404"):
            await client.get("test")

    @respx.mock
    async def test_429_raises_rate_limit(self, client):
        respx.get(f"{BASE_URL}/test").mock(return_value=httpx.Response(429, text="Too Many Requests"))
        with pytest.raises(UniFiRateLimitError, match="429"):
            await client.get("test")

    @respx.mock
    async def test_400_raises_bad_request(self, client):
        respx.get(f"{BASE_URL}/test").mock(return_value=httpx.Response(400, text="Bad Request"))
        with pytest.raises(UniFiBadRequestError, match="400"):
            await client.get("test")

    @respx.mock
    async def test_500_raises_server_error(self, client):
        respx.get(f"{BASE_URL}/test").mock(return_value=httpx.Response(500, text="Internal Server Error"))
        with pytest.raises(UniFiServerError, match="500"):
            await client.get("test")
        # Still a UniFiError subclass, so existing catchers keep working.

    @respx.mock
    async def test_502_raises_server_error(self, client):
        respx.get(f"{BASE_URL}/test").mock(return_value=httpx.Response(502, text="Bad Gateway"))
        with pytest.raises(UniFiServerError, match="502"):
            await client.get("test")

    @respx.mock
    async def test_418_raises_generic_unifi_error(self, client):
        respx.get(f"{BASE_URL}/test").mock(return_value=httpx.Response(418, text="I'm a teapot"))
        with pytest.raises(UniFiError, match="418"):
            await client.get("test")


class TestErrorBodyExtraction:
    """_extract_error_body pulls the actionable message out of known UniFi
    error envelopes instead of surfacing raw JSON truncated at 200 chars.
    """

    @respx.mock
    async def test_network_legacy_envelope_extracts_meta_msg(self, client):
        respx.get(f"{BASE_URL}/test").mock(
            return_value=httpx.Response(
                400,
                json={"meta": {"rc": "error", "msg": "api.err.FirewallRuleFieldsRequired"}, "data": []},
            )
        )
        with pytest.raises(UniFiBadRequestError) as exc_info:
            await client.get("test")
        assert "api.err.FirewallRuleFieldsRequired" in str(exc_info.value)
        # Raw JSON should NOT appear in the final message.
        assert '"meta":' not in str(exc_info.value)

    @respx.mock
    async def test_protect_integration_envelope_extracts_error_message(self, client):
        respx.get(f"{BASE_URL}/test").mock(
            return_value=httpx.Response(
                401,
                json={"error": {"code": 401, "message": "Unauthorized: invalid API key"}},
            )
        )
        with pytest.raises(UniFiAuthError) as exc_info:
            await client.get("test")
        assert "Unauthorized: invalid API key" in str(exc_info.value)
        assert '"error":' not in str(exc_info.value)

    @respx.mock
    async def test_reflected_api_key_value_scrubbed_from_message(self, client):
        """A controller that echoes the API key *value* inside a surfaced
        message field must not leak it. Key-*name* redaction (#148) can't catch
        a value reflected into free text, so the configured secret is
        value-scrubbed before the error string is built. Closes the
        value-reflection vector flagged in §4 of #97.
        """
        respx.get(f"{BASE_URL}/test").mock(
            return_value=httpx.Response(
                401,
                json={"meta": {"rc": "error", "msg": "invalid api key test-api-key for site default"}},
            )
        )
        with pytest.raises(UniFiAuthError) as exc_info:
            await client.get("test")
        msg = str(exc_info.value)
        assert "test-api-key" not in msg, f"API key leaked into error message: {msg!r}"
        # The rest of the message still surfaces (with the key masked) so the
        # operator keeps an actionable hint instead of an opaque blank.
        assert "***REDACTED***" in msg

    @respx.mock
    async def test_reflected_api_key_value_scrubbed_from_html_body(self, client):
        """The HTML-portal branch in ``_parse_json`` surfaces ``response.text[:200]``
        verbatim. It fires only on a 2xx that returns the UniFi OS portal (a
        non-2xx is intercepted by ``_raise_for_status`` first), so a key
        reflected in that HTML must be scrubbed on the success-but-HTML path too.
        """
        respx.get(f"{BASE_URL}/test").mock(
            return_value=httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text="<html><body>denied for key test-api-key</body></html>",
            )
        )
        with pytest.raises(UniFiAuthError) as exc_info:
            await client.get("test")
        msg = str(exc_info.value)
        assert "test-api-key" not in msg, f"API key leaked into HTML-body error message: {msg!r}"
        assert "***REDACTED***" in msg

    @respx.mock
    async def test_reflected_api_key_value_scrubbed_from_debug_log(self, client, caplog, monkeypatch):
        """The default DEBUG body log must not leak a reflected key *value*
        either. ``_redact_sensitive`` masks only sensitive key *names*, so a key
        echoed into a free-text field (``meta.msg``) survives into
        ``safe_payload`` — the value-scrub closes that log-side leak, not just
        the surfaced exception string.
        """
        monkeypatch.delenv("UNIFI_LOG_RAW_BODIES", raising=False)
        respx.get(f"{BASE_URL}/test").mock(
            return_value=httpx.Response(
                401,
                json={"meta": {"rc": "error", "msg": "invalid api key test-api-key for site default"}},
            )
        )
        with caplog.at_level(logging.DEBUG, logger="unifi_mcp.clients.base"), pytest.raises(UniFiAuthError):
            await client.get("test")
        for record in caplog.records:
            assert "test-api-key" not in record.getMessage(), f"API key leaked into DEBUG log: {record.getMessage()!r}"
        assert any("***REDACTED***" in r.getMessage() for r in caplog.records)

    def test_scrub_secret_leaves_unrelated_text_untouched(self, client):
        """A body that never contains the key passes through verbatim — the
        value-scrub must not mangle text that merely resembles it.
        """
        text = "device 00:11:22:33:44:55 not found in site default"
        assert client._scrub_secret(text) == text

    def test_scrub_secret_noop_when_key_empty(self):
        """An empty API key must short-circuit the scrub. Without the falsy
        guard, ``"" in text`` is always true and ``str.replace("", ...)`` would
        splice ``***REDACTED***`` between every character.
        """
        empty_key_client = _ConcreteClient(base_url=BASE_URL, api_key="")
        text = "some error mentioning test-api-key verbatim"
        assert empty_key_client._scrub_secret(text) == text

    def test_scrub_secret_skips_implausibly_short_key(self):
        """A 1-2 char key would mangle unrelated text (``ab`` -> ``t***ble``).
        Genuine UniFi keys are long opaque tokens, so the scrub skips secrets
        below ``_MIN_SCRUBBABLE_SECRET_LEN`` rather than over-redacting.
        """
        short_key_client = _ConcreteClient(base_url=BASE_URL, api_key="abc")
        text = "abc device not found in fabric abc"
        assert short_key_client._scrub_secret(text) == text

    def test_scrub_secret_boundary_at_min_length(self):
        """Pin the ``len(secret) < _MIN_SCRUBBABLE_SECRET_LEN`` hinge against an
        off-by-one or ``<=``/``<`` drift: a key one char below the threshold
        passes through, a key exactly at the threshold is scrubbed.
        """
        assert _MIN_SCRUBBABLE_SECRET_LEN == 8, "test keys are sized to the threshold"
        below = "k" * (_MIN_SCRUBBABLE_SECRET_LEN - 1)
        at = "k" * _MIN_SCRUBBABLE_SECRET_LEN

        below_client = _ConcreteClient(base_url=BASE_URL, api_key=below)
        text_below = f"controller rejected {below} for site default"
        assert below_client._scrub_secret(text_below) == text_below

        at_client = _ConcreteClient(base_url=BASE_URL, api_key=at)
        text_at = f"controller rejected {at} for site default"
        scrubbed = at_client._scrub_secret(text_at)
        assert at not in scrubbed, f"threshold-length key leaked: {scrubbed!r}"
        assert "***REDACTED***" in scrubbed

    def test_scrub_secret_masks_percent_encoded_reflection(self):
        """A controller that reflects the key into a URL/query field encodes it
        (e.g. ``+`` → ``%2B``), bypassing a literal-only match. The scrub must
        also mask the common percent-encoded forms of the secret.
        """
        key = "abc+def/ghi==jkl"
        client = _ConcreteClient(base_url=BASE_URL, api_key=key)
        encoded = urllib.parse.quote(key)  # 'abc%2Bdef/ghi%3D%3Djkl'
        assert encoded != key, "test key must actually change under percent-encoding"
        text = f"controller rejected {encoded} for site default"
        scrubbed = client._scrub_secret(text)
        assert encoded not in scrubbed, f"percent-encoded key leaked: {scrubbed!r}"
        assert "***REDACTED***" in scrubbed

    def test_scrub_secret_masks_quote_plus_reflection(self):
        """Query-style encoding (``quote_plus``: ``/`` → ``%2F``) must be caught
        too, not just the default ``quote`` form.
        """
        key = "abc+def/ghi==jkl"
        client = _ConcreteClient(base_url=BASE_URL, api_key=key)
        encoded = urllib.parse.quote_plus(key)  # 'abc%2Bdef%2Fghi%3D%3Djkl'
        text = f"denied: {encoded}"
        scrubbed = client._scrub_secret(text)
        assert encoded not in scrubbed, f"quote_plus-encoded key leaked: {scrubbed!r}"
        assert "***REDACTED***" in scrubbed

    def test_scrub_secret_masks_lowercase_hex_reflection(self):
        """Percent-encoding hex is case-insensitive (RFC 3986); a proxy may emit
        ``%2b`` where stdlib emits ``%2B``. The lowercase-hex reflection must be
        masked too, not just the uppercase ``quote`` output.
        """
        key = "abc+def/ghi==jkl"
        client = _ConcreteClient(base_url=BASE_URL, api_key=key)
        encoded = urllib.parse.quote(key).lower()  # 'abc%2bdef/ghi%3d%3djkl'
        assert "%2b" in encoded, "test key must exercise lowercase hex"
        text = f"controller rejected {encoded} for site default"
        scrubbed = client._scrub_secret(text)
        assert encoded not in scrubbed, f"lowercase-hex-encoded key leaked: {scrubbed!r}"
        assert "***REDACTED***" in scrubbed

    @respx.mock
    async def test_flat_error_string_envelope(self, client):
        respx.get(f"{BASE_URL}/test").mock(
            return_value=httpx.Response(404, json={"error": "device not found"}),
        )
        with pytest.raises(UniFiNotFoundError) as exc_info:
            await client.get("test")
        assert "device not found" in str(exc_info.value)

    @respx.mock
    async def test_flat_message_envelope(self, client):
        respx.get(f"{BASE_URL}/test").mock(
            return_value=httpx.Response(500, json={"message": "internal failure"}),
        )
        with pytest.raises(UniFiServerError) as exc_info:
            await client.get("test")
        assert "internal failure" in str(exc_info.value)

    @respx.mock
    async def test_unrecognized_json_yields_opaque_hint(self, client):
        """JSON that doesn't match any known envelope returns the opaque
        ``<unparseable body, see DEBUG log>`` hint rather than slicing the
        raw response — protects against reflected secrets (#148).
        """
        respx.get(f"{BASE_URL}/test").mock(
            return_value=httpx.Response(500, json={"weird_shape": [1, 2, 3], "other_field": "data"}),
        )
        with pytest.raises(UniFiServerError) as exc_info:
            await client.get("test")
        msg = str(exc_info.value)
        assert "HTTP 500" in msg
        assert "<unparseable body, see DEBUG log>" in msg
        assert "weird_shape" not in msg

    @respx.mock
    async def test_non_json_body_yields_opaque_hint(self, client):
        """Plain-text error body is opaque-hint by default — the raw bytes
        are only available via the opt-in raw-bodies DEBUG log.
        """
        respx.get(f"{BASE_URL}/test").mock(return_value=httpx.Response(503, text="Service Unavailable"))
        with pytest.raises(UniFiServerError) as exc_info:
            await client.get("test")
        msg = str(exc_info.value)
        assert "HTTP 503" in msg
        assert "<unparseable body, see DEBUG log>" in msg
        assert "Service Unavailable" not in msg

    @respx.mock
    @pytest.mark.parametrize(
        "json_body",
        [
            pytest.param(["err.one", "err.two"], id="json-list"),
            pytest.param("bare string error", id="json-string"),
        ],
    )
    async def test_non_dict_json_body_yields_opaque_hint(self, client, json_body):
        """A body that parses as JSON but is not a dict (a list or a bare
        string) falls through the envelope-matching ``isinstance(..., dict)``
        gate to the opaque ``<unparseable body, see DEBUG log>`` hint, rather
        than leaking the raw structure into the surfaced message.
        """
        respx.get(f"{BASE_URL}/test").mock(return_value=httpx.Response(500, json=json_body))
        with pytest.raises(UniFiServerError) as exc_info:
            await client.get("test")
        msg = str(exc_info.value)
        assert "HTTP 500" in msg
        assert "<unparseable body, see DEBUG log>" in msg
        # No element of the non-dict body leaks into the surfaced message.
        assert "err.one" not in msg
        assert "bare string error" not in msg

    @respx.mock
    async def test_raw_body_debug_log_suppressed_by_default(self, client, caplog, monkeypatch):
        """Without ``UNIFI_LOG_RAW_BODIES=1`` the full body never reaches the
        DEBUG log — the redacted/summary form goes out instead.
        """
        import logging

        monkeypatch.delenv("UNIFI_LOG_RAW_BODIES", raising=False)
        huge_body = "x" * 500
        respx.get(f"{BASE_URL}/test").mock(return_value=httpx.Response(500, text=huge_body))
        with caplog.at_level(logging.DEBUG, logger="unifi_mcp.clients.base"), pytest.raises(UniFiServerError):
            await client.get("test")
        for record in caplog.records:
            assert huge_body not in record.getMessage()

    @respx.mock
    async def test_raw_body_debug_log_emitted_with_opt_in(self, client, caplog, monkeypatch):
        """``UNIFI_LOG_RAW_BODIES=1`` restores the untouched-body DEBUG log."""
        import logging

        monkeypatch.setenv("UNIFI_LOG_RAW_BODIES", "1")
        huge_body = "x" * 500
        respx.get(f"{BASE_URL}/test").mock(return_value=httpx.Response(500, text=huge_body))
        with caplog.at_level(logging.DEBUG, logger="unifi_mcp.clients.base"), pytest.raises(UniFiServerError):
            await client.get("test")
        assert any(huge_body in r.getMessage() for r in caplog.records), (
            f"expected raw body in DEBUG log; got {[r.getMessage() for r in caplog.records]!r}"
        )

    @respx.mock
    async def test_raw_body_debug_log_emitted_with_opt_in_for_json_body(self, client, caplog, monkeypatch):
        """``UNIFI_LOG_RAW_BODIES=1`` logs the untouched body on the JSON path too.

        The default DEBUG branch logs the redacted form; the opt-in branch
        inside the ``parsed is not None`` block must emit ``response.text``
        verbatim so an operator diagnosing a structured error sees exactly what
        the controller sent.
        """
        import logging

        monkeypatch.setenv("UNIFI_LOG_RAW_BODIES", "1")
        respx.get(f"{BASE_URL}/test").mock(
            return_value=httpx.Response(500, json={"meta": {"rc": "error", "msg": "api.err.Internal"}}),
        )
        with caplog.at_level(logging.DEBUG, logger="unifi_mcp.clients.base"), pytest.raises(UniFiServerError):
            await client.get("test")
        debug_messages = [r.getMessage() for r in caplog.records if r.levelno == logging.DEBUG]
        assert any('"rc": "error"' in m or '"rc":"error"' in m for m in debug_messages), (
            f"expected untouched JSON body in DEBUG log; got {debug_messages!r}"
        )
        assert not any("redacted" in m.lower() for m in debug_messages), (
            f"raw opt-in must not take the redacted branch; got {debug_messages!r}"
        )

    @respx.mock
    async def test_sensitive_keys_redacted_in_message(self, client):
        """``x_passphrase``, ``radius_secret``, and similar keys are masked
        before any error string is built — even when the controller echoes
        the submitted payload back in a 400 response.
        """
        respx.get(f"{BASE_URL}/test").mock(
            return_value=httpx.Response(
                400,
                json={
                    "meta": {"rc": "error", "msg": "api.err.InvalidPayload"},
                    "data": [
                        {
                            "x_passphrase": "hunter2",
                            "radius_secret": "shared-key",
                            "nested": {"password": "p@ss", "api_key": "key-123"},
                        }
                    ],
                },
            )
        )
        with pytest.raises(UniFiBadRequestError) as exc_info:
            await client.get("test")
        msg = str(exc_info.value)
        assert "api.err.InvalidPayload" in msg
        # Sensitive values must never appear in the exception text.
        for secret in ("hunter2", "shared-key", "p@ss", "key-123"):
            assert secret not in msg, f"secret {secret!r} leaked into error message"

    @respx.mock
    async def test_sensitive_keys_redacted_in_debug_log(self, client, caplog, monkeypatch):
        """The default DEBUG body log carries the masked structure, not the
        raw secrets — only the opt-in raw log would expose them.
        """
        import logging

        monkeypatch.delenv("UNIFI_LOG_RAW_BODIES", raising=False)
        respx.get(f"{BASE_URL}/test").mock(
            return_value=httpx.Response(
                400,
                json={"meta": {"rc": "error", "msg": "api.err.X"}, "x_passphrase": "hunter2"},
            )
        )
        with caplog.at_level(logging.DEBUG, logger="unifi_mcp.clients.base"), pytest.raises(UniFiBadRequestError):
            await client.get("test")
        for record in caplog.records:
            assert "hunter2" not in record.getMessage()
        assert any("REDACTED" in r.getMessage() for r in caplog.records)

    @respx.mock
    async def test_empty_body_401_yields_empty_body_hint(self, client):
        """Empty body must produce '(empty body)' instead of a dangling
        'HTTP 401: ' so operators have something to look up.
        """
        respx.get(f"{BASE_URL}/test").mock(return_value=httpx.Response(401, text=""))
        with pytest.raises(UniFiAuthError) as exc_info:
            await client.get("test")
        msg = str(exc_info.value)
        assert "(empty body)" in msg
        assert not msg.rstrip().endswith(":")

    @respx.mock
    async def test_empty_body_401_with_www_authenticate_includes_header(self, client):
        """When the body is empty but WWW-Authenticate is present, surface
        the header value in the hint so operators can identify the scheme.
        """
        respx.get(f"{BASE_URL}/test").mock(
            return_value=httpx.Response(401, text="", headers={"WWW-Authenticate": "Bearer"})
        )
        with pytest.raises(UniFiAuthError) as exc_info:
            await client.get("test")
        assert "(empty body; WWW-Authenticate: Bearer)" in str(exc_info.value)

    @respx.mock
    async def test_whitespace_only_body_treated_as_empty(self, client):
        """A body containing only whitespace is functionally the same as an
        empty body — same hint, no dangling colon.
        """
        respx.get(f"{BASE_URL}/test").mock(return_value=httpx.Response(401, text="   \n\t  "))
        with pytest.raises(UniFiAuthError) as exc_info:
            await client.get("test")
        assert "(empty body)" in str(exc_info.value)


class TestMalformedJson:
    @respx.mock
    async def test_200_with_invalid_json_raises_unifi_error_with_none_status_code(self, client):
        respx.get(f"{BASE_URL}/test").mock(
            return_value=httpx.Response(200, content=b"not json", headers={"content-type": "application/json"})
        )
        with pytest.raises(UniFiError, match="Invalid JSON") as exc_info:
            await client.get("test")
        assert exc_info.value.status_code is None

    @respx.mock
    async def test_200_with_empty_body_on_get_raises_unifi_error(self, client):
        respx.get(f"{BASE_URL}/test").mock(
            return_value=httpx.Response(200, content=b"", headers={"content-type": "application/json"})
        )
        with pytest.raises(UniFiError, match="Invalid JSON") as exc_info:
            await client.get("test")
        assert exc_info.value.status_code is None

    @respx.mock
    async def test_200_with_html_body_raises_auth_error_not_invalid_json(self, client):
        """UniFi OS returns the SPA portal HTML on 200 when the request hits a
        path that rejects X-API-KEY (e.g. a protected proxy endpoint that
        requires cookie auth). This must classify as an auth/path mismatch,
        not a generic "Invalid JSON" error.
        """
        html_portal = b'<!doctype html><html lang="en"><head><title>UniFi OS</title></head><body></body></html>'
        respx.get(f"{BASE_URL}/test").mock(
            return_value=httpx.Response(200, content=html_portal, headers={"content-type": "text/html; charset=utf-8"})
        )
        with pytest.raises(UniFiAuthError, match="HTML instead of JSON") as exc_info:
            await client.get("test")
        assert exc_info.value.status_code == 200
        assert "auth/path mismatch" in str(exc_info.value)

    @respx.mock
    async def test_200_with_html_content_type_any_casing_caught(self, client):
        """Content-type header is case-insensitive; the sniff must lowercase before comparing."""
        respx.get(f"{BASE_URL}/test").mock(
            return_value=httpx.Response(200, content=b"<!DOCTYPE html>", headers={"content-type": "TEXT/HTML"})
        )
        with pytest.raises(UniFiAuthError):
            await client.get("test")


class TestRetry:
    @respx.mock
    async def test_retries_on_connect_error_then_succeeds(self, client):
        route = respx.get(f"{BASE_URL}/test")
        route.side_effect = [
            httpx.ConnectError("Connection refused"),
            httpx.Response(200, json={"ok": True}),
        ]
        result = await client.get("test")
        assert result == {"ok": True}
        assert route.call_count == 2

    @respx.mock
    async def test_raises_connection_error_after_retries_exhausted(self, client):
        respx.get(f"{BASE_URL}/test").mock(side_effect=httpx.ConnectError("Connection refused"))
        with pytest.raises(UniFiConnectionError, match="Connection refused"):
            await client.get("test")

    @respx.mock
    async def test_no_retry_on_auth_error(self, client):
        route = respx.get(f"{BASE_URL}/test").mock(return_value=httpx.Response(401, text="Unauthorized"))
        with pytest.raises(UniFiAuthError):
            await client.get("test")
        assert route.call_count == 1

    @respx.mock
    async def test_timeout_on_get_is_retried(self, client):
        # GET is idempotent, so TimeoutException retries up to max_retries.
        route = respx.get(f"{BASE_URL}/test")
        route.side_effect = [
            httpx.ReadTimeout("slow"),
            httpx.Response(200, json={"ok": True}),
        ]
        result = await client.get("test")
        assert result == {"ok": True}
        assert route.call_count == 2

    @respx.mock
    async def test_timeout_on_post_is_not_retried(self, client):
        # POST is non-idempotent; a timeout must not be retried — the server
        # may have processed the write before the response was lost.
        route = respx.post(f"{BASE_URL}/test").mock(side_effect=httpx.ReadTimeout("slow"))
        with pytest.raises(UniFiTimeoutError):
            await client.post("test", json={"x": 1})
        assert route.call_count == 1

    @respx.mock
    async def test_timeout_on_put_is_not_retried(self, client):
        route = respx.put(f"{BASE_URL}/test/1").mock(side_effect=httpx.ReadTimeout("slow"))
        with pytest.raises(UniFiTimeoutError):
            await client.put("test/1", json={"x": 1})
        assert route.call_count == 1

    @respx.mock
    async def test_timeout_on_delete_is_not_retried(self, client):
        route = respx.delete(f"{BASE_URL}/test/1").mock(side_effect=httpx.ReadTimeout("slow"))
        with pytest.raises(UniFiTimeoutError):
            await client.delete("test/1")
        assert route.call_count == 1

    @respx.mock
    async def test_connect_error_on_post_is_retried(self, client):
        # ConnectError is safe on every method — the request never reached the server.
        route = respx.post(f"{BASE_URL}/test")
        route.side_effect = [
            httpx.ConnectError("refused"),
            httpx.Response(200, json={"ok": True}),
        ]
        result = await client.post("test", json={"x": 1})
        assert result == {"ok": True}
        assert route.call_count == 2

    @respx.mock
    async def test_retry_emits_warning_log_on_before_sleep(self, client, caplog):
        """A transient ConnectError followed by success must leave a WARNING
        log trail so operators debugging flaky controllers can see retries
        fired. Without ``before_sleep_log``, retries are invisible.
        """
        route = respx.get(f"{BASE_URL}/test")
        route.side_effect = [
            httpx.ConnectError("refused"),
            httpx.Response(200, json={"ok": True}),
        ]
        with caplog.at_level(logging.WARNING, logger="unifi_mcp.clients.base"):
            result = await client.get("test")
        assert result == {"ok": True}
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert warnings, f"expected WARNING-level before_sleep log; got {caplog.records!r}"
        assert any("retrying" in r.getMessage().lower() for r in warnings), (
            f"expected a retry log; got messages: {[r.getMessage() for r in warnings]}"
        )


class TestRateLimitRetry:
    """Retry-After handling for idempotent 429 responses.

    Ubiquiti's integration API returns 429 with a Retry-After header when
    rate-limited. A single server-side retry removes the round-trip for
    transient bursts without surfacing the rate limit to the MCP client.
    """

    @respx.mock
    async def test_429_with_retry_after_on_get_is_retried_then_succeeds(self, client, monkeypatch):
        slept: list[float] = []

        async def fake_sleep(seconds: float) -> None:
            slept.append(seconds)

        monkeypatch.setattr("unifi_mcp.clients.base.asyncio.sleep", fake_sleep)

        route = respx.get(f"{BASE_URL}/test")
        route.side_effect = [
            httpx.Response(429, text="rate limited", headers={"Retry-After": "2"}),
            httpx.Response(200, json={"ok": True}),
        ]
        result = await client.get("test")
        assert result == {"ok": True}
        assert route.call_count == 2
        assert slept == [2]

    @respx.mock
    async def test_429_without_retry_after_falls_back_to_one_second(self, client, monkeypatch):
        slept: list[float] = []

        async def fake_sleep(seconds: float) -> None:
            slept.append(seconds)

        monkeypatch.setattr("unifi_mcp.clients.base.asyncio.sleep", fake_sleep)

        route = respx.get(f"{BASE_URL}/test")
        route.side_effect = [
            httpx.Response(429, text="rate limited"),
            httpx.Response(200, json={"ok": True}),
        ]
        result = await client.get("test")
        assert result == {"ok": True}
        assert slept == [1]

    @respx.mock
    async def test_429_retry_after_is_capped(self, client, monkeypatch):
        """An unreasonably large Retry-After must be capped so a single
        tool call doesn't block for many minutes."""
        import asyncio as _aio

        from unifi_mcp.clients.base import _MAX_RETRY_AFTER_SECONDS

        slept: list[float] = []

        # Freeze the loop clock and widen the wall-clock retry budget so
        # this test isolates the ``_MAX_RETRY_AFTER_SECONDS`` cap from the
        # elapsed-time fence. The fence has its own ``TestTotalElapsedBudget``
        # suite; here we just need a budget large enough to admit the capped
        # sleep at the fixture's ``timeout=5``.
        monkeypatch.setattr(_aio.get_running_loop(), "time", lambda: 0.0)
        monkeypatch.setattr("unifi_mcp.clients.base._TOTAL_ELAPSED_TIMEOUT_MULTIPLIER", 100)

        async def fake_sleep(seconds: float) -> None:
            slept.append(seconds)

        monkeypatch.setattr("unifi_mcp.clients.base.asyncio.sleep", fake_sleep)

        route = respx.get(f"{BASE_URL}/test")
        route.side_effect = [
            httpx.Response(429, text="rate limited", headers={"Retry-After": "3600"}),
            httpx.Response(200, json={"ok": True}),
        ]
        await client.get("test")
        assert slept == [_MAX_RETRY_AFTER_SECONDS]

    @respx.mock
    async def test_429_on_post_is_not_retried(self, client):
        """POST is non-idempotent; retrying 429 risks double-execution if the
        server partially processed the request before rate-limiting.
        """
        from unifi_mcp.errors import UniFiRateLimitError

        route = respx.post(f"{BASE_URL}/test").mock(
            return_value=httpx.Response(429, text="rate limited", headers={"Retry-After": "1"})
        )
        with pytest.raises(UniFiRateLimitError):
            await client.post("test", json={"x": 1})
        assert route.call_count == 1

    @respx.mock
    async def test_429_on_put_is_not_retried(self, client):
        from unifi_mcp.errors import UniFiRateLimitError

        route = respx.put(f"{BASE_URL}/test/1").mock(return_value=httpx.Response(429, text="rate limited"))
        with pytest.raises(UniFiRateLimitError):
            await client.put("test/1", json={"x": 1})
        assert route.call_count == 1

    @respx.mock
    async def test_429_exhausts_retries_and_surfaces_rate_limit_error(self, client, monkeypatch):
        from unifi_mcp.errors import UniFiRateLimitError

        async def fake_sleep(seconds: float) -> None:
            pass

        monkeypatch.setattr("unifi_mcp.clients.base.asyncio.sleep", fake_sleep)

        # Client is configured with max_retries=2 in the fixture.
        route = respx.get(f"{BASE_URL}/test").mock(
            return_value=httpx.Response(429, text="rate limited", headers={"Retry-After": "1"})
        )
        with pytest.raises(UniFiRateLimitError, match="429"):
            await client.get("test")
        # Bounded: initial request + max_retries retries.
        assert route.call_count == 1 + client._max_retries

    @respx.mock
    async def test_rate_limit_error_carries_retry_after(self, client):
        """The parsed Retry-After value is attached to the raised exception
        even on non-retried methods, so downstream logic (or the agent) can
        see how long to wait."""
        from unifi_mcp.errors import UniFiRateLimitError

        respx.post(f"{BASE_URL}/test").mock(
            return_value=httpx.Response(429, text="rate limited", headers={"Retry-After": "42"})
        )
        with pytest.raises(UniFiRateLimitError) as exc_info:
            await client.post("test", json={"x": 1})
        assert exc_info.value.retry_after == 42
        assert exc_info.value.status_code == 429

    def test_parse_retry_after_handles_invalid_values(self, client):
        """Non-integer Retry-After values must not crash; return None."""
        assert client._parse_retry_after(None) is None
        assert client._parse_retry_after("") is None
        assert client._parse_retry_after("not-a-number") is None
        assert client._parse_retry_after("Wed, 21 Oct 2026 07:28:00 GMT") is None  # HTTP-date form unsupported
        assert client._parse_retry_after("  5  ") == 5
        assert client._parse_retry_after("-3") == 0  # clamped non-negative


class TestPathPrefix:
    @respx.mock
    async def test_path_prefix_applied(self):
        client = _ConcreteClient(
            base_url=BASE_URL,
            api_key="key",
        )
        client._path_prefix = "/proxy/network/api/s/default/"
        respx.get(f"{BASE_URL}/proxy/network/api/s/default/stat/device").mock(
            return_value=httpx.Response(200, json={"data": []})
        )
        result = await client.get("stat/device")
        assert result == {"data": []}


class TestGetRaw:
    @respx.mock
    async def test_get_raw_returns_bytes(self, client):
        respx.get(f"{BASE_URL}/snap").mock(return_value=httpx.Response(200, content=b"\xff\xd8\xff\xe0"))
        result = await client.get_raw("snap")
        assert result == b"\xff\xd8\xff\xe0"

    @respx.mock
    async def test_get_raw_with_max_bytes_under_cap_returns_full_body(self, client):
        payload = b"x" * 1024
        respx.get(f"{BASE_URL}/clip").mock(return_value=httpx.Response(200, content=payload))
        result = await client.get_raw("clip", max_bytes=2048)
        assert result == payload

    @respx.mock
    async def test_get_raw_with_max_bytes_exceeded_raises(self, client):
        payload = b"x" * 2048
        respx.get(f"{BASE_URL}/clip").mock(return_value=httpx.Response(200, content=payload))
        with pytest.raises(UniFiError, match="max_bytes=1024"):
            await client.get_raw("clip", max_bytes=1024)

    @respx.mock
    async def test_get_raw_streamed_raises_on_http_error(self, client):
        respx.get(f"{BASE_URL}/clip").mock(return_value=httpx.Response(404, text="Not Found"))
        with pytest.raises(UniFiNotFoundError):
            await client.get_raw("clip", max_bytes=1024)

    @respx.mock
    async def test_get_raw_streaming_retries_connect_error(self, client):
        """The streaming branch must share the tenacity retry semantics of
        ``_request``: a transient ConnectError retries and succeeds on the
        second attempt.
        """
        route = respx.get(f"{BASE_URL}/clip")
        route.side_effect = [
            httpx.ConnectError("refused"),
            httpx.Response(200, content=b"\xff\xd8\xff\xe0ok"),
        ]
        result = await client.get_raw("clip", max_bytes=1024)
        assert result == b"\xff\xd8\xff\xe0ok"
        assert route.call_count == 2

    @respx.mock
    async def test_get_raw_streaming_maps_connect_error_when_retries_exhausted(self, client):
        """ConnectError after exhausted retries must surface as
        UniFiConnectionError, not a raw httpx exception that would fall
        through handle_client_error's 'Unexpected error' branch.
        """
        respx.get(f"{BASE_URL}/clip").mock(side_effect=httpx.ConnectError("refused"))
        with pytest.raises(UniFiConnectionError, match="refused"):
            await client.get_raw("clip", max_bytes=1024)

    @respx.mock
    async def test_get_raw_streaming_maps_timeout(self, client):
        """ReadTimeout in the streaming path must map to UniFiTimeoutError."""
        respx.get(f"{BASE_URL}/clip").mock(side_effect=httpx.ReadTimeout("slow"))
        with pytest.raises(UniFiTimeoutError, match="slow"):
            await client.get_raw("clip", max_bytes=1024)

    @respx.mock
    async def test_get_raw_streaming_does_not_retry_max_bytes_exceeded(self, client):
        """max_bytes exceeded is a deliberate abort, not transient — must not
        retry (tenacity only retries on Connect/Timeout).
        """
        payload = b"x" * 4096
        route = respx.get(f"{BASE_URL}/clip").mock(return_value=httpx.Response(200, content=payload))
        with pytest.raises(UniFiError, match="max_bytes=1024"):
            await client.get_raw("clip", max_bytes=1024)
        assert route.call_count == 1


class TestUrlSchemeRejection:
    """``_url`` refuses paths that could rewrite ``base_url`` after concat.

    Defense-in-depth on top of ``_segment`` (#145): every production client
    method uses a bare relative path (``stat/device``, ``rest/wlanconf/{id}``).
    A leading slash, an absolute URL, or a protocol-relative form would let
    a path argument pivot the request off the configured controller. See #151.
    """

    @pytest.mark.parametrize(
        "path",
        [
            "/test",
            "//evil.example.com/path",
            "http://evil.example.com/path",
            "https://evil.example.com/path",
        ],
    )
    def test_scheme_prefixed_paths_rejected(self, client, path):
        with pytest.raises(UniFiBadRequestError, match="invalid request path"):
            client._url(path)

    def test_non_string_path_rejected(self, client):
        with pytest.raises(UniFiBadRequestError, match="invalid request path"):
            client._url(None)  # type: ignore[arg-type]

    def test_relative_path_accepted(self, client):
        assert client._url("stat/device") == "stat/device"

    @respx.mock
    async def test_get_rejects_leading_slash_before_request(self, client):
        # No respx route registered — if the guard fails open, httpx would
        # actually issue a request and respx would raise its own error.
        with pytest.raises(UniFiBadRequestError, match="invalid request path"):
            await client.get("/abs/path")

    @respx.mock
    async def test_get_raw_streaming_rejects_absolute_url(self, client):
        with pytest.raises(UniFiBadRequestError, match="invalid request path"):
            await client.get_raw("https://evil.example.com/clip", max_bytes=1024)


class TestMultiPhaseTimeout:
    """``httpx.Timeout`` is split: short connect/pool, operator timeout for read/write.

    The original ``httpx.Timeout(timeout)`` collapsed all four phases onto the
    same value, so a 30s read budget also meant 30s of patience for a TCP
    connect to an unreachable host — making startup slow on misconfigured
    deployments. See #151.
    """

    def test_connect_and_pool_pinned_short(self):
        client = _ConcreteClient(base_url=BASE_URL, api_key="k", timeout=30)
        timeout = client._client.timeout
        assert timeout.connect == 5.0
        assert timeout.pool == 5.0

    def test_read_and_write_use_operator_timeout(self):
        client = _ConcreteClient(base_url=BASE_URL, api_key="k", timeout=45)
        timeout = client._client.timeout
        assert timeout.read == 45.0
        assert timeout.write == 45.0


class TestStreamKwargsCopy:
    """Each stream retry attempt gets its own ``kwargs`` snapshot.

    The previous implementation closed over the caller's ``kwargs`` dict and
    reused it across tenacity retries. Httpx is free to mutate values it
    consumes (notably streaming bodies, file uploads), so a future caller
    passing a mutable iterator would silently exhaust it on the first try.
    The copy is cheap and removes the latent footgun. See #151.
    """

    @respx.mock
    async def test_stream_kwargs_not_shared_between_attempts(self, client):
        seen_param_lists: list[list[tuple[str, str]]] = []

        def _record(request: httpx.Request) -> httpx.Response:
            seen_param_lists.append(list(request.url.params.multi_items()))
            if len(seen_param_lists) == 1:
                raise httpx.ConnectError("refused")
            return httpx.Response(200, content=b"ok")

        respx.get(f"{BASE_URL}/clip").mock(side_effect=_record)
        params = {"camera_id": "abc"}
        result = await client.get_raw("clip", max_bytes=1024, params=params)
        assert result == b"ok"
        # Both attempts saw the same arguments — the copy never mutated the
        # caller's dict.
        assert params == {"camera_id": "abc"}
        assert seen_param_lists[0] == seen_param_lists[1]


class TestTotalElapsedBudget:
    """A wall-clock fence stops the transient-error and 429 retry budgets from
    chaining past ``5 * timeout`` seconds in a single ``_request`` call.

    Without this fence, a controller that alternates between transient errors
    (consumed by the tenacity decorator) and 429 responses (consumed by the
    outer 429 loop) can extend a single tool call far past the documented
    ``_MAX_RETRY_AFTER_SECONDS`` cap. See #151.
    """

    @respx.mock
    async def test_repeated_429_capped_by_wall_clock_budget(self, monkeypatch):
        # Small fixture so the budget (5 * timeout = 25s) is tight.
        client = _ConcreteClient(base_url=BASE_URL, api_key="k", timeout=5, max_retries=10)
        slept: list[float] = []

        # Drive a fake clock so we don't depend on real time. ``loop.time``
        # is captured at the start of ``_request``; each fake sleep advances it.
        import asyncio as _aio

        real_loop = _aio.get_running_loop()
        fake_now = 0.0

        def fake_time() -> float:
            return fake_now

        async def fake_sleep(seconds: float) -> None:
            nonlocal fake_now
            slept.append(seconds)
            fake_now += seconds

        monkeypatch.setattr(real_loop, "time", fake_time)
        monkeypatch.setattr("unifi_mcp.clients.base.asyncio.sleep", fake_sleep)

        respx.get(f"{BASE_URL}/test").mock(
            return_value=httpx.Response(429, text="rate limited", headers={"Retry-After": "20"})
        )
        with pytest.raises(UniFiRateLimitError, match="429"):
            await client.get("test")
        # First sleep (20s) is inside the 25s budget; second sleep would push
        # elapsed to 40s and is refused — the call raises instead.
        assert slept == [20]

    @respx.mock
    async def test_single_legitimate_retry_fits_inside_budget(self, monkeypatch):
        # Real-world: one 429 with a sane Retry-After succeeds.
        client = _ConcreteClient(base_url=BASE_URL, api_key="k", timeout=30, max_retries=3)
        slept: list[float] = []

        async def fake_sleep(seconds: float) -> None:
            slept.append(seconds)

        monkeypatch.setattr("unifi_mcp.clients.base.asyncio.sleep", fake_sleep)

        route = respx.get(f"{BASE_URL}/test")
        route.side_effect = [
            httpx.Response(429, text="rate limited", headers={"Retry-After": "2"}),
            httpx.Response(200, json={"ok": True}),
        ]
        assert await client.get("test") == {"ok": True}
        assert slept == [2]


class TestClose:
    async def test_close_calls_aclose(self, client):
        await client.close()
        assert client._client.is_closed


class TestConcurrentRequests:
    """``BaseUniFiClient`` holds one ``httpx.AsyncClient`` per service for the
    process lifetime. Two simultaneous tool calls against the same client share
    that pool; these tests prove the shared pool services concurrent requests
    correctly without swapping responses, re-creating the client, or deadlocking.
    """

    @respx.mock
    async def test_two_distinct_concurrent_gets_return_independent_responses(self, client):
        respx.get(f"{BASE_URL}/test-a").mock(return_value=httpx.Response(200, json={"which": "a"}))
        respx.get(f"{BASE_URL}/test-b").mock(return_value=httpx.Response(200, json={"which": "b"}))
        client_id_before = id(client._client)

        result_a, result_b = await asyncio.gather(client.get("test-a"), client.get("test-b"))

        assert result_a == {"which": "a"}
        assert result_b == {"which": "b"}
        assert id(client._client) == client_id_before
        assert respx.calls.call_count == 2

    @respx.mock
    async def test_ten_concurrent_gets_same_path_all_complete(self, client):
        respx.get(f"{BASE_URL}/test").mock(return_value=httpx.Response(200, json={"ok": True}))
        client_id_before = id(client._client)

        results = await asyncio.gather(*[client.get("test") for _ in range(10)])

        assert len(results) == 10
        assert all(r == {"ok": True} for r in results)
        assert respx.calls.call_count == 10
        assert id(client._client) == client_id_before
