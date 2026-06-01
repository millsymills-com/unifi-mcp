"""Tests for UniFi MCP configuration."""

import logging
import socket
import time

import pytest
from pydantic import ValidationError

from unifi_mcp.config import _DNS_LOOKUP_TIMEOUT_S, UniFiConfig, UniFiMode, _resolve_host, get_config
from unifi_mcp.errors import (
    UniFiAuthError,
    UniFiConnectionError,
    UniFiError,
    UniFiNotFoundError,
    UniFiRateLimitError,
    UniFiReadOnlyError,
    handle_client_error,
)

_PIN = "a" * 64  # 64 hex chars — valid canonical pin
_PIN_WITH_COLONS = ":".join(["aa"] * 32)  # 32 pairs of 'aa' joined by colons


class TestUniFiMode:
    def test_readonly_is_default(self):
        config = UniFiConfig(
            _env_file=None,
            unifi_network_api=None,
        )
        assert config.unifi_mode == UniFiMode.READONLY

    def test_readwrite_mode(self):
        config = UniFiConfig(
            _env_file=None,
            unifi_mode=UniFiMode.READWRITE,
        )
        assert config.unifi_mode == UniFiMode.READWRITE
        assert config.writes_enabled is True

    def test_readonly_mode_property(self):
        config = UniFiConfig(
            _env_file=None,
            unifi_mode=UniFiMode.READONLY,
        )
        assert config.writes_enabled is False

    def test_invalid_mode_raises_validation_error(self):
        with pytest.raises(ValidationError):
            UniFiConfig(_env_file=None, unifi_mode="invalid")


class TestAPIEnabled:
    def test_network_enabled_when_api_key_set(self):
        config = UniFiConfig(_env_file=None, unifi_network_api="test-key")
        assert config.network_enabled is True

    def test_network_disabled_when_no_api_key(self):
        config = UniFiConfig(_env_file=None, unifi_network_api=None)
        assert config.network_enabled is False

    def test_protect_enabled_when_api_key_set(self):
        config = UniFiConfig(_env_file=None, unifi_protect_api="test-key")
        assert config.protect_enabled is True

    def test_protect_disabled_when_no_api_key(self):
        config = UniFiConfig(_env_file=None, unifi_protect_api=None)
        assert config.protect_enabled is False

    def test_site_manager_enabled_when_api_key_set(self):
        config = UniFiConfig(_env_file=None, unifi_site_manager_api="test-key")
        assert config.site_manager_enabled is True

    def test_site_manager_disabled_when_no_api_key(self):
        config = UniFiConfig(_env_file=None, unifi_site_manager_api=None)
        assert config.site_manager_enabled is False


class TestDefaults:
    def test_default_network_host(self):
        config = UniFiConfig(_env_file=None)
        assert config.unifi_network_host == "192.168.1.1"

    def test_default_network_port(self):
        config = UniFiConfig(_env_file=None)
        assert config.unifi_network_port == 443

    def test_default_network_site(self):
        config = UniFiConfig(_env_file=None)
        assert config.unifi_network_site == "default"

    def test_protect_host_defaults_to_network_host(self):
        config = UniFiConfig(_env_file=None, unifi_network_host="10.0.0.1")
        assert config.unifi_protect_host == "10.0.0.1"

    def test_protect_host_independent_when_set(self):
        config = UniFiConfig(
            _env_file=None,
            unifi_network_host="10.0.0.1",
            unifi_protect_host="10.0.0.2",
        )
        assert config.unifi_protect_host == "10.0.0.2"

    def test_protect_host_default_logs_info_when_api_key_set(self, caplog):
        """When the Protect host default fires and Protect is enabled, emit an
        INFO log so the operator can catch the split-host misconfig.
        """
        with caplog.at_level(logging.INFO, logger="unifi_mcp.config"):
            config = UniFiConfig(
                _env_file=None,
                unifi_network_host="10.0.0.1",
                unifi_protect_api="k",
            )
        assert config.unifi_protect_host == "10.0.0.1"
        matching = [
            r for r in caplog.records if r.levelno == logging.INFO and "UNIFI_PROTECT_HOST not set" in r.getMessage()
        ]
        assert matching, f"expected INFO log about Protect host default; got {caplog.records!r}"
        assert "10.0.0.1" in matching[0].getMessage()

    def test_protect_host_default_silent_when_api_key_unset(self, caplog):
        """When Protect isn't configured, the host default must not log — the
        fallback is inconsequential because Protect tools won't register.
        """
        with caplog.at_level(logging.INFO, logger="unifi_mcp.config"):
            config = UniFiConfig(_env_file=None, unifi_network_host="10.0.0.1")
        assert config.unifi_protect_host == "10.0.0.1"
        assert not [r for r in caplog.records if "UNIFI_PROTECT_HOST not set" in r.getMessage()], (
            "host-default log should only fire when UNIFI_PROTECT_API is set"
        )

    def test_protect_host_default_silent_when_host_explicit(self, caplog):
        """When the operator set UNIFI_PROTECT_HOST explicitly, no default
        fires and no log is emitted even if the value happens to match the
        Network host.
        """
        with caplog.at_level(logging.INFO, logger="unifi_mcp.config"):
            UniFiConfig(
                _env_file=None,
                unifi_network_host="10.0.0.1",
                unifi_protect_host="10.0.0.1",
                unifi_protect_api="k",
            )
        assert not [r for r in caplog.records if "UNIFI_PROTECT_HOST not set" in r.getMessage()]

    def test_default_timeout(self):
        config = UniFiConfig(_env_file=None)
        assert config.unifi_request_timeout == 30

    def test_default_max_retries(self):
        config = UniFiConfig(_env_file=None)
        assert config.unifi_max_retries == 3

    def test_default_verify_ssl_false(self):
        config = UniFiConfig(_env_file=None)
        assert config.unifi_network_verify_ssl is False
        assert config.unifi_protect_verify_ssl is False


class TestBaseURLs:
    def test_network_base_url(self):
        config = UniFiConfig(_env_file=None, unifi_network_host="10.0.0.1", unifi_network_port=8443)
        assert config.network_base_url == "https://10.0.0.1:8443"

    def test_protect_base_url(self):
        config = UniFiConfig(_env_file=None, unifi_protect_host="10.0.0.2", unifi_protect_port=7443)
        assert config.protect_base_url == "https://10.0.0.2:7443"


class TestFieldConstraints:
    def test_network_port_zero_raises_validation_error(self):
        with pytest.raises(ValidationError, match="greater than or equal to 1"):
            UniFiConfig(_env_file=None, unifi_network_port=0)

    def test_network_port_above_max_raises_validation_error(self):
        with pytest.raises(ValidationError, match="less than or equal to 65535"):
            UniFiConfig(_env_file=None, unifi_network_port=65536)

    def test_protect_port_zero_raises_validation_error(self):
        with pytest.raises(ValidationError, match="greater than or equal to 1"):
            UniFiConfig(_env_file=None, unifi_protect_port=0)

    def test_request_timeout_zero_raises_validation_error(self):
        with pytest.raises(ValidationError, match="greater than 0"):
            UniFiConfig(_env_file=None, unifi_request_timeout=0)

    def test_request_timeout_negative_raises_validation_error(self):
        with pytest.raises(ValidationError, match="greater than 0"):
            UniFiConfig(_env_file=None, unifi_request_timeout=-5)

    def test_max_retries_negative_raises_validation_error(self):
        with pytest.raises(ValidationError, match="greater than or equal to 0"):
            UniFiConfig(_env_file=None, unifi_max_retries=-1)

    def test_max_retries_zero_accepted(self):
        config = UniFiConfig(_env_file=None, unifi_max_retries=0)
        assert config.unifi_max_retries == 0


class TestHandleClientError:
    def test_auth_error_mapping(self):
        with pytest.raises(Exception, match="Authentication failed"):
            handle_client_error(UniFiAuthError("Invalid API key", status_code=401))

    def test_not_found_error_mapping(self):
        with pytest.raises(Exception, match="Resource not found"):
            handle_client_error(UniFiNotFoundError("Device xyz not found", status_code=404))

    def test_rate_limit_error_mapping(self):
        with pytest.raises(Exception, match="Rate limit exceeded"):
            handle_client_error(UniFiRateLimitError("Too many requests", status_code=429))

    def test_connection_error_mapping(self):
        with pytest.raises(Exception, match="Connection failed"):
            handle_client_error(UniFiConnectionError("Timeout"))

    def test_readonly_error_mapping(self):
        with pytest.raises(Exception, match="Write operation blocked"):
            handle_client_error(UniFiReadOnlyError("Cannot create WLAN"))

    def test_generic_unifi_error_mapping(self):
        with pytest.raises(Exception, match="UniFi API error"):
            handle_client_error(UniFiError("Something went wrong", status_code=500))

    def test_unexpected_error_mapping(self):
        with pytest.raises(Exception, match="Unexpected internal error"):
            handle_client_error(RuntimeError("Boom"))

    def test_cancelled_error_is_reraised_not_wrapped(self):
        """asyncio.CancelledError must propagate so FastMCP can honor
        cancellation. Wrapping it as ToolError would turn a cancel into
        a phantom tool failure.
        """
        import asyncio

        cancel = asyncio.CancelledError()
        with pytest.raises(asyncio.CancelledError) as exc_info:
            handle_client_error(cancel)
        # The exact exception object should propagate, not a new one.
        assert exc_info.value is cancel

    def test_keyboard_interrupt_is_reraised_not_wrapped(self):
        """KeyboardInterrupt must propagate so SIGINT returns control to
        the operator. Wrapping it as ToolError would swallow Ctrl-C mid-call.
        """
        kbd = KeyboardInterrupt()
        with pytest.raises(KeyboardInterrupt) as exc_info:
            handle_client_error(kbd)
        assert exc_info.value is kbd

    def test_system_exit_is_reraised_not_wrapped(self):
        """SystemExit must propagate so sys.exit() reaches the interpreter
        and terminates the process.
        """
        exit_exc = SystemExit(2)
        with pytest.raises(SystemExit) as exc_info:
            handle_client_error(exit_exc)
        assert exc_info.value is exit_exc
        assert exc_info.value.code == 2

    def test_generator_exit_is_reraised_not_wrapped(self):
        """GeneratorExit must propagate so async generator cleanup completes
        correctly. Catching it would corrupt coroutine state.
        """
        gen_exit = GeneratorExit()
        with pytest.raises(GeneratorExit) as exc_info:
            handle_client_error(gen_exit)
        assert exc_info.value is gen_exit

    def test_auth_error_message_includes_status_code_prefix(self):
        """Agents branch on HTTP status — surface it explicitly in the
        ToolError so they don't have to regex the inner exception.
        """
        with pytest.raises(Exception, match=r"\[HTTP 401\] Authentication failed"):
            handle_client_error(UniFiAuthError("Invalid API key", status_code=401))

    def test_not_found_error_message_includes_status_code_prefix(self):
        with pytest.raises(Exception, match=r"\[HTTP 404\] Resource not found"):
            handle_client_error(UniFiNotFoundError("Device xyz not found", status_code=404))

    def test_rate_limit_error_message_includes_status_code_prefix(self):
        with pytest.raises(Exception, match=r"\[HTTP 429\] Rate limit exceeded"):
            handle_client_error(UniFiRateLimitError("Slow down", status_code=429))

    def test_server_error_message_includes_status_code_prefix(self):
        from unifi_mcp.errors import UniFiServerError

        with pytest.raises(Exception, match=r"\[HTTP 503\] UniFi server error"):
            handle_client_error(UniFiServerError("Service Unavailable", status_code=503))

    def test_connection_error_message_omits_status_code_when_none(self):
        """Transport-layer failures don't have a status code; no prefix."""
        with pytest.raises(Exception, match="Connection failed") as exc_info:
            handle_client_error(UniFiConnectionError("Host unreachable"))
        msg = str(exc_info.value)
        assert msg.startswith("Connection failed"), f"expected no [HTTP…] prefix when status is None; got {msg!r}"

    def test_unexpected_error_has_no_status_code_prefix(self):
        """Non-UniFi exceptions don't have status_code; no prefix."""
        with pytest.raises(Exception, match="Unexpected internal error") as exc_info:
            handle_client_error(RuntimeError("boom"))
        assert "[HTTP" not in str(exc_info.value)


class TestCertFingerprintValidation:
    """Item 3 of #149: fingerprint format is validated at load time."""

    def test_accepts_canonical_64_hex(self):
        config = UniFiConfig(_env_file=None, unifi_network_cert_fingerprint=_PIN)
        assert config.unifi_network_cert_fingerprint == _PIN

    def test_accepts_colon_separated_openssl_form(self):
        config = UniFiConfig(_env_file=None, unifi_protect_cert_fingerprint=_PIN_WITH_COLONS)
        # Canonical form: colons stripped, lowercase.
        assert config.unifi_protect_cert_fingerprint == "aa" * 32

    def test_accepts_uppercase_hex(self):
        config = UniFiConfig(_env_file=None, unifi_network_cert_fingerprint=_PIN.upper())
        assert config.unifi_network_cert_fingerprint == _PIN

    def test_empty_string_normalizes_to_none(self):
        """Unset env vars come through as empty strings; treat as None, not
        as an invalid fingerprint."""
        config = UniFiConfig(_env_file=None, unifi_network_cert_fingerprint="")
        assert config.unifi_network_cert_fingerprint is None

    def test_rejects_too_short(self):
        with pytest.raises(ValidationError, match="64 hex chars"):
            UniFiConfig(_env_file=None, unifi_network_cert_fingerprint="aa")

    def test_rejects_non_hex(self):
        bad = "z" * 64
        with pytest.raises(ValidationError, match="64 hex chars"):
            UniFiConfig(_env_file=None, unifi_protect_cert_fingerprint=bad)

    def test_rejects_wrong_length_with_colons(self):
        with pytest.raises(ValidationError, match="64 hex chars"):
            UniFiConfig(_env_file=None, unifi_network_cert_fingerprint="aa:bb:cc")

    def test_rejects_non_string_non_none_value(self):
        """A non-string, non-None value (e.g. an int) is rejected outright.

        The validator runs in ``mode="before"`` so a raw int reaches it without
        coercion; it must not be treated as an unset/blank value or normalized.
        """
        with pytest.raises(ValidationError, match="fingerprint must be a string"):
            UniFiConfig(_env_file=None, unifi_network_cert_fingerprint=12345)


class TestVerifySSLAudit:
    """Items 1+2 of #149: warn on verify_ssl=False with an API key set."""

    def test_silent_when_verify_ssl_true(self, caplog):
        with caplog.at_level(logging.WARNING, logger="unifi_mcp.config"):
            UniFiConfig(
                _env_file=None,
                unifi_network_host="10.0.0.1",
                unifi_network_api="k",
                unifi_network_verify_ssl=True,
            )
        assert not [r for r in caplog.records if "verify_ssl=False" in r.getMessage()]

    def test_silent_when_no_api_key(self, caplog):
        """Without an API key the service won't register tools, so the WARN
        would be noise."""
        with caplog.at_level(logging.WARNING, logger="unifi_mcp.config"):
            UniFiConfig(
                _env_file=None,
                unifi_network_host="10.0.0.1",
                unifi_network_verify_ssl=False,
            )
        assert not [r for r in caplog.records if "verify_ssl=False" in r.getMessage()]

    def test_unconditional_warn_on_private_host(self, caplog, monkeypatch):
        """Item 1: private host still gets the unconditional WARN, but not
        the public-IP MITM WARN."""
        monkeypatch.setattr(socket, "gethostbyname", lambda _h: "10.0.0.1")
        with caplog.at_level(logging.WARNING, logger="unifi_mcp.config"):
            UniFiConfig(
                _env_file=None,
                unifi_network_host="10.0.0.1",
                unifi_network_api="k",
            )
        messages = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
        unconditional = [m for m in messages if "verify_ssl=False for Network" in m]
        public = [m for m in messages if "non-private host" in m]
        assert len(unconditional) == 1, messages
        assert public == [], messages
        assert "10.0.0.1" in unconditional[0]

    def test_both_warns_on_public_ip(self, caplog, monkeypatch):
        """Item 2: a non-RFC1918 resolution triggers the additional MITM WARN."""
        monkeypatch.setattr(socket, "gethostbyname", lambda _h: "8.8.8.8")
        with caplog.at_level(logging.WARNING, logger="unifi_mcp.config"):
            UniFiConfig(
                _env_file=None,
                unifi_network_host="controller.example.com",
                unifi_network_api="k",
            )
        messages = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
        unconditional = [m for m in messages if "verify_ssl=False for Network" in m]
        public = [m for m in messages if "non-private host" in m and "MITM" in m]
        assert len(unconditional) == 1, messages
        assert len(public) == 1, messages
        assert "8.8.8.8" in public[0]
        assert "controller.example.com" in public[0]

    def test_dns_failure_soft_warns(self, caplog, monkeypatch):
        """DNS failure must not crash startup; emit a soft WARN that the
        non-private check was skipped."""

        def boom(_h: str) -> str:
            raise socket.gaierror("nodename nor servname provided")

        monkeypatch.setattr(socket, "gethostbyname", boom)
        with caplog.at_level(logging.WARNING, logger="unifi_mcp.config"):
            UniFiConfig(
                _env_file=None,
                unifi_network_host="does-not-resolve.invalid",
                unifi_network_api="k",
            )
        messages = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
        assert any("verify_ssl=False for Network" in m for m in messages), messages
        assert any("could not resolve" in m for m in messages), messages
        # The public-IP WARN must NOT fire when resolution failed.
        assert not any("non-private host" in m and "MITM" in m for m in messages), messages

    def test_loopback_treated_as_safe(self, caplog, monkeypatch):
        monkeypatch.setattr(socket, "gethostbyname", lambda _h: "127.0.0.1")
        with caplog.at_level(logging.WARNING, logger="unifi_mcp.config"):
            UniFiConfig(
                _env_file=None,
                unifi_network_host="127.0.0.1",
                unifi_network_api="k",
            )
        messages = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
        assert not any("non-private host" in m for m in messages), messages

    def test_protect_branch_uses_protect_host(self, caplog, monkeypatch):
        """Protect host should be evaluated separately and surface 'Protect'
        in the WARN."""
        monkeypatch.setattr(socket, "gethostbyname", lambda _h: "8.8.8.8")
        with caplog.at_level(logging.WARNING, logger="unifi_mcp.config"):
            UniFiConfig(
                _env_file=None,
                unifi_network_host="10.0.0.1",
                unifi_protect_host="protect.example.com",
                unifi_protect_api="k",
                unifi_network_api=None,
            )
        messages = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
        assert any("verify_ssl=False for Protect" in m for m in messages), messages
        assert any("for Protect" in m and "non-private host" in m for m in messages), messages

    def test_dns_timeout_does_not_mutate_socket_default(self, monkeypatch):
        """#191: DNS bound via thread, never via socket.setdefaulttimeout.

        A slow resolver must raise OSError without touching
        ``socket.getdefaulttimeout()`` (process-global state).
        """

        def slow(_h: str) -> str:
            time.sleep(_DNS_LOOKUP_TIMEOUT_S + 1.0)
            return "1.2.3.4"

        monkeypatch.setattr(socket, "gethostbyname", slow)
        before = socket.getdefaulttimeout()
        with pytest.raises(OSError, match="exceeded"):
            _resolve_host("slow.example.invalid")
        assert socket.getdefaulttimeout() == before

    def test_get_config_caches_singleton_and_audits_once(self, caplog, monkeypatch):
        """#190: ``get_config`` returns the same instance and the TLS audit
        WARN fires exactly once per process, not once per ``UniFiConfig()``
        call.
        """
        monkeypatch.setattr(socket, "gethostbyname", lambda _h: "10.0.0.1")
        monkeypatch.setenv("UNIFI_NETWORK_HOST", "10.0.0.1")
        monkeypatch.setenv("UNIFI_NETWORK_API", "k")
        get_config.cache_clear()
        try:
            with caplog.at_level(logging.WARNING, logger="unifi_mcp.config"):
                first = get_config()
                second = get_config()
            assert first is second
            warns = [r.getMessage() for r in caplog.records if "verify_ssl=False for Network" in r.getMessage()]
            assert len(warns) == 1, warns
        finally:
            get_config.cache_clear()

    def test_pin_suppresses_verify_ssl_warns(self, caplog, monkeypatch):
        """Item 3: pinning provides identity, so the verify_ssl WARNs should
        not fire even on a non-private host."""
        monkeypatch.setattr(socket, "gethostbyname", lambda _h: "8.8.8.8")
        with caplog.at_level(logging.WARNING, logger="unifi_mcp.config"):
            UniFiConfig(
                _env_file=None,
                unifi_network_host="controller.example.com",
                unifi_network_api="k",
                unifi_network_cert_fingerprint=_PIN,
            )
        messages = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
        assert not [m for m in messages if "verify_ssl=False" in m], messages
        assert not [m for m in messages if "non-private host" in m], messages
