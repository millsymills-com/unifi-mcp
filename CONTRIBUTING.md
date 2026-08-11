# Contributing to unifi-mcp

Thanks for your interest in improving `unifi-mcp`. This document covers the development workflow, coding standards, and how to get a change merged.

## Development Setup

```bash
git clone https://github.com/millsymills-com/unifi-mcp.git
cd unifi-mcp
uv sync --extra dev
uv run pre-commit install
```

Copy `.env.example` to `.env` and fill in the API keys for whichever UniFi surfaces you want to test against. An unset key disables that surface; the server still starts, it just doesn't register those tools.

## Workflow

1. Fork the repo, or create a branch in the main repo if you have commit access.
2. Make your changes, keeping commits focused and well-described.
3. Run the local gates (below). CI runs the same gates on push.
4. Open a PR against `main` with a short summary of what changed and why.

## Local Quality Gates

All checks must pass locally before you push:

```bash
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run ty check src/unifi_mcp/
uv run pytest tests/unit/ -v
```

For security-sensitive changes also run:

```bash
uv run bandit -r src/unifi_mcp/ -c pyproject.toml
```

## Coding Standards

- **Python >=3.13**, strict `ty` type checks, `ruff` for lint and format.
- **Line length**: 120 characters.
- **No print statements**: use the `logging` module (enforced by ruff T20).
- **Clients** use `httpx.AsyncClient` with `tenacity`-based retry. API
  responses flow through as `dict[str, Any]`; there is no Pydantic validation
  layer between clients and tools.
- **Errors** propagate as typed `UniFiError` subclasses; tool layer maps them to `ToolError` via `handle_client_error`.

## Tool Naming and Registration

- Tool names follow `unifi_{api}_{verb}_{entity}` (e.g., `unifi_network_list_devices`, `unifi_protect_get_snapshot`). The `unifi_` prefix is mandatory: PROTO-002 requires every tool name to carry the server namespace, and the consistency audit gates on it.
- Write tools must be tagged `tags={"write"}` and annotated `readOnlyHint=False`.
- Write tools must also check `config.writes_enabled` inside the function body (defense-in-depth).
- Destructive tools (delete, block, adopt, etc.) should also carry `destructiveHint: True`.

## Testing

- Unit tests use `pytest` + `pytest-asyncio` + `respx` for HTTP mocking.
- Integration tests live under `tests/integration/` and require live UniFi hardware. Mark them with `@pytest.mark.integration`.
- When adding a tool, add at least one happy-path test and one error-path test. Cover mode gating for any write tool.

## Commits and PRs

- Write commit messages in the Conventional Commits style (`feat:`, `fix:`, `docs:`, `deps:`, `chore:`, etc.).
- Keep PRs small where possible. Large refactors are easier to review when split into sequenced commits.
- Reference the relevant plan, issue, or requirement ID in the PR body when it applies.

## Releases

The package is installed from source (`uv sync`, or `uvx --from git+…`), not published to a package index. Releases are marked by tagging `v*` on `main` with a matching [CHANGELOG.md](CHANGELOG.md) entry. Maintainers own the tag step; contributors should not tag releases directly.

There is no automated release pipeline. Maintainers cut a release manually:

1. Pick the new version per [SemVer](https://semver.org/) (`MAJOR.MINOR.PATCH`).
2. Bump the version in both `pyproject.toml` (`version = "X.Y.Z"`) and `src/unifi_mcp/__init__.py` (`__version__ = "X.Y.Z"`). The two must match.
3. Promote the `## [Unreleased]` section in `CHANGELOG.md` to `## [X.Y.Z] - YYYY-MM-DD` and open a fresh empty `## [Unreleased]` above it.
4. Land steps 1–3 on `main` via PR.
5. Verify the gates pass on `main`, then build the wheel:
   ```bash
   uv build   # produces dist/unifi_mcp-X.Y.Z-py3-none-any.whl
   ```
6. Tag the release commit and push the tag:
   ```bash
   git tag -a vX.Y.Z -m "vX.Y.Z"
   git push origin vX.Y.Z
   ```

PyPI publishing is not wired up; the `dist/` wheel is a local artifact.

## Reporting Security Issues

Please do not open public issues for security-sensitive bugs. Email the maintainers directly (see repository metadata) so we can assess and patch before public disclosure.
