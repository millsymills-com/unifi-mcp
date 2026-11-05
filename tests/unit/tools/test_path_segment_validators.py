"""Unit tests for the tool-layer ID/MAC validators (#145).

``validate_id`` / ``validate_mac`` in ``unifi_mcp.tools._common`` reject
agent-supplied path arguments that don't match a narrow allowlist, before
the request reaches the client. ``_segment`` is still the security gate;
these helpers exist to surface a clearer ``[HTTP 400] Invalid request:
<field>: invalid id format`` error to agents instead of relying on the
encoded-path fallback.
"""

from __future__ import annotations

import pytest

from unifi_mcp.errors import UniFiBadRequestError
from unifi_mcp.tools._common import validate_id, validate_mac


class TestValidateId:
    @pytest.mark.parametrize(
        "value",
        [
            "abc123",
            "ABC",
            "60a1b2c3d4e5f60718293a4b",  # mongo objectId
            "550e8400-e29b-41d4-a716-446655440000",  # uuid
            "snake_case_id",
            "a",  # single char
            "a" * 64,  # max length
        ],
    )
    def test_valid_ids_accepted(self, value: str) -> None:
        validate_id(value, field="x")

    @pytest.mark.parametrize(
        "value",
        [
            "",
            "..",
            "../foo",
            "foo/bar",
            "foo?bar",
            "foo#bar",
            "foo bar",
            "foo\nbar",
            "0\n",
            "a" * 64 + "\n",
            "foo\x00bar",
            "%2e%2e",  # `%` not in allowlist
            "a" * 65,  # over max length
        ],
    )
    def test_invalid_ids_rejected(self, value: str) -> None:
        with pytest.raises(UniFiBadRequestError, match="x: invalid id format"):
            validate_id(value, field="x")

    def test_non_string_rejected(self) -> None:
        with pytest.raises(UniFiBadRequestError, match="x: invalid id format"):
            validate_id(123, field="x")  # type: ignore[arg-type]

    def test_field_name_in_error(self) -> None:
        with pytest.raises(UniFiBadRequestError, match="camera_id: invalid id format"):
            validate_id("../oops", field="camera_id")


class TestValidateMac:
    @pytest.mark.parametrize(
        "value",
        [
            "aa:bb:cc:dd:ee:ff",
            "AA:BB:CC:DD:EE:FF",
            "aabbccddeeff",
            "aa-bb-cc-dd-ee-ff",
            "aabb.ccdd.eeff",
        ],
    )
    def test_valid_macs_accepted(self, value: str) -> None:
        validate_mac(value, field="mac")

    @pytest.mark.parametrize(
        "value",
        [
            "",
            "../foo",
            "aa:bb:cc:dd:ee:ff/extra",
            "aa:bb:cc",  # too short
            "aa:bb:cc:dd:ee:ff\n",
            "AA:BB:CC:DD:EE:FF\n",
            "aabbccddeeff\n",
            "aa-bb-cc-dd-ee-ff\n",
            "aabb.ccdd.eeff\n",
            "aa:bb:cc:dd:ee:ff:gg",  # too long
            "ggggggggggggg",  # non-hex
            "aa bb cc dd ee ff",  # space
            "aa:bb-cc.dd:ee.ff",  # mixed separators
            "aa-bb:cc-dd:ee-ff",  # mixed colon/dash
            "aabb.ccdd:eeff",  # dot + colon
            "aa:bb:cc:dd:ee",  # 5 colon groups
            "aabb.ccdd.eeff.0011",  # 4 dotted quads
        ],
    )
    def test_invalid_macs_rejected(self, value: str) -> None:
        with pytest.raises(UniFiBadRequestError, match="mac: invalid mac format"):
            validate_mac(value, field="mac")

    def test_non_string_rejected(self) -> None:
        with pytest.raises(UniFiBadRequestError, match="mac: invalid mac format"):
            validate_mac(None, field="mac")  # type: ignore[arg-type]
