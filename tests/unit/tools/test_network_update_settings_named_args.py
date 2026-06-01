"""Named-scalar-arg variants for unifi_network_update_settings (#202).

Completes the option-1 rollout from #202 for the Network controller-wide
``rest/setting`` endpoint. Exercises the allowlist API:
- supplying named args builds the correct nested body server-side,
- supplying no named args raises BadRequest,
- the shared ``build_named_arg_body`` helper rejects path collisions
  (locks in the contract for future allowlist additions).

All HTTP is mocked with ``respx``; nothing reaches real hardware.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
import respx
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from unifi_mcp.clients.network import NetworkClient
from unifi_mcp.config import UniFiConfig, UniFiMode
from unifi_mcp.errors import UniFiBadRequestError
from unifi_mcp.tools._common import build_named_arg_body
from unifi_mcp.tools.network.system import register_system_tools

BASE_URL = "https://10.0.0.1:443"
SITE_PREFIX = f"{BASE_URL}/proxy/network/api/s/default"


# ── Fixtures ───────────────────────────────────────────────────────────────


@dataclass
class FakeLifespan:
    config: UniFiConfig
    clients: dict[str, Any] = field(default_factory=dict)


def _readwrite_config() -> UniFiConfig:
    return UniFiConfig(
        _env_file=None,
        unifi_mode=UniFiMode.READWRITE,
        unifi_network_api="k",
        unifi_protect_api="k",
        unifi_site_manager_api=None,
    )


def _ctx_with_network_client() -> tuple[AsyncMock, NetworkClient]:
    """Build a ctx whose Network client talks to the respx-mocked base URL."""
    client = NetworkClient(
        base_url=BASE_URL,
        api_key="test-key",
        site="default",
        timeout=5,
        max_retries=1,
    )
    ctx = AsyncMock()
    ctx.lifespan_context = FakeLifespan(config=_readwrite_config(), clients={"network": client})
    return ctx, client


async def _call(server: FastMCP, tool_name: str, ctx: AsyncMock, **kwargs: Any) -> Any:
    tool = await server.get_tool(tool_name)
    return await tool.fn(ctx, **kwargs)


# ── update_settings ────────────────────────────────────────────────────────


class TestUpdateSettingsNamedArgs:
    @respx.mock
    async def test_single_named_arg_routes_to_ntp_section_via_per_section_put(self):
        server = FastMCP(name="t")
        register_system_tools(server)
        ctx, _ = _ctx_with_network_client()
        route = respx.put(f"{SITE_PREFIX}/rest/setting/ntp").mock(return_value=httpx.Response(200, json={"ok": True}))

        result = await _call(
            server,
            "unifi_network_update_settings",
            ctx,
            ntp_server_1="time.example.com",
        )

        assert result == {"ok": True}
        sent = json.loads(route.calls[0].request.content)
        assert sent == {"ntp_server_1": "time.example.com"}

    @respx.mock
    async def test_mgmt_led_enabled_routes_to_mgmt_section(self):
        server = FastMCP(name="t")
        register_system_tools(server)
        ctx, _ = _ctx_with_network_client()
        route = respx.put(f"{SITE_PREFIX}/rest/setting/mgmt").mock(return_value=httpx.Response(200, json={}))

        await _call(server, "unifi_network_update_settings", ctx, mgmt_led_enabled=False)

        sent = json.loads(route.calls[0].request.content)
        assert sent == {"led_enabled": False}

    @respx.mock
    async def test_both_ntp_servers_merge_under_one_section_put(self):
        server = FastMCP(name="t")
        register_system_tools(server)
        ctx, _ = _ctx_with_network_client()
        route = respx.put(f"{SITE_PREFIX}/rest/setting/ntp").mock(return_value=httpx.Response(200, json={}))

        await _call(
            server,
            "unifi_network_update_settings",
            ctx,
            ntp_server_1="time.example.com",
            ntp_server_2="time2.example.com",
        )

        assert route.call_count == 1
        sent = json.loads(route.calls[0].request.content)
        assert sent == {"ntp_server_1": "time.example.com", "ntp_server_2": "time2.example.com"}

    @respx.mock
    async def test_partial_failure_surfaces_tool_error_first_section_applied(self):
        """Tool-layer mirror of #225: second-section 500 surfaces as ToolError
        with HTTP 500 in the message, AND the first section's PUT has already
        been hit. Locks in the cross-section non-atomicity gap at the tool
        boundary in addition to the client layer.

        Relies on dict insertion-order iteration (Python 3.7+) for the
        ``ntp`` -> ``mgmt`` dispatch order.
        """
        server = FastMCP(name="t")
        register_system_tools(server)
        ctx, _ = _ctx_with_network_client()
        ntp_route = respx.put(f"{SITE_PREFIX}/rest/setting/ntp").mock(
            return_value=httpx.Response(200, json={"meta": {"rc": "ok"}}),
        )
        mgmt_route = respx.put(f"{SITE_PREFIX}/rest/setting/mgmt").mock(
            return_value=httpx.Response(500, json={"meta": {"rc": "error"}}),
        )

        with pytest.raises(ToolError) as exc:
            await _call(
                server,
                "unifi_network_update_settings",
                ctx,
                ntp_server_1="time.example.com",
                mgmt_led_enabled=False,
            )
        assert "HTTP 500" in str(exc.value)
        assert "UniFi server error" in str(exc.value)
        assert ntp_route.call_count == 1, "first section must have been applied before the second failed"
        assert mgmt_route.call_count >= 1

    @respx.mock
    async def test_mixed_sections_dispatch_one_put_per_section(self):
        server = FastMCP(name="t")
        register_system_tools(server)
        ctx, _ = _ctx_with_network_client()
        ntp_route = respx.put(f"{SITE_PREFIX}/rest/setting/ntp").mock(return_value=httpx.Response(200, json={}))
        mgmt_route = respx.put(f"{SITE_PREFIX}/rest/setting/mgmt").mock(return_value=httpx.Response(200, json={}))

        await _call(
            server,
            "unifi_network_update_settings",
            ctx,
            ntp_server_1="0.uk.pool.ntp.org",
            mgmt_led_enabled=True,
        )

        assert ntp_route.call_count == 1
        assert mgmt_route.call_count == 1
        assert json.loads(ntp_route.calls[0].request.content) == {"ntp_server_1": "0.uk.pool.ntp.org"}
        assert json.loads(mgmt_route.calls[0].request.content) == {"led_enabled": True}

    async def test_no_args_raises_bad_request(self):
        server = FastMCP(name="t")
        register_system_tools(server)
        ctx, _ = _ctx_with_network_client()

        with pytest.raises(ToolError) as exc:
            await _call(server, "unifi_network_update_settings", ctx)
        assert "at least one field" in str(exc.value).lower()


# ── build_named_arg_body contract ──────────────────────────────────────────
#
# Lock in the helper's path-collision branch before any future allowlist
# addition can trip it silently. ``_SETTINGS_FIELD_PATHS`` is the first
# allowlist with nested paths long enough to make collisions conceivable
# (a section root + a leaf under the same section). PR #205 review called
# this out as the right home for the test.


class TestBuildNamedArgBodyContract:
    def test_path_collision_between_scalar_and_nested_field_raises(self):
        # Two kwargs target the same section: one as a leaf (ntp = scalar),
        # one as a nested child (ntp.ntp_server_1). The first write puts a
        # scalar at ``body["ntp"]``; the second tries to descend into it.
        field_paths: dict[str, tuple[str, ...]] = {
            "ntp": ("ntp",),
            "ntp_server_1": ("ntp", "ntp_server_1"),
        }
        with pytest.raises(UniFiBadRequestError) as exc:
            build_named_arg_body(
                tool_name="test_tool",
                field_paths=field_paths,
                named_values={"ntp": "scalar", "ntp_server_1": "time.example.com"},
                data=None,
            )
        assert "path collision" in str(exc.value)
        assert "ntp" in str(exc.value)

    def test_no_collision_when_paths_share_only_a_dict_parent(self):
        # Two leaves under the same dict parent must coexist without
        # raising — this is the legitimate ``ntp.ntp_server_1`` +
        # ``ntp.ntp_server_2`` shape exercised by the integration test
        # above; tested here at the helper level to guard against an
        # over-aggressive collision check.
        field_paths: dict[str, tuple[str, ...]] = {
            "a": ("section", "a"),
            "b": ("section", "b"),
        }
        body = build_named_arg_body(
            tool_name="test_tool",
            field_paths=field_paths,
            named_values={"a": 1, "b": 2},
            data=None,
        )
        assert body == {"section": {"a": 1, "b": 2}}

    def test_empty_data_dict_is_rejected_like_no_args(self):
        # ``data={}`` previously slipped past the "at least one field"
        # guard via the ``data is not None`` check. After #212 the helper
        # treats an empty dict the same as ``None`` so the empty-update
        # contract is symmetric across the legacy-dict and named-arg
        # surfaces.
        field_paths: dict[str, tuple[str, ...]] = {"x": ("x",)}
        with pytest.raises(UniFiBadRequestError, match="at least one field"):
            build_named_arg_body(
                tool_name="test_tool",
                field_paths=field_paths,
                named_values={"x": None},
                data={},
            )

    def test_named_arg_with_empty_data_dict_raises_mix_error(self):
        # ``data={}`` counts as supplied (``data is not None``), so pairing it
        # with a named arg trips the mix guard rather than silently winning.
        field_paths: dict[str, tuple[str, ...]] = {"x": ("x",)}
        with pytest.raises(UniFiBadRequestError, match="Cannot mix"):
            build_named_arg_body(
                tool_name="test_tool",
                field_paths=field_paths,
                named_values={"x": 1},
                data={},
            )

    def test_non_empty_data_dict_passes_through(self):
        field_paths: dict[str, tuple[str, ...]] = {"x": ("x",)}
        body = build_named_arg_body(
            tool_name="test_tool",
            field_paths=field_paths,
            named_values={"x": None},
            data={"raw": 1},
        )
        assert body == {"raw": 1}
