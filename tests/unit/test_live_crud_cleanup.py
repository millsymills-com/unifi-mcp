"""Run the CRUD cleanup path with actual tool gates and synthetic clients only."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from tests.integration import test_all_tools_live as live_tests
from unifi_mcp.config import UniFiConfig, UniFiMode
from unifi_mcp.errors import UniFiBadRequestError
from unifi_mcp.tools.network.firewall import register_firewall_tools
from unifi_mcp.tools.network.port_profiles import register_port_profile_tools


@pytest.mark.parametrize("resource", ["port_profile", "firewall_rule"])
@pytest.mark.parametrize("failure", [None, "update", "get", "readback"])
async def test_cleanup_passes_confirmation_even_after_roundtrip_failure(resource, failure):
    """Exercise the real finally path against the real delete confirmation gate.

    The live pytest fixtures and server lifespan are never requested or started.
    All backend methods and artifact writes are mocks; no controller is involved.
    """
    server = FastMCP(name="offline cleanup fixture")
    register = register_port_profile_tools if resource == "port_profile" else register_firewall_tools
    register(server)
    resource_id = f"synthetic-{resource}-1"
    field = "poe_mode" if resource == "port_profile" else "action"
    expected = "auto" if resource == "port_profile" else "reject"
    wrong = "off" if resource == "port_profile" else "drop"
    backend = AsyncMock()
    getattr(backend, f"create_{resource}").return_value = {"data": [{"_id": resource_id}]}
    getattr(backend, f"update_{resource}").return_value = {"ok": True}
    getattr(backend, f"get_{resource}").return_value = {
        "data": [{"_id": resource_id, field: wrong if failure == "readback" else expected}]
    }
    getattr(backend, f"delete_{resource}").return_value = {"ok": True}
    if failure in {"update", "get"}:
        getattr(backend, f"{failure}_{resource}").side_effect = UniFiBadRequestError(f"synthetic {failure} failure")
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
    roundtrip = getattr(live_tests.TestWriteRoundtrips(), f"test_{resource}_crud")
    extra = ("synthetic-vlan-1",) if resource == "port_profile" else ()
    invocation = roundtrip(client, artifacts, *extra)
    if failure == "readback":
        with pytest.raises(AssertionError, match=f"Read-back {field} mismatch"):
            await invocation
    elif failure:
        with pytest.raises(ToolError, match=f"synthetic {failure} failure"):
            await invocation
    else:
        await invocation

    getattr(backend, f"delete_{resource}").assert_awaited_once_with(resource_id)
    assert client.call_tool.await_args_list[-1].args == (
        f"unifi_network_delete_{resource}",
        {("profile_id" if resource == "port_profile" else "rule_id"): resource_id, "confirm": True},
    )
    assert any(call.args[0].startswith(f"delete_{resource}-") for call in artifacts.dump.call_args_list)
