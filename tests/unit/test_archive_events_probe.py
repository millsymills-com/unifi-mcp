"""Offline lifecycle checks for the archive probe (#565)."""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "archive_events_probe.py"
_CANDIDATES = [
    ("cmd/evtmgr", {"cmd": "archive-all-alarms"}),
    ("cmd/evtmgr", {"cmd": "archive-alarm"}),
    ("cmd/evtmgr", {"cmd": "archive"}),
    ("cmd/notification", {"cmd": "archive-all-alarms"}),
    ("cmd/alarmmgr", {"cmd": "archive-all-alarms"}),
    ("cmd/sitemgr", {"cmd": "archive-all-alarms"}),
    ("cmd/alarm", {"cmd": "archive-all-alarms"}),
    ("cmd/system", {"cmd": "archive-all-alarms"}),
    ("list/alarm", {}),
]


@pytest.fixture
def probe(monkeypatch):
    spec = importlib.util.spec_from_file_location("archive_events_probe", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    client = Mock(
        get=AsyncMock(return_value={"data": [{"_id": "alarm-1", "archived": False}]}),
        post=AsyncMock(return_value={"meta": {"rc": "ok"}}),
        close=AsyncMock(),
    )
    monkeypatch.setenv("UNIFI_NETWORK_API", "synthetic-key")
    monkeypatch.setenv("UNIFI_NETWORK_VERIFY_SSL", "true")
    monkeypatch.setattr(module, "NetworkClient", Mock(return_value=client))
    return module, client


async def test_success_preserves_candidates_and_closes_once(probe):
    module, client = probe
    await module.main()
    client.get.assert_awaited_once_with("rest/alarm")
    assert [(call.args[0], call.kwargs["json"]) for call in client.post.await_args_list] == _CANDIDATES
    client.close.assert_awaited_once_with()


@pytest.mark.parametrize("failure", [RuntimeError("initial-read"), asyncio.CancelledError()])
async def test_initial_read_failure_still_closes(probe, failure):
    module, client = probe
    client.get.side_effect = failure
    with pytest.raises(type(failure)) as caught:
        await module.main()
    assert caught.value is failure
    client.post.assert_not_awaited()
    client.close.assert_awaited_once_with()


async def test_malformed_alarm_still_closes(probe):
    module, client = probe
    client.get.return_value = {"data": [None]}
    with pytest.raises(AttributeError):
        await module.main()
    client.post.assert_not_awaited()
    client.close.assert_awaited_once_with()


async def test_initial_output_failure_still_closes(probe, monkeypatch):
    module, client = probe
    failure = OSError("output-failed")
    monkeypatch.setattr(module, "print", Mock(side_effect=failure), raising=False)
    with pytest.raises(OSError, match="output-failed") as caught:
        await module.main()
    assert caught.value is failure
    client.post.assert_not_awaited()
    client.close.assert_awaited_once_with()


async def test_rejected_candidates_continue_and_close(probe):
    module, client = probe
    client.post.side_effect = RuntimeError("candidate-rejected")
    await module.main()
    assert client.post.await_count == len(_CANDIDATES)
    client.close.assert_awaited_once_with()


async def test_cancelled_candidate_stops_and_closes(probe):
    module, client = probe
    client.post.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await module.main()
    assert client.post.await_count == 1
    client.close.assert_awaited_once_with()


async def test_close_failure_after_success_is_visible(probe):
    module, client = probe
    client.close.side_effect = RuntimeError("close-failed")
    with pytest.raises(RuntimeError, match="close-failed"):
        await module.main()
    client.close.assert_awaited_once_with()


@pytest.mark.parametrize("failure", [RuntimeError("initial-read"), asyncio.CancelledError()])
async def test_close_failure_preserves_primary_failure(probe, failure, caplog):
    module, client = probe
    client.get.side_effect = failure
    client.close.side_effect = RuntimeError("close-failed")
    with pytest.raises(type(failure)) as caught:
        await module.main()
    assert caught.value is failure
    assert any("close-failed" in note for note in failure.__notes__)
    assert "close-failed" in caplog.text
    client.close.assert_awaited_once_with()
