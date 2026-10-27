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

import json
import re
from typing import Any
from urllib.parse import unquote_plus

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
        # Returned as 32 hex chars on every `list_wlans` row; it is the shared
        # key APs use for IAPP roaming, and no read path needs its value.
        "x_iapp_key",
        # Legacy WEP key on old WLAN configs; too short a name for any suffix.
        "x_wep",
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
    # `x_openvpn_shared_secret_key` ends in `secretkey`, which neither the
    # `secret` nor the `sharedkey` suffix reaches.
    "secretkey",
    # Matches `iappKey`, which normalizes without the `x` of `x_iapp_key`.
    "iappkey",
    # `passphrase` alone is an exact match; `wpa_passphrase` and
    # `guestPassphrase` need the suffix.
    "passphrase",
    "wepkey",
    "md5key",
)

# A PSK token ahead of a value-ish tail (`psk_value`, `wpa_psk_key`). A bare
# token is not enough: `psk_mode` and `psk_enabled` are benign settings.
_PSK_VALUE_TAILS: tuple[str, ...] = ("key", "value", "hex")

_X_PREFIX_RE = re.compile(r"[xX][_-]|x(?=[A-Z])")


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
    "access_token",
    "pwd",
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
# key matching cannot help. Self-labelling forms, matched anywhere:
#   - WireGuard / hostapd style lines whose name has spaces or separators
#     (`Pre-Shared Key = ...`, `Private Key: ...`) — see the line rules below;
#   - the strongSwan ipsec.secrets form `<ids> : PSK "secret"` (or a `0x` hex
#     / `0s` base64 secret);
#   - an `Authorization: Bearer|Basic|Digest ...` or `Set-Cookie: k=v` header,
#     or a bare JWT;
#   - a scheme-relative `//user:pass@host` URL;
#   - a PEM private key, an OpenVPN static key, or an OpenVPN inline
#     `<key>` / `<tls-auth>` / `<tls-crypt>` / `<secret>` block.
# Every repeatable token is anchored or length-capped so no input can make a
# match restart over a long run, which would be quadratic.
# A blob that survived an extra round of JSON encoding has literal `\n` / `\t`
# where its whitespace was, so those escapes count as line breaks and indents.
_KEY_LINE_NAMES = r"(?:Private[-_ ]?Key|Pre[-_ ]?Shared[-_ ]?Key|PSK)"
_INDENT = r"(?:[ \t]|\\t)*"
_LINE_START = r"(?:\A|[\r\n]|\\n)"
_EMBEDDED_SECRET_RE = re.compile(
    rf"{_LINE_START}{_INDENT}{_KEY_LINE_NAMES}[ \t]*="
    rf"|(?:[\r\n]|\\n){_INDENT}{_KEY_LINE_NAMES}[ \t]*:"
    rf"|\A[ \t]*{_KEY_LINE_NAMES}[ \t]*:[ \t]*\S+\s*\Z"
    r"|:[ \t]*PSK[ \t]+(?:[\"']|0[xs])"
    r"|Authorization[ \t]*:[ \t]*(?:Bearer|Basic|Digest)[ \t]+\S"
    r"|-----BEGIN[A-Z0-9 ]*(?:PRIVATE KEY|STATIC KEY)"
    r"|<(?:key|tls-auth|tls-crypt|tls-crypt-v2|secret)>"
    r"|(?:Set-)?Cookie[ \t]*:[ \t]*[^\s=;]{1,128}="
    r"|(?<![A-Za-z0-9])eyJ[A-Za-z0-9_-]{8,256}\.eyJ[A-Za-z0-9_-]{8}"
    r"|(?<![:A-Za-z0-9])//[^/\s:@]+:[^/\s@]+@[^@/\s]",
    re.IGNORECASE,
)

# A line-leading `name = value` or `name: value` (INI, YAML, hostapd, shell),
# where the name is checked against the key rules. `=` counts on any line;
# `:` only after a line break or when the whole value is a single
# `name: token` pair, so a one-line message like `password: too short` stays
# readable. `rest` stops at a literal `\n` so escaped lines are seen too.
_LINE_KEY_RE = re.compile(
    rf"(?:(?P<start>\A)|[\r\n]|\\n){_INDENT}"
    r"(?P<name>[A-Za-z0-9_][A-Za-z0-9_.\[\]\-]{0,127})[^\S\r\n]*(?P<sep>[=:])"
    r"(?P<rest>(?:[^\r\n\\]|\\(?!n))*)"
)

# A tight `name=value` pair after whitespace, a separator (`;&,?|`), a quote or
# an opening bracket,
# as in `user=admin password=...` or `a=1;psk=...` (spaces around `=` read as
# prose mid-line, so only line-leading assignments allow them), and a
# `--name value` / `--name=value` command-line flag. Names go through the key rules.
_INLINE_ASSIGN_RE = re.compile(
    r"(?:(?<=[\s;&,?|\"'(\[{])|\A)(?:export\s+)?(?P<name>[A-Za-z0-9_][A-Za-z0-9_.\[\]\-]{0,127})=[^\s=]"
    r"|(?:(?<=[\s\"'(\[{,])|\A)--(?P<flag>[A-Za-z][A-Za-z0-9_\-]{0,63})(?:=|[^\S\r\n]+)[^\s\-]"
)

# An XML element whose tag is a credential name, such as `<password>x</password>`.
_XML_KEY_RE = re.compile(r"<(?P<name>[A-Za-z_][A-Za-z0-9_.\-]{0,63})>\s*[^<\s]")

# A quoted name followed by `:` and a string, object, array, number, bool or
# null value — a key
# inside JSON, a Python repr, or JSON escaped into another string — wherever
# it sits in the text. Requiring a value-shaped right-hand side keeps prose
# such as `Field "token": required` readable.
_QUOTED_KEY_RE = re.compile(
    r"""["']([A-Za-z0-9_][A-Za-z0-9_.\- ]{0,127})\\*["']\s*:\s*"""
    r"""\\*(?:["'{\[]|-?\d|(?:true|false|null|True|False|None)\b)"""
)

# A URL anywhere inside a larger text value, checked with ``_is_credentialed_url``.
# The scheme must start at a word boundary and is length-capped: an unbounded
# scheme lets every position of a long alphanumeric run start a match, which
# is quadratic.
_EMBEDDED_URL_RE = re.compile(r"(?<![A-Za-z])[A-Za-z][A-Za-z0-9+.\-]{0,31}://[^\s\"'\\]+")


def _is_sensitive_name(name: str) -> bool:
    """Apply the key rules to a name found in text; `vpn.ipsec_psk` checks `ipsec_psk`."""
    return _is_sensitive_key(name.rsplit(".", 1)[-1])


def _line_assigns_secret(match: re.Match[str], value: str) -> bool:
    if not _is_sensitive_name(match.group("name")):
        return False
    if match.group("sep") == "=" or match.group("start") is None:
        return True
    rest = match.group("rest").split()
    return match.end() == len(_strip_trailing_breaks(value)) and len(rest) == 1


def _strip_trailing_breaks(value: str) -> str:
    """Drop trailing line breaks, real or JSON-escaped (`\\n`, `\\r`).

    Walks back by index so a long run of breaks costs one pass, not one copy
    per break.
    """
    end = len(value)
    while end > 0:
        if value[end - 1] in "\r\n":
            end -= 1
        elif end >= 2 and value[end - 2] == "\\" and value[end - 1] in "nr":
            end -= 2
        else:
            break
    return value[:end]


def _inline_assigns_secret(match: re.Match[str]) -> bool:
    return _is_sensitive_name(match.group("name") or match.group("flag"))


def _scan_text(text: str) -> bool:
    # JSON may escape `/` as `\/` and `&` as `\u0026`, hiding a URL's shape.
    text = text.replace("\\/", "/").replace("\\u0026", "&")
    if _EMBEDDED_SECRET_RE.search(text) is not None:
        return True
    if any(_line_assigns_secret(m, text) for m in _LINE_KEY_RE.finditer(text)):
        return True
    if any(_inline_assigns_secret(m) for m in _INLINE_ASSIGN_RE.finditer(text)):
        return True
    if any(_is_sensitive_name(m.group(1)) for m in _QUOTED_KEY_RE.finditer(text)):
        return True
    if any(_is_sensitive_name(m.group("name")) for m in _XML_KEY_RE.finditer(text)):
        return True
    return any(_is_credentialed_url(m.group(0)) for m in _EMBEDDED_URL_RE.finditer(text))


# Enough for a doubly encoded payload; each pass is a full linear rescan.
_URL_DECODE_PASSES = 2


def _has_embedded_secret(value: str) -> bool:
    """True when ``value`` is a text blob with key material inside it.

    Catches the case a key-name denylist structurally cannot: a whole config
    file, or serialized JSON, returned under a benign-sounding key. The scans
    run in linear time, cover JSON with text around it, and cannot hit a
    recursion limit; up to two URL-decoded passes catch form-encoded payloads, and a
    best-effort JSON decode catches escapes the raw text hides.
    """
    if _scan_text(value):
        return True
    decoded = value
    for _ in range(_URL_DECODE_PASSES):
        if "%" not in decoded:
            break
        previous, decoded = decoded, unquote_plus(decoded)
        if decoded == previous:
            break
        if _scan_text(decoded):
            return True
    return _is_json_with_secret(value)


def _is_json_with_secret(value: str) -> bool:
    """True when ``value`` parses as JSON that carries a secret the scans missed.

    Decoding catches what the raw-text scans cannot see, such as a key name
    written with ``\\uXXXX`` escapes. Input too deeply nested to decode falls
    back to the scans' verdict instead of raising.
    """
    if not value.lstrip().startswith(("{", "[")):
        return False
    try:
        parsed = json.loads(value)
        return isinstance(parsed, (dict, list)) and redact_secrets(parsed) != parsed
    except (ValueError, RecursionError):
        return False


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
    if any(normalized.endswith(suffix) for suffix in _NORMALIZED_SUFFIXES):
        return True
    # UniFi prefixes its hidden secret fields with `x_` (`x_passphrase`,
    # `x_authkey`), so an `x_` / `x-` / camelCase `xFoo` field ending in `key`
    # is key material. This also catches public material such as
    # `x_public_key`; no UniFi `x_` field is known to carry one, so it fails
    # closed. A bare `xKey` (a coordinate-style name) has no qualifier and is
    # left alone.
    if _X_PREFIX_RE.match(key) and normalized.endswith("key") and normalized != "xkey":
        return True
    return "psk" in normalized and normalized.endswith(_PSK_VALUE_TAILS)


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
    ``privatekey`` / ``psk`` / ``sharedkey`` / ``secretkey`` / ``iappkey`` /
    ``passphrase`` / ``wepkey`` / ``md5key``, any ``x_`` / ``x-`` / camelCase
    ``xFoo`` field ending in ``key``, and a ``psk`` token ahead of a
    ``key`` / ``value`` / ``hex`` tail.
    String values are redacted regardless of their key name when they are a
    URL carrying an inline credential (userinfo or a credential-bearing query
    param, e.g. an RTSPS ``?token=…`` stream descriptor), or a text blob with
    key material inside it: a credential-named line or inline assignment
    (INI, YAML, hostapd, WireGuard, ``--flag``), an ipsec.secrets ``PSK``, an
    ``Authorization`` or ``Set-Cookie`` header, a JWT, a PEM private key or
    OpenVPN key block, an XML credential element, serialized JSON carrying a
    sensitive key, or an embedded credentialed URL. See
    ``_has_embedded_secret``. Other non-container values pass through
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
