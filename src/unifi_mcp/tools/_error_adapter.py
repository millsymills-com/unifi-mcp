"""Present transport exceptions as FastMCP tool errors."""

from __future__ import annotations

import logging
from typing import NoReturn

from fastmcp.exceptions import ToolError

from unifi_mcp.errors import (
    UniFiAuthError,
    UniFiBadRequestError,
    UniFiConnectionError,
    UniFiDeviceAlreadyAdoptedError,
    UniFiError,
    UniFiNotFoundError,
    UniFiRateLimitError,
    UniFiReadOnlyError,
    UniFiServerError,
    UniFiTimeoutError,
    UniFiUnsupportedError,
)

logger = logging.getLogger("unifi_mcp.errors")


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
    if isinstance(error, UniFiUnsupportedError):
        raise ToolError(f"{tag}Unsupported operation: {error}") from error
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
