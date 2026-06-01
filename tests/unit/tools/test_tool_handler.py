"""Contract tests for the shared ``tool_handler`` decorator.

Every tool handler is wrapped by ``tool_handler`` (see ``tools/_common``),
which owns two cross-cutting concerns: routing exceptions through
``handle_client_error`` and gating write tools on ``config.writes_enabled``.
The handler-body and write-gate suites exercise it through real tools; these
tests pin its behavior in isolation, including the contract that it preserves
the wrapped function's signature for FastMCP schema introspection.
"""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastmcp.exceptions import ToolError

from unifi_mcp.config import UniFiConfig, UniFiMode
from unifi_mcp.errors import UniFiAuthError
from unifi_mcp.tools._common import tool_handler


@dataclass
class _FakeLifespan:
    config: UniFiConfig
    clients: dict[str, Any] = field(default_factory=dict)


def _ctx(*, writes_enabled: bool) -> AsyncMock:
    mode = UniFiMode.READWRITE if writes_enabled else UniFiMode.READONLY
    ctx = AsyncMock()
    ctx.lifespan_context = _FakeLifespan(config=UniFiConfig(_env_file=None, unifi_mode=mode, unifi_network_api="k"))
    return ctx


async def test_read_handler_passes_through_return_value() -> None:
    @tool_handler()
    async def handler(ctx: Any, value: int) -> int:
        return value * 2

    assert await handler(_ctx(writes_enabled=False), 21) == 42


async def test_exceptions_route_through_handle_client_error() -> None:
    @tool_handler()
    async def handler(ctx: Any) -> None:
        raise UniFiAuthError("bad key", status_code=401)

    with pytest.raises(ToolError, match="Authentication failed"):
        await handler(_ctx(writes_enabled=False))


async def test_write_gate_blocks_and_skips_body_in_readonly_mode() -> None:
    ran = False

    @tool_handler(write=True)
    async def handler(ctx: Any) -> None:
        nonlocal ran
        ran = True

    with pytest.raises(ToolError, match="read-only mode"):
        await handler(_ctx(writes_enabled=False))
    assert not ran, "the write gate must fire before the handler body runs"


async def test_write_handler_runs_when_writes_enabled() -> None:
    @tool_handler(write=True)
    async def handler(ctx: Any) -> str:
        return "did-write"

    assert await handler(_ctx(writes_enabled=True)) == "did-write"


async def test_non_exception_baseexception_propagates_unwrapped() -> None:
    @tool_handler()
    async def handler(ctx: Any) -> None:
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await handler(_ctx(writes_enabled=False))


def test_decorator_preserves_wrapped_signature() -> None:
    @tool_handler(write=True)
    async def handler(ctx: Any, rule_id: str, count: int = 5) -> None: ...

    params = list(inspect.signature(handler).parameters)
    assert params == ["ctx", "rule_id", "count"]
