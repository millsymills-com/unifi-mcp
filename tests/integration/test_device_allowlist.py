"""Unit-level checks for the live-write device-MAC allowlist parser.

These run in the default ``-m "not integration"`` suite (no marker, no live
hardware) so the allowlist normalization is verified in CI even though the
write tests that consume it never collect there.
"""

from __future__ import annotations

import pytest

from tests.integration.conftest import _normalize_mac, live_test_device_macs


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("E438830FD628", "e438830fd628"),
        ("e4:38:83:0f:d6:28", "e438830fd628"),
        ("e4-38-83-0f-d6-28", "e438830fd628"),
        ("E4:38:83:0F:D6:28", "e438830fd628"),
        ("not-a-mac", ""),
        ("e438830fd6", ""),
        ("", ""),
    ],
)
def test_normalize_mac(raw: str, expected: str) -> None:
    assert _normalize_mac(raw) == expected


def test_allowlist_empty_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LIVE_TEST_DEVICE_MACS", raising=False)
    assert live_test_device_macs() == frozenset()


def test_allowlist_folds_separators_and_case(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIVE_TEST_DEVICE_MACS", "E438830FD628, aa:bb:cc:dd:ee:ff")
    assert live_test_device_macs() == frozenset({"e438830fd628", "aabbccddeeff"})


def test_allowlist_drops_unparseable_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIVE_TEST_DEVICE_MACS", "e438830fd628, garbage, , short")
    assert live_test_device_macs() == frozenset({"e438830fd628"})
