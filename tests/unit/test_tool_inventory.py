"""Tool-count drift guard (#363).

Pins the live registered tool surface and the README inventory to the canonical
counts in ``unifi_mcp._inventory``. A tool added or
removed without updating the constant — or docs left to drift from it — fails
here. Historical CHANGELOG release counts are point-in-time and excluded.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from unifi_mcp._inventory import (
    EXPECTED_NAMESPACE_SPLITS,
    EXPECTED_READ_TOOLS,
    EXPECTED_TOOL_COUNTS,
    EXPECTED_WRITE_TOOLS,
    NAMESPACE_PREFIXES,
    NETWORK_INTEGRATION_TAG,
    NETWORK_ORIGIN_SPLITS,
    TOTAL_TOOLS,
)
from unifi_mcp.config import UniFiConfig, UniFiMode
from unifi_mcp.server import create_server

if TYPE_CHECKING:
    from collections.abc import Sequence

    from fastmcp.tools import Tool

_REPO_ROOT = Path(__file__).resolve().parents[2]


async def _list_all_tools() -> Sequence[Tool]:
    """List every tool the server registers in readwrite mode (writes included)."""
    cfg = UniFiConfig(
        _env_file=None,
        unifi_mode=UniFiMode.READWRITE,
        unifi_network_api="net",
        unifi_protect_api="prot",
        unifi_site_manager_api="sm",
    )
    return await create_server(cfg).list_tools()


def _doc(name: str) -> str:
    return (_REPO_ROOT / name).read_text(encoding="utf-8")


class TestLiveCountMatchesConstant:
    """The registered surface must equal the declared inventory."""

    async def test_total(self):
        tools = await _list_all_tools()
        assert len(tools) == TOTAL_TOOLS

    async def test_per_namespace(self):
        tools = await _list_all_tools()
        counts = dict.fromkeys(NAMESPACE_PREFIXES, 0)
        for tool in tools:
            for namespace, prefix in NAMESPACE_PREFIXES.items():
                if tool.name.startswith(prefix):
                    counts[namespace] += 1
        assert counts == EXPECTED_TOOL_COUNTS

    async def test_read_write_split(self):
        tools = await _list_all_tools()
        writes = sum(1 for tool in tools if "write" in set(tool.tags))
        assert writes == EXPECTED_WRITE_TOOLS
        assert len(tools) - writes == EXPECTED_READ_TOOLS

    async def test_per_namespace_read_write_split(self):
        tools = await _list_all_tools()
        splits = {namespace: {"read": 0, "write": 0} for namespace in NAMESPACE_PREFIXES}
        for tool in tools:
            for namespace, prefix in NAMESPACE_PREFIXES.items():
                if tool.name.startswith(prefix):
                    kind = "write" if "write" in set(tool.tags) else "read"
                    splits[namespace][kind] += 1
        assert splits == EXPECTED_NAMESPACE_SPLITS

    async def test_network_origin_split(self):
        tools = await _list_all_tools()
        splits = {origin: {"read": 0, "write": 0} for origin in NETWORK_ORIGIN_SPLITS}
        for tool in tools:
            if not tool.name.startswith(NAMESPACE_PREFIXES["network"]):
                continue
            tags = set(tool.tags)
            origin = "integration" if NETWORK_INTEGRATION_TAG in tags else "legacy"
            splits[origin]["write" if "write" in tags else "read"] += 1
        assert splits == NETWORK_ORIGIN_SPLITS

    def test_network_origin_split_sums_to_namespace(self):
        for kind in ("read", "write"):
            assert (
                sum(split[kind] for split in NETWORK_ORIGIN_SPLITS.values())
                == EXPECTED_NAMESPACE_SPLITS["network"][kind]
            )


class TestDocsCiteCanonicalCounts:
    """Current-state docs must quote the same numbers as the constant."""

    def test_readme_totals(self):
        text = _doc("README.md")
        assert f"{TOTAL_TOOLS} tools" in text
        features = text.split("## Features\n", 1)[1].split("\n## ", 1)[0]
        assert f"{TOTAL_TOOLS} MCP tools" in features
        for label, namespace in (
            ("UniFi Network", "network"),
            ("Protect", "protect"),
            ("Site Manager", "site_manager"),
        ):
            assert f"{label} ({EXPECTED_TOOL_COUNTS[namespace]})" in features
        assert f"{EXPECTED_WRITE_TOOLS} write tools" in text

    def test_readme_namespace_inventory(self):
        inventory = _doc("README.md").split("## Tool inventory\n", 1)[1].split("\n## ", 1)[0]
        for label, namespace in (
            ("Network", "network"),
            ("Protect", "protect"),
            ("Site Manager", "site_manager"),
        ):
            split = EXPECTED_NAMESPACE_SPLITS[namespace]
            assert (
                f"| {label} | {split['read']} | {split['write']} | {EXPECTED_TOOL_COUNTS[namespace]} |"
                in inventory.splitlines()
            )
        assert f"| Total | {EXPECTED_READ_TOOLS} | {EXPECTED_WRITE_TOOLS} | {TOTAL_TOOLS} |" in inventory.splitlines()

    def test_readme_network_origin_inventory(self):
        inventory = _doc("README.md").split("## Tool inventory\n", 1)[1].split("\n## ", 1)[0]
        for label, origin in (("Legacy controller", "legacy"), ("Network Integration", "integration")):
            split = NETWORK_ORIGIN_SPLITS[origin]
            assert f"| {label} | {split['read']} | {split['write']} | {sum(split.values())} |" in inventory.splitlines()

    def test_claude_md_links_inventory_without_repeating_counts(self):
        text = _doc("CLAUDE.md")
        assert "[README tool inventory](README.md#tool-inventory)" in text
        assert "tests/unit/test_tool_inventory.py" in text
        assert re.search(r"\b\d+\s+(?:read|write|read-only|MCP tools?|tools?)\b", text) is None
