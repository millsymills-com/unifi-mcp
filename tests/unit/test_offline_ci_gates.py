"""Keep the offline transport job explicit, documented, and merge blocking."""

from pathlib import Path

import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[2]


def test_offline_job_selects_only_simulated_integration_files():
    workflow = yaml.safe_load((_ROOT / ".github/workflows/ci.yml").read_text())
    job = workflow["jobs"]["offline-transport"]
    command = next(
        step["run"] for step in job["steps"] if step.get("name") == "Run simulated transport and allowlist tests"
    )
    assert command.split() == [
        "uv",
        "run",
        "pytest",
        "tests/integration/test_stdio_transport.py",
        "tests/integration/test_device_allowlist.py",
        "-v",
    ]
    gate = workflow["jobs"]["ci-pass"]
    assert "offline-transport" in gate["needs"]
    assert gate["if"] == "always()"
    assert '${{ needs.offline-transport.result }}" != "success"' in gate["steps"][0]["run"]


@pytest.mark.parametrize("surface", ["CLAUDE.md", "CONTRIBUTING.md"])
def test_offline_command_is_documented(surface):
    assert (
        "uv run pytest tests/integration/test_stdio_transport.py tests/integration/test_device_allowlist.py -v"
        in (_ROOT / surface).read_text()
    )
