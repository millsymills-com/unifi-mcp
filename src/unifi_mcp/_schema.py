"""Canonical input-schema rendering — the single source of truth for the
tool↔schema drift guard (companion to ``_inventory.py``).

The tool *count* is pinned by ``_inventory.py``; this module pins each tool's
*parameter surface* (names, types, required/optional, defaults). ``render_matrix``
produces both the checked-in ``docs/tool-schema-matrix.md`` table (via
``scripts/gen_schema_matrix.py``) and the expectation that
``tests/unit/test_schema_matrix.py`` asserts against the live server, so the doc
and the registered schemas cannot drift apart silently.

A parameter is rendered as ``name: type`` (required) or ``name?: type`` with a
trailing `` = <json>`` when the schema carries a default. Types collapse JSON
Schema ``anyOf``/``array``/``enum`` into a compact, stable string.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from unifi_mcp._inventory import (
    EXPECTED_NAMESPACE_SPLITS,
    EXPECTED_READ_TOOLS,
    EXPECTED_TOOL_COUNTS,
    EXPECTED_WRITE_TOOLS,
    NAMESPACE_PREFIXES,
    TOTAL_TOOLS,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from fastmcp.tools import Tool

NO_PARAMS = "—"

MATRIX_PATH = "docs/tool-schema-matrix.md"

_SECTIONS: tuple[tuple[str, str, str], ...] = (
    ("network", "Network API", "/proxy/network/api/s/{site}/ (legacy controller)"),
    ("protect", "Protect API", "/proxy/protect/integration/v1/"),
    ("site_manager", "Site Manager API", "https://api.ui.com/v1/"),
)


def render_type(spec: dict[str, Any]) -> str:
    """Collapse a JSON Schema property spec into a compact type string."""
    if "anyOf" in spec:
        return " | ".join(render_type(member) for member in spec["anyOf"])
    if "enum" in spec:
        return " | ".join(json.dumps(value) for value in spec["enum"])
    schema_type = spec.get("type")
    if schema_type == "array":
        items = spec.get("items")
        return f"array<{render_type(items)}>" if items else "array"
    if schema_type is None:
        return "any"
    return schema_type


def render_param(name: str, spec: dict[str, Any], *, required: bool) -> str:
    """Render one parameter as ``name: type`` / ``name?: type [= default]``."""
    suffix = "" if required else "?"
    rendered = f"{name}{suffix}: {render_type(spec)}"
    if "default" in spec:
        rendered += f" = {json.dumps(spec['default'])}"
    return rendered


def render_signature(parameters: dict[str, Any]) -> str:
    """Render a tool's full input schema as a comma-joined parameter list.

    ``parameters`` is the FastMCP ``Tool.parameters`` JSON Schema object. The
    framework-supplied ``Context`` argument is already excluded from it.
    """
    properties: dict[str, Any] = parameters.get("properties") or {}
    if not properties:
        return NO_PARAMS
    required = set(parameters.get("required") or [])
    return ", ".join(render_param(name, spec, required=name in required) for name, spec in properties.items())


def tool_mode(tool: Tool) -> str:
    """``W`` for write-tagged tools, ``R`` otherwise."""
    return "W" if "write" in set(tool.tags) else "R"


def tool_rows(tools: Sequence[Tool]) -> dict[str, tuple[str, str]]:
    """Map each tool name to its ``(mode, signature)`` pair, sorted by name."""
    return {
        tool.name: (tool_mode(tool), render_signature(tool.parameters or {}))
        for tool in sorted(tools, key=lambda t: t.name)
    }


def _cell(signature: str) -> str:
    """Wrap a rendered signature for a GFM table cell (escaping union pipes)."""
    if signature == NO_PARAMS:
        return NO_PARAMS
    return "`" + signature.replace("|", "\\|") + "`"


def render_matrix(tools: Sequence[Tool]) -> str:
    """Render the full ``docs/tool-schema-matrix.md`` document for ``tools``.

    Shared verbatim by the generator script and the drift test: the script
    writes this string to disk and the test asserts the checked-in file equals
    it, so the doc is regenerated, never hand-edited.
    """
    rows = tool_rows(tools)
    lines: list[str] = [
        "# Tool ↔ Schema Matrix",
        "",
        f"The input-schema surface of all **{TOTAL_TOOLS} MCP tools** "
        f"({EXPECTED_READ_TOOLS} read, {EXPECTED_WRITE_TOOLS} write), one row per tool. "
        "This is the companion to the *endpoint* map in "
        "[`api-coverage-matrix.md`](api-coverage-matrix.md): that file answers *which "
        "UniFi endpoints are covered*; this one answers *what arguments each tool accepts*.",
        "",
        "Unlike the endpoint matrix, this table is **machine-asserted**. "
        "`tests/unit/test_schema_matrix.py` rebuilds the live server, renders every tool's "
        "`parameters` schema, and fails if any row here drifts from the registered schema — a "
        "parameter added, removed, renamed, retyped, or re-defaulted without updating this file "
        "breaks CI. Regenerate, do not hand-edit, the rows: `python scripts/gen_schema_matrix.py`.",
        "",
        "## Legend",
        "",
        "- **Mode** — `R` read-only · `W` write (tagged `write`, hidden unless `UNIFI_MODE=readwrite`).",
        "- **Parameters** — the tool's input schema, excluding the framework-supplied `Context`. "
        "Each parameter is `name: type` (required) or `name?: type` (optional), with `` = <default>`` "
        "when the schema carries one. `—` means the tool takes no arguments. `|` denotes a union "
        "(e.g. `string | null` is an optional/nullable value); `array<T>` and `object` mirror the "
        "JSON Schema type. An enum renders its allowed values as quoted literals joined by `|` "
        '(e.g. `"5m" | "1h"`); `any` marks a parameter with no declared type.',
        "",
        "## Counts",
        "",
        "| API | Read | Write | Total |",
        "|---|---:|---:|---:|",
    ]
    for namespace, title, _base in _SECTIONS:
        split = EXPECTED_NAMESPACE_SPLITS[namespace]
        lines.append(f"| {title} | {split['read']} | {split['write']} | {EXPECTED_TOOL_COUNTS[namespace]} |")
    lines += [
        f"| **All** | **{EXPECTED_READ_TOOLS}** | **{EXPECTED_WRITE_TOOLS}** | **{TOTAL_TOOLS}** |",
        "",
        "Counts mirror `src/unifi_mcp/_inventory.py`; the per-tool rows below are rendered from the "
        "live registered schemas.",
    ]

    for namespace, title, base in _SECTIONS:
        names = [name for name in rows if name.startswith(NAMESPACE_PREFIXES[namespace])]
        lines += [
            "",
            "---",
            "",
            f"## {title}",
            "",
            f"Backing surface: `{base}`. {len(names)} tools.",
            "",
            "| Tool | Mode | Parameters |",
            "|---|:--:|---|",
        ]
        for name in names:
            mode, signature = rows[name]
            lines.append(f"| `{name}` | {mode} | {_cell(signature)} |")

    lines += [
        "",
        "---",
        "",
        "## Maintenance",
        "",
        "Generated, not hand-written. After changing any tool signature run "
        "`python scripts/gen_schema_matrix.py` to regenerate this file, then "
        "`uv run pytest tests/unit/test_schema_matrix.py` to confirm zero drift. The renderer and "
        "the test share `unifi_mcp._schema`, so the table and the live schemas use identical "
        "formatting.",
        "",
    ]
    return "\n".join(lines)
