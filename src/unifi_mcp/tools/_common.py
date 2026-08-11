"""Shared helpers and type aliases for tool modules."""

from __future__ import annotations

import functools
import re
from typing import TYPE_CHECKING, Any, Concatenate, cast

from unifi_mcp._redaction import normalize_key, redact_secrets
from unifi_mcp.errors import UniFiBadRequestError, UniFiReadOnlyError, handle_client_error

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from fastmcp import Context

    from unifi_mcp.server import ServerContext

type JsonObject = dict[str, Any]

__all__ = [
    "JsonObject",
    "build_named_arg_body",
    "get_server_context",
    "redact_secrets",
    "reject_dangerous_keys",
    "tool_handler",
    "validate_id",
    "validate_mac",
]


def get_server_context(ctx: Context) -> ServerContext:
    """Return the typed lifespan context for a tool call."""
    return cast("ServerContext", ctx.lifespan_context)


def tool_handler[**P, R](
    *, write: bool = False
) -> Callable[[Callable[Concatenate[Context, P], Awaitable[R]]], Callable[Concatenate[Context, P], Awaitable[R]]]:
    """Wrap a tool handler with the cross-cutting envelope every tool shares.

    Two concerns, identical across all tools, live here instead of being
    copied into each handler body:

    - **Error funnel:** the body runs inside a ``try`` whose ``except`` routes
      every exception through :func:`handle_client_error`, which maps UniFi
      exceptions to agent-readable ``ToolError`` and re-raises non-``Exception``
      ``BaseException`` (cancellation, ``KeyboardInterrupt``) untouched.
    - **Write gate (defense-in-depth):** when ``write=True``, the handler
      refuses to run unless ``config.writes_enabled``. Write tools are already
      hidden by the ``{"write"}`` tag in readonly mode; this is the second line
      that protects a misconfigured server that exposed the tool anyway. The
      gate fires before the body, so input validation never runs ahead of it.

    The wrapper preserves the wrapped function's signature via
    ``functools.wraps`` so FastMCP's schema introspection sees the real
    parameters, defaults, and ``Args`` docstring unchanged.

    Args:
        write: Whether the handler mutates state and must be gated on
            ``config.writes_enabled``.
    """

    def decorator(
        func: Callable[Concatenate[Context, P], Awaitable[R]],
    ) -> Callable[Concatenate[Context, P], Awaitable[R]]:
        @functools.wraps(func)
        async def wrapper(ctx: Context, *args: P.args, **kwargs: P.kwargs) -> R:
            try:
                if write and not get_server_context(ctx).config.writes_enabled:
                    raise UniFiReadOnlyError("write tool invoked while server is in read-only mode")
                return await func(ctx, *args, **kwargs)
            except Exception as exc:
                handle_client_error(exc)

        return wrapper

    return decorator


# ── Settings-smuggling denylist (#147) ─────────────────────────────────────
#
# `dict[str, Any]` write tools forward the body verbatim to the controller.
# A write-mode agent receiving a prompt-injected instruction can smuggle
# config changes the tool name does NOT advertise. Caught here: RADIUS
# hijack via `radius_servers`, callback exfil via `super_mgmt_url`, lockout
# via `mac_filter_list`.
#
# NOT caught: evidence suppression via Protect recording fields.
# `recordingSettings` normalizes to `recordingsettings`, which is in no
# exact-key set, starts with no denied prefix, and ends in neither suffix.
# Unreachable today only because no Protect writer that targets
# `cameras/{id}` accepts a raw dict: `update_camera` takes named scalar args
# only and passes `data=None`. `update_chime`, `update_light` and
# `update_sensor` do forward `data` verbatim, but their endpoints carry no
# recording settings. A camera writer that accepts `data` reopens it (#501).
#
# This denylist is a stopgap (option 2 from the issue). The honest answer
# (option 1) is per-endpoint named scalar args + an explicit allowlist —
# tracked as a follow-up.

_DENYLIST_EXACT_KEYS: frozenset[str] = frozenset(
    {
        "cmd",
        "x_cmd",
        "is_admin",
        "role",
        "roles",
        "permissions",
        "mac_filter_list",
        "mac_filter_enabled",
    }
)
_DENYLIST_KEY_PREFIXES: tuple[str, ...] = ("super_", "radius_")
_DENYLIST_KEY_SUFFIXES: tuple[str, ...] = ("_url", "_command")

# Normalized forms of the patterns above — built once at import time. The
# normalize step (lowercase + strip underscores) is shared with the redaction
# denylist so both classify snake_case (Network) and camelCase (Protect) keys
# identically; the denylists themselves stay independent.
_NORM_EXACT_KEYS: frozenset[str] = frozenset(normalize_key(k) for k in _DENYLIST_EXACT_KEYS)
_NORM_PREFIXES: tuple[str, ...] = tuple(normalize_key(p) for p in _DENYLIST_KEY_PREFIXES)
_NORM_SUFFIXES: tuple[str, ...] = tuple(normalize_key(s) for s in _DENYLIST_KEY_SUFFIXES)


def _is_dangerous_key(key: str) -> bool:
    normalized = normalize_key(key)
    if normalized in _NORM_EXACT_KEYS:
        return True
    if any(normalized.startswith(p) for p in _NORM_PREFIXES):
        return True
    return any(normalized.endswith(s) for s in _NORM_SUFFIXES)


def _walk(value: Any, path: str, *, tool_name: str) -> None:
    if isinstance(value, dict):
        for raw_key, sub in value.items():
            key = str(raw_key)
            sub_path = f"{path}.{key}" if path else key
            if _is_dangerous_key(key):
                raise UniFiBadRequestError(
                    f"{tool_name}: dangerous key '{sub_path}' is not allowed; "
                    f"use the dedicated tool or split your update."
                )
            _walk(sub, sub_path, tool_name=tool_name)
    elif isinstance(value, list):
        for idx, item in enumerate(value):
            _walk(item, f"{path}[{idx}]", tool_name=tool_name)


def reject_dangerous_keys(data: Any, *, tool_name: str) -> None:
    """Raise ``UniFiBadRequestError`` if ``data`` contains a smuggling key.

    Walks dicts and lists recursively. Keys are matched after a normalize
    step (lowercase + strip underscores) so the same rule catches both
    snake_case (Network APIs) and camelCase (Protect APIs) variants.
    Designed to be called at the top of every ``dict[str, Any]`` write
    tool, after the ``writes_enabled`` mode gate, before the client call.

    Args:
        data: Request body to inspect — typically a top-level ``dict``.
        tool_name: Tool identifier for the error message.

    Raises:
        UniFiBadRequestError: If a dangerous key is found, with a dotted
            path locating it in the payload.
    """
    _walk(data, "", tool_name=tool_name)


# ── Path-segment input validation (#145) ───────────────────────────────────
#
# ``BaseUniFiClient._segment`` is the last-line defense — it percent-encodes
# whatever it receives so a traversal payload cannot escape ``_path_prefix``.
# These tool-layer validators reject the same payloads earlier, with a
# clearer error message (``invalid id format`` vs. the encoded surface),
# and prevent surprising IDs from reaching the controller in the first
# place. Patterns intentionally narrow — UniFi IDs are mongo ObjectIds or
# similar short tokens, never URL-shaped.

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_MAC_RE = re.compile(
    r"(?:^[0-9a-fA-F]{12}$)"
    r"|(?:^([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}$)"
    r"|(?:^([0-9a-fA-F]{2}-){5}[0-9a-fA-F]{2}$)"
    r"|(?:^([0-9a-fA-F]{4}\.){2}[0-9a-fA-F]{4}$)"
)


def validate_id(value: str, *, field: str) -> None:
    """Validate that ``value`` looks like a UniFi resource ID.

    Accepts 1-64 chars from ``[A-Za-z0-9_-]``. Anything outside that set —
    notably ``/``, ``?``, ``#``, ``..``, or whitespace — is rejected.
    See #145 for the path-traversal motivation.

    Args:
        value: The candidate ID string from a tool argument.
        field: Name of the tool argument, used to make the error specific.

    Raises:
        UniFiBadRequestError: If ``value`` doesn't match the ID pattern.
    """
    if not isinstance(value, str) or not _ID_RE.match(value):
        raise UniFiBadRequestError(f"{field}: invalid id format")


def validate_mac(value: str, *, field: str) -> None:
    """Validate that ``value`` looks like a MAC address.

    Accepts the common representations (``aa:bb:cc:dd:ee:ff``,
    ``aabbccddeeff``, ``aa-bb-cc-dd-ee-ff``, ``aabb.ccdd.eeff``). Strict
    canonicalization is left to the upstream controller; this is just
    a path-injection gate.

    Args:
        value: The candidate MAC string from a tool argument.
        field: Name of the tool argument, used to make the error specific.

    Raises:
        UniFiBadRequestError: If ``value`` doesn't match the MAC pattern.
    """
    if not isinstance(value, str) or not _MAC_RE.match(value):
        raise UniFiBadRequestError(f"{field}: invalid mac format")


# ── Option-1 named-arg builder (#202) ──────────────────────────────────────
#
# Per-endpoint write tools expose a flat, named-scalar surface that maps
# allowlisted kwargs to nested fields in the controller's request body.
# This builder enforces the shared contract:
#   - named args win over the legacy ``data`` dict and may not be mixed,
#   - at least one input is required,
#   - the resulting body still flows through ``reject_dangerous_keys``.
# Deliberately omitted fields (e.g. Protect ``recordingSettings``) stay
# outside the allowlist so the named API can never reach them.


def _assign_nested(body: dict[str, Any], path: tuple[str, ...], value: Any) -> None:
    cursor: dict[str, Any] = body
    for segment in path[:-1]:
        next_cursor = cursor.setdefault(segment, {})
        if not isinstance(next_cursor, dict):
            raise UniFiBadRequestError(f"path collision at '{segment}' while building update body")
        cursor = next_cursor
    cursor[path[-1]] = value


def build_named_arg_body(
    *,
    tool_name: str,
    field_paths: dict[str, tuple[str, ...]],
    named_values: dict[str, Any],
    data: JsonObject | None,
) -> JsonObject:
    """Resolve named scalar args + legacy ``data`` dict into one request body.

    "``data`` was supplied" means ``data is not None`` — an explicitly passed
    empty dict counts as supplied. This single definition drives both guards:
    mixing named args with any non-``None`` ``data`` raises the mix error, and
    once that is cleared an empty ``data={}`` produces an empty body that falls
    through to the "at least one field" error.

    Args:
        tool_name: Calling tool name, used in error messages.
        field_paths: Maps each kwarg name to its dotted destination in the
            outgoing body. Keys not present here cannot be set via the
            named API — the named-arg surface is the allowlist.
        named_values: Snapshot of the tool's keyword arguments, including
            ``None`` for unsupplied ones; ``None`` values are skipped.
        data: Legacy raw-dict path. ``None`` when the caller used named
            args; otherwise passed through verbatim.

    Returns:
        The request body to forward to the upstream API.

    Raises:
        UniFiBadRequestError: If both ``data`` and named args are
            supplied, or neither.
    """
    supplied_named = {k: v for k, v in named_values.items() if v is not None}
    data_supplied = data is not None
    if supplied_named and data_supplied:
        raise UniFiBadRequestError("Cannot mix named args with raw data dict")
    if data_supplied and data:
        return data
    if not supplied_named:
        raise UniFiBadRequestError(f"{tool_name}: at least one field must be provided")
    body: JsonObject = {}
    for kwarg, value in supplied_named.items():
        _assign_nested(body, field_paths[kwarg], value)
    return body
