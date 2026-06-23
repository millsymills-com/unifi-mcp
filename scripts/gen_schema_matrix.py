"""Regenerate ``docs/tool-schema-matrix.md`` from the live registered tools.

The matrix is the checked-in, machine-asserted record of every tool's input
schema (see ``tests/unit/test_schema_matrix.py``). Run this after changing any
tool signature, then commit the result:

    uv run python scripts/gen_schema_matrix.py

Rendering lives in ``unifi_mcp._schema`` so this script and the drift test stay
byte-for-byte in agreement.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from unifi_mcp._schema import MATRIX_PATH, render_matrix
from unifi_mcp.config import UniFiConfig, UniFiMode
from unifi_mcp.server import create_server

_REPO_ROOT = Path(__file__).resolve().parents[1]


async def _render() -> str:
    cfg = UniFiConfig(
        _env_file=None,
        unifi_mode=UniFiMode.READWRITE,
        unifi_network_api="net",
        unifi_protect_api="prot",
        unifi_site_manager_api="sm",
    )
    return render_matrix(await create_server(cfg).list_tools())


def main() -> None:
    """Render the matrix and write it to ``docs/tool-schema-matrix.md``."""
    target = _REPO_ROOT / MATRIX_PATH
    target.write_text(asyncio.run(_render()), encoding="utf-8")


if __name__ == "__main__":
    main()
