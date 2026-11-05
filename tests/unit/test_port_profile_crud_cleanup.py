"""Run the CRUD cleanup path with actual tool gates and synthetic clients only."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from tests.integration import test_all_tools_live as live_tests
from unifi_mcp.config import UniFiConfig, UniFiMode
from unifi_mcp.errors import UniFiBadRequestError
from unifi_mcp.tools.network.port_profiles import register_port_profile_tools


@pytest.mark.parametrize("failure", [None, "update", "get", "readback"])
async def test_profile_cleanup_passes_confirmation_even_after_roundtrip_failure(failure):
    """Exercise the real finally path against the real delete confirmation gate.

    The live pytest fixtures and server lifespan are never requested or started.
    All backend methods and artifact writes are mocks; no controller is involved.
    """
    server = FastMCP(name="offline cleanup fixture")
    register_port_profile_tools(server)
    backend = AsyncMock()
    backend.create_port_profile.return_value = {"data": [{"_id": "synthetic-profile-1"}]}
    backend.update_port_profile.return_value = {"ok": True}
    backend.get_port_profile.return_value = {
        "data": [{"_id": "synthetic-profile-1", "poe_mode": "off" if failure == "readback" else "auto"}]
    }
    backend.delete_port_profile.return_value = {"ok": True}
    if failure in {"update", "get"}:
        getattr(backend, f"{failure}_port_profile").side_effect = UniFiBadRequestError(f"synthetic {failure} failure")
    ctx = AsyncMock()
    ctx.lifespan_context = SimpleNamespace(
        config=UniFiConfig(_env_file=None, unifi_mode=UniFiMode.READWRITE), clients={"network": backend}
    )

    async def call_tool(name, args):
        tool = await server.get_tool(name)
        result = await tool.fn(ctx, **args)
        return SimpleNamespace(structured_content=result)

    client = SimpleNamespace(call_tool=AsyncMock(side_effect=call_tool))
    artifacts = SimpleNamespace(dump=Mock())
    invocation = live_tests.TestWriteRoundtrips().test_port_profile_crud(client, artifacts, "synthetic-vlan-1")
    if failure == "readback":
        with pytest.raises(AssertionError, match="Read-back poe_mode mismatch"):
            await invocation
    elif failure:
        with pytest.raises(ToolError, match=f"synthetic {failure} failure"):
            await invocation
    else:
        await invocation

    backend.delete_port_profile.assert_awaited_once_with("synthetic-profile-1")
    assert client.call_tool.await_args_list[-1].args == (
        "unifi_network_delete_port_profile",
        {"profile_id": "synthetic-profile-1", "confirm": True},
    )
    assert any(call.args[0].startswith("delete_port_profile-") for call in artifacts.dump.call_args_list)
