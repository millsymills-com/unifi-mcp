"""Synthetic association/roam/disconnect snapshots, not a controller event feed."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import respx
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

from unifi_mcp._redaction import REDACTED
from unifi_mcp.clients.network import NetworkClient
from unifi_mcp.config import UniFiConfig, UniFiMode
from unifi_mcp.tools.network.clients import register_client_tools
from unifi_mcp.tools.network.stats import register_stats_tools

CONTROLLER = "https://fixture-controller.invalid"
SITE_PREFIX = f"{CONTROLLER}/proxy/network/api/s/default"
TABLET = "02:00:00:00:00:01"
SPEAKER = "02:00:00:00:00:02"


@pytest.fixture
def timeline():
    path = Path(__file__).parents[2] / "fixtures" / "network_client_timeline.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def readonly_server(monkeypatch):
    # Ignore an operator proxy; RESpx intercepts the invented endpoint in-process.
    monkeypatch.setenv("no_proxy", "*")

    @asynccontextmanager
    async def lifespan(_server):
        config = UniFiConfig(_env_file=None, unifi_mode=UniFiMode.READONLY)
        network = NetworkClient(base_url=CONTROLLER, api_key="placeholder", site="default", max_retries=1)
        try:
            yield SimpleNamespace(config=config, clients={"network": network})
        finally:
            await network.close()

    server = FastMCP(name="synthetic-timeline", lifespan=lifespan)
    register_client_tools(server)
    register_stats_tools(server)
    server.disable(tags={"write"})
    return server


@respx.mock
async def test_active_snapshots_observe_roam_and_disconnect_without_reordering(readonly_server, timeline):
    snapshots = timeline["active_snapshots"]
    active_route = respx.get(f"{SITE_PREFIX}/stat/sta").mock(
        side_effect=[
            httpx.Response(200, json=snapshots[phase])
            for phase in ("associated", "roamed", "roamed", "disconnected", "disconnected")
        ],
    )
    all_route = respx.get(f"{SITE_PREFIX}/stat/alluser").mock(
        return_value=httpx.Response(200, json=timeline["all_clients_after_disconnect"]),
    )
    async with Client(readonly_server) as client:
        associated = (await client.call_tool("unifi_network_list_active_clients")).data["data"]
        roamed = (await client.call_tool("unifi_network_list_active_clients")).data["data"]
        found = (await client.call_tool("unifi_network_get_client", {"mac": TABLET})).data
        disconnected = (await client.call_tool("unifi_network_list_active_clients")).data["data"]
        with pytest.raises(ToolError, match="not found among active clients"):
            await client.call_tool("unifi_network_get_client", {"mac": TABLET})
        all_clients = (await client.call_tool("unifi_network_list_all_clients")).data["data"]

    assert [row["mac"] for row in associated] == [SPEAKER, TABLET]
    assert [row["mac"] for row in roamed] == [SPEAKER, TABLET]
    assert associated[1]["ap_mac"] == "02:00:00:00:01:01"
    assert roamed[1]["ap_mac"] == "02:00:00:00:01:02"
    assert associated[1]["last_seen"] < roamed[1]["last_seen"]
    assert associated[1]["token"] == roamed[1]["token"] == REDACTED
    assert found == roamed[1]
    assert [row["mac"] for row in disconnected] == [SPEAKER]
    assert [row["mac"] for row in all_clients] == [SPEAKER, TABLET]
    assert all_clients[1]["last_seen"] == roamed[1]["last_seen"]
    assert active_route.call_count == 5
    assert all_route.call_count == 1


@respx.mock
async def test_legacy_alarm_empty_and_unsupported_are_distinct(readonly_server, timeline):
    alarms = respx.get(f"{SITE_PREFIX}/list/alarm").mock(
        side_effect=[
            httpx.Response(200, json=timeline["legacy_alarms"]),
            httpx.Response(200, json={"data": []}),
            httpx.Response(404, json={"meta": {"rc": "error"}}),
        ],
    )
    async with Client(readonly_server) as client:
        populated = (await client.call_tool("unifi_network_list_events", {"limit": 2})).data["data"]
        empty = (await client.call_tool("unifi_network_list_events", {"limit": 2})).data
        with pytest.raises(ToolError, match=r"\[HTTP 404\] Unsupported operation"):
            await client.call_tool("unifi_network_list_events", {"limit": 2})

    assert [row["_id"] for row in populated] == ["fixture-alarm-2", "fixture-alarm-1"]
    assert populated[0]["token"] == REDACTED
    assert empty == {"data": []}
    assert alarms.call_count == 3
    assert [call.request.url.params["_limit"] for call in alarms.calls] == ["2", "2", "2"]
