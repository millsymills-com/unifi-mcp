# Tool ↔ Schema Matrix

The input-schema surface of all **160 MCP tools** (100 read, 60 write), one row per tool. This is the companion to the *endpoint* map in [`api-coverage-matrix.md`](api-coverage-matrix.md): that file answers *which UniFi endpoints are covered*; this one answers *what arguments each tool accepts*.

Unlike the endpoint matrix, this table is **machine-asserted**. `tests/unit/test_schema_matrix.py` rebuilds the live server, renders every tool's `parameters` schema, and fails if any row here drifts from the registered schema — a parameter added, removed, renamed, retyped, or re-defaulted without updating this file breaks CI. Regenerate, do not hand-edit, the rows: `python scripts/gen_schema_matrix.py`.

## Legend

- **Mode** — `R` read-only · `W` write (tagged `write`, hidden unless `UNIFI_MODE=readwrite`).
- **Parameters** — the tool's input schema, excluding the framework-supplied `Context`. Each parameter is `name: type` (required) or `name?: type` (optional), with `` = <default>`` when the schema carries one. `—` means the tool takes no arguments. `|` denotes a union (e.g. `string | null` is an optional/nullable value); `array<T>` and `object` mirror the JSON Schema type. An enum renders its allowed values as quoted literals joined by `|` (e.g. `"5m" | "1h"`); `any` marks a parameter with no declared type.

## Counts

| API | Read | Write | Total |
|---|---:|---:|---:|
| Network API | 54 | 52 | 106 |
| Protect API | 37 | 8 | 45 |
| Site Manager API | 9 | 0 | 9 |
| **All** | **100** | **60** | **160** |

Counts mirror `src/unifi_mcp/_inventory.py`; the per-tool rows below are rendered from the live registered schemas.

---

## Network API

Backing surface: `/proxy/network/api/s/{site}/ (legacy controller)`. 106 tools.

| Tool | Mode | Parameters |
|---|:--:|---|
| `unifi_network_adopt_device` | W | `mac: string, confirm?: boolean = false` |
| `unifi_network_assign_port_profile` | W | `mac: string, port_idx: integer, profile_id: string, confirm?: boolean = false` |
| `unifi_network_authorize_guest` | W | `mac: string, minutes?: integer = 60` |
| `unifi_network_block_client` | W | `mac: string, confirm?: boolean = false` |
| `unifi_network_create_acl_rule` | W | `data: object` |
| `unifi_network_create_backup` | W | — |
| `unifi_network_create_dns_policy` | W | `data: object` |
| `unifi_network_create_firewall_group` | W | `name: string, group_type: string, group_members: array<string>` |
| `unifi_network_create_firewall_rule` | W | `name: string, ruleset: string, action?: string = "drop", enabled?: boolean = true, protocol?: string = "all", src_address?: string \| null = null, dst_address?: string \| null = null, data?: object \| null = null` |
| `unifi_network_create_firewall_zone` | W | `name: string, network_ids: array<string>` |
| `unifi_network_create_network` | W | `name: string, purpose?: string = "corporate", subnet?: string \| null = null, vlan?: integer \| null = null, dhcpd_enabled?: boolean = true` |
| `unifi_network_create_port_forward` | W | `name: string, dst_port: string, fwd: string, fwd_port: string, proto?: string = "tcp_udp", enabled?: boolean = true` |
| `unifi_network_create_port_profile` | W | `data: object` |
| `unifi_network_create_route` | W | `name: string, network: string, route_type?: string = "nexthop-route", gateway_ip?: string \| null = null, interface?: string \| null = null, enabled?: boolean = true` |
| `unifi_network_create_vouchers` | W | `name: string, time_limit_minutes: integer, count?: integer = 1, authorized_guest_limit?: integer \| null = null, data_usage_limit_mbytes?: integer \| null = null, rx_rate_limit_kbps?: integer \| null = null, tx_rate_limit_kbps?: integer \| null = null` |
| `unifi_network_create_wlan` | W | `name: string, security?: string = "wpapsk", wpa_mode?: string = "wpa2", x_passphrase?: string = "", enabled?: boolean = true` |
| `unifi_network_delete_acl_rule` | W | `acl_rule_id: string, confirm?: boolean = false` |
| `unifi_network_delete_dns_policy` | W | `dns_policy_id: string, confirm?: boolean = false` |
| `unifi_network_delete_firewall_group` | W | `group_id: string, confirm?: boolean = false` |
| `unifi_network_delete_firewall_rule` | W | `rule_id: string, confirm?: boolean = false` |
| `unifi_network_delete_firewall_zone` | W | `zone_id: string, confirm?: boolean = false` |
| `unifi_network_delete_network` | W | `network_id: string, confirm?: boolean = false` |
| `unifi_network_delete_port_forward` | W | `port_forward_id: string, confirm?: boolean = false` |
| `unifi_network_delete_port_profile` | W | `profile_id: string, confirm?: boolean = false` |
| `unifi_network_delete_route` | W | `route_id: string, confirm?: boolean = false` |
| `unifi_network_delete_voucher` | W | `voucher_id: string, confirm?: boolean = false` |
| `unifi_network_delete_vouchers` | W | `voucher_filter: string, confirm?: boolean = false` |
| `unifi_network_delete_wlan` | W | `wlan_id: string, confirm?: boolean = false` |
| `unifi_network_forget_device` | W | `mac: string, confirm?: boolean = false` |
| `unifi_network_get_acl_rule` | R | `acl_rule_id: string` |
| `unifi_network_get_acl_rules_ordering` | R | — |
| `unifi_network_get_client` | R | `mac: string` |
| `unifi_network_get_device` | R | `mac: string` |
| `unifi_network_get_dns_policy` | R | `dns_policy_id: string` |
| `unifi_network_get_dpi_stats` | R | `dpi_type?: string = "by_app"` |
| `unifi_network_get_firewall_group` | R | `group_id: string` |
| `unifi_network_get_firewall_policies_ordering` | R | — |
| `unifi_network_get_firewall_rule` | R | `rule_id: string` |
| `unifi_network_get_firewall_zone` | R | `zone_id: string` |
| `unifi_network_get_health` | R | — |
| `unifi_network_get_lag` | R | `lag_id: string` |
| `unifi_network_get_mc_lag_domain` | R | `domain_id: string` |
| `unifi_network_get_network` | R | `network_id: string` |
| `unifi_network_get_network_references` | R | `network_id: string` |
| `unifi_network_get_port_forward` | R | `port_forward_id: string` |
| `unifi_network_get_port_profile` | R | `profile_id: string` |
| `unifi_network_get_route` | R | `route_id: string` |
| `unifi_network_get_settings` | R | — |
| `unifi_network_get_switch_stack` | R | `stack_id: string` |
| `unifi_network_get_sysinfo` | R | — |
| `unifi_network_get_traffic_matching_list` | R | `list_id: string` |
| `unifi_network_get_voucher` | R | `voucher_id: string` |
| `unifi_network_get_wlan` | R | `wlan_id: string` |
| `unifi_network_kick_client` | W | `mac: string` |
| `unifi_network_list_acl_rules` | R | `offset?: integer = 0, limit?: integer = 200` |
| `unifi_network_list_active_clients` | R | — |
| `unifi_network_list_all_clients` | R | — |
| `unifi_network_list_configured_clients` | R | — |
| `unifi_network_list_device_tags` | R | — |
| `unifi_network_list_devices` | R | — |
| `unifi_network_list_devices_basic` | R | — |
| `unifi_network_list_dns_policies` | R | `offset?: integer = 0, limit?: integer = 200` |
| `unifi_network_list_dpi_applications` | R | `offset?: integer = 0, limit?: integer = 200` |
| `unifi_network_list_dpi_categories` | R | `offset?: integer = 0, limit?: integer = 200` |
| `unifi_network_list_events` | R | `limit?: integer = 100` |
| `unifi_network_list_firewall_groups` | R | — |
| `unifi_network_list_firewall_rules` | R | — |
| `unifi_network_list_firewall_zones` | R | `offset?: integer = 0, limit?: integer = 200` |
| `unifi_network_list_lags` | R | `offset?: integer = 0, limit?: integer = 200` |
| `unifi_network_list_mc_lag_domains` | R | `offset?: integer = 0, limit?: integer = 200` |
| `unifi_network_list_networks` | R | — |
| `unifi_network_list_pending_devices` | R | — |
| `unifi_network_list_port_forwards` | R | — |
| `unifi_network_list_port_profiles` | R | — |
| `unifi_network_list_radius_profiles` | R | `offset?: integer = 0, limit?: integer = 200` |
| `unifi_network_list_routes` | R | — |
| `unifi_network_list_site_to_site_tunnels` | R | `offset?: integer = 0, limit?: integer = 200` |
| `unifi_network_list_sites` | R | `offset?: integer = 0, limit?: integer = 200` |
| `unifi_network_list_switch_stacks` | R | `offset?: integer = 0, limit?: integer = 200` |
| `unifi_network_list_traffic_matching_lists` | R | `offset?: integer = 0, limit?: integer = 200` |
| `unifi_network_list_vouchers` | R | `offset?: integer = 0, limit?: integer = 200` |
| `unifi_network_list_vpn_servers` | R | `offset?: integer = 0, limit?: integer = 200` |
| `unifi_network_list_wans` | R | `offset?: integer = 0, limit?: integer = 200` |
| `unifi_network_list_wlans` | R | — |
| `unifi_network_locate_device` | W | `mac: string` |
| `unifi_network_power_cycle_port` | W | `mac: string, port_idx: integer, confirm?: boolean = false` |
| `unifi_network_provision_device` | W | `mac: string` |
| `unifi_network_reorder_acl_rules` | W | `ordered_acl_rule_ids: array<string>, confirm?: boolean = false` |
| `unifi_network_reset_dpi` | W | `confirm?: boolean = false` |
| `unifi_network_restart_device` | W | `mac: string, confirm?: boolean = false` |
| `unifi_network_run_speedtest` | W | — |
| `unifi_network_unauthorize_guest` | W | `mac: string` |
| `unifi_network_unblock_client` | W | `mac: string` |
| `unifi_network_unlocate_device` | W | `mac: string` |
| `unifi_network_update_acl_rule` | W | `acl_rule_id: string, data: object` |
| `unifi_network_update_dns_policy` | W | `dns_policy_id: string, data: object` |
| `unifi_network_update_firewall_group` | W | `group_id: string, data: object` |
| `unifi_network_update_firewall_rule` | W | `rule_id: string, data: object` |
| `unifi_network_update_firewall_zone` | W | `zone_id: string, name: string, network_ids: array<string>` |
| `unifi_network_update_network` | W | `network_id: string, data: object` |
| `unifi_network_update_port_forward` | W | `port_forward_id: string, data: object` |
| `unifi_network_update_port_profile` | W | `profile_id: string, data: object` |
| `unifi_network_update_route` | W | `route_id: string, data: object` |
| `unifi_network_update_settings` | W | `ntp_server_1?: string \| null = null, ntp_server_2?: string \| null = null, mgmt_led_enabled?: boolean \| null = null` |
| `unifi_network_update_wlan` | W | `wlan_id: string, data: object` |
| `unifi_network_upgrade_device` | W | `mac: string, confirm?: boolean = false` |

---

## Protect API

Backing surface: `/proxy/protect/integration/v1/`. 45 tools.

| Tool | Mode | Parameters |
|---|:--:|---|
| `unifi_protect_export_video` | R | `camera_id: string, start: integer, end: integer` |
| `unifi_protect_get_alarm_hub` | R | `alarm_hub_id: string` |
| `unifi_protect_get_bridge` | R | `bridge_id: string` |
| `unifi_protect_get_camera` | R | `camera_id: string` |
| `unifi_protect_get_chime` | R | `chime_id: string` |
| `unifi_protect_get_file_asset` | R | `file_type: string` |
| `unifi_protect_get_fob` | R | `fob_id: string` |
| `unifi_protect_get_light` | R | `light_id: string` |
| `unifi_protect_get_link_station` | R | `link_station_id: string` |
| `unifi_protect_get_liveview` | R | `liveview_id: string` |
| `unifi_protect_get_meta_info` | R | — |
| `unifi_protect_get_nvr` | R | — |
| `unifi_protect_get_relay` | R | `relay_id: string` |
| `unifi_protect_get_rtsps_stream` | R | `camera_id: string, qualities?: array<string> \| null = null` |
| `unifi_protect_get_sensor` | R | `sensor_id: string` |
| `unifi_protect_get_siren` | R | `siren_id: string` |
| `unifi_protect_get_snapshot` | R | `camera_id: string, timestamp?: integer \| null = null` |
| `unifi_protect_get_speaker` | R | `speaker_id: string` |
| `unifi_protect_get_ulp_user` | R | `ulp_user_id: string` |
| `unifi_protect_get_user` | R | `user_id: string` |
| `unifi_protect_get_viewer` | R | `viewer_id: string` |
| `unifi_protect_list_alarm_hubs` | R | — |
| `unifi_protect_list_arm_profiles` | R | — |
| `unifi_protect_list_bridges` | R | — |
| `unifi_protect_list_cameras` | R | — |
| `unifi_protect_list_chimes` | R | — |
| `unifi_protect_list_fobs` | R | — |
| `unifi_protect_list_lights` | R | — |
| `unifi_protect_list_link_stations` | R | — |
| `unifi_protect_list_liveviews` | R | — |
| `unifi_protect_list_relays` | R | — |
| `unifi_protect_list_sensors` | R | — |
| `unifi_protect_list_sirens` | R | — |
| `unifi_protect_list_speakers` | R | — |
| `unifi_protect_list_ulp_users` | R | — |
| `unifi_protect_list_users` | R | — |
| `unifi_protect_list_viewers` | R | — |
| `unifi_protect_set_light_mode` | W | `light_id: string, mode: string` |
| `unifi_protect_set_recording_mode` | W | `camera_id: string, mode: string, pre_padding?: integer \| null = null, post_padding?: integer \| null = null` |
| `unifi_protect_set_smart_detection` | W | `camera_id: string, object_types: array<string>` |
| `unifi_protect_set_viewer_liveview` | W | `viewer_id: string, liveview_id: string` |
| `unifi_protect_update_camera` | W | `camera_id: string, name?: string \| null = null, led_settings_is_enabled?: boolean \| null = null, osd_settings_is_name_enabled?: boolean \| null = null, osd_settings_is_date_enabled?: boolean \| null = null, osd_settings_is_logo_enabled?: boolean \| null = null, osd_settings_is_debug_enabled?: boolean \| null = null` |
| `unifi_protect_update_chime` | W | `chime_id: string, volume?: integer \| null = null, repeat_times?: integer \| null = null, data?: object \| null = null` |
| `unifi_protect_update_light` | W | `light_id: string, led_level?: integer \| null = null, pir_duration?: integer \| null = null, pir_sensitivity?: integer \| null = null, mode?: string \| null = null, data?: object \| null = null` |
| `unifi_protect_update_sensor` | W | `sensor_id: string, mount_type?: string \| null = null, motion_is_enabled?: boolean \| null = null, light_is_enabled?: boolean \| null = null, data?: object \| null = null` |

---

## Site Manager API

Backing surface: `https://api.ui.com/v1/`. 9 tools.

| Tool | Mode | Parameters |
|---|:--:|---|
| `unifi_site_manager_get_host` | R | `host_id: string` |
| `unifi_site_manager_get_isp_metrics` | R | `metric_type: string, begin_timestamp?: string \| null = null, end_timestamp?: string \| null = null, duration?: string \| null = null` |
| `unifi_site_manager_get_sdwan_config` | R | `config_id: string` |
| `unifi_site_manager_get_sdwan_config_status` | R | `config_id: string` |
| `unifi_site_manager_list_devices` | R | `host_id?: string \| null = null` |
| `unifi_site_manager_list_hosts` | R | — |
| `unifi_site_manager_list_sdwan_configs` | R | — |
| `unifi_site_manager_list_sites` | R | — |
| `unifi_site_manager_query_isp_metrics` | R | `metric_type: string, sites: array<object>` |

---

## Maintenance

Generated, not hand-written. After changing any tool signature run `python scripts/gen_schema_matrix.py` to regenerate this file, then `uv run pytest tests/unit/test_schema_matrix.py` to confirm zero drift. The renderer and the test share `unifi_mcp._schema`, so the table and the live schemas use identical formatting.
