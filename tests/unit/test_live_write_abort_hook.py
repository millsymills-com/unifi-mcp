"""Unit coverage for the #271 live_write guardrails in tests/integration/conftest.py.

The integration suite is excluded from CI, so neither the
``pytest_collection_modifyitems`` guard (Part B) nor the
``pytest_runtest_makereport`` abort hook (Part A) ever runs there. These tests
exercise both: the collection guard directly against the pytest item protocol
(marker signal and the #438 destructive-source scan), and the abort hook via
``pytester`` sub-sessions that load the real hook.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from tests.integration.conftest import (
    _destructive_calls_in_source,
    _is_write_gated,
    _unguarded_destructive,
    pytest_collection_modifyitems,
)

pytest_plugins = ["pytester"]

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Sub-session conftest: load the real abort hook and register the marker it keys
# on. The repo root is injected so ``tests.integration.conftest`` imports inside
# the isolated pytester session. The ``sys.path`` insert persists across the
# in-process ``runpytest_inprocess`` sub-sessions below, but it is idempotent
# (always the same repo root) and harmless, so it does not need teardown.
_HOOK_CONFTEST = f"""
import sys
sys.path.insert(0, {str(_REPO_ROOT)!r})
import pytest
from tests.integration.conftest import pytest_runtest_makereport  # noqa: F401


def pytest_configure(config):
    config.addinivalue_line("markers", "live_write: marks live write tests")
"""


class _Marker:
    def __init__(self, name: str, **kwargs: object) -> None:
        self.name = name
        self.kwargs = kwargs


class _Item:
    """Minimal stand-in for ``pytest.Item`` exposing the marker API the guard uses."""

    def __init__(self, nodeid: str, *markers: _Marker) -> None:
        self.nodeid = nodeid
        self._markers = markers

    def get_closest_marker(self, name: str) -> _Marker | None:
        return next((m for m in self._markers if m.name == name), None)


def _item(nodeid: str, *markers: _Marker) -> pytest.Item:
    """Build a stub typed as ``pytest.Item`` (it implements the marker API the guard uses)."""
    return cast("pytest.Item", _Item(nodeid, *markers))


def test_write_gate_detected_by_marker() -> None:
    assert _is_write_gated(_item("t::a", _Marker("write_gated")))
    assert not _is_write_gated(_item("t::a", _Marker("skipif", reason="needs live hardware")))
    assert not _is_write_gated(_item("t::a"))


def test_guard_raises_for_write_gated_without_marker() -> None:
    item = _item("t::a", _Marker("write_gated"))
    with pytest.raises(pytest.UsageError, match="missing the live_write marker"):
        pytest_collection_modifyitems(items=[item])


def test_guard_lists_every_offender() -> None:
    items = [
        _item("t::a", _Marker("write_gated")),
        _item("t::b", _Marker("write_gated"), _Marker("live_write")),
        _item("t::c", _Marker("write_gated")),
    ]
    with pytest.raises(pytest.UsageError) as excinfo:
        pytest_collection_modifyitems(items=items)
    message = str(excinfo.value)
    assert "t::a" in message
    assert "t::c" in message
    assert "t::b" not in message  # carries live_write, not an offender


def test_guard_passes_when_marker_present() -> None:
    item = _item("t::a", _Marker("write_gated"), _Marker("live_write"))
    pytest_collection_modifyitems(items=[item])  # must not raise


def test_guard_ignores_non_write_gated_tests() -> None:
    items = [
        _item("t::read", _Marker("skipif", reason="needs live hardware")),
        _item("t::plain"),
    ]
    pytest_collection_modifyitems(items=items)  # must not raise


# ── #438: source-scanning detector ─────────────────────────────────────────


@pytest.mark.parametrize(
    "source",
    [
        "await client.forget_device(mac)",
        "await network_live_client.upgrade_device(mac)",
        "resp = await c.restart_device(m)",
        "await c.reset_dpi()",
        "await c.power_cycle_port(mac, 1)",
        "await c.create_network({'name': n})",
        "await client.delete_firewall_group(group_id)",
        "await client.update_wlan(wid, {'name': n})",
        "await c.block_client(mac)",
        "await c.authorize_guest(mac, minutes=1)",
    ],
)
def test_detector_flags_destructive_calls(source: str) -> None:
    assert _destructive_calls_in_source(source), f"expected destructive call in: {source!r}"


@pytest.mark.parametrize(
    "source",
    [
        "await client.list_devices()",
        "await client.get_firewall_group(group_id)",
        "server = create_server()",  # bare call, no leading dot
        "# create_network is mentioned only in a comment",
        "creating_backup = True  # variable name, not a call",
    ],
)
def test_detector_ignores_read_only_source(source: str) -> None:
    assert not _destructive_calls_in_source(source), f"false positive in: {source!r}"


class _SourceMarker:
    def __init__(self, name: str) -> None:
        self.name = name


class _SourceItem:
    """Item stub whose ``.function`` source the detector can inspect."""

    def __init__(self, nodeid: str, func: object, *markers: _SourceMarker) -> None:
        self.nodeid = nodeid
        self.function = func
        self._markers = markers

    def get_closest_marker(self, name: str) -> _SourceMarker | None:
        return next((m for m in self._markers if m.name == name), None)


async def _destructive_test_body(client: object) -> None:
    await client.forget_device("aa:bb:cc:dd:ee:ff")  # type: ignore[attr-defined]


async def _read_only_test_body(client: object) -> None:
    await client.list_devices()  # type: ignore[attr-defined]


def test_unguarded_destructive_flags_source_without_marker() -> None:
    item = cast("pytest.Item", _SourceItem("t::a", _destructive_test_body))
    assert _unguarded_destructive(item)


def test_unguarded_destructive_clears_with_live_write_marker() -> None:
    item = cast(
        "pytest.Item",
        _SourceItem("t::a", _destructive_test_body, _SourceMarker("live_write")),
    )
    assert not _unguarded_destructive(item)


def test_unguarded_destructive_ignores_read_only_source() -> None:
    item = cast("pytest.Item", _SourceItem("t::a", _read_only_test_body))
    assert not _unguarded_destructive(item)


def test_guard_raises_for_destructive_source_without_marker() -> None:
    item = cast("pytest.Item", _SourceItem("t::forget", _destructive_test_body))
    with pytest.raises(pytest.UsageError, match="missing the live_write marker"):
        pytest_collection_modifyitems(items=[item])


def _run_hook_case(pytester: pytest.Pytester, test_body: str) -> pytest.RunResult:
    pytester.makeconftest(_HOOK_CONFTEST)
    pytester.makepyfile(test_body)
    # The sub-session tests are synchronous; disable pytest-asyncio so its
    # configure-time deprecation warning can't surface as an INTERNALERROR
    # under the process-inherited ``-W error`` filter.
    return pytester.runpytest_inprocess("-p", "no:asyncio")


def _output(result: pytest.RunResult) -> str:
    return result.stdout.str() + result.stderr.str()


def test_bare_tool_error_aborts_session(pytester: pytest.Pytester) -> None:
    result = _run_hook_case(
        pytester,
        """
        import pytest
        from fastmcp.exceptions import ToolError

        @pytest.mark.live_write
        def test_boom():
            raise ToolError("kaboom")
        """,
    )
    assert result.ret == 2
    assert "#271" in _output(result)


def test_expected_tool_error_under_raises_stays_green(pytester: pytest.Pytester) -> None:
    result = _run_hook_case(
        pytester,
        """
        import pytest
        from fastmcp.exceptions import ToolError

        @pytest.mark.live_write
        def test_expected():
            with pytest.raises(ToolError, match="expected"):
                raise ToolError("expected boom")
        """,
    )
    assert result.ret == 0
    result.assert_outcomes(passed=1)


def test_assertion_error_fails_without_aborting(pytester: pytest.Pytester) -> None:
    result = _run_hook_case(
        pytester,
        """
        import pytest

        @pytest.mark.live_write
        def test_assert():
            assert False, "plain failure"
        """,
    )
    assert result.ret == 1
    result.assert_outcomes(failed=1)
    assert "aborting live write sweep" not in _output(result)


def test_unmarked_tool_error_fails_without_aborting(pytester: pytest.Pytester) -> None:
    result = _run_hook_case(
        pytester,
        """
        from fastmcp.exceptions import ToolError

        def test_unmarked():
            raise ToolError("boom")
        """,
    )
    assert result.ret == 1
    result.assert_outcomes(failed=1)
    assert "aborting live write sweep" not in _output(result)


def test_setup_phase_tool_error_does_not_abort(pytester: pytest.Pytester) -> None:
    result = _run_hook_case(
        pytester,
        """
        import pytest
        from fastmcp.exceptions import ToolError

        @pytest.fixture
        def boom():
            raise ToolError("setup boom")

        @pytest.mark.live_write
        def test_setup_error(boom):
            pass
        """,
    )
    assert result.ret == 1
    result.assert_outcomes(errors=1)
    assert "aborting live write sweep" not in _output(result)
