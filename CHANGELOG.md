# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Protect light, chime, sensor, and viewer write tools
  (`unifi_protect_update_light`, `unifi_protect_set_light_mode`,
  `unifi_protect_update_chime`, `unifi_protect_update_sensor`,
  `unifi_protect_set_viewer_liveview`), issued as PATCH on the integration
  v1 API.
- `patch()` verb on the base API client.

### Fixed

- Protect camera writes (`unifi_protect_update_camera`,
  `unifi_protect_set_recording_mode`, `unifi_protect_set_smart_detection`)
  now work: they are issued as PATCH on the integration v1 API instead of
  an unsupported PUT (#139, #237).

### Removed

- `unifi_protect_update_nvr`: the integration v1 API is GET-only for the
  NVR, so the tool could never succeed.

## [0.3.0] - 2026-05-07

### Changed

- **Breaking — minimum supported Python is now 3.13.** Drops 3.11 and 3.12.
  Update your runtime before installing 0.3.0. CI matrix and the
  `Programming Language` classifiers were trimmed to 3.13 only (#171).

### Added

- `tests/property/` with hypothesis-driven tests for the error-classifier
  helper (#161, #174).
- `register_read_tools` / `register_write_tools` helpers in
  `unifi_mcp.tools` so the read and write surfaces are registered through
  named entry points (#168).
- README "MCP client setup" section with copy-pasteable Claude Desktop,
  Claude Code, Cursor, and Continue.dev configs (#160).

### Changed

- Rename `unifi_mcp.errors._status_tag` to `_classify_error_tag` so the
  error-mapping helper matches the standard's pattern (#170).
- Use PEP 695 `type` syntax for `JsonObject` now that the floor is 3.13.
- The "Returns: The upstream API response." docstring is no longer
  generated as a fallback for new tools — write a tool-specific
  Returns description instead.

## [0.2.0] - 2026-05-06

### Changed

- **Breaking — every MCP tool is now exposed under the `unifi_*` namespace.**
  `network_*` tools are renamed to `unifi_network_*`, `protect_*` tools to
  `unifi_protect_*`, and `site_manager_*` tools to `unifi_site_manager_*`.
  Update any client configuration or scripts that reference tools by name.
  This is the consistency-check audit's PROTO-002 requirement; see #165.

### Added

- `SECURITY.md` describing the private-disclosure path (#157, #162).
- `tests/unit/test_logging.py` and a structured stderr JSON logger
  (`unifi_mcp._logging`) so MCP stdio traffic on stdout stays uncorrupted
  (#163, #164).
- `tools._common.JsonObject` type alias used on every UniFi-payload
  parameter (#166).
- Args/Returns docstring sections on every `@mcp.tool` (#167).
- `py.typed` PEP 561 marker so downstream type checkers consume the
  package's annotations (#172).

### Changed

- `UniFiConfig.is_readwrite` renamed to `writes_enabled` (#169).
- The project type checker is now `ty` instead of `mypy` (#173).
- `__main__` and `clients/__init__` import `from __future__ import
  annotations` for consistency with the rest of the package (#175).
- `.gitignore` carries a literal `*.pyc` entry alongside the existing
  `*.py[cod]` glob (#158).

## [0.1.0] - 2026-04-16

### Added

- 84 MCP tools across UniFi Network, Protect, and Site Manager.
- Read-only / read-write mode separation, gated by `UNIFI_MODE`.
- Graceful per-API degradation when a key is missing or unreachable.
- Strict typing, ruff lint + format, full unit + opt-in integration suites.
