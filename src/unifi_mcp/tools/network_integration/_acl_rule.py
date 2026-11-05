"""Named ACL bodies for the Integration IPv4 and MAC discriminated union."""

from __future__ import annotations

from typing import Any, Literal

from unifi_mcp.errors import UniFiBadRequestError
from unifi_mcp.tools._common import build_named_arg_body, reject_dangerous_keys, validate_id, validate_mac

AclRuleType = Literal["IPV4", "MAC"]
AclAction = Literal["ALLOW", "BLOCK"]
AclProtocol = Literal["TCP", "UDP"]

_FIELD_PATHS: dict[str, tuple[str, ...]] = {
    "rule_type": ("type",),
    "enabled": ("enabled",),
    "name": ("name",),
    "action": ("action",),
    "description": ("description",),
    "network_id": ("networkIdFilter",),
    "protocol_filter": ("protocolFilter",),
    "enforcing_device_ids": ("enforcingDeviceFilter", "deviceIds"),
}
for _side in ("source", "destination"):
    for _name, _key in {
        "ip_addresses_or_subnets": "ipAddressesOrSubnets",
        "network_ids": "networkIds",
        "ports": "portFilter",
        "mac_addresses": "macAddresses",
        "mac_prefix_length": "prefixLength",
    }.items():
        _FIELD_PATHS[f"{_side}_{_name}"] = (_side + "Filter", _key)


def _validate_list(field: str, value: object) -> None:
    if not isinstance(value, list) or not value:
        raise UniFiBadRequestError(f"{field} must be a nonempty list")
    if field.endswith("_ports"):
        if any(type(item) is not int or not 1 <= item <= 65535 for item in value):
            raise UniFiBadRequestError(f"{field} must contain integer ports from 1 to 65535")
    elif any(not isinstance(item, str) or not item for item in value):
        raise UniFiBadRequestError(f"{field} must contain nonempty strings")
    if field.endswith("_ids"):
        for index, item in enumerate(value):
            validate_id(item, field=f"{field}[{index}]")
    if field.endswith("_mac_addresses"):
        for index, item in enumerate(value):
            validate_mac(item, field=f"{field}[{index}]")
    if field == "protocol_filter" and any(item not in {"TCP", "UDP"} for item in value):
        raise UniFiBadRequestError("protocol_filter accepts TCP and UDP only")
    if (field.endswith(("_ids", "_ports")) or field == "protocol_filter") and len(set(value)) != len(value):
        raise UniFiBadRequestError(f"{field} must contain unique values")


def _validate_base(values: dict[str, Any]) -> None:
    if set(values) - set(_FIELD_PATHS):
        raise UniFiBadRequestError("unsupported ACL field")
    if values.get("rule_type") not in ("IPV4", "MAC"):
        raise UniFiBadRequestError("rule_type must be IPV4 or MAC")
    if values.get("action") not in ("ALLOW", "BLOCK"):
        raise UniFiBadRequestError("action must be ALLOW or BLOCK")
    if type(values.get("enabled")) is not bool:
        raise UniFiBadRequestError("enabled must be a boolean")
    if not isinstance(values.get("name"), str) or not values["name"]:
        raise UniFiBadRequestError("name must be a nonempty string")
    if values.get("description") is not None and not isinstance(values["description"], str):
        raise UniFiBadRequestError("description must be a string")


def _validate_variant(values: dict[str, Any]) -> None:
    if values["rule_type"] == "MAC":
        if values.get("network_id") is None:
            raise UniFiBadRequestError("network_id is required for MAC rules")
        validate_id(values["network_id"], field="network_id")
        if values.get("protocol_filter") is not None:
            raise UniFiBadRequestError("protocol_filter is only supported for IPV4 rules")
    elif values.get("network_id") is not None:
        raise UniFiBadRequestError("network_id is only supported for MAC rules")


def _endpoint_kind(side: str, values: dict[str, Any]) -> str | None:
    ips = values.get(f"{side}_ip_addresses_or_subnets")
    networks = values.get(f"{side}_network_ids")
    ports = values.get(f"{side}_ports")
    macs = values.get(f"{side}_mac_addresses")
    prefix = values.get(f"{side}_mac_prefix_length")
    if values["rule_type"] == "MAC":
        if any(value is not None for value in (ips, networks, ports)):
            raise UniFiBadRequestError(f"{side}: IP/network/port fields cannot be used in a MAC rule")
        if prefix is not None and macs is None:
            raise UniFiBadRequestError(f"{side}: MAC prefix requires MAC addresses")
        return "MAC_ADDRESSES" if macs is not None else None
    if macs is not None or prefix is not None:
        raise UniFiBadRequestError(f"{side}: MAC fields cannot be used in an IPV4 rule")
    if ips is not None and networks is not None:
        raise UniFiBadRequestError(f"{side}: choose IP addresses/subnets or network IDs")
    if ips is not None:
        return "IP_ADDRESSES_OR_SUBNETS"
    if networks is not None:
        return "NETWORKS"
    return "PORTS" if ports is not None else None


def _validate_optional(values: dict[str, Any]) -> None:
    for field, value in values.items():
        if value is None:
            continue
        if field.endswith("_mac_prefix_length"):
            if type(value) is not int or not 1 <= value <= 48:
                raise UniFiBadRequestError(f"{field} must be an integer from 1 to 48")
        elif (
            field.endswith(("_ids", "_ports", "_mac_addresses", "_ip_addresses_or_subnets"))
            or field == "protocol_filter"
        ):
            _validate_list(field, value)


def build_acl_rule_body(*, tool_name: str, values: dict[str, Any]) -> dict[str, Any]:
    """Build the complete supplied rule without fetching/merging prior state."""
    _validate_base(values)
    _validate_variant(values)
    _validate_optional(values)
    kinds = {side: _endpoint_kind(side, values) for side in ("source", "destination")}
    body = build_named_arg_body(tool_name=tool_name, field_paths=_FIELD_PATHS, named_values=values, data=None)
    if "enforcingDeviceFilter" in body:
        body["enforcingDeviceFilter"]["type"] = "DEVICES"
    for side, kind in kinds.items():
        if kind is not None:
            body[side + "Filter"]["type"] = kind
    reject_dangerous_keys(body, tool_name=tool_name)
    return body
