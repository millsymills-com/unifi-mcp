"""Smoke test to verify project is importable."""

from unifi_mcp import __version__


def test_version_is_set():
    assert __version__ == "0.4.0"
