# ACL rule named-field migration

`unifi_network_create_acl_rule` and `unifi_network_update_acl_rule` replace raw
`data` with named fields. Both require `rule_type` (IPV4 or MAC), `enabled`, a
nonempty `name`, and `action` (ALLOW or BLOCK). Update also requires
`acl_rule_id` and remains a full-object PUT. Send the complete desired rule;
the client builds its body solely from supplied fields, without a GET/merge
or copying old filters. Resupply every filter you intend to retain. The cited
schema does not define the controller effect of omitting sourceFilter or
destinationFilter, and that behavior has not been live verified here.

## Filter selection

For either `source_` or `destination_`, use the following named suffixes:

| Rule type | Arguments | Constructed endpoint type |
| --- | --- | --- |
| IPV4 | ip_addresses_or_subnets, optional ports | IP_ADDRESSES_OR_SUBNETS |
| IPV4 | network_ids, optional ports | NETWORKS |
| IPV4 | ports alone | PORTS |
| MAC | mac_addresses, optional mac_prefix_length | MAC_ADDRESSES |

Address/subnet and network selectors cannot mix on one endpoint. IP/network/port
selectors cannot be used in MAC rules, and MAC selectors cannot be used in IPv4
rules. A MAC prefix requires its corresponding address list. Lists are nonempty;
ports are integers 1 through 65535, and MAC prefixes are 1 through 48. Ports and
ID lists are unique. IP/subnet and MAC lists retain supplied duplicates because
the published schema does not mark them unique.

MAC rules require `network_id`, mapped to `networkIdFilter`. IPv4 rules forbid
it and may supply a nonempty unique `protocol_filter` of TCP and/or UDP. Optional
`enforcing_device_ids` becomes a DEVICES filter. Its list is nonempty and unique;
None omits enforcingDeviceFilter from the request. The API describes null
device filters as applying to all switches and null IPv4 protocol filters as
applying to all protocols. For address/subnet and network endpoints, the optional
null portFilter is described as applying to all ports; PORTS endpoints instead
require a nonempty port list.
None for an endpoint selector sends no sourceFilter/destinationFilter property.
That request shape is tested offline; controller-side omission effects are
unverified. Explicit null-clearing is not exposed, and omission must not be
assumed to preserve or clear a filter.

`description` may be omitted; an empty string is sent explicitly. False is also
sent explicitly. ID path syntax and MAC syntax use the shared validators; IP,
UUID and controller policy semantics remain controller-validated. FastMCP keeps
normal scalar coercion. No raw object argument or deprecated `index` is exposed;
use `unifi_network_reorder_acl_rules` with its existing confirmation for priority.

## Evidence and operating boundary

Field variants, required keys, bounds and uniqueness were checked on 2026-11-05
against the official Network 10.6.102
[create](https://developer.ui.com/network/v10.6.102/createaclrule) and
[update](https://developer.ui.com/network/v10.6.102/updateaclrule) schemas.
The tool body is limited to those fields, including fixed nested filter types.
Both declarative and runtime write gates, response redaction, dangerous-key
defense, fixed client endpoint routing and delete/reorder confirmations remain
intact. No live hardware validation, device writes or service changes were run.
#500 stays open while the separate WLAN migration remains held for GitGuardian.
