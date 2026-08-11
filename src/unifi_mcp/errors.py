"""Exception hierarchy and error mapping for UniFi MCP server."""

from __future__ import annotations

import logging
from typing import NoReturn

from fastmcp.exceptions import ToolError

logger = logging.getLogger(__name__)


class UniFiError(Exception):
    """Base exception for all UniFi API errors."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        self.status_code = status_code
        super().__init__(message)


class UniFiAuthError(UniFiError):
    """Authentication or authorization failure (401/403)."""


class UniFiPortalHtmlError(UniFiAuthError):
    """Controller served the UniFi OS SPA portal (HTML) on a JSON ``/proxy/<api>/*``
    path — a wrong-host / wrong-path / wrong-key-scope signature, not a credential
    rejection.

    Subclasses :class:`UniFiAuthError` so existing auth-error mapping still applies,
    while the distinct name keeps the typical ``HTTP 200`` case from reading as a
    self-contradictory "auth failure" in the startup deregistration WARN.

    ``guidance`` is a fixed, reflected-content-free hint safe to surface at WARN;
    the scrubbed reflected body snippet rides ``str(self)`` for DEBUG/tool sinks only.
    """

    guidance = (
        "Controller returned HTML instead of JSON (hit the UniFi OS portal) — likely "
        "a wrong host/port or API-key scope, not a credential rejection. Check host, "
        "port, and API-key scope for this service."
    )

    def __init__(self, body: str, status_code: int | None = None) -> None:
        self.body = body
        super().__init__(f"{self.guidance} Body: {body}", status_code=status_code)


class UniFiBadRequestError(UniFiError):
    """Malformed or invalid request payload (400)."""


class UniFiNotFoundError(UniFiError):
    """Resource not found (404)."""


class UniFiRateLimitError(UniFiError):
    """Rate limit exceeded (429)."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        retry_after: int | None = None,
    ) -> None:
        super().__init__(message, status_code=status_code)
        self.retry_after = retry_after


class UniFiServerError(UniFiError):
    """Upstream server failure (5xx)."""


class UniFiConnectionError(UniFiError):
    """Connection failure (DNS, network, TCP reset)."""


class UniFiTimeoutError(UniFiConnectionError):
    """Request exceeded the configured timeout."""


class UniFiReadOnlyError(UniFiError):
    """Write operation attempted in read-only mode."""


class UniFiDeviceAlreadyAdoptedError(UniFiError):
    """Adopt invoked on a device that's already adopted by this controller.

    The controller returns a generic ``api.err.InvalidTarget`` for this case,
    which is indistinguishable from "MAC unknown to controller" at the raw API
    level. ``NetworkClient.adopt_device`` pre-checks against ``list_devices``
    and raises this to give agents a specific, actionable error to branch on.
    """


def _classify_error_tag(error: BaseException) -> str:
    """Prefix ToolError messages with ``[HTTP <status>] `` when a code is known.

    Agents typically branch on status to decide whether to retry, re-auth,
    or give up. Embedding the code in the message avoids forcing them to
    regex out "HTTP 4xx" from the inner exception stringification.
    """
    status = getattr(error, "status_code", None)
    return f"[HTTP {status}] " if isinstance(status, int) else ""


def handle_client_error(error: BaseException) -> NoReturn:
    """Map UniFi exceptions to FastMCP ToolError with agent-readable messages.

    Non-``Exception`` ``BaseException`` subclasses are re-raised untouched —
    wrapping them as ``ToolError`` would break FastMCP's propagation of
    cancellation, interrupts, and interpreter shutdown:

    - ``asyncio.CancelledError`` — cooperative task cancellation; wrapping
      it would turn a cancel into a phantom tool failure and prevent
      shutdown finally-blocks from running.
    - ``KeyboardInterrupt`` — SIGINT during tool execution; must propagate
      so the operator regains control.
    - ``SystemExit`` — explicit ``sys.exit``; must terminate the process.
    - ``GeneratorExit`` — async generator cleanup; catching it would
      corrupt coroutine state.

    Raises:
        BaseException (non-``Exception``): Propagated without wrapping.
        ToolError: For any ``Exception`` subclass, with a descriptive
            message. Messages carry a ``[HTTP <status>]`` prefix when the
            UniFi exception carried a status code, so agents can branch
            on status without regex-ing the inner message.
    """
    # BaseException subclasses that aren't Exception must propagate as-is:
    # asyncio.CancelledError, KeyboardInterrupt, SystemExit, GeneratorExit.
    if not isinstance(error, Exception):
        raise error
    tag = _classify_error_tag(error)
    if isinstance(error, UniFiAuthError):
        raise ToolError(f"{tag}Authentication failed: {error}. Check your API key.") from error
    if isinstance(error, UniFiBadRequestError):
        raise ToolError(f"{tag}Invalid request: {error}.") from error
    if isinstance(error, UniFiNotFoundError):
        raise ToolError(f"{tag}Resource not found: {error}") from error
    if isinstance(error, UniFiRateLimitError):
        raise ToolError(f"{tag}Rate limit exceeded: {error}. Try again later.") from error
    if isinstance(error, UniFiServerError):
        raise ToolError(f"{tag}UniFi server error: {error}. The controller may be unhealthy.") from error
    if isinstance(error, UniFiTimeoutError):
        raise ToolError(f"{tag}Request timed out: {error}. The controller did not respond in time.") from error
    if isinstance(error, UniFiConnectionError):
        raise ToolError(f"{tag}Connection failed: {error}. Check host and network.") from error
    if isinstance(error, UniFiReadOnlyError):
        raise ToolError(f"Write operation blocked: {error}. Server is in read-only mode.") from error
    if isinstance(error, UniFiDeviceAlreadyAdoptedError):
        raise ToolError(f"Device already adopted: {error}") from error
    if isinstance(error, UniFiError):
        raise ToolError(f"{tag}UniFi API error: {error}") from error
    # Unexpected errors — do NOT echo str(error) to the agent. ``exc_info=error``
    # keeps the full traceback in the server log for the operator; the call is not
    # lexically inside an ``except`` block, which is what rules out logger.exception.
    logger.error("Unexpected error in tool execution", exc_info=error)
    raise ToolError("Unexpected internal error; check server logs") from error
