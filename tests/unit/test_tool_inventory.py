"""Tool-count drift guard (#363).

Pins the live registered tool surface and the current-state docs (README,
CLAUDE.md) to the canonical counts in ``unifi_mcp._inventory``. A tool added or
removed without updating the constant — or docs left to drift from it — fails
here. Historical CHANGELOG release counts are point-in-time and excluded.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from unifi_mcp._inventory import (
    EXPECTED_NAMESPACE_SPLITS,
    EXPECTED_READ_TOOLS,
    EXPECTED_TOOL_COUNTS,
    EXPECTED_WRITE_TOOLS,
    NAMESPACE_PREFIXES,
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


class TestDocsCiteCanonicalCounts:
    """Current-state docs must quote the same numbers as the constant."""

    def test_readme_totals(self):
        text = _doc("README.md")
        assert f"{TOTAL_TOOLS} tools" in text
        assert (
            f"{TOTAL_TOOLS} MCP tools** covering UniFi Network "
            f"({EXPECTED_TOOL_COUNTS['network']}), Protect "
            f"({EXPECTED_TOOL_COUNTS['protect']}), and Site Manager "
            f"({EXPECTED_TOOL_COUNTS['site_manager']})"
        ) in text
        assert f"{EXPECTED_WRITE_TOOLS} write tools" in text

    def test_claude_md_counts(self):
        text = _doc("CLAUDE.md")
        assert f"{EXPECTED_WRITE_TOOLS} write tools" in text
        assert f"({EXPECTED_TOOL_COUNTS['network']} total)" in text
        assert f"({EXPECTED_TOOL_COUNTS['protect']} total" in text

    def test_claude_md_per_api_splits(self):
        text = _doc("CLAUDE.md")
        for namespace in ("network", "protect"):
            split = EXPECTED_NAMESPACE_SPLITS[namespace]
            total = EXPECTED_TOOL_COUNTS[namespace]
            assert f"{split['read']} read + {split['write']} write tools ({total} total" in text
