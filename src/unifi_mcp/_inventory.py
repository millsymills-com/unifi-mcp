"""Canonical tool-count inventory — the single source of truth for #363.

Tool counts were hand-maintained across the README and CLAUDE.md and drifted
repeatedly (#357 → #361). These constants are the one place the numbers live;
``tests/unit/test_tool_inventory.py`` asserts both the live registered surface
and the current-state docs against them, so adding or removing a tool without
updating this module (and the docs) fails CI.

Historical, point-in-time counts in CHANGELOG release sections (e.g. the
``84 MCP tools`` recorded at 0.1.0) are intentionally frozen and are *not*
guarded here.
"""

from __future__ import annotations

EXPECTED_NAMESPACE_SPLITS: dict[str, dict[str, int]] = {
    "network": {"read": 26, "write": 39},
    "protect": {"read": 37, "write": 8},
    "site_manager": {"read": 9, "write": 0},
}

EXPECTED_TOOL_COUNTS: dict[str, int] = {
    namespace: split["read"] + split["write"] for namespace, split in EXPECTED_NAMESPACE_SPLITS.items()
}

EXPECTED_WRITE_TOOLS = sum(split["write"] for split in EXPECTED_NAMESPACE_SPLITS.values())

TOTAL_TOOLS = sum(EXPECTED_TOOL_COUNTS.values())

EXPECTED_READ_TOOLS = TOTAL_TOOLS - EXPECTED_WRITE_TOOLS

NAMESPACE_PREFIXES: dict[str, str] = {
    "network": "unifi_network_",
    "protect": "unifi_protect_",
    "site_manager": "unifi_site_manager_",
}
