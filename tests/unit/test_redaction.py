"""Unit tests for ``unifi_mcp._redaction.redact_secrets``."""

from __future__ import annotations

import pytest

from unifi_mcp._redaction import REDACTED, SENSITIVE_KEYS, redact_secrets


class TestRedactSecretsLeaf:
    def test_passes_through_non_containers(self):
        assert redact_secrets("plain") == "plain"
        assert redact_secrets(42) == 42
        assert redact_secrets(None) is None
        assert redact_secrets(True) is True

    def test_returns_redacted_for_sensitive_top_level_key(self):
        out = redact_secrets({"x_passphrase": "hunter2"})
        assert out == {"x_passphrase": REDACTED}

    def test_leaves_safe_keys_alone(self):
        payload = {"name": "guest", "enabled": True}
        assert redact_secrets(payload) == payload


class TestRedactSecretsRecursion:
    def test_redacts_nested_dict(self):
        payload = {"wlan": {"name": "g", "x_passphrase": "pw"}}
        assert redact_secrets(payload) == {"wlan": {"name": "g", "x_passphrase": REDACTED}}

    def test_redacts_inside_list_of_dicts(self):
        payload = {"data": [{"radius_secret": "s1"}, {"radius_secret": "s2"}]}
        out = redact_secrets(payload)
        assert out == {"data": [{"radius_secret": REDACTED}, {"radius_secret": REDACTED}]}

    def test_redacts_lists_of_lists(self):
        payload = [[{"token": "t"}], [{"name": "ok"}]]
        assert redact_secrets(payload) == [[{"token": REDACTED}], [{"name": "ok"}]]


class TestRedactSecretsKeyMatching:
    @pytest.mark.parametrize(
        "key",
        ["x_passphrase", "X_Passphrase", "X_PASSPHRASE", "Password", "PASSWORD"],
    )
    def test_case_insensitive_match(self, key):
        out = redact_secrets({key: "v"})
        assert out[key] == REDACTED

    @pytest.mark.parametrize(
        "key",
        [
            "super_smtp_password",
            "super_identity_password",
            "super_mgmt_url",
            "super_identity_url",
            "SUPER_SMTP_URL",
        ],
    )
    def test_super_wildcard_password_and_url(self, key):
        out = redact_secrets({key: "v"})
        assert out[key] == REDACTED

    def test_super_prefix_without_password_or_url_suffix_is_safe(self):
        # super_mgmt_key has no _password / _url suffix; not on exact denylist.
        out = redact_secrets({"super_name": "g"})
        assert out == {"super_name": "g"}

    def test_all_sensitive_keys_redacted(self):
        payload = {k: f"val-{k}" for k in SENSITIVE_KEYS}
        out = redact_secrets(payload)
        for k in SENSITIVE_KEYS:
            assert out[k] == REDACTED

    @pytest.mark.parametrize(
        "key",
        [
            "x_ssh_password",
            "x_authkey",
            "x_inform_authkey",
            "x_vrrpd_md5_key",
            "x_ddns_pwd",
            "client_secret",
        ],
    )
    def test_device_and_ddns_secrets_redacted(self, key):
        out = redact_secrets({key: "v"})
        assert out[key] == REDACTED

    @pytest.mark.parametrize(
        "key",
        ["clientSecret", "smtpPassword", "userToken", "sshAuthkey"],
    )
    def test_camelcase_suffix_secrets_redacted(self, key):
        """Suffix matching on lowercased key catches camelCase variants."""
        out = redact_secrets({key: "v"})
        assert out[key] == REDACTED


class TestRedactSecretsCookieAndAuthKeys:
    """#442 — cookie / authorization / session / credential key names redact."""

    @pytest.mark.parametrize(
        "key",
        [
            "cookie",
            "Cookie",
            "set_cookie",
            "set-cookie",
            "Set-Cookie",
            "authorization",
            "Authorization",
            "credential",
            "credentials",
            "session",
            "sessionid",
            "sessionId",
            "csrf",
            "CSRF",
            "jwt",
            "JWT",
        ],
    )
    def test_cookie_and_auth_keys_redacted(self, key):
        out = redact_secrets({key: "v"})
        assert out[key] == REDACTED

    def test_non_credential_session_lookalikes_pass_through(self):
        payload = {"sessionCount": 3, "lastSeen": "2026-06-24"}
        assert redact_secrets(payload) == payload


class TestRedactSecretsCredentialUrlValues:
    """#442 — URL values carrying a credential redact regardless of key name."""

    @pytest.mark.parametrize(
        "key",
        ["rtspsUrl", "url", "streamUrl", "href"],
    )
    def test_rtsps_url_with_token_query_redacted(self, key):
        out = redact_secrets({key: "rtsps://10.0.0.1:7441/abc?token=deadbeef"})
        assert out[key] == REDACTED

    def test_url_with_password_query_param_redacted(self):
        out = redact_secrets({"url": "https://host/stream?password=hunter2"})
        assert out["url"] == REDACTED

    def test_url_with_userinfo_credentials_redacted(self):
        out = redact_secrets({"endpoint": "rtsp://admin:s3cret@10.0.0.1:554/live"})
        assert out["endpoint"] == REDACTED

    def test_url_with_bare_userinfo_token_redacted(self):
        """#455 — a bearer token in the username position (no colon) redacts."""
        out = redact_secrets({"endpoint": "rtsp://deadbeeftoken@10.0.0.1:554/live"})
        assert out["endpoint"] == REDACTED

    @pytest.mark.parametrize(
        "key",
        ["rtspsUrl", "url", "streamUrl", "href", "high", "medium"],
    )
    def test_rtsps_path_alias_stream_redacted(self, key):
        """#455 — Protect rtsps-stream descriptors carry the credential in the
        path alias, not a ``?token=`` query param; redact by stream-URL shape."""
        out = redact_secrets({key: "rtsps://10.0.0.1:7441/aB3xY9?enableSrtp"})
        assert out[key] == REDACTED

    def test_rtsps_stream_descriptor_shape_redacted(self):
        """The real ``cameras/{id}/rtsps-stream`` shape: quality -> stream URL."""
        out = redact_secrets({"high": "rtsps://10.0.0.1:7441/aB3xY9", "medium": "rtsps://10.0.0.1:7441/cD4zW8"})
        assert out == {"high": REDACTED, "medium": REDACTED}

    def test_credentialed_url_in_nested_list_redacted(self):
        payload = {"streams": [{"quality": "high", "url": "rtsps://h/s?token=abc"}]}
        out = redact_secrets(payload)
        assert out["streams"][0]["url"] == REDACTED
        assert out["streams"][0]["quality"] == "high"

    def test_benign_key_query_param_passes_through(self):
        """#455 — ``?key=`` is not a credential param; ``?key=sortOrder`` stays."""
        out = redact_secrets({"url": "https://host/list?key=sortOrder"})
        assert out["url"] == "https://host/list?key=sortOrder"

    @pytest.mark.parametrize(
        "value",
        [
            "https://ui.com/docs",
            "rtsps://10.0.0.1:7441/",
            "https://host/path?q=search&page=2",
            "not a url at all",
        ],
    )
    def test_ordinary_urls_pass_through(self, value):
        out = redact_secrets({"url": value})
        assert out["url"] == value


class TestRedactSecretsEmbeddedKeyMaterial:
    """A whole config blob returned under a benign-sounding key name."""

    # Shape returned by unifi_network_list_networks for a `purpose: vpn-client`
    # network. The key reads as a filename, so no key-name rule catches it.
    WIREGUARD_CONF = (
        "[Interface]\n"
        "# Key for unifi_example\n"
        "PrivateKey = EXAMPLE0000000000000000000000000000000000000=\n"
        "Address = 10.2.0.2/32\n"
        "DNS = 10.2.0.1\n"
        "\n"
        "[Peer]\n"
        "PublicKey = EXAMPLE1111111111111111111111111111111111111=\n"
        "AllowedIPs = 0.0.0.0/0\n"
        "Endpoint = 203.0.113.10:51820"
    )

    def test_wireguard_config_blob_redacted_by_key_name(self):
        out = redact_secrets({"wireguard_client_configuration_file": self.WIREGUARD_CONF})
        assert out["wireguard_client_configuration_file"] == REDACTED

    def test_wireguard_config_blob_redacted_under_any_key_name(self):
        """The value-level rule is the backstop when the key name is unknown."""
        out = redact_secrets({"some_future_vpn_blob": self.WIREGUARD_CONF})
        assert out["some_future_vpn_blob"] == REDACTED

    def test_private_key_not_leaked_from_realistic_network_row(self):
        payload = {
            "data": [
                {
                    "name": "Example VPN",
                    "purpose": "vpn-client",
                    "wireguard_client_configuration_file": self.WIREGUARD_CONF,
                    "ip_subnet": "10.2.0.2/32",
                }
            ]
        }
        out = redact_secrets(payload)
        assert "EXAMPLE0000000000000000000000000000000000000=" not in str(out)
        assert out["data"][0]["name"] == "Example VPN"
        assert out["data"][0]["ip_subnet"] == "10.2.0.2/32"

    @pytest.mark.parametrize(
        "key",
        ["wireguard_private_key", "x_private_key", "privateKey", "peerPrivateKey"],
    )
    def test_qualified_private_key_names_redacted(self, key):
        """`private_key` was an exact match only; a qualifier used to slip past."""
        out = redact_secrets({key: "EXAMPLE0000000000000000000000000="})
        assert out[key] == REDACTED

    @pytest.mark.parametrize(
        "pem",
        [
            "-----BEGIN PRIVATE KEY-----\nMIIEvQ==\n-----END PRIVATE KEY-----",
            "-----BEGIN RSA PRIVATE KEY-----\nMIIEow==\n-----END RSA PRIVATE KEY-----",
            "-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNz\n-----END OPENSSH PRIVATE KEY-----",
        ],
    )
    def test_pem_private_key_blocks_redacted(self, pem):
        out = redact_secrets({"cert_blob": pem})
        assert out["cert_blob"] == REDACTED

    def test_public_key_only_config_passes_through(self):
        """A peer section with no PrivateKey is not credential-bearing."""
        value = "[Peer]\nPublicKey = EXAMPLE1111111111111\nAllowedIPs = 0.0.0.0/0"
        out = redact_secrets({"peer_config": value})
        assert out["peer_config"] == value

    @pytest.mark.parametrize(
        "value",
        [
            "The PrivateKey field is required for WireGuard peers.",
            "see docs for PrivateKey usage",
            "-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----",
        ],
    )
    def test_prose_and_public_material_pass_through(self, value):
        """`PrivateKey` must start a line; a certificate is not a private key."""
        out = redact_secrets({"notes": value})
        assert out["notes"] == value


class TestRedactSecretsProperties:
    def test_does_not_mutate_input(self):
        original = {"x_passphrase": "pw", "nested": {"token": "t"}}
        before = {"x_passphrase": "pw", "nested": {"token": "t"}}
        _ = redact_secrets(original)
        assert original == before

    def test_idempotent(self):
        payload = {"x_passphrase": "pw", "nested": {"token": "t", "name": "g"}}
        once = redact_secrets(payload)
        twice = redact_secrets(once)
        assert once == twice

    def test_realistic_wlan_list_payload(self):
        """Snapshot test against a realistic UniFi list_wlans shape."""
        payload = {
            "meta": {"rc": "ok"},
            "data": [
                {
                    "_id": "abc",
                    "name": "Home",
                    "enabled": True,
                    "security": "wpapsk",
                    "x_passphrase": "supersecret",
                    "wpa_mode": "wpa2",
                    "radius_secret": "radius-secret",
                    "guest_portal": {"x_password": "portal-pw"},
                },
                {
                    "_id": "def",
                    "name": "Guest",
                    "x_passphrase": "another",
                },
            ],
        }
        out = redact_secrets(payload)
        assert out["data"][0]["x_passphrase"] == REDACTED
        assert out["data"][0]["radius_secret"] == REDACTED
        assert out["data"][0]["guest_portal"]["x_password"] == REDACTED
        assert out["data"][1]["x_passphrase"] == REDACTED
        # Safe fields untouched
        assert out["data"][0]["name"] == "Home"
        assert out["data"][0]["security"] == "wpapsk"
        assert out["meta"] == {"rc": "ok"}
