"""Property tests for the path-traversal validators.

PY-013 / MCP-013: every package ships at least one hypothesis-driven test
that pins an invariant rather than an example. The path-traversal
validators (#145, #212) are pure functions over agent-controlled strings,
so they are good candidates for property coverage. These tests sit
alongside the example-based suites in ``tests/unit/`` and pin the
allowlist contract that the security review depends on.
"""

from __future__ import annotations

import string
import urllib.parse

import pytest
from hypothesis import example, given
from hypothesis import strategies as st

from unifi_mcp.clients.base import BaseUniFiClient
from unifi_mcp.errors import UniFiBadRequestError
from unifi_mcp.tools._common import validate_id, validate_mac

_ID_ALPHABET = string.ascii_letters + string.digits + "_-"
_HEX_ALPHABET = "0123456789abcdefABCDEF"


# ── validate_id ─────────────────────────────────────────────────────────


@given(value=st.text(alphabet=_ID_ALPHABET, min_size=1, max_size=64))
def test_validate_id_accepts_allowlist(value: str) -> None:
    """Any 1..64-char string from ``[A-Za-z0-9_-]`` must be accepted."""
    validate_id(value, field="x")


def _is_valid_id(value: str) -> bool:
    return 1 <= len(value) <= 64 and all(ch in _ID_ALPHABET for ch in value)


@given(value=st.text(min_size=0, max_size=80).filter(lambda v: not _is_valid_id(v)))
@example(value="0\n")
def test_validate_id_rejects_outside_allowlist(value: str) -> None:
    """Any string that fails the allowlist regex must raise.

    Covers three rejection paths in one strategy: empty (length 0),
    over-length (length > 64), and any non-allowlist character.
    """
    with pytest.raises(UniFiBadRequestError, match="x: invalid id format"):
        validate_id(value, field="x")


# ── validate_mac ────────────────────────────────────────────────────────


_HEX_OCTET = st.text(alphabet=_HEX_ALPHABET, min_size=2, max_size=2)
_HEX_QUAD = st.text(alphabet=_HEX_ALPHABET, min_size=4, max_size=4)


@st.composite
def _canonical_mac(draw: st.DrawFn) -> str:
    """Draw one of the 4 canonical MAC forms accepted by ``validate_mac``."""
    form = draw(st.sampled_from(("plain", "colon", "dash", "cisco")))
    if form == "plain":
        octets = [draw(_HEX_OCTET) for _ in range(6)]
        return "".join(octets)
    if form == "colon":
        octets = [draw(_HEX_OCTET) for _ in range(6)]
        return ":".join(octets)
    if form == "dash":
        octets = [draw(_HEX_OCTET) for _ in range(6)]
        return "-".join(octets)
    quads = [draw(_HEX_QUAD) for _ in range(3)]
    return ".".join(quads)


@given(value=_canonical_mac())
def test_validate_mac_accepts_canonical_forms(value: str) -> None:
    """All four canonical MAC forms (post-#212) must be accepted."""
    validate_mac(value, field="mac")


@given(value=_canonical_mac())
def test_validate_mac_rejects_final_newline(value: str) -> None:
    """A valid MAC followed by a newline is not a complete accepted form."""
    validate_mac(value, field="mac")
    with pytest.raises(UniFiBadRequestError, match="mac: invalid mac format"):
        validate_mac(value + "\n", field="mac")


@st.composite
def _mixed_separator_mac(draw: st.DrawFn) -> str:
    """Draw a 6-octet hex string joined with at least two distinct separators.

    Output matches ``[0-9a-fA-F:.-]{12,17}`` but mixes separators, so it
    cannot match any single canonical form and must be rejected.
    """
    octets = [draw(_HEX_OCTET) for _ in range(6)]
    seps = draw(st.lists(st.sampled_from((":", "-", ".")), min_size=5, max_size=5).filter(lambda xs: len(set(xs)) >= 2))
    parts: list[str] = []
    for idx, octet in enumerate(octets):
        if idx > 0:
            parts.append(seps[idx - 1])
        parts.append(octet)
    return "".join(parts)


@given(value=_mixed_separator_mac())
def test_validate_mac_rejects_mixed_separators(value: str) -> None:
    """A 6-octet hex string with mixed separators must raise."""
    with pytest.raises(UniFiBadRequestError, match="mac: invalid mac format"):
        validate_mac(value, field="mac")


# ── BaseUniFiClient._segment ────────────────────────────────────────────


@given(value=st.text(max_size=80))
def test_segment_never_introduces_path_separator(value: str) -> None:
    """For any string, ``_segment`` either raises or returns a single segment.

    The contract: an agent-controlled value can never inject a ``/`` into the
    URL path. ``_segment`` enforces this by (a) rejecting empty / ``..`` /
    embedded-``/`` / control-char inputs and (b) percent-encoding everything
    else with ``safe=""`` so ``/`` becomes ``%2F``. Either way the returned
    string contains zero ``/`` characters, and the parsed URL path splits
    into exactly the segments the caller wrote — no more.
    """
    try:
        encoded = BaseUniFiClient._segment(value)
    except UniFiBadRequestError:
        return
    assert encoded.count("/") == 0
    url = f"https://x/prefix/{encoded}/suffix"
    parts = urllib.parse.urlparse(url).path.split("/")
    # Path is "/prefix/<encoded>/suffix" -> ["", "prefix", "<encoded>", "suffix"].
    assert parts == ["", "prefix", encoded, "suffix"]
    # And the segment cannot be a standalone parent-dir traversal.
    assert encoded != ".."
