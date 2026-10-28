"""Framework-independent UniFi API exceptions and legacy mapping entry point."""

from __future__ import annotations

from typing import NoReturn


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


class UniFiUnsupportedError(UniFiError):
    """Operation unavailable on this controller or API surface."""


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


def handle_client_error(error: BaseException) -> NoReturn:
    """Compatibility entry point for MCP error mapping; imports FastMCP on call."""
    from unifi_mcp.tools._error_adapter import handle_client_error as map_error

    map_error(error)
