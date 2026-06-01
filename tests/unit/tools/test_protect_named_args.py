"""Named-scalar-arg variants for Protect update_camera (#202).

Exercises the option-1 allowlist API:
- supplying named args builds the correct nested body server-side,
- supplying neither named args nor ``data=`` raises BadRequest,
- mixing named args with ``data=`` raises BadRequest,
- the legacy ``data=`` path still trips the dangerous-key denylist.

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

from unifi_mcp.clients.protect import ProtectClient
from unifi_mcp.config import UniFiConfig, UniFiMode
from unifi_mcp.tools.protect.cameras import register_camera_tools

BASE_URL = "https://10.0.0.1:443"
PROTECT_PREFIX = f"{BASE_URL}/proxy/protect/integration/v1"


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


def _ctx_with_protect_client() -> tuple[AsyncMock, ProtectClient]:
    """Build a ctx whose Protect client talks to the respx-mocked base URL."""
    client = ProtectClient(base_url=BASE_URL, api_key="test-key", timeout=5, max_retries=1)
    ctx = AsyncMock()
    ctx.lifespan_context = FakeLifespan(config=_readwrite_config(), clients={"protect": client})
    return ctx, client


async def _call(server: FastMCP, tool_name: str, ctx: AsyncMock, **kwargs: Any) -> Any:
    tool = await server.get_tool(tool_name)
    return await tool.fn(ctx, **kwargs)


# ── update_camera ──────────────────────────────────────────────────────────


class TestUpdateCameraNamedArgs:
    @respx.mock
    async def test_named_args_build_nested_body(self):
        server = FastMCP(name="t")
        register_camera_tools(server)
        ctx, _ = _ctx_with_protect_client()
        route = respx.patch(f"{PROTECT_PREFIX}/cameras/cam-1").mock(return_value=httpx.Response(200, json={"ok": True}))

        result = await _call(
            server,
            "unifi_protect_update_camera",
            ctx,
            camera_id="cam-1",
            name="Front door",
            led_settings_is_enabled=False,
        )

        assert result == {"ok": True}
        sent = json.loads(route.calls[0].request.content)
        assert sent == {"name": "Front door", "ledSettings": {"isEnabled": False}}

    @respx.mock
    async def test_all_osd_named_args_routed_under_osd_settings(self):
        server = FastMCP(name="t")
        register_camera_tools(server)
        ctx, _ = _ctx_with_protect_client()
        route = respx.patch(f"{PROTECT_PREFIX}/cameras/cam-1").mock(return_value=httpx.Response(200, json={}))

        await _call(
            server,
            "unifi_protect_update_camera",
            ctx,
            camera_id="cam-1",
            osd_settings_is_name_enabled=True,
            osd_settings_is_date_enabled=False,
            osd_settings_is_logo_enabled=True,
            osd_settings_is_debug_enabled=False,
        )

        sent = json.loads(route.calls[0].request.content)
        assert sent == {
            "osdSettings": {
                "isNameEnabled": True,
                "isDateEnabled": False,
                "isLogoEnabled": True,
                "isDebugEnabled": False,
            }
        }

    async def test_no_args_raises_bad_request(self):
        server = FastMCP(name="t")
        register_camera_tools(server)
        ctx, _ = _ctx_with_protect_client()

        with pytest.raises(ToolError) as exc:
            await _call(server, "unifi_protect_update_camera", ctx, camera_id="cam-1")
        assert "at least one field" in str(exc.value).lower()

    async def test_mixing_named_and_data_raises_bad_request(self):
        server = FastMCP(name="t")
        register_camera_tools(server)
        ctx, _ = _ctx_with_protect_client()

        with pytest.raises(ToolError) as exc:
            await _call(
                server,
                "unifi_protect_update_camera",
                ctx,
                camera_id="cam-1",
                name="x",
                data={"foo": 1},
            )
        assert "cannot mix" in str(exc.value).lower()

    @respx.mock
    async def test_legacy_data_dict_still_passes_through(self):
        server = FastMCP(name="t")
        register_camera_tools(server)
        ctx, _ = _ctx_with_protect_client()
        route = respx.patch(f"{PROTECT_PREFIX}/cameras/cam-1").mock(return_value=httpx.Response(200, json={}))

        await _call(
            server,
            "unifi_protect_update_camera",
            ctx,
            camera_id="cam-1",
            data={"name": "renamed", "ledSettings": {"isEnabled": True}},
        )

        sent = json.loads(route.calls[0].request.content)
        assert sent == {"name": "renamed", "ledSettings": {"isEnabled": True}}

    async def test_legacy_data_dict_still_hits_denylist(self):
        server = FastMCP(name="t")
        register_camera_tools(server)
        ctx, _ = _ctx_with_protect_client()

        with pytest.raises(ToolError) as exc:
            await _call(
                server,
                "unifi_protect_update_camera",
                ctx,
                camera_id="cam-1",
                data={"radius_secret": "x"},
            )
        assert "radius_secret" in str(exc.value)
