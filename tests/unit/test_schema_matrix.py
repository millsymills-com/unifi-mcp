"""Tool↔schema drift guard.

Pins every registered tool's input-schema surface (parameter names, types,
required/optional, defaults) to the checked-in ``docs/tool-schema-matrix.md``.
The doc is rendered from the live server by ``unifi_mcp._schema.render_matrix``;
this test rebuilds the live server, renders the same string, and asserts the
file matches byte-for-byte. Any signature change — a parameter added, removed,
renamed, retyped, or re-defaulted — fails here until the matrix is regenerated
with ``scripts/gen_schema_matrix.py``.

The complementary ``test_tool_inventory.py`` pins tool *counts*; this pins their
*shapes*.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from unifi_mcp._schema import (
    MATRIX_PATH,
    NO_PARAMS,
    render_matrix,
    render_param,
    render_signature,
    render_type,
)
from unifi_mcp.config import UniFiConfig, UniFiMode
from unifi_mcp.server import create_server

if TYPE_CHECKING:
    from collections.abc import Sequence

    from fastmcp.tools import Tool

_REPO_ROOT = Path(__file__).resolve().parents[2]


async def _list_all_tools() -> Sequence[Tool]:
    cfg = UniFiConfig(
        _env_file=None,
        unifi_mode=UniFiMode.READWRITE,
        unifi_network_api="net",
        unifi_protect_api="prot",
        unifi_site_manager_api="sm",
    )
    return await create_server(cfg).list_tools()


class TestMatrixMatchesLiveSchemas:
    """The checked-in matrix must equal a fresh render of the live tools."""

    async def test_doc_is_byte_for_byte_current(self):
        expected = render_matrix(await _list_all_tools())
        actual = (_REPO_ROOT / MATRIX_PATH).read_text(encoding="utf-8")
        assert actual == expected, (
            "docs/tool-schema-matrix.md is stale — regenerate with `python scripts/gen_schema_matrix.py`."
        )

    async def test_every_tool_has_a_row(self):
        text = (_REPO_ROOT / MATRIX_PATH).read_text(encoding="utf-8")
        missing = [tool.name for tool in await _list_all_tools() if f"`{tool.name}`" not in text]
        assert missing == [], f"Tools absent from the schema matrix: {missing}"


class TestRendererSemantics:
    """Lock the rendering contract the matrix and test both depend on."""

    def test_required_param(self):
        assert render_param("mac", {"type": "string"}, required=True) == "mac: string"

    def test_optional_param_with_default(self):
        spec = {"type": "integer", "default": 60}
        assert render_param("minutes", spec, required=False) == "minutes?: integer = 60"

    def test_nullable_union_type(self):
        spec = {"anyOf": [{"type": "string"}, {"type": "null"}], "default": None}
        assert render_param("subnet", spec, required=False) == "subnet?: string | null = null"

    def test_array_and_enum_types(self):
        assert render_type({"type": "array", "items": {"type": "string"}}) == "array<string>"

    def test_enum_renders_allowed_values(self):
        assert render_type({"enum": ["5m", "1h"]}) == '"5m" | "1h"'
        assert render_type({"type": "string", "enum": ["a", "b"]}) == '"a" | "b"'
        assert render_type({"enum": [1, 2]}) == "1 | 2"

    def test_untyped_param_is_any(self):
        assert render_type({}) == "any"

    def test_no_params(self):
        assert render_signature({}) == NO_PARAMS
        assert render_signature({"properties": {}}) == NO_PARAMS
