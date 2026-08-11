# Plan: API Coverage Completion (Network 100%, Protect 81%)

> Source PRD: the API coverage PRD, 47 numbered user stories. Not committed to this
> repo — file it as a GitHub issue and replace this line with the issue number
> before merging, so the story references below resolve.
>
> Adds 24 tools (23 write, 1 read), taking the server from 160 tools
> (100 read / 60 write) to 184 (101 read / 83 write). Prior work: #423 plan,
> PRs #424 / #428 / #429 / #430.

## Architectural decisions

Durable decisions that apply across all phases.

- **Tool naming**: `unifi_{api}_{verb}_{entity}`. Network Integration tools use the
  `unifi_network_` prefix and fold into the `network` counting namespace; their
  `{"network_integration"}` tag drives graceful degradation.
- **Tags and annotations**: write tools are tagged `{"write", "protect"}` or
  `{"write", "network_integration"}` and annotated `readOnlyHint: False`. They are
  hidden wholesale in the default readonly mode and additionally check
  `config.writes_enabled` at runtime.
- **Destructive classification** (ADR-0001 decisions 1 and 4, a biconditional
  enforced server-wide by `test_confirm_gate.py`). Exactly four new tools are
  destructive and carry both `destructiveHint: True` and `confirm: bool = False`:
  `unifi_network_delete_traffic_matching_list`,
  `unifi_network_reorder_firewall_policies`,
  `unifi_protect_delete_arm_profile`,
  `unifi_protect_disable_camera_mic_permanently`.
  The other nineteen are `destructiveHint: False` with no `confirm` argument. A
  full-object update whose omitted fields are dropped is documented in the
  docstring, not gated — that keeps the hint's signal.
- **Confirm gate**: one helper, `require_confirm(confirm, *, action)` in
  `tools/_common.py`, raising `UniFiBadRequestError` with the existing message
  shape. It is the only place the gate's behavior or wording lives.
- **Body shape**: config-shaped bodies take named scalar arguments resolved
  through `build_named_arg_body` against a per-resource field-path allowlist,
  following the `unifi_protect_update_camera` / `_CAMERA_FIELD_PATHS` migration.
  Each phase reads its allowed field list off the pinned OpenAPI mirror.
- **Where the allowlist boundary actually lives.** It is the *tool signature*,
  not the helper. `build_named_arg_body` returns a non-empty `data` dict verbatim
  without consulting `field_paths` (`tools/_common.py:277-278`), and three
  existing tools — `update_chime`, `update_light`, `update_sensor` — still declare
  `data: JsonObject | None = None` and pass it through. Phase 5 adds seven tools
  to that same module, so an implementer copying the local house style would
  reopen the bypass and make the story-12 guarantee false on arrival. No tool
  added by this change declares a `data` parameter; every call passes `data=None`.
  Phase 1 removes the parameter outright so it cannot be copied.
- **The allowlist is necessary, not sufficient.** It restricts key *paths*, not
  value *shapes*: `_assign_nested` drops an allowlisted value in wholesale, so a
  container-typed argument carries arbitrary nested keys under an allowed path.
  Every new write tool therefore also calls
  `reject_dangerous_keys(body, tool_name=...)` after building the body, matching
  every existing call site (`cameras.py:128`, `devices.py:136/193/280`,
  `system.py:130`) — the helper does not call it despite its own comment
  suggesting otherwise. Note that the denylist is a documented stopgap and does
  not stop `action`, `enabled`, `armed`, `isArmed`, `recordingSettings`, or
  `webhookUri` (`_DENYLIST_KEY_SUFFIXES` is `("_url", "_command")`, and
  `webhookUri` normalizes to `webhookuri`, which ends in neither). Where a phase
  has container-typed arguments it names them and states what validates their
  element shape.
- **Client boundary**: `ProtectClient` gains 18 write methods,
  `NetworkIntegrationClient` gains 5 write methods plus `list_countries`.
  `BaseUniFiClient` is unchanged — its `post`/`put`/`patch`/`delete` forward
  `**kwargs` to httpx. Clients keep passing `dict[str, Any]` through; no Pydantic
  layer. Writes are not retry-free: `ConnectError` retries on every method; only
  timeout retries and the 429 Retry-After loop are GET/HEAD-only.
- **Path safety**: every caller-supplied id in a path flows through `_segment`;
  per-site Network Integration paths go through `_site_path`, which raises while
  the site UUID is unresolved, keeping writes inert until `validate_connection`
  succeeds. `/v1/countries` is not site-scoped and bypasses `_site_path`.
- **Module placement**: new tools go beside their existing reads. Protect device
  PATCHes → `tools/protect/devices.py`; RTSPS
  enable/disable, mic-disable, file upload → `tools/protect/access.py`; live-view
  and alarm-manager writes → `tools/protect/liveviews.py` (already a misnomer;
  renaming it is a follow-up). Network writes extend
  `tools/network_integration/traffic.py` and `firewall.py`.
- **Coverage formula**: `docs/api-coverage-matrix.md` standardizes on
  covered/total with excluded operations left in the denominator (Protect's
  existing convention), stated in the legend. Starting points restate as Network
  67/73 (92%) and Protect 41/73 (56%).
- **Disposition of new rows**: every row this change adds lands as
  **Covered (unverified)**, never **Covered** — verification is cassette-only, so
  no new tool is exercised against a controller. The summary table gains a
  **Covered (unverified)** column between **Covered** and **Excluded**; the
  percentage counts both as covered.
- **Verification strategy**: cassette-based. No new live integration tests, no
  changes to `tests/integration/`, the `LIVE_TEST_DEVICE_MACS` allowlist, or
  `docs/agents/live-test-safety.md`. This is a deliberate trade against the
  spec-drift risk, taken because the destructive live sweep that bricked a UCG
  Ultra (#271) makes expanding live write coverage the more dangerous option.
- **Rollout**: one PR per resource group. Phase 1 lands first (later groups build
  on the helper) and phase 8 lands before phase 9 (the stream tools' tests are
  written against it). Phases 2–7 and 10 are otherwise independent. Phase 11 lands
  last.

### Cross-cutting acceptance criteria

**User stories**: 30, 31, 37, 38, 39, 40, 41, 43, 47

These nine stories are requirements on every phase rather than work of their own, so
they live here instead of being restated eleven times. Together with the per-phase
lists below they account for all 47 stories in the PRD: 30 (readonly hides the new
write tools), 31 (destructive tools named explicitly, in the header above), 37
(`_inventory.py` in the same PR), 38 (schema matrix regenerated), 39 (one PR per
group), 40 (respx verb/URL/body per client method), 41 (error-path tests), 43
(Args/Returns/Raises docstrings), 47 (CHANGELOG per group).

Every tool-adding phase (2–7, 9, 10) must satisfy all of these, in the same PR:

- [ ] `_inventory.py` `EXPECTED_NAMESPACE_SPLITS` updated for the tools added, so
      `tests/unit/test_tool_inventory.py` catches count drift at the point it is
      introduced (CI is red without it).
- [ ] `docs/tool-schema-matrix.md` regenerated with
      `uv run python scripts/gen_schema_matrix.py`, never hand-edited, so
      `tests/unit/test_schema_matrix.py` stays green.
- [ ] `README.md` and `CLAUDE.md` count literals updated (both are CI-guarded).
- [ ] `CHANGELOG.md` gains an `Unreleased` → `Added` entry naming the tool group,
      matching the shape of the 0.4.0 release section. CI does not check this.
- [ ] One respx test per new client method asserting verb, URL, and request body
      against a recorded response.
- [ ] Error-path tests per endpoint: 404, 400, and 401 map to the right typed
      exception and surface as a `ToolError` with an actionable message.
- [ ] Id-encoding coverage for new paths via `test_url_contracts.py` and
      `test_path_traversal.py`.
- [ ] Each new tool's docstring states Args, Returns, and Raises.
- [ ] Tools reject fields outside their allowlist and reject malformed ids.
- [ ] No new tool declares a `data: JsonObject` parameter, and every
      `build_named_arg_body` call passes `data=None`.
- [ ] Every new write tool calls `reject_dangerous_keys(body, tool_name=...)`
      after building its body, with a test that a dangerous key nested inside an
      allowlisted container argument is rejected.
- [ ] Lint, types, and unit tests green: `uv run ruff check src/ tests/`,
      `uv run ruff format --check src/ tests/`, `uv run ty check src/unifi_mcp/`,
      `uv run pytest tests/unit/ -v`.

Readonly-mode absence needs no per-tool tests: `tests/unit/test_audit_inventory.py`
§3e enumerates the `write`-tagged tools in a readonly server and asserts the set is
empty, so tagging alone covers all 23. `test_confirm_gate.py` is likewise an
enumeration over the whole surface, so the four destructive tools are picked up by
their annotation.

Tests assert what a caller can observe — the HTTP request a client method produces,
the error a tool raises, whether a tool is registered in a given mode. Not internal
call sequences or private attribute state. If the seven device-class handlers were
later consolidated into a loop, these tests should pass unchanged.

---

## Phase 1: `require_confirm` extraction

**User stories**: 35, 36

### What to build

Extract the confirm gate that 21 write tools hand-roll (`if not confirm: raise
UniFiBadRequestError(...)`) into a single `require_confirm(confirm, *, action)`
helper in `tools/_common.py`, preserving the existing message shape. Migrate all 21
sites mechanically. Handle the twenty-second site,
`unifi_protect_set_recording_mode`, explicitly: it gates conditionally on
`mode == "never"`, so it calls the helper from inside that branch and keeps
accepting its three other modes without a confirm argument.

Two changes to `build_named_arg_body` ride along, because phases 2–10 all build on
it and both defects are cheapest to close before 23 tools copy them. First, remove
its `data` parameter and the verbatim-passthrough branch, along with the `data`
arguments on `update_chime`, `update_light`, and `update_sensor` — per the repo's
replace-don't-deprecate rule — so the allowlist bypass cannot be inherited by the
seven tools phase 5 adds to that module. Second, guard that `field_paths` covers
every key in `named_values`; today a drift between the two hand-written dicts
raises a bare `KeyError` that surfaces through `handle_client_error` as an opaque
runtime error, and 23 new tools each maintaining a pair of these dicts makes that a
likely failure.

No tools are added, no counts change. This lands first so every later phase builds
on the helper rather than copying the gate again.

### Acceptance criteria

- [ ] `require_confirm` exists in `tools/_common.py` and is the only place the
      gate's raise and message live.
- [ ] `build_named_arg_body` no longer accepts `data`; the verbatim-passthrough
      branch is gone; `update_chime`, `update_light`, and `update_sensor` no longer
      expose a `data` parameter. No tool in `src/unifi_mcp/tools/` reaches
      `build_named_arg_body` with a raw dict.
- [ ] A `field_paths` / `named_values` key mismatch raises a clear error rather
      than a bare `KeyError`.
- [ ] Schema matrix regenerated and `_inventory.py` unchanged — the removed `data`
      arguments change three tools' input schemas without changing any count.
- [ ] `CHANGELOG.md` records the `data` removal under `Unreleased` → `Removed` as a
      breaking change to three shipped tools' input schemas.

> **Scope note.** Removing `data` from the three existing `devices.py` tools goes
> beyond the PRD, which scoped phase 1 to the confirm-gate extraction alone. It is
> here because phase 5 adds seven tools to that exact module and the PRD's own
> "no tool takes a free-form `data: JsonObject`" rule is unenforceable while the
> neighbours it tells implementers to imitate still do. If the breaking change is
> unacceptable, the fallback is to keep the parameter and rely on the cross-cutting
> criterion above — weaker, because it is a convention rather than a
> compiler-checked constraint.
- [ ] All 21 mechanical call sites use it; no `if not confirm:` raise remains in
      `src/unifi_mcp/tools/`.
- [ ] `unifi_protect_set_recording_mode` still accepts `always`, `motion`, and
      `schedule` without a `confirm` argument, and still gates `never`.
      `_RECORDING_MODES` is unchanged by this phase.
- [ ] `test_confirm_gate.py` extended to assert the shared message shape and to pin
      the `set_recording_mode` non-`never` behavior.
- [ ] Tool counts unchanged; existing unit suite green.

---

## Phase 2: Network Integration traffic-matching list writes

**User stories**: 1, 2, 3

### What to build

Three write tools completing the traffic-matching-list group beside its existing
reads: `unifi_network_create_traffic_matching_list`,
`unifi_network_update_traffic_matching_list`, and
`unifi_network_delete_traffic_matching_list`. The delete is destructive — it takes
`confirm: bool = False` via `require_confirm` and carries `destructiveHint: True`.
Create and update take named scalar arguments against a field-path allowlist read
off the pinned Network `10.4.57` spec.

One argument here is container-typed: the match-criteria list (`items`, per the
#423 plan) is a list of dicts, so the field-path allowlist constrains where it
lands but not what it contains. Its element shape is validated explicitly, and
`reject_dangerous_keys` runs over the assembled body.

Network Integration write count goes 13 → 16; network namespace 54 read / 55 write.

### Acceptance criteria

- [ ] Three tools registered, tagged `{"write", "network_integration"}`,
      `readOnlyHint: False`.
- [ ] Delete carries `destructiveHint: True` and refuses to act without
      `confirm=True`; create and update carry neither.
- [ ] Create/update reject any field outside their allowlist.
- [ ] Matrix rows for the three endpoints move Gap → Covered (unverified).
- [ ] All cross-cutting criteria met.

---

## Phase 3: Network Integration firewall policy reorder and PATCH

**User stories**: 4, 5, 6

### What to build

Two write tools on the firewall-policies resource.
`unifi_network_reorder_firewall_policies` is a full-replacement PUT of the ordering
and is destructive under ADR-0001 decision 4 — an omitted id silently loses its
enforcement position — so it carries `destructiveHint: True`, a confirm gate, and
the same non-empty-list guard `unifi_network_reorder_acl_rules` has.
`unifi_network_patch_firewall_policy` takes exactly `firewall_policy_id: str,
logging_enabled: bool`; spec 10.4.57 exposes only `loggingEnabled` on this PATCH,
and #423 already ruled out `action`, `enabled`, and `name` patch arguments.

The reorder request body and query-parameter names were flagged spec-unverified in
#423 and remain so; the PR states this in the tool docstring and the matrix note.

One property of the PATCH needs saying out loud even though it does not change the
classification. `logging_enabled=False` is an anti-forensics primitive: it disables
the record of the policy's own enforcement, and it leaves no trace in the logs it
just turned off. This codebase already treats the Protect analogue that way —
`set_recording_mode("never")` is confirm-gated as "an evidence-suppression
primitive," and `_common.py` names evidence suppression as a motivating case for
the denylist. It stays `destructiveHint: False` because ADR-0001's definition turns
on dropped state and nothing is dropped here, and because the biconditional means
marking it destructive would force a confirm argument onto a single-field toggle.
The docstring states the anti-forensics property so a caller is not surprised by it.

Network Integration write count goes 16 → 18; network namespace 54 read / 57 write.

### Acceptance criteria

- [ ] Reorder rejects an empty list with an actionable error before any HTTP call.
- [ ] Reorder carries `destructiveHint: True` and requires `confirm=True`.
- [ ] PATCH exposes only `firewall_policy_id` and `logging_enabled`; it is not
      destructive and takes no confirm argument.
- [ ] PATCH sends only `loggingEnabled` in its body — asserted by respx test.
- [ ] Matrix rows for both endpoints move Gap → Covered (unverified), with a note
      that the reorder body shape is spec-unverified.
- [ ] All cross-cutting criteria met.

---

## Phase 4: Network Integration countries read

**User stories**: 7

### What to build

One read tool, `unifi_network_list_countries`, over `/v1/countries` — a
non-site-scoped path that bypasses `_site_path`. It returns the controller's
country codes so an operator can pick a valid regulatory-domain value when
configuring a WLAN. The matrix row reclassifies from Excluded (UI-only reference
data) to Covered (unverified), which is what takes Network to 73/73.

Network namespace 55 read / 57 write. This is the only read tool in the change.

### Acceptance criteria

- [ ] Tool registered without the `write` tag; visible in the default readonly mode.
- [ ] Client method builds the non-site-scoped `/v1/countries` path — asserted by
      respx test — and does not require a resolved site UUID.
- [ ] Matrix row moves Excluded → Covered (unverified) and the Network excluded
      count drops to 0.
- [ ] All cross-cutting criteria met.

---

## Phase 5: Protect device-class PATCHes

**User stories**: 9, 10, 11, 12

### What to build

Seven update tools, one per device class that is currently readable but not
writable: `unifi_protect_update_speaker`, `update_siren`, `update_bridge`,
`update_relay`, `update_link_station`, `update_fob`, and `update_alarm_hub`. They
join the five existing Protect device writes in `tools/protect/devices.py`.

Each takes named scalar arguments against its own field-path allowlist read off the
pinned Protect `7.1.42` mirror. The allowlist is the point of the story-12
requirement: `update_alarm_hub` structurally cannot reach arming or sensitivity
settings, regardless of what the agent was instructed to do.

None is destructive, and the reason is that a PATCH here is a genuine partial
update: `build_named_arg_body` skips `None` values, so an omitted argument is never
sent and no state is dropped. ADR-0001 decision 4's drop-on-omit case is about
full-object PUTs — it names `update_firewall_zone` and `update_dns_policy` — and
does not apply. Docstrings follow the `unifi_protect_update_camera` precedent
("pass only the fields to change") rather than warning about a footgun these tools
do not have.

Protect namespace 37 read / 15 write.

### Acceptance criteria

- [ ] Seven tools registered, tagged `{"write", "protect"}`, `readOnlyHint: False`,
      `destructiveHint: False`, none taking a confirm argument.
- [ ] `update_alarm_hub` rejects arming and sensitivity fields; each tool rejects
      every field outside its own allowlist — one test per class.
- [ ] `ProtectClient` class docstring revised: it is no longer a mostly-read client.
- [ ] Seven matrix rows move Gap → Covered (unverified).
- [ ] All cross-cutting criteria met.

---

## Phase 6: Protect live view create and update

**User stories**: 13, 14

### What to build

Two write tools beside the existing live-view reads in `tools/protect/liveviews.py`:
`unifi_protect_create_liveview` and `unifi_protect_update_liveview`. They let an
operator assemble and revise a camera layout for a viewer without the Protect UI.
Named scalar arguments against a field-path allowlist; neither is destructive.

The camera-slot layout is structurally a nested array, so this phase has a
container-typed argument for the same reason phase 2 does: the allowlist places it
but does not constrain its contents. Its element shape is validated explicitly and
`reject_dangerous_keys` runs over the assembled body.

Protect namespace 37 read / 17 write.

### Acceptance criteria

- [ ] Two tools registered with the standard write tagging; neither destructive.
- [ ] Both reject fields outside the live-view allowlist.
- [ ] Two matrix rows move Gap → Covered (unverified).
- [ ] All cross-cutting criteria met.

---

## Phase 7: Protect alarm manager

**User stories**: 15, 16, 17, 18, 19, 20, 21

### What to build

Five write tools in `tools/protect/liveviews.py`, where `list_arm_profiles` already
lives: `unifi_protect_create_arm_profile`, `update_arm_profile`,
`delete_arm_profile`, `update_arm_profile_settings`, and `trigger_alarm_webhook`.

Two constraints are structural, not advisory. `trigger_alarm_webhook` takes a
webhook **id** and never a URL — the controller sits inside the LAN, so a
caller-supplied URL would be a request-forgery primitive. And
`update_arm_profile_settings` runs against a field allowlist that excludes
`webhookUri`, so the same primitive cannot be reached the long way round.

That is only two of the five tools, so the constraint has to cover the other three
or it does not hold. If the arm-profile object itself carries a webhook target or
action list — plausible for the alarm manager, and to be confirmed against the
pinned `7.1.42` mirror as the first step of this phase — then
`create_arm_profile` with an attacker-chosen URL followed by `trigger_alarm_webhook`
by id reconstitutes the whole primitive through the front door. The allowlists for
`create_arm_profile` and `update_arm_profile` therefore exclude every URI-shaped
field, and that exclusion is asserted by test rather than left to the field list
happening to omit it. Note that the denylist does not backstop this:
`webhookUri` normalizes to `webhookuri`, which matches neither `_url` nor
`_command`.

`trigger_alarm_webhook` remains a confused-deputy *fire* primitive against whatever
destination the operator already configured — the controller holds the credential
and the network position. It fires the same downstream automation as
`alarm-hub output trigger`, which this change defers as physical actuation. It
ships anyway because it is the story-19 requirement (test an integration without
staging a real alarm) and because it cannot choose its own destination once the
allowlists above hold. If that reasoning does not survive review, the tool moves to
the deferred set rather than shipping behind a confirm gate the plan already says
is not a security boundary.

`delete_arm_profile` is destructive: `destructiveHint: True` plus a confirm gate.
The other four are not.

Arming and disarming stay out (`POST arm-profiles/enable` and `disable` remain Gap),
so nothing in the readwrite surface can turn off an intrusion alarm.

Protect namespace 37 read / 22 write.

### Acceptance criteria

- [ ] Five tools registered; only `delete_arm_profile` is destructive/confirm-gated.
- [ ] `trigger_alarm_webhook` has no URL-shaped parameter in its input schema.
- [ ] `update_arm_profile_settings`, `create_arm_profile`, and `update_arm_profile`
      each reject `webhookUri` and every other URI-shaped field, asserted by test
      per tool — not left implicit in the field list.
- [ ] The `7.1.42` mirror checked for a webhook target on the arm-profile object,
      and the finding recorded in the PR body either way.
- [ ] No tool in the change enables or disables an arm profile; both endpoints stay
      Gap in the matrix.
- [ ] Five matrix rows move Gap → Covered (unverified).
- [ ] All cross-cutting criteria met.

---

## Phase 8: Redaction scheme extension

**User stories**: 42

### What to build

Extend `_redaction.py`'s `_RTSP_STREAM_RE` beyond the `rtsps?://` scheme it matches
today. Verified gap: `wss://host:7444/talkback/<alias>`, `udp://`, and `srt://`
payloads pass through unredacted, and no key-name rule catches `url` or `streamUrl`.
It matters even with talkback deferred.

Widening the scheme list alone is wrong, and this is the trap to avoid.
`_RTSP_STREAM_RE` treats *any non-empty path* as credentialed — sound for
`rtsp`/`rtsps`, where the path alias is the bearer credential, but applied to
`ws`/`wss` it blanks essentially every WebSocket URL, since ordinary ones have
paths too. That would satisfy the first criterion below while violating the second.
The extension therefore needs a discriminator per added scheme — a port, a path
prefix such as `/talkback/`, or the containing key name — and this phase specifies
which before touching the regex. `rtmp`/`rtmps` are included only if the pinned
spec shows Protect emitting them; the confirmed gap is `wss`, `udp`, and `srt`.

The per-scheme tests must use path-alias fixtures, not userinfo fixtures.
`_URL_USERINFO_RE` already matches any scheme carrying `user:pass@`, so a test
written as `wss://user:pass@host/x` passes green without exercising a line of the
new code — the same false-green this phase exists to avoid.

A scheme list is not sufficient even then. `_is_credentialed_url` returns early on
any value without `://` (`_redaction.py:114`), so a response carrying the bearer
alias as a bare token — `{"alias": "…"}`, `{"rtspAlias": …}`, `{"streamPath": …}` —
matches no URL rule, and `_is_sensitive_key` has no match either: `alias` is not in
`SENSITIVE_KEYS` and ends in none of `password`/`secret`/`authkey`/`token`/`passwd`.
This phase therefore adds key-name rules for the alias-shaped keys alongside the
scheme extension.

Phase 9 does not depend on this for its own guarantee — see the note there — but
this lands first regardless, per the PRD, so the stream tools' tests are written
against the finished matcher.

No tools added, no counts change.

### Acceptance criteria

- [ ] The discriminator for each added scheme is stated in the PR body before the
      regex changes.
- [ ] A credentialed URL under each added scheme — `wss`, `ws`, `udp`, `srt`, plus
      `rtmp`/`rtmps` if the spec shows Protect emitting them — is blanked, with one
      test per scheme, each using a path-alias fixture rather than a `user:pass@`
      one. A test written only against an `rtsps://` or userinfo fixture would pass
      while covering nothing.
- [ ] An ordinary `wss://host/socket` URL with a path and no credential is **not**
      blanked, proving the widening did not swallow the general case.
- [ ] A bare alias value under an alias-shaped key is blanked, covering the
      no-`://` route the scheme list cannot reach.
- [ ] Ordinary non-credentialed URLs still pass through untouched.
- [ ] Existing `tests/unit/test_redaction.py` cases stay green.

---

## Phase 9: Protect camera and stream

**User stories**: 22, 23, 24, 25, 26

### What to build

Three write tools in `tools/protect/access.py`, beside `get_rtsps_stream`:
`unifi_protect_enable_rtsps_stream`, `disable_rtsps_stream`, and
`disable_camera_mic_permanently`.

`enable_rtsps_stream` returns a confirmation that the stream is on and directs the
operator to the Protect UI for the URL. It does not return the URL: the
`rtsps://host:7441/<alias>` path alias *is* the bearer credential, which is why
`_redaction.py` blanks it. Exempting these tools from redaction to satisfy a
"give me the URL" reading is rejected.

The way that guarantee is enforced matters. `enable_rtsps_stream` builds its
response from literals and discards the controller body entirely; it does not
return a redacted passthrough. Redaction is pattern-matching against a response
shape this plan has not verified — the sibling `files/{fileType}` content-type is
explicitly unverified in phase 10, and the same uncertainty applies here — so
staking a bearer credential on it is the wrong control. Constructing the response
makes the guarantee structural and independent of what the controller returns.

`disable_camera_mic_permanently` is destructive: `destructiveHint: True`, a confirm
gate, and a docstring stating that recovery requires a physical factory reset —
which also un-adopts the camera. Ubiquiti support confirms the microphone can be
restored only that way, so the operation is unrecoverable through the API and UI but
not permanent at the hardware level.

Protect namespace 37 read / 25 write.

### Acceptance criteria

- [ ] `enable_rtsps_stream` returns no stream URL or path alias — asserted against
      the tool's response, not just the client's, with a cassette whose controller
      body *does* contain an alias, so a passthrough regression fails the test.
- [ ] `disable_camera_mic_permanently` carries `destructiveHint: True`, requires
      `confirm=True`, and its docstring states the factory-reset recovery path.
- [ ] `enable`/`disable_rtsps_stream` are not destructive and take no confirm
      argument.
- [ ] Three matrix rows move Gap → Covered (unverified).
- [ ] All cross-cutting criteria met.

---

## Phase 10: Protect file asset upload

**User stories**: 27, 28, 29

### What to build

One write tool, `unifi_protect_upload_file_asset`, in `tools/protect/access.py`
beside `get_file_asset`. It takes base64 content as a string — a filesystem path
argument is rejected because the server may run remote from the agent.

The size bound is checked on the **decoded** length before any HTTP call, against a
new `unifi_max_upload_bytes` config key. This is controller protection, not memory
protection: the JSON-RPC message is fully buffered before the tool body runs, so
nothing at the tool layer can stop a large payload from being received. It is not
analogous to the `max_bytes` bound on `get_snapshot` and `export_video`, which is
enforced mid-stream on an outbound response.

An encoded-length pre-check runs first, before `b64decode` allocates anything: a
decoded bound checked only after decoding means the process already holds the
encoded string plus the full decoded buffer, roughly 1.75x the payload, at the
moment it decides to reject. Rejecting on `len(content)` against the encoded
equivalent of the bound costs nothing and makes the limit bound something. The
decoded check stays as the authoritative one.

Decoding uses `base64.b64decode(..., validate=True)` so malformed input fails loudly
rather than being silently truncated. The `file_type` segment already flows through
`BaseUniFiClient._segment`, which blocks traversal; the tool adds `validate_id` for
message quality and consistency with `get_file_asset`.

The `files/{fileType}` response content-type is unverified — if the endpoint returns
raw bytes rather than JSON metadata, the response handling needs adjusting.

Protect namespace 37 read / 26 write. This completes the tool work: 184 total,
101 read / 83 write.

### Acceptance criteria

- [ ] Oversized content is rejected before any HTTP call is made — asserted by a
      test that would fail if the request went out — and oversized *encoded*
      content is rejected before `b64decode` runs.
- [ ] Non-base64 content fails with a clear message distinguishable from a
      size rejection; no silent truncation.
- [ ] `unifi_max_upload_bytes` config key added, defaulted, and documented in
      `.env.example` and the README config table.
- [ ] Malformed `file_type` rejected by `validate_id` with an actionable message.
- [ ] One matrix row moves Gap → Covered (unverified).
- [ ] All cross-cutting criteria met; `_inventory.py` reads network 55/57,
      protect 37/26, site_manager 9/0.

---

## Phase 11: Matrix, README, and CLAUDE.md reconciliation

**User stories**: 8, 32, 33, 34, 44, 45, 46

### What to build

Bring `docs/api-coverage-matrix.md` into one internally consistent state. Four edits
that nothing in CI catches, so each needs to be done deliberately:

1. **Legend and summary table.** State the covered/total formula with excluded
   operations in the denominator. Add a **Covered (unverified)** column between
   **Covered** and **Excluded**; the percentage counts both as covered. Network
   ends 73/73 (100%), 6 unverified; Protect 59/73 (81%), 18 unverified.

   The other two rows need values in the new column, and neither is mentioned in
   the PRD. Site Manager already carries unverified coverage as prose inside its
   Coverage cell ("6 GA live-validated; 3 EA sd-wan unverified"); that becomes
   Covered 6 / Covered (unverified) 3, and the parenthetical drops as redundant.
   The legacy-controller row counts paths rather than documented operations and has
   no disposition columns today — it takes an em-dash in the new column, matching
   how it already handles Excluded and Gap.
2. **The §3b disposition audit.** Applying the unverified marker only to new rows
   would leave §3b with two conventions in one table. Audit the 27 existing §3b
   Covered write rows — §3b holds 32 rows with a write method, 5 of which are the
   Gap rows phases 2 and 3 fill — and the Protect write rows against
   `tests/integration/`, and demote to
   **Covered (unverified)** any row no live test exercises. A row is verified iff an
   integration test calls a tool that reaches it. The NI write rows from #424, #428,
   #429, and #430 are the expected population — their live roundtrip tests were
   deferred. Mechanical check, same PR.
3. **The stale §3b trailer.** "Coverage 54/73 ops (75%); 1 excluded; 18 gaps" is not
   a number swap. It counts only *direct* Network Integration tools against the
   Integration spec, while the summary table's 67/73 also counts legacy controller
   tools that are functional equivalents. Replacing 54 with 73 would silently merge
   two denominators the file deliberately keeps apart. The corrected trailer names
   its population: direct NI coverage rises 54/73 → 60/73 with these 6 tools, and
   the remaining rows reach 73/73 only by counting the legacy functional equivalents
   the summary table already counts.
4. **The intro prose.** The intro hardcodes the same totals: "the 160 MCP tools this
   server exposes," "Network 106, Protect 45, Site Manager 9 = 160," and "41 Network
   Integration tools (28 read + 13 write, §3b)." These become 184, "Network 112,
   Protect 63, Site Manager 9 = 184," and "47 Network Integration tools (29 read +
   18 write, §3b)." `tests/unit/test_tool_inventory.py` pins count literals in
   `README.md` and `CLAUDE.md` only and never opens the matrix, so CI will not catch
   these. The §3a "all 65 Network tools" figure is unchanged.

Twelve Protect endpoints stay **Gap** with a note that they are deferred pending an
actuation-safety design: nine physical-actuation operations (PTZ goto, PTZ patrol
start, PTZ patrol stop, siren play, siren stop, siren test-sound, speaker
test-sound, relay output activate, alarm-hub output trigger), plus
talkback-session, arm-profiles enable, and arm-profiles disable. The two WebSocket
subscription endpoints stay Excluded under the existing streaming scope exclusion,
so Protect's ceiling is 71 of 73. The note should say plainly that 81% is a scope
decision about hardware actuation and irreversible operations, not an
implementation shortfall.

Before starting, re-verify the pinned specs. The matrix is a manual snapshot dated
2026-06-09 with no automated drift check; Network is pinned at `10.4.57` and Protect
at `7.1.42`, and Protect has advanced to `7.1.77` upstream with an identical path
set.

### Acceptance criteria

- [ ] Legend states the coverage formula; both API rows use it and are comparable.
- [ ] Summary table has the **Covered (unverified)** column and reads Network 73/73
      (100%, 6 unverified) and Protect 59/73 (81%, 18 unverified); all four rows
      carry a value in the new column, including Site Manager and the
      legacy-controller row.
- [ ] §3b audit complete: every §3b and Protect write row carries one disposition
      convention, with unexercised rows demoted to Covered (unverified).
- [ ] §3b trailer names the population it counts and no longer contradicts the
      summary table.
- [ ] Intro prose counts updated: 184 total; Network 112, Protect 63, Site Manager 9;
      47 NI tools (29 read + 18 write). §3a's 65 unchanged.
- [ ] Twelve deferred endpoints listed as Gap with the deferral note; two WebSocket
      endpoints still Excluded.
- [ ] `README.md` and `CLAUDE.md` state Network 100% and Protect 81% under the one
      stated formula.
- [ ] Snapshot date and pinned spec versions re-verified and updated.
- [ ] `uv run pytest tests/unit/ -v` green, including `test_tool_inventory.py` and
      `test_schema_matrix.py`.

---

## Out of scope

- The twelve deferred Protect endpoints. They need a safety design this plan does
  not attempt: what a confirm gate means for a transient physical action, whether a
  second default-off environment flag should gate a dangerous tier (the way
  `protonmail-mcp` splits `ENABLE_WRITES` from `ENABLE_DANGEROUS`), and whether a
  live test may ever fire one.
- WebSocket subscriptions (`subscribe/devices`, `subscribe/events`).
- New live integration tests, device-allowlist entries, or run-protocol changes.
- The legacy Network controller surface (§3a).
- Site Manager — already 9 of 9.
- Tool-surface reduction / per-client filtering, tracked in #480.
- Renaming `tools/protect/liveviews.py`.
- Reviving the abandoned `models/` Pydantic layer.

## Accepted risks

Protect endpoint paths are derived from the pinned `7.1.42` OpenAPI mirror and are
not verified against live hardware. Under cassette-only verification a wrong path
404s silently in production. Client-level respx tests assert the exact URL each
method builds, which catches a typo but not a mistake in the spec itself. The same
applies to the per-resource field allowlists, which are read off that mirror.

The firewall-policies reorder request body and query-parameter names remain
spec-unverified, as flagged in #423. The `files/{fileType}` response content-type is
also unverified.

The `confirm` argument is a defense against a misread instruction, not a security
boundary — the agent supplies it, so any model that decides to call the tool also
decides to pass `confirm=True`. A hostile DHCP hostname or camera name read back
through `unifi_network_list_active_clients` is a real path into agent context. That
is precisely why the physical-actuation operations a confirm gate cannot
meaningfully protect were deferred rather than shipped behind one.

**The deferral line is drawn on actuation, not on reversibility, and the two do not
coincide.** `disable_camera_mic_permanently` (phase 9) is unrecoverable through both
the API and the UI and destroys the camera's adoption state, while nine of the
twelve deferred operations — PTZ moves, siren and speaker sounds — are transient and
fully reversible. On the irreversibility axis this change ships the worst item in
the set and defers milder ones. It ships behind a confirm gate the paragraph above
says is not a security boundary, and its injection path is *shorter* than the
generic one: the attacker-controlled camera name and the `camera_id` the tool takes
are read back from the same call.

The PRD makes this call deliberately, on the grounds that the microphone is
restorable by physical factory reset and the operation satisfies a legal
requirement (story 25). This plan implements that decision. The tension is recorded
here rather than resolved because resolving it means either deferring the tool or
building the `ENABLE_DANGEROUS`-style second flag the deferred set is already
blocked on — and that flag is the natural home for this tool if the reasoning is
revisited.
