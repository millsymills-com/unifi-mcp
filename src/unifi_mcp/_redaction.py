"""Secret-redaction helper shared by clients (error bodies) and tools (responses).

`clients/base.py` calls this to scrub the JSON parsed from upstream 4xx
bodies before they reach the agent (#148). The tool layer calls it on
every response — read and write alike — so PSKs / RADIUS secrets / SSO
tokens never leave the server in cleartext (#146, #325).

The "don't scrub" stance from #146 applies only to REQUEST bodies: the
controller legitimately needs cleartext values to perform a round-trip
write, so request/body construction is never run through this helper.
Write RESPONSES, however, can echo those same credential fields straight
back to the agent, so they are now scrubbed exactly like read responses.
"""

from __future__ import annotations

from typing import Any

SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        # Wi-Fi / RADIUS / portal credentials
        "x_passphrase",
        "x_password",
        "password",
        "passphrase",
        "radius_secret",
        "wpa_psk",
        # Device-level credentials (SSH / inform / VRRP)
        "x_ssh_password",
        "x_authkey",
        "x_inform_authkey",
        "x_vrrpd_md5_key",
        # Dynamic-DNS credentials
        "x_ddns_pwd",
        # Generic credential keys
        "private_key",
        "ssotoken",
        "bearer",
        "token",
        "api_key",
        "apikey",
        "secret",
        "client_secret",
    }
)

REDACTED = "***REDACTED***"


def normalize_key(key: str) -> str:
    """Lowercase + strip underscores so snake_case and camelCase forms of the
    same key (`client_secret` and `clientSecret`) collapse to one identity.

    Shared by this module's secret-key matching and the tool-layer
    dangerous-key denylist (``tools/_common``) so both classify keys the
    same way; the two denylists themselves stay independent.
    """
    return key.lower().replace("_", "")


# Normalized denylist — matched against the normalized key.
_NORMALIZED_KEYS: frozenset[str] = frozenset(normalize_key(k) for k in SENSITIVE_KEYS)

# Suffix patterns — match the **normalized** end of a key, so the same rule
# catches `x_ssh_password`, `xSshPassword`, and `sshPassword`.
_NORMALIZED_SUFFIXES: tuple[str, ...] = ("password", "secret", "authkey", "token", "passwd")


def _is_sensitive_key(key: str) -> bool:
    normalized = normalize_key(key)
    if normalized in _NORMALIZED_KEYS:
        return True
    if normalized.startswith("super") and (normalized.endswith("password") or normalized.endswith("url")):
        return True
    return any(normalized.endswith(suffix) for suffix in _NORMALIZED_SUFFIXES)


def flatten_key_names(value: Any, _prefix: str = "") -> list[str]:
    """Return dotted top-level + nested key *names* of a JSON body, no values.

    Used to log the shape of an outbound write without exposing any value
    (values may carry credentials). Recurses into nested dicts, joining with
    ``.`` (e.g. ``lightDeviceSettings.ledLevel``); lists and scalars are
    leaves whose key name is recorded but whose contents are never walked.
    A non-dict top-level ``value`` yields an empty list.
    """
    if not isinstance(value, dict):
        return []
    names: list[str] = []
    for key, sub in value.items():
        dotted = f"{_prefix}{key}"
        if isinstance(sub, dict) and sub:
            names.extend(flatten_key_names(sub, f"{dotted}."))
        else:
            names.append(dotted)
    return names


def redact_secrets(value: Any) -> Any:
    """Return a deep copy of ``value`` with sensitive keys replaced.

    Recursively walks dicts and lists. Dict-key matching is case-insensitive
    and underscore-insensitive (so ``client_secret`` and ``clientSecret`` are
    both caught). Also matches ``super_*_password`` / ``super_*_url`` callback
    keys that have historically leaked controller config, plus the credential
    suffixes ``password`` / ``secret`` / ``authkey`` / ``token`` / ``passwd``.
    Non-container values pass through untouched. Input is not mutated.
    """
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, sub in value.items():
            key_str = str(key)
            if _is_sensitive_key(key_str):
                redacted[key_str] = REDACTED
            else:
                redacted[key_str] = redact_secrets(sub)
        return redacted
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    return value
