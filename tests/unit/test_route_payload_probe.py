"""Offline state and ordering checks for the route probe (#564)."""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
from unittest.mock import Mock

import pytest

from unifi_mcp.errors import UniFiBadRequestError, UniFiServerError, UniFiTimeoutError

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "route_payload_probe.py"


class FakeClient:
    def __init__(self):
        self.operations = []
        self.remaining = set()
        self.payloads = []
        self.response = {"data": [{"_id": "route-1"}]}
        self.reject_count = 0
        self.create_error = None
        self.read_error = None
        self.delete_error = None
        self.close_error = None

    async def create_route(self, data):
        self.operations.append("create")
        self.payloads.append(data)
        if self.reject_count:
            self.reject_count -= 1
            raise UniFiBadRequestError("invalid-payload", status_code=400)
        if self.create_error is not None:
            raise self.create_error
        self.remaining.add("route-1")
        return self.response

    async def get_route(self, route_id):
        self.operations.append(f"read:{route_id}")
        if self.read_error is not None:
            raise self.read_error
        return {"data": [{"_id": route_id, "enabled": False}]}

    async def delete_route(self, route_id):
        self.operations.append(f"delete:{route_id}")
        if self.delete_error is not None:
            raise self.delete_error
        self.remaining.remove(route_id)

    async def close(self):
        self.operations.append("close")
        if self.close_error is not None:
            raise self.close_error


@pytest.fixture
def probe(monkeypatch):
    spec = importlib.util.spec_from_file_location("route_payload_probe", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    client = FakeClient()
    monkeypatch.setenv("UNIFI_NETWORK_API", "synthetic-key")
    monkeypatch.setenv("UNIFI_NETWORK_VERIFY_SSL", "true")
    monkeypatch.setattr(module, "NetworkClient", Mock(return_value=client))
    return module, client


async def test_success_cleans_before_closing(probe):
    module, client = probe
    await module.main()
    assert client.operations == ["create", "read:route-1", "delete:route-1", "close"]
    assert client.remaining == set()
    assert client.payloads[0]["enabled"] is False
    assert module.NetworkClient.call_args.kwargs["max_retries"] == 1


async def test_controller_rejection_can_try_next_candidate(probe):
    module, client = probe
    client.reject_count = 1
    await module.main()
    assert client.operations == ["create", "create", "read:route-1", "delete:route-1", "close"]
    assert client.remaining == set()
    assert all(data["enabled"] is False for data in client.payloads)


async def test_all_candidates_rejected_closes_without_delete(probe):
    module, client = probe
    client.reject_count = 3
    await module.main()
    assert client.operations == ["create", "create", "create", "close"]
    assert client.remaining == set()


@pytest.mark.parametrize(
    "response",
    [
        None,
        {},
        {"data": []},
        {"data": [None]},
        {"data": [{}]},
        {"data": [{"_id": ""}]},
        {"data": [{"_id": " "}]},
        {"data": [{"_id": 3}]},
        {"data": [{"_id": "a"}, {"_id": "b"}]},
    ],
)
async def test_missing_unique_id_stops_with_probe_name(probe, response):
    module, client = probe
    client.response = response
    with pytest.raises(RuntimeError, match="outcome indeterminate for probe-route-") as caught:
        await module.main()
    assert client.payloads[0]["name"] in str(caught.value)
    assert client.operations == ["create", "close"]
    assert client.remaining == {"route-1"}


@pytest.mark.parametrize(
    "failure",
    [
        UniFiTimeoutError("timeout"),
        UniFiServerError("upstream", status_code=500),
        UniFiBadRequestError("unknown-status"),
        asyncio.CancelledError(),
    ],
)
async def test_ambiguous_create_stops_without_delete(probe, failure):
    module, client = probe
    client.create_error = failure
    with pytest.raises(type(failure)) as caught:
        await module.main()
    assert caught.value is failure
    assert client.payloads[0]["name"] in failure.__notes__[0]
    assert client.operations == ["create", "close"]


@pytest.mark.parametrize("failure", [RuntimeError("read-failed"), asyncio.CancelledError()])
async def test_read_failure_cleans_then_stops(probe, failure):
    module, client = probe
    client.read_error = failure
    with pytest.raises(type(failure)) as caught:
        await module.main()
    assert caught.value is failure
    assert client.operations == ["create", "read:route-1", "delete:route-1", "close"]
    assert client.remaining == set()


async def test_output_failure_still_deletes(probe, monkeypatch):
    module, client = probe
    monkeypatch.setattr(module, "print", Mock(side_effect=OSError("output-failed")), raising=False)
    with pytest.raises(OSError, match="output-failed"):
        await module.main()
    assert client.operations == ["create", "delete:route-1", "close"]
    assert client.remaining == set()


async def test_delete_failure_stops_and_identifies_resource(probe, caplog):
    module, client = probe
    client.delete_error = RuntimeError("delete-failed")
    with pytest.raises(RuntimeError, match="delete-failed") as caught:
        await module.main()
    assert client.operations == ["create", "read:route-1", "delete:route-1", "close"]
    assert client.remaining == {"route-1"}
    assert "route-1" in caplog.text
    assert client.payloads[0]["name"] in caplog.text
    assert "manual cleanup required" in caught.value.__notes__[0]


@pytest.mark.parametrize("failure", [RuntimeError("read-failed"), asyncio.CancelledError()])
async def test_combined_failures_keep_primary_and_report_cleanup(probe, failure, caplog):
    module, client = probe
    client.read_error = failure
    client.delete_error = RuntimeError("delete-failed")
    client.close_error = RuntimeError("close-failed")
    with pytest.raises(type(failure)) as caught:
        await module.main()
    assert caught.value is failure
    assert client.operations == ["create", "read:route-1", "delete:route-1", "close"]
    assert client.remaining == {"route-1"}
    assert "route-1" in caplog.text
    assert "delete-failed" in caplog.text
    assert "close-failed" in caplog.text
    assert any("delete-failed" in note for note in failure.__notes__)
    assert any("close-failed" in note for note in failure.__notes__)


async def test_close_failure_after_success_propagates(probe):
    module, client = probe
    client.close_error = RuntimeError("close-failed")
    with pytest.raises(RuntimeError, match="close-failed"):
        await module.main()
    assert client.operations == ["create", "read:route-1", "delete:route-1", "close"]
    assert client.remaining == set()
