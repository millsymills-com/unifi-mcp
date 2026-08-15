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

import re
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
        # VPN tunnel material. The WireGuard peer config is a whole .conf blob
        # whose key name reads as a filename, not a credential, so neither the
        # exact list nor the suffixes below would catch it (#519-followup).
        "wireguard_client_configuration_file",
        # Generic credential keys
        "private_key",
        "ssotoken",
        "bearer",
        "token",
        "api_key",
        "apikey",
        "secret",
        "client_secret",
        # Auth / session artifacts reflected into responses or error bodies (#442)
        "cookie",
        "set_cookie",
        "authorization",
        "credential",
        "credentials",
        "session",
        "sessionid",
        "csrf",
        "jwt",
    }
)

REDACTED = "***REDACTED***"


def normalize_key(key: str) -> str:
    """Lowercase + strip underscores/hyphens so snake_case, camelCase, and
    kebab-case forms of the same key (`client_secret`, `clientSecret`,
    `set-cookie`/`set_cookie`) collapse to one identity.

    Shared by this module's secret-key matching and the tool-layer
    dangerous-key denylist (``tools/_common``) so both classify keys the
    same way; the two denylists themselves stay independent.
    """
    return key.lower().replace("_", "").replace("-", "")


# Normalized denylist — matched against the normalized key.
_NORMALIZED_KEYS: frozenset[str] = frozenset(normalize_key(k) for k in SENSITIVE_KEYS)

# Suffix patterns — match the **normalized** end of a key, so the same rule
# catches `x_ssh_password`, `xSshPassword`, and `sshPassword`.
_NORMALIZED_SUFFIXES: tuple[str, ...] = (
    "password",
    "secret",
    "authkey",
    "token",
    "passwd",
    # `private_key` alone is an exact match, but a qualified name such as
    # `wireguard_private_key` normalizes to `wireguardprivatekey`, which the
    # exact list misses; match the suffix so any qualifier is covered.
    "privatekey",
    # Same shape for pre-shared keys: only the literal `wpa_psk` was an exact
    # match, so `ipsec_psk` / `preshared_key` / `shared_key` reached the agent
    # in cleartext despite `vpn.py` promising otherwise. `sharedkey` covers the
    # pre-shared spelling too, so it subsumes `presharedkey`.
    "psk",
    "sharedkey",
)


# Query-param names that carry a credential when present in a URL value.
# ``key`` is intentionally absent: it collides with benign params such as
# ``?key=sortOrder`` (#455). Use ``apikey``/``api_key`` for genuine key params.
_CREDENTIAL_QUERY_PARAMS: tuple[str, ...] = (
    "token",
    "password",
    "passwd",
    "secret",
    "apikey",
    "api_key",
    "auth",
)

# A URL with userinfo (``scheme://userinfo@host``). The password after a colon
# is the obvious case, but Protect stream URLs can carry a bare bearer token in
# the username position (``rtsp://<token>@host``), so the colon is optional and
# any userinfo is treated as credential-bearing (#455).
_URL_USERINFO_RE = re.compile(r"^[a-z][a-z0-9+.\-]*://[^/@\s]+@[^@/\s]", re.IGNORECASE)

# An RTSP/RTSPS stream URL whose path segment is the bearer credential. UniFi
# Protect ``cameras/{id}/rtsps-stream`` returns ``rtsps://host:7441/<alias>``
# where ``<alias>`` *is* the secret — there is no ``?token=`` query param, so
# the query-param matcher misses it. Any non-empty path makes it credentialed.
_RTSP_STREAM_RE = re.compile(r"^rtsps?://[^/\s]+/\S+", re.IGNORECASE)

# A ``?``/``&`` query param whose name is credential-bearing and which has a value.
_URL_CREDENTIAL_QUERY_RE = re.compile(
    r"[?&](?:" + "|".join(re.escape(p) for p in _CREDENTIAL_QUERY_PARAMS) + r")=[^&\s]+",
    re.IGNORECASE,
)


# Key material embedded *inside* a larger text value, where the key name
# describes the container ("configuration file") rather than its contents, so
# key matching cannot help. Both forms are unambiguous enough to match on the
# value: a WireGuard peer config assigns `PrivateKey = <base64>`, and a PEM
# block is self-labelling. A `[Peer]` section can also carry a `PresharedKey`
# or `PSK` without any `PrivateKey` line, so those assignments count too.
# A blob that survived an extra round of JSON encoding has literal `\n` where
# its newlines were, which is why the escape is a line separator here as well.
# Deliberately narrow — the key name must be a line's first token, so prose
# mentioning the word is untouched.
_EMBEDDED_SECRET_RE = re.compile(
    r"(?:\A|[\r\n]|\\n)[ \t]*(?:PrivateKey|PresharedKey|PSK)[ \t]*=|-----BEGIN[A-Z ]*PRIVATE KEY-----",
    re.IGNORECASE,
)


def _has_embedded_secret(value: str) -> bool:
    """True when ``value`` is a text blob with key material inside it.

    Catches the case a key-name denylist structurally cannot: a whole config
    file returned under a benign-sounding key. See ``_EMBEDDED_SECRET_RE``.
    """
    return _EMBEDDED_SECRET_RE.search(value) is not None


def _is_credentialed_url(value: str) -> bool:
    """True when ``value`` is a URL carrying an inline credential.

    Targets credential-bearing URL values whose key name is generic (#442).
    Matches userinfo credentials (``scheme://user:pass@host`` or a bare
    ``scheme://token@host``), a credential-bearing query param, or an
    RTSP/RTSPS stream URL whose path segment is the bearer alias (#455).
    Ordinary URLs without a credential are left untouched.
    """
    if "://" not in value:
        return False
    if _URL_USERINFO_RE.match(value):
        return True
    if _RTSP_STREAM_RE.match(value):
        return True
    return _URL_CREDENTIAL_QUERY_RE.search(value) is not None


def _is_sensitive_key(key: str) -> bool:
    normalized = normalize_key(key)
    if normalized in _NORMALIZED_KEYS:
        return True
    if normalized.startswith("super") and (normalized.endswith("password") or normalized.endswith("url")):
        return True
    # A plural field holds the same material as its singular (`preshared_keys`,
    # `psks`, `passwords`), so test the depluralized tail too. Applied only to
    # the suffix check: depluralizing against the exact list would sweep in
    # container fields such as `sessions` that are not themselves credentials.
    candidates = (normalized, normalized[:-1]) if normalized.endswith("s") else (normalized,)
    return any(c.endswith(suffix) for c in candidates for suffix in _NORMALIZED_SUFFIXES)


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
    suffixes ``password`` / ``secret`` / ``authkey`` / ``token`` / ``passwd`` /
    ``privatekey`` / ``psk`` / ``sharedkey``.
    String values are redacted regardless of their key name when they are a
    URL carrying an inline credential (userinfo or a credential-bearing query
    param, e.g. an RTSPS ``?token=…`` stream descriptor), or a text blob with
    key material inside it (a WireGuard ``PrivateKey =`` / ``PresharedKey =``
    line or a PEM private key). Other non-container values pass through
    untouched. Input is not mutated.
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
    if isinstance(value, str) and (_is_credentialed_url(value) or _has_embedded_secret(value)):
        return REDACTED
    return value
