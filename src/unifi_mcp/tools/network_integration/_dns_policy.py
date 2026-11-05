"""Named DNS-policy bodies, following the Integration create/update union."""

from __future__ import annotations

from typing import Any, Literal

from unifi_mcp.errors import UniFiBadRequestError
from unifi_mcp.tools._common import build_named_arg_body, reject_dangerous_keys

DnsPolicyType = Literal[
    "A_RECORD", "AAAA_RECORD", "CNAME_RECORD", "MX_RECORD", "TXT_RECORD", "SRV_RECORD", "FORWARD_DOMAIN"
]

_FIELD_PATHS: dict[str, tuple[str, ...]] = {
    "ipv4_address": ("ipv4Address",),
    "ipv6_address": ("ipv6Address",),
    "target_domain": ("targetDomain",),
    "mail_server_domain": ("mailServerDomain",),
    "text": ("text",),
    "server_domain": ("serverDomain",),
    "ip_address": ("ipAddress",),
    "service": ("service",),
    "protocol": ("protocol",),
    "ttl_seconds": ("ttlSeconds",),
    "priority": ("priority",),
    "port": ("port",),
    "weight": ("weight",),
}
_REQUIRED = {
    "A_RECORD": {"ipv4_address", "ttl_seconds"},
    "AAAA_RECORD": {"ipv6_address", "ttl_seconds"},
    "CNAME_RECORD": {"target_domain", "ttl_seconds"},
    "MX_RECORD": {"mail_server_domain", "priority"},
    "TXT_RECORD": {"text"},
    "SRV_RECORD": {"server_domain", "service", "protocol", "port", "priority", "weight"},
    "FORWARD_DOMAIN": {"ip_address"},
}


def _validate_values(policy_type: str, values: dict[str, Any]) -> None:
    for field, value in values.items():
        if field in {"ttl_seconds", "priority", "port", "weight"}:
            maximum = (604800 if policy_type == "CNAME_RECORD" else 86400) if field == "ttl_seconds" else 65535
            if type(value) is not int or not 0 <= value <= maximum:
                raise UniFiBadRequestError(f"{field} must be an integer from 0 to {maximum}")
        elif not isinstance(value, str):
            raise UniFiBadRequestError(f"{field} must be a string")
        elif field in {"domain", "target_domain", "mail_server_domain", "server_domain", "text"}:
            maximum = 1024 if field == "text" else 127
            if not 1 <= len(value) <= maximum:
                raise UniFiBadRequestError(f"{field} must contain 1 to {maximum} characters")


def build_dns_policy_body(
    *, tool_name: str, policy_type: str, enabled: bool, domain: str, fields: dict[str, Any]
) -> dict[str, Any]:
    """Require exactly the selected variant's fields; never merge a stored body."""
    if policy_type not in _REQUIRED:
        raise UniFiBadRequestError("policy_type is not a supported DNS policy type")
    if type(enabled) is not bool:
        raise UniFiBadRequestError("enabled must be a boolean")
    supplied = {key: value for key, value in fields.items() if value is not None}
    required = _REQUIRED[policy_type]
    if set(supplied) != required:
        raise UniFiBadRequestError("provide exactly the fields required by policy_type: " + ", ".join(sorted(required)))
    _validate_values(policy_type, {"domain": domain, **supplied})
    body = build_named_arg_body(tool_name=tool_name, field_paths=_FIELD_PATHS, named_values=supplied, data=None)
    body.update(type=policy_type, enabled=enabled, domain=domain)
    reject_dangerous_keys(body, tool_name=tool_name)
    return body
