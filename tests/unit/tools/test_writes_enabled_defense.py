"""Defense-in-depth coverage for the in-handler ``writes_enabled`` runtime gate.

``TestModeGating`` in ``tests/unit/test_server.py`` only asserts that write
tools are hidden via the ``{"write"}`` tag in readonly mode. Every write
handler also carries a second-line check —
``if not context.config.writes_enabled: raise UniFiReadOnlyError(...)`` —
which would protect against a misconfigured server that exposed a write tool
in readonly mode for any reason. This module force-enables the tools via
``server.enable(tags={"write"})`` (bypassing the tag gate) and invokes each
through ``fastmcp.Client`` to confirm the in-handler gate also fires.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from unifi_mcp.config import UniFiConfig, UniFiMode
from unifi_mcp.server import create_server


@pytest.fixture(autouse=True)
def _stub_live_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the FastMCP lifespan offline so the write-gate test is hermetic.

    Opening ``Client(server)`` runs ``server_lifespan``, which calls each
    client's ``validate_connection`` against the configured host (default
    ``192.168.1.1``). On a LAN with a real UniFi controller — the documented
    ``.env`` dev setup — those live calls return 401, the lifespan disables
    every API's tools, and the write tool under test resolves to "Unknown tool"
    before its in-handler ``writes_enabled`` gate can fire. Stubbing validation
    to succeed keeps registration offline and deterministic regardless of the
    machine's network.
    """

    async def _ok(self: Any) -> bool:
        return True

    for target in (
        "unifi_mcp.clients.network.NetworkClient.validate_connection",
        "unifi_mcp.clients.network_integration.NetworkIntegrationClient.validate_connection",
        "unifi_mcp.clients.protect.ProtectClient.validate_connection",
        "unifi_mcp.clients.site_manager.SiteManagerClient.validate_connection",
    ):
        monkeypatch.setattr(target, _ok, raising=True)


def _make_config(**overrides: Any) -> UniFiConfig:
    defaults: dict[str, Any] = {
        "_env_file": None,
        "unifi_network_api": "test-net-key",
        "unifi_protect_api": "test-prot-key",
        "unifi_site_manager_api": "test-sm-key",
    }
    defaults.update(overrides)
    return UniFiConfig(**defaults)


_TYPE_PLACEHOLDERS: dict[str, Any] = {
    "integer": 1,
    "number": 1,
    "boolean": False,
    "object": {},
    "array": [],
}


def _placeholder_for_schema(prop: dict[str, Any]) -> Any:
    """Return a minimal value satisfying the JSON-schema fragment for a single arg.

    Strings whose description mentions a MAC address get a syntactically valid
    MAC so ``validate_mac`` (which runs before the writes_enabled check in
    several handlers) doesn't short-circuit the gate. Integers default to 1
    because ``port_idx`` is bounded to ``1..52`` before the gate fires in
    ``unifi_network_assign_port_profile`` and ``unifi_network_power_cycle_port``.
    """
    schema_type = prop.get("type")
    if schema_type is None:
        any_of = prop.get("anyOf") or []
        return _placeholder_for_schema(any_of[0]) if any_of else None
    if schema_type == "string":
        description = (prop.get("description") or "").lower()
        return "aabbccddeeff" if "mac address" in description else "a"
    return _TYPE_PLACEHOLDERS.get(schema_type)


def _minimal_args_from_schema(schema: dict[str, Any]) -> dict[str, Any]:
    required = schema.get("required") or []
    props = schema.get("properties") or {}
    return {name: _placeholder_for_schema(props.get(name, {})) for name in required}


async def _collect_write_tools() -> list[tuple[str, dict[str, Any]]]:
    config = _make_config(unifi_mode=UniFiMode.READWRITE)
    server = create_server(config)
    tools = await server.list_tools()
    return [(t.name, t.parameters) for t in tools if "write" in getattr(t, "tags", set())]


_WRITE_TOOLS: list[tuple[str, dict[str, Any]]] = asyncio.run(_collect_write_tools())


# Floor catches silent tag-loss regressions: a refactor that drops `{"write"}`
# from a handful of handlers would shrink the parametrize set silently without
# the >=1 check noticing. Project docs (CLAUDE.md) document ~43 write tools;
# 40 is the loosest floor that still trips on a meaningful regression.
_WRITE_TOOLS_FLOOR = 40


def test_write_tool_inventory_meets_floor() -> None:
    assert len(_WRITE_TOOLS) >= _WRITE_TOOLS_FLOOR, (
        f"expected >= {_WRITE_TOOLS_FLOOR} write-tagged tools, got {len(_WRITE_TOOLS)}; "
        "tag wiring may be broken or write tools may have been silently removed"
    )


@pytest.mark.parametrize(
    ("tool_name", "schema"),
    _WRITE_TOOLS,
    ids=[name for name, _ in _WRITE_TOOLS],
)
async def test_writes_enabled_gate_fires_in_readonly_mode(tool_name: str, schema: dict[str, Any]) -> None:
    config = _make_config(unifi_mode=UniFiMode.READONLY)
    server = create_server(config)
    # Force-re-enable the write tag so the tool is reachable from the Client;
    # this bypasses the registration-layer gate so the in-handler runtime
    # gate is the only thing standing between the call and the client layer.
    server.enable(tags={"write"})

    args = _minimal_args_from_schema(schema)
    async with Client(server) as client:
        with pytest.raises(ToolError) as excinfo:
            await client.call_tool(tool_name, args)

    # fastmcp.Client re-raises ToolError from the wire format without preserving
    # __cause__, so isinstance-on-cause is unavailable across the Client boundary
    # — message-content is the only contract surfaced to the agent. Both literals
    # come from handle_client_error's UniFiReadOnlyError branch (errors.py:125-126);
    # mismatch means either the writes_enabled gate didn't fire or arg-level
    # validation surfaced ahead of it (placeholder values may need updating).
    message = str(excinfo.value).lower()
    assert "read-only mode" in message, (
        f"{tool_name}: expected ToolError carrying the readonly suffix; got {excinfo.value!r}."
    )
    assert "write operation blocked" in message, (
        f"{tool_name}: expected ToolError carrying the handle_client_error prefix "
        f"for UniFiReadOnlyError; got {excinfo.value!r}."
    )
