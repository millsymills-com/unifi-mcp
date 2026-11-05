# DNS policy named-field migration

`unifi_network_create_dns_policy` and `unifi_network_update_dns_policy` no longer
accept raw `data`. Pass `policy_type`, `enabled`, `domain` and the fields for the
selected variant as named arguments. Update remains a full-object PUT: send the
complete desired policy, not a patch. Omitted or None variant fields are absent;
they cannot clear a field or satisfy a required field. Supplying another
variant's fields refuses before HTTP.

| policy_type | Additional required arguments |
| --- | --- |
| A_RECORD | ipv4_address, ttl_seconds |
| AAAA_RECORD | ipv6_address, ttl_seconds |
| CNAME_RECORD | target_domain, ttl_seconds |
| MX_RECORD | mail_server_domain, priority |
| TXT_RECORD | text |
| SRV_RECORD | server_domain, service, protocol, port, priority, weight |
| FORWARD_DOMAIN | ip_address |

All seven variants remain supported. Names map to the controller's camel-case
fields. `enabled=False` and numeric zero are sent explicitly. A/AAAA TTL is
0 through 86400 seconds; CNAME TTL is 0 through 604800. TTL is unavailable for the
other variants. Priority, port and weight are 0 through 65535. Domain fields
are 1 through 127 characters; TXT text is 1 through 1024. Service/protocol and
IP syntax remain controller-validated. FastMCP retains normal scalar coercion;
these bounds do not imply strict rejection of every coercible input type.

For example, a full A-policy replacement uses `dns_policy_id`,
`policy_type="A_RECORD"`, `enabled=False`, `domain="example.test"`,
`ipv4_address="192.0.2.10"` and `ttl_seconds=60`. The resulting body has exactly
`type`, `enabled`, `domain`, `ipv4Address` and `ttlSeconds`.

This field union and bounds were checked against the official Network 10.6.102
[create](https://developer.ui.com/network/v10.6.102/creatednspolicy) and
[update](https://developer.ui.com/network/v10.6.102/updatednspolicy) schemas on
2026-11-05. This is documentation and mocked-test evidence, not live hardware
validation. Clients still enforce their fixed endpoint paths; tools retain the
readonly registration/runtime gates, dangerous-key defense and response
redaction. Delete and its confirmation are unchanged. Other #500 raw-body
interfaces and the separate held WLAN migration remain outside this PR.
