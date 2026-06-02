"""Base API client with retry, auth, and error mapping."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import urllib.parse
from abc import ABC, abstractmethod
from typing import Any

import httpx
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from unifi_mcp._redaction import REDACTED
from unifi_mcp._redaction import redact_secrets as _redact_sensitive
from unifi_mcp.clients._pinning import CertPinningTransport
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

logger = logging.getLogger(__name__)

# Upper bound on a single Retry-After sleep. Ubiquiti sometimes returns very
# generous values; capping keeps a single tool call bounded.
_MAX_RETRY_AFTER_SECONDS = 30

# Multiplier applied to ``timeout`` for the per-request total elapsed budget.
# The tenacity transient-error budget and the 429 retry budget run in
# independent loops, so a pathological controller can chain them and exceed
# the documented ``_MAX_RETRY_AFTER_SECONDS`` cap. This wall-clock fence is
# the final gate: once the cumulative sleep+request time for one ``_request``
# call exceeds ``timeout * _TOTAL_ELAPSED_TIMEOUT_MULTIPLIER`` we refuse to
# retry further and raise. See #151.
_TOTAL_ELAPSED_TIMEOUT_MULTIPLIER = 5

# Floor below which a configured "secret" is too short to value-scrub safely:
# a 1-2 char value would splice ``REDACTED`` into unrelated text (a key of
# ``ab`` mangling ``table``). Genuine UniFi OS API keys are long opaque tokens
# well above this, so skipping the scrub for shorter values trades a
# theoretical leak of an implausibly short key for not corrupting every error
# message. See #303.
_MIN_SCRUBBABLE_SECRET_LEN = 8


def _log_raw_bodies_enabled() -> bool:
    """Whether the operator opted into untouched-body DEBUG logging.

    Read from the environment directly (rather than through ``UniFiConfig``)
    so the helper stays available to callers that construct clients without
    a config object — notably tests. Truthy values: ``1``, ``true``, ``yes``
    (case-insensitive).
    """
    return os.environ.get("UNIFI_LOG_RAW_BODIES", "").strip().lower() in {"1", "true", "yes"}


class BaseUniFiClient(ABC):
    """Base client for UniFi APIs with retry, auth, and error mapping.

    Subclasses must set ``_path_prefix`` and implement ``validate_connection()``.
    """

    _path_prefix: str = ""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        verify_ssl: bool = False,
        cert_fingerprint: str | None = None,
        timeout: int = 30,
        max_retries: int = 3,
    ) -> None:
        self._max_retries = max_retries
        self._timeout = timeout
        # Multi-phase timeout: short connect/pool waits keep startup snappy
        # against unreachable hosts while leaving the operator-configured
        # ``timeout`` to bound the read/write phases (the slow ones on UniFi
        # APIs — e.g. backup exports). See #151.
        client_kwargs: dict[str, Any] = {
            "base_url": base_url,
            "headers": {"X-API-Key": api_key},
        }
        if cert_fingerprint is not None:
            # Pinning takes precedence over verify_ssl: chain/hostname checks
            # are disabled inside the pinning transport because the pin is
            # the trust anchor.
            client_kwargs["transport"] = CertPinningTransport(expected_fingerprint=cert_fingerprint)
        else:
            client_kwargs["verify"] = verify_ssl
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5.0, read=float(timeout), write=float(timeout), pool=5.0),
            **client_kwargs,
        )
        # Captured by validate_connection on failure so the lifespan can
        # report WHY the API was disabled (auth vs. unreachability vs. path
        # mismatch) instead of a generic "validate_connection failed". See
        # #104.
        self._last_validation_error: BaseException | None = None

    # ── HTTP helpers ────────────────────────────────────────────────────

    def _url(self, path: str) -> str:
        """Build full path with prefix.

        Refuses paths that could override ``base_url`` after concatenation:

        - Leading ``/`` would route past ``_path_prefix`` entirely.
        - ``http://`` / ``https://`` get parsed as absolute URLs by httpx,
          pivoting the request off the configured controller.
        - Protocol-relative ``//host`` is parsed as a network-path reference
          and pivots to a different host on the same scheme.

        Defense-in-depth on top of ``_segment`` (#145): an agent-controlled
        ID still goes through that helper, but any path-shaped value that
        slips past the tool-layer ID/MAC validators meets this gate too.
        Production client methods all use bare relative paths
        (``stat/device``, ``rest/wlanconf/{id}``); a leading-slash path
        would be a bug — fail fast rather than silently rewrite the URL.
        See #151.
        """
        if not isinstance(path, str) or path.startswith(("/", "http://", "https://")):
            raise UniFiBadRequestError(f"invalid request path: {path!r}")
        return f"{self._path_prefix}{path}"

    @staticmethod
    def _segment(value: str) -> str:
        """Return a URL-safe single path segment from an agent-controlled value.

        Defends against path traversal (#145). ``httpx`` does not normalize
        ``..`` segments client-side, so an unencoded ID interpolated into a
        path string can escape ``_path_prefix`` and pivot to a different
        endpoint under the same auth. Every ID, MAC, or similar caller-
        supplied value that lands in a URL path segment must flow through
        this helper.

        Rejects empty strings, ``..``, segments containing ``/``, and ASCII
        control characters (incl. NUL, CR, LF) with ``UniFiBadRequestError``.
        Other characters are percent-encoded via ``urllib.parse.quote`` with
        ``safe=""`` so query separators (``?``, ``#``) and reserved chars
        are escaped rather than reinterpreted.
        """
        if not isinstance(value, str) or not value or value == ".." or "/" in value:
            raise UniFiBadRequestError(f"invalid URL path segment: {value!r}")
        if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
            raise UniFiBadRequestError(f"invalid URL path segment: {value!r}")
        return urllib.parse.quote(value, safe="")

    @staticmethod
    def _parse_retry_after(header_value: str | None) -> int | None:
        """Parse a Retry-After header value in seconds.

        Handles the integer-seconds form (`Retry-After: 30`). The HTTP-date
        form is rare on JSON APIs and not parsed here; unparseable values
        return None.
        """
        if header_value is None:
            return None
        try:
            seconds = int(header_value.strip())
        except (TypeError, ValueError):
            return None
        return max(seconds, 0)

    def _extract_error_body(self, response: httpx.Response) -> str:
        """Return a short, actionable error description from a response body.

        UniFi APIs wrap error details in structured JSON; extracting the
        useful field beats truncating raw JSON at 200 chars and cutting the
        message off mid-word. Recognized envelopes:

        - Network legacy: ``{"meta": {"rc": "error", "msg": "api.err.X"}}``
        - Protect integration: ``{"error": {"message": "..."}}``
        - Simpler forms: ``{"error": "..."}`` or ``{"message": "..."}``

        Sensitive keys (passphrases, secrets, tokens) are masked at this
        boundary so downstream WARN logs and ``ToolError`` strings never
        carry reflected credentials (#148). When ``UNIFI_LOG_RAW_BODIES`` is
        unset (default), the DEBUG body log receives the key-name-redacted
        form with the configured API-key value additionally scrubbed, so a
        value reflected into a free-text field never lands in the log either;
        operators that need the untouched body for diagnosis must opt in.
        """
        raw_log_enabled = _log_raw_bodies_enabled()
        try:
            parsed = response.json()
        except ValueError:
            parsed = None

        if parsed is not None:
            safe_payload = _redact_sensitive(parsed)
            if raw_log_enabled:
                logger.debug("Error response body (HTTP %d): %s", response.status_code, response.text)
            else:
                logger.debug(
                    "Error response body (HTTP %d, redacted): %s",
                    response.status_code,
                    self._scrub_secret(str(safe_payload)),
                )
            if isinstance(safe_payload, dict):
                meta = safe_payload.get("meta") if isinstance(safe_payload.get("meta"), dict) else None
                err = safe_payload.get("error")
                candidates: list[Any] = [
                    meta.get("msg") if meta else None,
                    err.get("message") if isinstance(err, dict) else None,
                    err if isinstance(err, str) else None,
                    safe_payload.get("message"),
                ]
                for candidate in candidates:
                    if isinstance(candidate, str) and candidate:
                        return candidate
            # Structured but unrecognized — surface a stable opaque hint
            # rather than a 200-char slice that could leak HTML scraps.
            return "<unparseable body, see DEBUG log>"

        # Non-JSON body.
        if raw_log_enabled:
            logger.debug("Error response body (HTTP %d): %s", response.status_code, response.text)
        else:
            logger.debug(
                "Error response body (HTTP %d, %d bytes): redacted (set UNIFI_LOG_RAW_BODIES=1 to log)",
                response.status_code,
                len(response.text),
            )
        if not response.text.strip():
            # Empty (or whitespace-only) body: surface a hint instead of an
            # uninformative dangling "HTTP 401: " so operators have something
            # to look up. WWW-Authenticate is the most useful auth-error clue.
            www_auth = response.headers.get("www-authenticate")
            if www_auth:
                return f"(empty body; WWW-Authenticate: {www_auth})"
            return "(empty body)"
        return "<unparseable body, see DEBUG log>"

    @staticmethod
    def _secret_scrub_forms(secret: str) -> list[str]:
        """Return the literal secret plus the percent-encodings it might be reflected as.

        A controller that echoes the key into a URL or query field encodes it
        first — ``+`` becomes ``%2B``, ``/`` may become ``%2F`` — so a literal
        ``secret in text`` match misses it. UniFi OS keys are opaque tokens that
        can contain ``+``, ``/``, and ``=``, so the standard ``quote`` /
        ``quote_plus`` forms are the realistic reflection encodings to cover.
        Percent-encoding hex is case-insensitive (RFC 3986 §6.2.2.1) and a proxy
        may emit lowercase (``%2b``) where stdlib emits uppercase (``%2B``), so
        the lowercase-hex variant of each encoded form is included too. Real keys
        rarely contain ``+``/``/``/``=``, so for the common alphanumeric key every
        form collapses to the literal. The forms differ in their raw-vs-encoded
        bytes, so none is a substring of another and replacement order is
        irrelevant; returned sorted purely for deterministic output. See #303.
        """
        encoded = {
            urllib.parse.quote(secret),
            urllib.parse.quote(secret, safe=""),
            urllib.parse.quote_plus(secret),
        }
        lowercased = {re.sub(r"%[0-9A-F]{2}", lambda m: m.group().lower(), form) for form in encoded}
        forms = {secret, *encoded, *lowercased}
        return sorted(forms)

    def _scrub_secret(self, text: str) -> str:
        """Mask the configured API key's value anywhere it appears in ``text``.

        ``_redact_sensitive`` masks sensitive *keys* in a parsed body, but a
        controller can reflect the key *value* into a free-text field it echoes
        back (e.g. ``meta.msg``) or an HTML error page. This value-level scrub
        is the final backstop so the secret can never reach a surfaced error
        message regardless of where the upstream puts it, including when the
        upstream percent-encodes it. Secrets shorter than
        ``_MIN_SCRUBBABLE_SECRET_LEN`` are skipped to avoid mangling unrelated
        text. See §4 of #97 and #303.
        """
        secret = self._client.headers.get("X-API-Key")
        if not secret or len(secret) < _MIN_SCRUBBABLE_SECRET_LEN:
            return text
        for form in self._secret_scrub_forms(secret):
            if form in text:
                text = text.replace(form, REDACTED)
        return text

    def _raise_for_status(self, response: httpx.Response) -> None:
        """Map HTTP status codes to typed exceptions."""
        if response.is_success:
            return
        status = response.status_code
        body = self._scrub_secret(self._extract_error_body(response))
        if status == 400:
            raise UniFiBadRequestError(f"HTTP {status}: {body}", status_code=status)
        if status in (401, 403):
            raise UniFiAuthError(f"HTTP {status}: {body}", status_code=status)
        if status == 404:
            raise UniFiNotFoundError(f"HTTP {status}: {body}", status_code=status)
        if status == 429:
            retry_after = self._parse_retry_after(response.headers.get("retry-after"))
            raise UniFiRateLimitError(
                f"HTTP {status}: {body}",
                status_code=status,
                retry_after=retry_after,
            )
        if 500 <= status < 600:
            raise UniFiServerError(f"HTTP {status}: {body}", status_code=status)
        raise UniFiError(f"HTTP {status}: {body}", status_code=status)

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Execute an HTTP request with retry on transient errors.

        ConnectError is always retried (the request never reached the server).
        TimeoutException is only retried for GET/HEAD — for POST/PUT/DELETE/PATCH
        the server may have processed the write before the response was lost,
        and a retry would cause double-execution.

        HTTP 429 is retried for idempotent methods (GET/HEAD), sleeping for
        the ``Retry-After`` duration (capped at ``_MAX_RETRY_AFTER_SECONDS``)
        or 1 second if the header is absent. Bounded by ``self._max_retries``.

        The tenacity transient-error budget and the explicit 429-loop run
        independently, so the 429 loop applies a wall-clock fence: it
        refuses to sleep past ``timeout * _TOTAL_ELAPSED_TIMEOUT_MULTIPLIER``
        in cumulative elapsed time since ``_request`` was entered. The
        tenacity loop is bounded by ``max_retries`` x ``wait_exponential(max=10)``
        on its own. Without the 429 fence a pathological controller that
        alternates between transient failures and 429s can chain both
        budgets and produce single-tool calls that block for minutes. See
        #151.
        """
        method_upper = method.upper()
        retry_on: tuple[type[BaseException], ...] = (httpx.ConnectError,)
        if method_upper in ("GET", "HEAD"):
            retry_on = (httpx.ConnectError, httpx.TimeoutException)

        loop = asyncio.get_running_loop()
        start = loop.time()
        total_budget = float(self._timeout * _TOTAL_ELAPSED_TIMEOUT_MULTIPLIER)

        @retry(
            stop=stop_after_attempt(self._max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type(retry_on),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        )
        async def _do() -> httpx.Response:
            return await self._client.request(method, self._url(path), **kwargs)

        rate_limit_attempts = 0
        while True:
            try:
                response = await _do()
            except httpx.TimeoutException as exc:
                raise UniFiTimeoutError(str(exc)) from exc
            except httpx.ConnectError as exc:
                raise UniFiConnectionError(str(exc)) from exc

            try:
                self._raise_for_status(response)
            except UniFiRateLimitError as exc:
                # Honor Retry-After on idempotent methods only; a POST/PUT/DELETE
                # that returned 429 may have partially processed, and a retry
                # could cause double-execution.
                if method_upper not in ("GET", "HEAD"):
                    raise
                if rate_limit_attempts >= self._max_retries:
                    raise
                sleep_seconds = min(exc.retry_after or 1, _MAX_RETRY_AFTER_SECONDS)
                elapsed = loop.time() - start
                if elapsed + sleep_seconds > total_budget:
                    logger.warning(
                        "Rate-limit retry budget exhausted on %s %s "
                        "(elapsed=%.1fs + sleep=%ds > budget=%.1fs); surfacing 429.",
                        method_upper,
                        path,
                        elapsed,
                        sleep_seconds,
                        total_budget,
                    )
                    raise
                rate_limit_attempts += 1
                logger.warning(
                    "Rate limited (429) on %s %s; sleeping %ds before retry %d/%d",
                    method_upper,
                    path,
                    sleep_seconds,
                    rate_limit_attempts,
                    self._max_retries,
                )
                await asyncio.sleep(sleep_seconds)
                continue

            return response

    def _parse_json(self, response: httpx.Response) -> Any:
        """Parse JSON response body, wrapping decode errors as UniFiError.

        Raises UniFiAuthError when the controller returns HTML on a JSON
        endpoint. UniFi OS serves the SPA portal (HTML) on ``/proxy/<api>/*``
        when the request hits a path that rejects the configured auth — a
        signature of wrong ``_path_prefix``, key-for-wrong-host, or an
        API that requires session auth. Classifying this case as "auth /
        path mismatch" instead of generic "invalid JSON" lets the operator
        act on it.
        """
        content_type = response.headers.get("content-type", "").lower()
        if content_type.startswith("text/html"):
            body = self._scrub_secret(response.text[:200])
            raise UniFiAuthError(
                f"Controller returned HTML instead of JSON on HTTP {response.status_code} — "
                f"likely an auth/path mismatch (hit the UniFi OS portal). Check host, "
                f"port, and API-key scope. Body: {body}",
                status_code=response.status_code,
            )
        try:
            return response.json()
        except ValueError as exc:
            body = self._scrub_secret(response.text[:200])
            raise UniFiError(
                f"Invalid JSON in response (HTTP {response.status_code}): {body}",
                status_code=None,
            ) from exc

    async def get(self, path: str, **kwargs: Any) -> Any:
        """HTTP GET, returns parsed JSON."""
        response = await self._request("GET", path, **kwargs)
        return self._parse_json(response)

    async def post(self, path: str, **kwargs: Any) -> Any:
        """HTTP POST, returns parsed JSON."""
        response = await self._request("POST", path, **kwargs)
        if response.status_code == 204 or not response.content:
            return {}
        return self._parse_json(response)

    async def put(self, path: str, **kwargs: Any) -> Any:
        """HTTP PUT, returns parsed JSON."""
        response = await self._request("PUT", path, **kwargs)
        if response.status_code == 204 or not response.content:
            return {}
        return self._parse_json(response)

    async def patch(self, path: str, **kwargs: Any) -> Any:
        """HTTP PATCH, returns parsed JSON.

        PATCH is non-idempotent, so ``_request`` does not retry it on a lost
        response (only GET/HEAD are retried on timeout) — a partially applied
        write is never silently re-sent.
        """
        response = await self._request("PATCH", path, **kwargs)
        if response.status_code == 204 or not response.content:
            return {}
        return self._parse_json(response)

    async def delete(self, path: str, **kwargs: Any) -> Any:
        """HTTP DELETE, returns parsed JSON or empty dict."""
        response = await self._request("DELETE", path, **kwargs)
        if response.status_code == 204 or not response.content:
            return {}
        return self._parse_json(response)

    async def get_raw(self, path: str, *, max_bytes: int | None = None, **kwargs: Any) -> bytes:
        """HTTP GET returning raw bytes (for media endpoints).

        When ``max_bytes`` is set the response is streamed and aborted as soon
        as the accumulated payload exceeds the cap, raising ``UniFiError``
        instead of silently consuming unbounded memory.

        Both branches share the same transient-error retry semantics as
        ``_request``: ``ConnectError`` and ``TimeoutException`` are retried
        (bounded by ``max_retries``), status-code errors are mapped to typed
        UniFi exceptions.
        """
        if max_bytes is None:
            response = await self._request("GET", path, **kwargs)
            result: bytes = response.content
            return result

        url = self._url(path)
        retry_on: tuple[type[BaseException], ...] = (httpx.ConnectError, httpx.TimeoutException)

        @retry(
            stop=stop_after_attempt(self._max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type(retry_on),
            reraise=True,
        )
        async def _stream_once() -> bytes:
            """Stream one request attempt, enforcing max_bytes mid-stream.

            Transport errors raised in here bubble out of the context manager
            and are caught by tenacity for retry. Mapped UniFi errors bubble
            unchanged (they aren't in ``retry_on``).

            Defensive copy of ``kwargs`` per attempt: httpx is free to mutate
            mutable values (a streaming-body iterator would be exhausted on
            the first try) and a future caller passing such a value should
            not silently diverge between retries. See #151.
            """
            attempt_kwargs = dict(kwargs)
            async with self._client.stream("GET", url, **attempt_kwargs) as response:
                if not response.is_success:
                    # _raise_for_status reads response.text, which on a
                    # streaming response requires the body to be loaded first.
                    await response.aread()
                    self._raise_for_status(response)
                chunks: list[bytes] = []
                total = 0
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > max_bytes:
                        raise UniFiError(
                            f"Response exceeded max_bytes={max_bytes} while streaming {path}",
                            status_code=response.status_code,
                        )
                    chunks.append(chunk)
                return b"".join(chunks)

        try:
            return await _stream_once()
        except httpx.TimeoutException as exc:
            raise UniFiTimeoutError(str(exc)) from exc
        except httpx.ConnectError as exc:
            raise UniFiConnectionError(str(exc)) from exc

    # ── Lifecycle ───────────────────────────────────────────────────────

    @abstractmethod
    async def validate_connection(self) -> bool:
        """Validate that the API is reachable and authenticated.

        Subclasses must override with a lightweight health-check request.

        Returns False on any UniFi or HTTP error.

        NOTE: a False return causes the server lifespan to deregister every
        tool for this API via ``server.disable(tags={api_name})``. Failure
        modes that feel transient — a wrong ``_path_prefix``, expired API
        key, transient 404, SSL mismatch — will make all of this API's
        tools disappear from the MCP tool list with only a log line. See
        #104 for the diagnostic enhancement that surfaces *why* validation
        failed.
        """

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
