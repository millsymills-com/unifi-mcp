# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Read-only `unifi_network_list_countries` for the global Network Integration
  country-code reference catalog, with bounded pagination and response redaction
  (#494). Endpoint coverage is doc-derived and not yet live-validated.

### Removed

- **BREAKING:** removed raw `data` from `unifi_network_update_wlan` (#500).
  Pass named WLAN fields instead, e.g. `name="fixture"` or `enabled=False`.
  Supported fields cover SSID/security, guest/isolation flags, network/group
  IDs and radio bands; `wlan_band` and `wlan_bands` are independent wire fields
  and are changed only when supplied. At least one non-null field is required.
  None omits a field; empty strings/lists and False remain explicit values.
  Other controller keys and null-clearing are unsupported. Updates do not infer
  site IDs or establish guest firewall isolation. No live validation was run.

- **BREAKING:** removed raw `data` from `unifi_network_create_port_profile`
  and `unifi_network_update_port_profile` (#500). Pass `name`, `poe_mode`,
  `forward` and optional `native_networkconf_id` as named fields. Create requires
  the first three and a network ID for `forward="native"`; update requires at
  least one non-null field. Other controller keys and explicit null-clearing
  are unsupported; omitted/None fields are unchanged on update. Existing
  delete/assignment confirmations are unchanged. No live hardware validation
  was performed for this migration.

- **BREAKING:** removed raw `data` from `unifi_network_update_network` and
  `unifi_network_update_firewall_group` (#500). Pass named fields, for example
  `dhcpd_enabled=False` or `group_members=[]`. The latter sends an explicit
  empty membership list. VLAN ID and `vlan_enabled` are independent fields; pass
  both when explicitly enabling tagging. At least one non-null field is
  required; omitted/None fields are unchanged, arbitrary controller keys and
  explicit null-clearing are unsupported. The guest-zone warning still applies.

- **BREAKING:** removed raw `data` from `unifi_network_update_route` and
  `unifi_network_update_port_forward` (#500). Pass named fields instead, for
  example `enabled=False` or `gateway_ip="192.0.2.1"` for a route, and
  `fwd_port="8080"` for a port forward. Route fields map to the controller's
  `static-route_*` keys automatically. Supported fields mirror each create
  tool's named inputs; arbitrary controller keys and explicit null-clearing are
  no longer exposed. At least one non-null field is required; omitted fields
  are unchanged. Other raw-data tools remain pending migration.

## [0.4.0] - 2026-06-24

### Added

- Tool-count drift guard: `unifi_mcp._inventory` is the single source of truth
  for the registered tool surface, and `tests/unit/test_tool_inventory.py`
  asserts both the live count (total, per-API, read/write split) and the
  current-state docs against it (#363).
- Protect light, chime, sensor, and viewer write tools
  (`unifi_protect_update_light`, `unifi_protect_set_light_mode`,
  `unifi_protect_update_chime`, `unifi_protect_update_sensor`,
  `unifi_protect_set_viewer_liveview`), issued as PATCH on the integration
  v1 API.
- `patch()` verb on the base API client.

### Changed

- **BREAKING:** every destructive legacy-network write tool now requires
  `confirm=True` and raises `UniFiBadRequestError` otherwise, matching the
  Network Integration deletes. This covers the 7 deletes (`delete_firewall_rule`,
  `delete_firewall_group`, `delete_port_forward`, `delete_wlan`, `delete_network`,
  `delete_route`, `delete_port_profile`) plus `restart_device`, `adopt_device`,
  `forget_device`, `upgrade_device`, `power_cycle_port`, `reset_dpi`,
  `assign_port_profile`, and `block_client`. Agents calling these tools must add
  `confirm=True`. The invariant — `destructiveHint: True` iff a `confirm` param
  exists — is now asserted server-wide. Resolves the asymmetry recorded in
  ADR-0001 (#432).
- Protect PATCH write tools now document that integration v1 returns an empty
  ack (`{}`) on success and that callers should re-read to confirm the change;
  the accessory tools (light/chime/sensor/viewer) carry an explicit "field
  paths unverified against hardware" caveat (#333, #330). `set_light_mode`
  notes it is a deliberate convenience shortcut over `update_light` (#326).
- Every MCP tool handler now shares a single `tool_handler` decorator
  (`unifi_mcp.tools._common`) that owns the `try`/`handle_client_error`
  error funnel and the defense-in-depth write-mode gate, replacing the
  identical envelope previously hand-coded in all 81 handlers. The served
  tool surface (names, schemas, descriptions, tags, annotations) is
  unchanged. Net −275 lines.
- Collapsed `register_read_tools` / `register_write_tools` back into
  `register_all_tools`, which now disables write-tagged tools with a single
  conditional instead of a disable-then-re-enable pass. The two split
  helpers are removed.
- The lifespan shutdown loop now reuses `_safe_close` instead of an inline
  duplicate of its swallow-and-log close handling.
- Promoted the duplicated key-normalization helper to a shared
  `unifi_mcp._redaction.normalize_key`, reused by the tool-layer
  dangerous-key denylist; the two denylists themselves stay independent.

### Fixed

- Protect camera writes (`unifi_protect_update_camera`,
  `unifi_protect_set_recording_mode`, `unifi_protect_set_smart_detection`)
  now work: they are issued as PATCH on the integration v1 API instead of
  an unsupported PUT (#139, #237).

### Removed

- `unifi_protect_update_nvr`: the integration v1 API is GET-only for the
  NVR, so the tool could never succeed.
- **Breaking**: the deprecated `data` raw-dict parameter on
  `unifi_network_update_settings` and `unifi_protect_update_camera`. Use the
  named scalar args (`ntp_server_1`, `mgmt_led_enabled`, `name`,
  `led_settings_is_enabled`, the `osd_settings_*` flags), which are the
  write allowlist. The other write tools' `data` payloads are unaffected.

### Security

- Write-tool responses are now scrubbed through `redact_secrets` exactly
  like read responses, so credential fields a write echoes back
  (`x_passphrase`, `radius_secret`, `ssoToken`, camera creds, etc.) no
  longer reach the agent in cleartext. The `#146` "don't scrub" stance is
  re-scoped to REQUEST bodies only, which legitimately need cleartext to
  reach the controller (#325).

## [0.3.0] - 2026-05-07

### Changed

- **Breaking: minimum supported Python is now 3.13.** Drops 3.11 and 3.12.
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
  generated as a fallback for new tools; write a tool-specific
  Returns description instead.

## [0.2.0] - 2026-05-06

### Changed

- **Breaking: every MCP tool is now exposed under the `unifi_*` namespace.**
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
