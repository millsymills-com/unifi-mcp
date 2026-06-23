# UniFi API Coverage Matrix

Endpoint-by-endpoint map of the three UniFi APIs against the 157 MCP tools this
server exposes. Every documented endpoint of each official API appears below with
exactly one disposition:

- **Covered** — backed by one or more `unifi_*` tools (named).
- **Covered (unverified)** — a tool exists, but the endpoint path is doc-derived
  and not yet confirmed against live hardware (a wrong path 404s silently).
- **Gap** — plausibly in scope, not yet implemented (one-line note on what it does).
- **Excluded** — deliberately out of scope (one-line reason).

Tool totals here agree with `src/unifi_mcp/_inventory.py` (Network 103, Protect 45,
Site Manager 9 = 157). The Network 103 splits into 65 legacy-controller tools
(§3a) and 38 Network Integration tools (28 read + 10 write, §3b).

For the *input-schema* surface of each tool (parameters, types, defaults), see the
machine-asserted [`tool-schema-matrix.md`](tool-schema-matrix.md): this file maps
tools to endpoints, that one maps tools to their arguments.

## Snapshot

| API | Upstream version pinned | Base path our client uses | Enumeration source |
|---|---|---|---|
| Network (official Integration API) | v10.4.57, OpenAPI 3.1.0 | n/a — see note | `integration.json` mirror (beezly/unifi-apis) |
| Network (legacy controller API) | n/a (undocumented) | `/proxy/network/api/s/{site}/` | our client (ground truth) |
| Protect (Integration API) | v7.1.42, OpenAPI 3.1.0 | `/proxy/protect/integration/v1/` | `7.1.42.json` mirror + developer.ui.com |
| Site Manager API | v1.0 (+ `/ea/` early access) | `https://api.ui.com/v1/` | developer.ui.com/site-manager |

**Snapshot date:** 2026-06-09. Re-verify against upstream when these versions move
(this enumeration is a manual snapshot; there is no automated drift check).

**Upstream counts last verified:** 2026-06-09, against the pinned OpenAPI mirrors
(beezly/unifi-apis). Network `10.4.57` and Protect `7.1.42` each enumerate **73**
operations, and the §3b Network table is an exact path-set match to `10.4.57.json`
(zero diff). Reproduce per spec with:

```
jq '[.paths[]|to_entries[]|select(.key|test("^(get|post|put|patch|delete)$"))]|length' <spec>.json
```

Drift at verification time: Network `10.4.57` is the latest mirrored spec. Protect
has advanced to `7.1.77` upstream, but its path set is **identical** to the pinned
`7.1.42` (73 ops, zero diff), so the Protect rows below are unaffected. Site Manager
(9 ops) has no OpenAPI mirror; its count was confirmed against
developer.ui.com/site-manager (`/hosts`, `/hosts/{id}`, `/sites`, `/devices`,
`/isp-metrics/{type}`, `/isp-metrics/{type}/query`, and the three `/ea/sd-wan-configs`
early-access rows).

> **Network caveat — two different surfaces.** The official, developer.ui.com-documented
> UniFi Network API is the modern *Integration API* at `/proxy/network/integration/v1/`
> (UUID site IDs, `X-API-KEY`). The server now calls **both** surfaces. Our legacy
> `NetworkClient` targets the older *controller API* at `/proxy/network/api/s/{site}/`
> (legacy `stat/*`, `rest/*`, `cmd/*` paths), which is undocumented by Ubiquiti but
> exposes a much broader surface (port-forwards, routing, port profiles, settings,
> firewall groups, device/client commands) that the Integration API still lacks. A
> separate read-only `NetworkIntegrationClient` adds 28 GET/list tools over the
> Integration API for resources the legacy controller doesn't expose (ACL rules,
> firewall zones, DNS policies, hotspot vouchers, switching/LAGs, VPN, WANs, RADIUS).
> The Network section below therefore has two tables: (3a) the legacy paths we call,
> mapping the 65 legacy Network tools; and (3b) the official Integration API, with the
> 28 read tools and the ACL + DNS + firewall-zone write groups named, and the remaining
> writes left as functional-equivalent or gap rows.

## Coverage summary

| API | Covered | Excluded | Gap | Documented total | Coverage |
|---|---:|---:|---:|---:|---:|
| Network — official Integration API (functional equivalent + direct reads) | 64 | 1 | 8 | 73 ops | **89%** |
| Network — legacy controller paths we depend on | 47 paths | — | — | 47 | **100%** of what we call |
| Protect — Integration API | 41 | 2 | 30 | 73 ops | **56%** |
| Site Manager API | 9 | 0 | 0 | 9 | **100% tooled** (6 GA live-validated; 3 EA sd-wan unverified) |

The "feature-complete" framing in the README is accurate for the **legacy Network
controller workflows** the server was built around, and for the *core device classes*
of Protect and Site Manager — but it overstates coverage of the **official** Network
Integration API and of Protect's full device catalog. See the per-API gap lists.

---

## 1. Site Manager API (`https://api.ui.com`)

9 of 9 tools map here. Read-only API (no documented write endpoints yet).

| Method | Path | Tier | Disposition | Tool / reason |
|---|---|---|---|---|
| GET | `/v1/hosts` | GA | **Covered** | `unifi_site_manager_list_hosts` |
| GET | `/v1/hosts/{id}` | GA | **Covered** | `unifi_site_manager_get_host` |
| GET | `/v1/sites` | GA | **Covered** | `unifi_site_manager_list_sites` |
| GET | `/v1/devices` | GA | **Covered** | `unifi_site_manager_list_devices` (optional `host_id` filter) |
| GET | `/v1/isp-metrics/{type}` | GA | **Covered** | `unifi_site_manager_get_isp_metrics` (5m/1h windows) |
| POST | `/v1/isp-metrics/{type}/query` | GA | **Covered** | `unifi_site_manager_query_isp_metrics` (pure selector query) |
| GET | `/ea/sd-wan-configs` | EA | **Covered (unverified)** | `unifi_site_manager_list_sdwan_configs` |
| GET | `/ea/sd-wan-configs/{id}` | EA | **Covered (unverified)** | `unifi_site_manager_get_sdwan_config` |
| GET | `/ea/sd-wan-configs/{id}/status` | EA | **Covered (unverified)** | `unifi_site_manager_get_sdwan_config_status` |

GA coverage 6/6 (100%, live-validated); EA sd-wan 3/3 **tooled but unverified**.
**Covered (unverified)** means a tool exists but the `/ea/sd-wan-configs*` path
spellings are taken from developer.ui.com docs and have **not** been confirmed
against a controller with early access enabled — a wrong EA path 404s silently
while the tool stays registered (same failure mode as `export_video`, #227).
Verifying the three paths against live EA hardware would justify dropping the
qualifier.

---

## 2. Protect Integration API (`/proxy/protect/integration/v1/`)

45 of 45 tools map here. Paths are relative to the integration v1 base.

### Covered

| Method | Path | Disposition | Tool(s) |
|---|---|---|---|
| GET | `cameras` | **Covered** | `unifi_protect_list_cameras` |
| GET | `cameras/{id}` | **Covered** | `unifi_protect_get_camera` |
| PATCH | `cameras/{id}` | **Covered** | `unifi_protect_update_camera`, `unifi_protect_set_recording_mode`, `unifi_protect_set_smart_detection` |
| GET | `cameras/{id}/snapshot` | **Covered** | `unifi_protect_get_snapshot` |
| GET | `cameras/{id}/video/export` | **Covered** | `unifi_protect_export_video` — not present in the pinned 7.1.42 OpenAPI snapshot but live-verified working; likely undocumented or newer than the mirror. |
| GET | `cameras/{id}/rtsps-stream` | **Covered** | `unifi_protect_get_rtsps_stream` — GET only; may 404/empty with no active stream (like `export_video`). |
| GET | `nvrs` | **Covered** | `unifi_protect_get_nvr` |
| GET | `chimes` | **Covered** | `unifi_protect_list_chimes` |
| GET | `chimes/{id}` | **Covered** | `unifi_protect_get_chime` |
| PATCH | `chimes/{id}` | **Covered** | `unifi_protect_update_chime` |
| GET | `lights` | **Covered** | `unifi_protect_list_lights` |
| GET | `lights/{id}` | **Covered** | `unifi_protect_get_light` |
| PATCH | `lights/{id}` | **Covered** | `unifi_protect_update_light`, `unifi_protect_set_light_mode` |
| GET | `sensors` | **Covered** | `unifi_protect_list_sensors` |
| GET | `sensors/{id}` | **Covered** | `unifi_protect_get_sensor` |
| PATCH | `sensors/{id}` | **Covered** | `unifi_protect_update_sensor` |
| GET | `viewers` | **Covered** | `unifi_protect_list_viewers` |
| GET | `viewers/{id}` | **Covered** | `unifi_protect_get_viewer` |
| PATCH | `viewers/{id}` | **Covered** | `unifi_protect_set_viewer_liveview` |
| GET | `speakers` | **Covered** | `unifi_protect_list_speakers` |
| GET | `speakers/{id}` | **Covered** | `unifi_protect_get_speaker` |
| GET | `sirens` | **Covered** | `unifi_protect_list_sirens` |
| GET | `sirens/{id}` | **Covered** | `unifi_protect_get_siren` |
| GET | `bridges` | **Covered** | `unifi_protect_list_bridges` |
| GET | `bridges/{id}` | **Covered** | `unifi_protect_get_bridge` |
| GET | `relays` | **Covered** | `unifi_protect_list_relays` |
| GET | `relays/{id}` | **Covered** | `unifi_protect_get_relay` |
| GET | `link-stations` | **Covered** | `unifi_protect_list_link_stations` |
| GET | `link-stations/{id}` | **Covered** | `unifi_protect_get_link_station` |
| GET | `fobs` | **Covered** | `unifi_protect_list_fobs` |
| GET | `fobs/{id}` | **Covered** | `unifi_protect_get_fob` |
| GET | `alarm-hubs` | **Covered** | `unifi_protect_list_alarm_hubs` |
| GET | `alarm-hubs/{id}` | **Covered** | `unifi_protect_get_alarm_hub` |
| GET | `liveviews` | **Covered** | `unifi_protect_list_liveviews` |
| GET | `liveviews/{id}` | **Covered** | `unifi_protect_get_liveview` |
| GET | `arm-profiles` | **Covered** | `unifi_protect_list_arm_profiles` |
| GET | `users` | **Covered** | `unifi_protect_list_users` |
| GET | `users/{id}` | **Covered** | `unifi_protect_get_user` |
| GET | `ulp-users` | **Covered** | `unifi_protect_list_ulp_users` |
| GET | `ulp-users/{id}` | **Covered** | `unifi_protect_get_ulp_user` |
| GET | `meta/info` | **Covered** | `unifi_protect_get_meta_info` |
| GET | `files/{fileType}` | **Covered** | `unifi_protect_get_file_asset` — content-type unverified; assumes JSON metadata, may move to `media.py` if raw bytes. |

### Excluded

| Method | Path | Reason |
|---|---|---|
| GET (WS) | `subscribe/devices` | WebSocket device-change stream — streaming is an explicit project scope exclusion. |
| GET (WS) | `subscribe/events` | WebSocket event stream (motion/smart-detect/ring) — streaming exclusion. |

### Gap

All remaining gaps are writes (`POST`/`PATCH`/`DELETE`) or excluded WS streams —
every `GET`/read endpoint is now covered, so the read ceiling (56%) is reached.

Camera actions: `POST cameras/{id}/disable-mic-permanently`, `POST cameras/{id}/ptz/goto/{slot}`,
`POST cameras/{id}/ptz/patrol/start/{slot}`, `POST cameras/{id}/ptz/patrol/stop`,
`POST/DELETE cameras/{id}/rtsps-stream` (GET is covered), `POST cameras/{id}/talkback-session`.

Device-class writes (each device class exposes `PATCH {id}`, now the only gap after
list/get were covered): `PATCH speakers/{id}` (+`POST {id}/test-sound`),
`PATCH sirens/{id}` (+`play`/`stop`/`test-sound`), `PATCH bridges/{id}`,
`PATCH relays/{id}` (+`POST {id}/outputs/{outputId}/activate`), `PATCH link-stations/{id}`,
`PATCH fobs/{id}`, `PATCH alarm-hubs/{id}` (+`POST {id}/outputs/{outputId}/trigger`).

Live views: `POST liveviews`, `PATCH liveviews/{id}` (GET/list covered).

Alarm manager: `POST arm-profiles`, `POST arm-profiles/enable`, `POST arm-profiles/disable`,
`PATCH arm-profiles/settings`, `PATCH arm-profiles/{id}`, `DELETE arm-profiles/{id}`,
`POST alarm-manager/webhook/{id}` (the `GET arm-profiles` list is covered).

Other: `POST files/{fileType}` (asset upload; the GET is covered).

Covered 41/73 ops (56%); WebSocket subscriptions excluded.

---

## 3. Network API

### 3a. Legacy controller paths we call (`/proxy/network/api/s/{site}/`)

This is the actual backing surface for all 65 Network tools. Every path we depend on
is exercised by at least one tool, so coverage of *what we call* is 100% by
construction. `{id}` segments are controller object IDs; `cmd/*` endpoints multiplex
on a `cmd` body field.

| Method | Path (+ cmd) | Tool(s) |
|---|---|---|
| GET | `stat/health` | `unifi_network_get_health` |
| GET | `list/alarm` | `unifi_network_list_events` |
| GET | `stat/device` | `unifi_network_list_devices`, `unifi_network_get_device` |
| GET | `stat/device-basic` | `unifi_network_list_devices_basic` |
| GET | `stat/sta` | `unifi_network_list_active_clients` |
| GET | `rest/user` | `unifi_network_list_configured_clients` |
| GET | `stat/alluser` | `unifi_network_list_all_clients`, `unifi_network_get_client` |
| GET | `stat/dpi` | `unifi_network_get_dpi_stats` |
| GET | `stat/sysinfo` | `unifi_network_get_sysinfo` |
| GET | `rest/wlanconf` | `unifi_network_list_wlans` |
| GET | `rest/wlanconf/{id}` | `unifi_network_get_wlan` |
| GET | `rest/networkconf` | `unifi_network_list_networks` |
| GET | `rest/networkconf/{id}` | `unifi_network_get_network` |
| GET | `rest/firewallrule` | `unifi_network_list_firewall_rules` |
| GET | `rest/firewallrule/{id}` | `unifi_network_get_firewall_rule` |
| GET | `rest/firewallgroup` | `unifi_network_list_firewall_groups` |
| GET | `rest/firewallgroup/{id}` | `unifi_network_get_firewall_group` |
| GET | `rest/portforward` | `unifi_network_list_port_forwards` |
| GET | `rest/portforward/{id}` | `unifi_network_get_port_forward` |
| GET | `rest/routing` | `unifi_network_list_routes` |
| GET | `rest/routing/{id}` | `unifi_network_get_route` |
| GET | `rest/setting` | `unifi_network_get_settings` |
| GET | `rest/portconf` | `unifi_network_list_port_profiles` |
| GET | `rest/portconf/{id}` | `unifi_network_get_port_profile` |
| POST | `rest/wlanconf` | `unifi_network_create_wlan` |
| PUT | `rest/wlanconf/{id}` | `unifi_network_update_wlan` |
| DELETE | `rest/wlanconf/{id}` | `unifi_network_delete_wlan` |
| POST | `rest/networkconf` | `unifi_network_create_network` |
| PUT | `rest/networkconf/{id}` | `unifi_network_update_network` |
| DELETE | `rest/networkconf/{id}` | `unifi_network_delete_network` |
| POST | `rest/firewallrule` | `unifi_network_create_firewall_rule` |
| PUT | `rest/firewallrule/{id}` | `unifi_network_update_firewall_rule` |
| DELETE | `rest/firewallrule/{id}` | `unifi_network_delete_firewall_rule` |
| POST | `rest/firewallgroup` | `unifi_network_create_firewall_group` |
| PUT | `rest/firewallgroup/{id}` | `unifi_network_update_firewall_group` |
| DELETE | `rest/firewallgroup/{id}` | `unifi_network_delete_firewall_group` |
| POST | `rest/portforward` | `unifi_network_create_port_forward` |
| PUT | `rest/portforward/{id}` | `unifi_network_update_port_forward` |
| DELETE | `rest/portforward/{id}` | `unifi_network_delete_port_forward` |
| POST | `rest/routing` | `unifi_network_create_route` |
| PUT | `rest/routing/{id}` | `unifi_network_update_route` |
| DELETE | `rest/routing/{id}` | `unifi_network_delete_route` |
| PUT | `rest/setting/{key}` | `unifi_network_update_settings` (per-section PUTs) |
| POST | `rest/portconf` | `unifi_network_create_port_profile` |
| PUT | `rest/portconf/{id}` | `unifi_network_update_port_profile` |
| DELETE | `rest/portconf/{id}` | `unifi_network_delete_port_profile` |
| PUT | `rest/device/{id}` | `unifi_network_assign_port_profile` (splices `port_overrides`) |
| POST | `cmd/devmgr` `speedtest` | `unifi_network_run_speedtest` |
| POST | `cmd/backup` `backup` | `unifi_network_create_backup` |
| POST | `cmd/devmgr` `restart` | `unifi_network_restart_device` |
| POST | `cmd/devmgr` `adopt` | `unifi_network_adopt_device` |
| POST | `cmd/devmgr` `set-locate` | `unifi_network_locate_device` |
| POST | `cmd/devmgr` `unset-locate` | `unifi_network_unlocate_device` |
| POST | `cmd/devmgr` `force-provision` | `unifi_network_provision_device` |
| POST | `cmd/devmgr` `upgrade` | `unifi_network_upgrade_device` |
| POST | `cmd/devmgr` `power-cycle` | `unifi_network_power_cycle_port` |
| POST | `cmd/sitemgr` `delete-device` | `unifi_network_forget_device` |
| POST | `cmd/stamgr` `block-sta` | `unifi_network_block_client` |
| POST | `cmd/stamgr` `unblock-sta` | `unifi_network_unblock_client` |
| POST | `cmd/stamgr` `kick-sta` | `unifi_network_kick_client` |
| POST | `cmd/stamgr` `authorize-guest` | `unifi_network_authorize_guest` |
| POST | `cmd/stamgr` `unauthorize-guest` | `unifi_network_unauthorize_guest` |
| POST | `cmd/stat` `reset-dpi` | `unifi_network_reset_dpi` |

### 3b. Official Network Integration API (`/proxy/network/integration/v1/`)

We now call this surface via `NetworkIntegrationClient` (28 read tools plus the
ACL, DNS, and firewall-zone write groups, all `unifi_network_*`, tagged
`{"network_integration"}`; write tools also carry `{"write"}`). "Covered" rows are
backed either by a direct Integration tool (named) or — for resources the legacy
controller already serves — by a **functional-equivalent** legacy tool. The site
UUID is resolved once at startup and injected by the client, so the per-site
tools take no `siteId` argument.

| Method | Path | Disposition | Tool / note |
|---|---|---|---|
| GET | `/v1/info` | **Covered** | `unifi_network_get_sysinfo` (legacy `stat/sysinfo`) |
| GET | `/v1/sites` | **Covered** | `unifi_network_list_sites` |
| GET | `/v1/pending-devices` | **Covered** | `unifi_network_list_pending_devices` |
| GET | `/v1/countries` | **Excluded** | Reference data (country list) — UI-only. |
| GET | `/v1/dpi/applications` | **Covered** | `unifi_network_list_dpi_applications` |
| GET | `/v1/dpi/categories` | **Covered** | `unifi_network_list_dpi_categories` |
| GET | `/v1/sites/{siteId}/clients` | **Covered** | `unifi_network_list_active_clients` (legacy `stat/sta`) |
| GET | `/v1/sites/{siteId}/clients/{clientId}` | **Covered** | `unifi_network_get_client` (legacy `stat/alluser`) |
| POST | `/v1/sites/{siteId}/clients/{clientId}/actions` | **Covered** | `authorize_guest`/`unauthorize_guest`/`block_client`/`unblock_client`/`kick_client` (legacy `cmd/stamgr`) |
| GET | `/v1/sites/{siteId}/devices` | **Covered** | `unifi_network_list_devices` (legacy `stat/device`) |
| POST | `/v1/sites/{siteId}/devices` | **Covered** | `unifi_network_adopt_device` (legacy `cmd/devmgr adopt`) |
| GET | `/v1/sites/{siteId}/devices/{deviceId}` | **Covered** | `unifi_network_get_device` |
| DELETE | `/v1/sites/{siteId}/devices/{deviceId}` | **Covered** | `unifi_network_forget_device` (legacy `cmd/sitemgr delete-device`) |
| POST | `/v1/sites/{siteId}/devices/{deviceId}/actions` | **Covered** | `restart_device`/`provision_device`/`upgrade_device`/`locate_device`/`unlocate_device` (legacy `cmd/devmgr`) |
| GET | `/v1/sites/{siteId}/devices/{deviceId}/statistics/latest` | **Covered** | `unifi_network_list_devices` returns per-device stats (legacy `stat/device`) |
| POST | `/v1/sites/{siteId}/devices/{deviceId}/interfaces/ports/{portIdx}/actions` | **Covered** | `unifi_network_power_cycle_port` (legacy `cmd/devmgr power-cycle`) |
| GET | `/v1/sites/{siteId}/device-tags` | **Covered** | `unifi_network_list_device_tags` |
| GET | `/v1/sites/{siteId}/acl-rules` | **Covered** | `unifi_network_list_acl_rules` |
| POST | `/v1/sites/{siteId}/acl-rules` | **Covered** | `unifi_network_create_acl_rule` |
| GET | `/v1/sites/{siteId}/acl-rules/ordering` | **Covered** | `unifi_network_get_acl_rules_ordering` |
| PUT | `/v1/sites/{siteId}/acl-rules/ordering` | **Covered** | `unifi_network_reorder_acl_rules` |
| GET | `/v1/sites/{siteId}/acl-rules/{aclRuleId}` | **Covered** | `unifi_network_get_acl_rule` |
| PUT | `/v1/sites/{siteId}/acl-rules/{aclRuleId}` | **Covered** | `unifi_network_update_acl_rule` |
| DELETE | `/v1/sites/{siteId}/acl-rules/{aclRuleId}` | **Covered** | `unifi_network_delete_acl_rule` |
| GET | `/v1/sites/{siteId}/firewall/policies` | **Covered** | `unifi_network_list_firewall_rules` (legacy `rest/firewallrule`) |
| POST | `/v1/sites/{siteId}/firewall/policies` | **Covered** | `unifi_network_create_firewall_rule` |
| GET | `/v1/sites/{siteId}/firewall/policies/ordering` | **Covered** | `unifi_network_get_firewall_policies_ordering` |
| PUT | `/v1/sites/{siteId}/firewall/policies/ordering` | **Gap** | Reorder policies. |
| GET | `/v1/sites/{siteId}/firewall/policies/{firewallPolicyId}` | **Covered** | `unifi_network_get_firewall_rule` |
| PUT | `/v1/sites/{siteId}/firewall/policies/{firewallPolicyId}` | **Covered** | `unifi_network_update_firewall_rule` |
| PATCH | `/v1/sites/{siteId}/firewall/policies/{firewallPolicyId}` | **Gap** | Partial update; our tool does full-object PUT only. |
| DELETE | `/v1/sites/{siteId}/firewall/policies/{firewallPolicyId}` | **Covered** | `unifi_network_delete_firewall_rule` |
| GET | `/v1/sites/{siteId}/firewall/zones` | **Covered** | `unifi_network_list_firewall_zones` |
| POST | `/v1/sites/{siteId}/firewall/zones` | **Covered** | `unifi_network_create_firewall_zone` |
| GET | `/v1/sites/{siteId}/firewall/zones/{firewallZoneId}` | **Covered** | `unifi_network_get_firewall_zone` |
| PUT | `/v1/sites/{siteId}/firewall/zones/{firewallZoneId}` | **Covered** | `unifi_network_update_firewall_zone` |
| DELETE | `/v1/sites/{siteId}/firewall/zones/{firewallZoneId}` | **Covered** | `unifi_network_delete_firewall_zone` |
| GET | `/v1/sites/{siteId}/dns/policies` | **Covered** | `unifi_network_list_dns_policies` |
| POST | `/v1/sites/{siteId}/dns/policies` | **Covered** | `unifi_network_create_dns_policy` |
| GET | `/v1/sites/{siteId}/dns/policies/{dnsPolicyId}` | **Covered** | `unifi_network_get_dns_policy` |
| PUT | `/v1/sites/{siteId}/dns/policies/{dnsPolicyId}` | **Covered** | `unifi_network_update_dns_policy` |
| DELETE | `/v1/sites/{siteId}/dns/policies/{dnsPolicyId}` | **Covered** | `unifi_network_delete_dns_policy` |
| GET | `/v1/sites/{siteId}/networks` | **Covered** | `unifi_network_list_networks` (legacy `rest/networkconf`) |
| POST | `/v1/sites/{siteId}/networks` | **Covered** | `unifi_network_create_network` |
| GET | `/v1/sites/{siteId}/networks/{networkId}` | **Covered** | `unifi_network_get_network` |
| PUT | `/v1/sites/{siteId}/networks/{networkId}` | **Covered** | `unifi_network_update_network` |
| DELETE | `/v1/sites/{siteId}/networks/{networkId}` | **Covered** | `unifi_network_delete_network` |
| GET | `/v1/sites/{siteId}/networks/{networkId}/references` | **Covered** | `unifi_network_get_network_references` |
| GET | `/v1/sites/{siteId}/wifi/broadcasts` | **Covered** | `unifi_network_list_wlans` (legacy `rest/wlanconf`) |
| POST | `/v1/sites/{siteId}/wifi/broadcasts` | **Covered** | `unifi_network_create_wlan` |
| GET | `/v1/sites/{siteId}/wifi/broadcasts/{wifiBroadcastId}` | **Covered** | `unifi_network_get_wlan` |
| PUT | `/v1/sites/{siteId}/wifi/broadcasts/{wifiBroadcastId}` | **Covered** | `unifi_network_update_wlan` |
| DELETE | `/v1/sites/{siteId}/wifi/broadcasts/{wifiBroadcastId}` | **Covered** | `unifi_network_delete_wlan` |
| GET | `/v1/sites/{siteId}/hotspot/vouchers` | **Covered** | `unifi_network_list_vouchers` |
| POST | `/v1/sites/{siteId}/hotspot/vouchers` | **Gap** | Generate vouchers. |
| DELETE | `/v1/sites/{siteId}/hotspot/vouchers` | **Gap** | Delete vouchers by filter. |
| GET | `/v1/sites/{siteId}/hotspot/vouchers/{voucherId}` | **Covered** | `unifi_network_get_voucher` |
| DELETE | `/v1/sites/{siteId}/hotspot/vouchers/{voucherId}` | **Gap** | Delete single voucher. |
| GET | `/v1/sites/{siteId}/traffic-matching-lists` | **Covered** | `unifi_network_list_traffic_matching_lists` |
| POST | `/v1/sites/{siteId}/traffic-matching-lists` | **Gap** | Create traffic-matching list. |
| GET | `/v1/sites/{siteId}/traffic-matching-lists/{id}` | **Covered** | `unifi_network_get_traffic_matching_list` |
| PUT | `/v1/sites/{siteId}/traffic-matching-lists/{id}` | **Gap** | Update traffic-matching list. |
| DELETE | `/v1/sites/{siteId}/traffic-matching-lists/{id}` | **Gap** | Delete traffic-matching list. |
| GET | `/v1/sites/{siteId}/switching/lags` | **Covered** | `unifi_network_list_lags` |
| GET | `/v1/sites/{siteId}/switching/lags/{lagId}` | **Covered** | `unifi_network_get_lag` |
| GET | `/v1/sites/{siteId}/switching/mc-lag-domains` | **Covered** | `unifi_network_list_mc_lag_domains` |
| GET | `/v1/sites/{siteId}/switching/mc-lag-domains/{id}` | **Covered** | `unifi_network_get_mc_lag_domain` |
| GET | `/v1/sites/{siteId}/switching/switch-stacks` | **Covered** | `unifi_network_list_switch_stacks` |
| GET | `/v1/sites/{siteId}/switching/switch-stacks/{id}` | **Covered** | `unifi_network_get_switch_stack` |
| GET | `/v1/sites/{siteId}/vpn/servers` | **Covered** | `unifi_network_list_vpn_servers` |
| GET | `/v1/sites/{siteId}/vpn/site-to-site-tunnels` | **Covered** | `unifi_network_list_site_to_site_tunnels` |
| GET | `/v1/sites/{siteId}/wans` | **Covered** | `unifi_network_list_wans` |
| GET | `/v1/sites/{siteId}/radius/profiles` | **Covered** | `unifi_network_list_radius_profiles` |

Coverage 54/73 ops (75%); 1 excluded; 18 gaps. All 18 remaining gaps are writes
(POST/PUT/PATCH/DELETE) — the read ceiling for this surface. The 28 direct
Network Integration read tools are named (above); the remaining Covered rows are
functional-equivalent legacy tools.

**Legacy-only capabilities** (we cover these; the official Integration API does *not*
document them): port-forwards, static routes, switch-port profiles, controller
settings, firewall *groups* (address/port sets), `stat/health`, `list/alarm` events,
`stat/device-basic`, configured/all clients, controller backup, speedtest, DPI reset.

---

## Maintenance

This is a manual snapshot, not an automated check. When upstream API versions move
(see the Snapshot table), re-run the enumeration and reconcile this file plus the
README "feature-complete" line. Tool↔endpoint rows must stay consistent with
`src/unifi_mcp/_inventory.py`; if you add or remove a tool, add or remove its row here.
