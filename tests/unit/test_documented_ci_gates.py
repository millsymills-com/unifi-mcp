"""Keep current contributor commands aligned with CI (#513).

Compare the tool, operation, and scopes. CI-only output/coverage options and uv
runner options are deliberately excluded; historical plans are not current docs.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW = ".github/workflows/ci.yml"
# Explicit omissions: README and PR template do not advertise the lock check;
# pre-commit advertises only ty. Plans are historical and are excluded entirely.
_SURFACES = {
    "CLAUDE.md": ("lock", "lint", "format", "ty", "pytest"),
    "CONTRIBUTING.md": ("lock", "lint", "format", "ty", "pytest"),
    "README.md": ("lint", "format", "ty", "pytest"),
    ".pre-commit-config.yaml": ("ty",),
    ".github/PULL_REQUEST_TEMPLATE.md": ("ty", "pytest"),
}
_STEPS = {
    "lock": ("lint", "Verify lockfile in sync"),
    "lint": ("lint", "Ruff lint"),
    "format": ("lint", "Ruff format check"),
    "ty": ("typecheck", "ty check"),
    "pytest": ("test", "Run tests"),
}


def _command(root: Path, gate: str) -> tuple[str, int]:
    """Read the command and its source line from the actual workflow."""
    source = (root / _WORKFLOW).read_text(encoding="utf-8")
    workflow = yaml.safe_load(source)
    job, name = _STEPS[gate]
    step = next(step for step in workflow["jobs"][job]["steps"] if step.get("name") == name)
    tokens = shlex.split(step["run"])
    assert tokens[:2] == ["uv", "run"] or gate == "lock", step["run"]
    if gate != "lock":
        tokens = tokens[2:]
    # Workflow renderer output is irrelevant to contributor command equivalence.
    tokens = [token for token in tokens if not token.startswith("--output-format=")]
    if gate == "pytest":
        # Compare the test scopes, excluding CI's coverage and verbosity options.
        end = next((i for i, token in enumerate(tokens) if token.startswith("-")), len(tokens))
        tokens = tokens[:end]
    command = " ".join(tokens)
    first_line = " ".join(shlex.split(step["run"])[:4])
    line = next(i for i, text in enumerate(source.splitlines(), 1) if first_line in text)
    return command, line


def _assert_surface(root: Path, surface: str, gate: str) -> None:
    command, line = _command(root, gate)
    text = (root / surface).read_text(encoding="utf-8")
    # Compare complete command scopes, so narrowing CI to src/ alone cannot
    # accidentally match the prefix of a stale documented src/ tests/ command.
    candidates = []
    prefix = " ".join(command.split()[:2])
    for fragment in re.split(r"[`\n]", text):
        match = re.search(rf"\b{re.escape(prefix)}(?:\s|$)", fragment)
        if match is None:
            continue
        tokens = shlex.split(fragment[match.start() :])
        if gate == "pytest":
            end = next((i for i, token in enumerate(tokens) if token.startswith("-")), len(tokens))
            tokens = tokens[:end]
        candidates.append(" ".join(tokens))
    assert command in candidates, f"{surface}: missing {command!r} from {_WORKFLOW}:{line}"


@pytest.mark.parametrize(("surface", "gate"), [(s, g) for s, gates in _SURFACES.items() for g in gates])
def test_documented_gate_matches_ci(surface: str, gate: str) -> None:
    _assert_surface(_REPO_ROOT, surface, gate)


@pytest.mark.parametrize("surface", list(_SURFACES))
@pytest.mark.parametrize("scope", ["src/ tests/ scripts/", "src/"])
def test_ci_scope_change_requires_doc_update(tmp_path: Path, surface: str, scope: str) -> None:
    """A workflow-only scope mutation must fail against every ty surface."""
    workflow = tmp_path / _WORKFLOW
    workflow.parent.mkdir(parents=True)
    source = (_REPO_ROOT / _WORKFLOW).read_text(encoding="utf-8")
    workflow.write_text(source.replace("uv run ty check src/ tests/", f"uv run ty check {scope}"))
    doc = tmp_path / surface
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text((_REPO_ROOT / surface).read_text(encoding="utf-8"))
    with pytest.raises(AssertionError, match=surface.replace(".", r"\.")):
        _assert_surface(tmp_path, surface, "ty")
