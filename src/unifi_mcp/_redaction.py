"""Secret-redaction helper shared by clients (error bodies) and tools (responses).

`clients/base.py` calls this to scrub the JSON parsed from upstream 4xx
bodies before they reach the agent (#148). The tool layer calls it from
read-mode read tools so PSKs / RADIUS secrets / SSO tokens never leave
the server in cleartext (#146). Write tools deliberately do **not** scrub
because the controller needs the cleartext values for round-trip writes.
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
