"""Tests for the server lifespan and _register_client helper.

Covers the async-generator boot path in ``unifi_mcp.server`` that previous
tests couldn't reach. Drives ``server_lifespan._fn`` directly (bypassing
the FastMCP Lifespan wrapper) and patches the lazy-imported client classes.
"""

from __future__ import annotations

import os
from contextlib import aclosing
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from unifi_mcp.errors import UniFiAuthError, UniFiConnectionError, UniFiPortalHtmlError
from unifi_mcp.server import ServerContext, _register_client, create_server, server_lifespan


def _as_config():
    """Build a real UniFiConfig with all three APIs enabled."""
    from unifi_mcp.config import UniFiConfig, UniFiMode

    return UniFiConfig(
        _env_file=None,
        unifi_mode=UniFiMode.READONLY,
        unifi_network_api="net",
        unifi_protect_api="prot",
        unifi_site_manager_api="sm",
    )


# ── _register_client branch coverage ──────────────────────────────────────


class TestRegisterClient:
    async def test_registers_on_success(self):
        context = ServerContext(config=_as_config())
        client = AsyncMock()
        client.validate_connection.return_value = True
        await _register_client(context, "network", client)
        assert "network" in context.clients
        client.close.assert_not_awaited()

    async def test_skips_when_validation_returns_false(self):
        context = ServerContext(config=_as_config())
        client = AsyncMock()
        client.validate_connection.return_value = False
        await _register_client(context, "network", client)
        assert "network" not in context.clients
        client.close.assert_awaited_once()

    async def test_closes_on_unifi_error(self):
        context = ServerContext(config=_as_config())
        client = AsyncMock()
        client.validate_connection.side_effect = UniFiAuthError("bad", status_code=401)
        await _register_client(context, "protect", client)
        assert "protect" not in context.clients
        client.close.assert_awaited_once()

    async def test_closes_on_http_error(self):
        context = ServerContext(config=_as_config())
        client = AsyncMock()
        client.validate_connection.side_effect = httpx.ConnectError("refused")
        await _register_client(context, "site_manager", client)
        assert "site_manager" not in context.clients
        client.close.assert_awaited_once()


# ── server_lifespan full boot path ────────────────────────────────────────


def _setup_env_for_lifespan(monkeypatch, tmp_path=None):
    """Ensure UniFiConfig() in the lifespan reads a valid full-stack config.

    ``tmp_path`` (optional): when supplied, ``monkeypatch.chdir(tmp_path)``
    isolates the test from any ``.env`` in cwd. Tests that explicitly set
    every API key they care about can omit it; tests that *subtract* keys
    from the config must pass it, otherwise a contributor's real ``.env``
    at repo root leaks the "absent" key back in.
    """
    monkeypatch.setenv("UNIFI_MODE", "readonly")
    monkeypatch.setenv("UNIFI_NETWORK_API", "net-k")
    monkeypatch.setenv("UNIFI_PROTECT_API", "prot-k")
    monkeypatch.setenv("UNIFI_SITE_MANAGER_API", "sm-k")
    # Ensure no stray .env is read.
    for var in ("UNIFI_PROTECT_HOST", "UNIFI_NETWORK_HOST"):
        monkeypatch.delenv(var, raising=False)
    if tmp_path is not None:
        monkeypatch.chdir(tmp_path)


def _make_validating_client(valid: bool = True) -> AsyncMock:
    c = AsyncMock()
    c.validate_connection.return_value = valid
    return c


class TestServerLifespan:
    async def test_yields_context_with_all_three_clients(self, monkeypatch):
        _setup_env_for_lifespan(monkeypatch)

        net_client = _make_validating_client()
        prot_client = _make_validating_client()
        sm_client = _make_validating_client()

        with (
            patch("unifi_mcp.clients.network.NetworkClient", return_value=net_client),
            patch("unifi_mcp.clients.protect.ProtectClient", return_value=prot_client),
            patch("unifi_mcp.clients.site_manager.SiteManagerClient", return_value=sm_client),
        ):
            gen = server_lifespan._fn(None)
            async with aclosing(gen):
                context = await gen.__anext__()
                assert set(context.clients.keys()) == {"network", "protect", "site_manager"}
                # Drive the generator to completion to exercise the close loop.
                with pytest.raises(StopAsyncIteration):
                    await gen.__anext__()

        # Close loop ran exactly once per registered client.
        net_client.close.assert_awaited_once()
        prot_client.close.assert_awaited_once()
        sm_client.close.assert_awaited_once()

    async def test_skips_disabled_apis(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)  # isolate from any .env leaking the "absent" keys
        monkeypatch.setenv("UNIFI_MODE", "readonly")
        monkeypatch.setenv("UNIFI_NETWORK_API", "k")
        # Protect and Site Manager stay unset.
        monkeypatch.delenv("UNIFI_PROTECT_API", raising=False)
        monkeypatch.delenv("UNIFI_SITE_MANAGER_API", raising=False)

        net_client = _make_validating_client()
        with patch("unifi_mcp.clients.network.NetworkClient", return_value=net_client):
            gen = server_lifespan._fn(None)
            async with aclosing(gen):
                context = await gen.__anext__()
                assert set(context.clients.keys()) == {"network"}
                with pytest.raises(StopAsyncIteration):
                    await gen.__anext__()

    async def test_handles_no_configured_apis(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)  # isolate from any .env leaking API keys
        monkeypatch.setenv("UNIFI_MODE", "readonly")
        for var in ("UNIFI_NETWORK_API", "UNIFI_PROTECT_API", "UNIFI_SITE_MANAGER_API"):
            monkeypatch.delenv(var, raising=False)

        gen = server_lifespan._fn(None)
        async with aclosing(gen):
            context = await gen.__anext__()
            assert context.clients == {}
            with pytest.raises(StopAsyncIteration):
                await gen.__anext__()

    async def test_validation_failure_keeps_other_apis(self, monkeypatch):
        """One API failing validation shouldn't take the others down."""
        _setup_env_for_lifespan(monkeypatch)

        failing_net = AsyncMock()
        failing_net.validate_connection.side_effect = UniFiConnectionError("unreachable")

        good_prot = _make_validating_client()
        good_sm = _make_validating_client()

        with (
            patch("unifi_mcp.clients.network.NetworkClient", return_value=failing_net),
            patch("unifi_mcp.clients.protect.ProtectClient", return_value=good_prot),
            patch("unifi_mcp.clients.site_manager.SiteManagerClient", return_value=good_sm),
        ):
            gen = server_lifespan._fn(None)
            async with aclosing(gen):
                context = await gen.__anext__()
                assert set(context.clients.keys()) == {"protect", "site_manager"}
                with pytest.raises(StopAsyncIteration):
                    await gen.__anext__()

        # failing_net was closed via the exception branch in _register_client.
        failing_net.close.assert_awaited_once()

    async def test_close_error_does_not_bubble(self, monkeypatch, tmp_path):
        """A close() raising OSError during shutdown must not propagate."""
        _setup_env_for_lifespan(monkeypatch, tmp_path)  # isolate from .env leaking disabled keys
        monkeypatch.delenv("UNIFI_PROTECT_API", raising=False)
        monkeypatch.delenv("UNIFI_SITE_MANAGER_API", raising=False)

        net_client = _make_validating_client()
        net_client.close.side_effect = OSError("socket already closed")

        with patch("unifi_mcp.clients.network.NetworkClient", return_value=net_client):
            gen = server_lifespan._fn(None)
            async with aclosing(gen):
                await gen.__anext__()
                with pytest.raises(StopAsyncIteration):
                    await gen.__anext__()
        # No exception escaped.

    async def test_shutdown_close_loop_isolates_failures_across_clients(self, monkeypatch):
        """A failing close() on one client must not skip close() on the others.

        Before this PR the close loop caught only (OSError, httpx.HTTPError);
        a RuntimeError from one client's close would abort the loop and leak
        the remaining clients' sockets.
        """
        _setup_env_for_lifespan(monkeypatch)

        net_client = _make_validating_client()
        prot_client = _make_validating_client()
        sm_client = _make_validating_client()
        # Pick the middle one to fail; the loop must still close sm_client.
        prot_client.close.side_effect = RuntimeError("unexpected close failure")

        with (
            patch("unifi_mcp.clients.network.NetworkClient", return_value=net_client),
            patch("unifi_mcp.clients.protect.ProtectClient", return_value=prot_client),
            patch("unifi_mcp.clients.site_manager.SiteManagerClient", return_value=sm_client),
        ):
            gen = server_lifespan._fn(None)
            async with aclosing(gen):
                await gen.__anext__()
                with pytest.raises(StopAsyncIteration):
                    await gen.__anext__()

        net_client.close.assert_awaited_once()
        prot_client.close.assert_awaited_once()  # failed, but was called
        sm_client.close.assert_awaited_once()  # would be skipped pre-fix

    async def test_validation_failure_warn_includes_exception_class(self, monkeypatch, caplog):
        """When validate_connection raises, the lifespan's 'tools disabled'
        WARN must name the exception class and message so operators can
        distinguish auth failures from unreachability from path mismatches
        (#104).
        """
        import logging

        _setup_env_for_lifespan(monkeypatch)

        failing_net = AsyncMock()
        failing_net.validate_connection.side_effect = UniFiAuthError("HTTP 401: bad key", status_code=401)

        good_prot = _make_validating_client()
        good_sm = _make_validating_client()

        with (
            patch("unifi_mcp.clients.network.NetworkClient", return_value=failing_net),
            patch("unifi_mcp.clients.protect.ProtectClient", return_value=good_prot),
            patch("unifi_mcp.clients.site_manager.SiteManagerClient", return_value=good_sm),
            caplog.at_level(logging.WARNING, logger="unifi_mcp.server"),
        ):
            gen = server_lifespan._fn(None)
            async with aclosing(gen):
                await gen.__anext__()
                with pytest.raises(StopAsyncIteration):
                    await gen.__anext__()

        disabled_warns = [
            r for r in caplog.records if "network tools disabled" in r.getMessage() and r.levelno == logging.WARNING
        ]
        assert disabled_warns, f"expected 'network tools disabled' WARN; got {[r.getMessage() for r in caplog.records]}"
        msg = disabled_warns[0].getMessage()
        assert "UniFiAuthError" in msg, f"expected exception class in WARN; got {msg!r}"
        assert "HTTP 401" in msg, f"expected exception message text in WARN; got {msg!r}"

    async def test_html_portal_failure_warn_is_actionable_not_contradictory(self, monkeypatch, caplog):
        """A host returning the UniFi OS portal HTML on a JSON proxy path fails
        validation with ``UniFiPortalHtmlError`` (typically HTTP 200). The WARN
        must name host/path/key-scope as the likely cause instead of the
        self-contradictory bare ``UniFiAuthError (HTTP 200)`` (#382), and must
        keep the reflected HTML body out of the WARN sink (#148).
        """
        import logging

        _setup_env_for_lifespan(monkeypatch)

        reflected_body = "<!doctype html><title>UniFi OS</title>"
        failing_prot = AsyncMock()
        failing_prot.validate_connection.side_effect = UniFiPortalHtmlError(reflected_body, status_code=200)

        good_net = _make_validating_client()
        good_sm = _make_validating_client()

        with (
            patch("unifi_mcp.clients.network.NetworkClient", return_value=good_net),
            patch("unifi_mcp.clients.protect.ProtectClient", return_value=failing_prot),
            patch("unifi_mcp.clients.site_manager.SiteManagerClient", return_value=good_sm),
            caplog.at_level(logging.DEBUG, logger="unifi_mcp.server"),
        ):
            gen = server_lifespan._fn(None)
            async with aclosing(gen):
                await gen.__anext__()
                with pytest.raises(StopAsyncIteration):
                    await gen.__anext__()

        disabled_warns = [
            r for r in caplog.records if "protect tools disabled" in r.getMessage() and r.levelno == logging.WARNING
        ]
        assert disabled_warns, "expected 'protect tools disabled' WARN"
        msg = disabled_warns[0].getMessage()
        assert "UniFiPortalHtmlError" in msg, f"expected distinct portal-HTML class in WARN; got {msg!r}"
        assert "host" in msg.lower(), f"expected actionable host guidance in WARN; got {msg!r}"
        assert "API-key scope" in msg, f"expected actionable key-scope guidance in WARN; got {msg!r}"
        assert reflected_body not in msg, f"reflected HTML body must not reach the WARN sink; got {msg!r}"
        debug_records = [r for r in caplog.records if r.levelno == logging.DEBUG and r.exc_info]
        assert any(reflected_body in str(r.exc_info[1]) for r in debug_records if r.exc_info), (
            "expected DEBUG log carrying the full exception (with reflected body) via exc_info"
        )

    async def test_validation_false_return_warn_includes_stashed_exception(self, monkeypatch, caplog):
        """When validate_connection returns False after swallowing the
        exception internally (the default BaseUniFiClient pattern), the
        lifespan recovers the exception from _last_validation_error and
        still surfaces the class in the WARN.
        """
        import logging

        from unifi_mcp.errors import UniFiConnectionError

        _setup_env_for_lifespan(monkeypatch)

        # Stub a client that returned False from validate AND stashed an exc.
        failing_prot = AsyncMock()
        failing_prot.validate_connection.return_value = False
        failing_prot._last_validation_error = UniFiConnectionError("host unreachable")

        good_net = _make_validating_client()
        good_sm = _make_validating_client()

        with (
            patch("unifi_mcp.clients.network.NetworkClient", return_value=good_net),
            patch("unifi_mcp.clients.protect.ProtectClient", return_value=failing_prot),
            patch("unifi_mcp.clients.site_manager.SiteManagerClient", return_value=good_sm),
            caplog.at_level(logging.DEBUG, logger="unifi_mcp.server"),
        ):
            gen = server_lifespan._fn(None)
            async with aclosing(gen):
                await gen.__anext__()
                with pytest.raises(StopAsyncIteration):
                    await gen.__anext__()

        disabled_warns = [
            r for r in caplog.records if "protect tools disabled" in r.getMessage() and r.levelno == logging.WARNING
        ]
        assert disabled_warns, "expected 'protect tools disabled' WARN"
        msg = disabled_warns[0].getMessage()
        # Post-#148: WARN carries the exception class and status code only.
        # The full message ships to DEBUG via exc_info so reflected bodies
        # never reach a WARN-level sink.
        assert "UniFiConnectionError" in msg, f"expected stashed exception class in WARN; got {msg!r}"
        assert "host unreachable" not in msg, f"WARN must not echo stashed exception text; got {msg!r}"
        debug_records = [r for r in caplog.records if r.levelno == logging.DEBUG and r.exc_info]
        assert any("host unreachable" in str(r.exc_info[1]) for r in debug_records if r.exc_info), (
            "expected DEBUG log with full exception via exc_info"
        )

    async def test_validation_false_return_without_stashed_exception_falls_back(self, monkeypatch, caplog):
        """If a client returns False but stashed nothing (e.g. pre-#104
        client or a legitimate 'not reachable, no error captured' state),
        the lifespan still emits the generic WARN — never silently skips.
        """
        import logging

        _setup_env_for_lifespan(monkeypatch)

        failing_prot = AsyncMock()
        failing_prot.validate_connection.return_value = False
        # No _last_validation_error attribute at all (AsyncMock auto-creates
        # attrs, so explicitly None).
        failing_prot._last_validation_error = None

        good_net = _make_validating_client()
        good_sm = _make_validating_client()

        with (
            patch("unifi_mcp.clients.network.NetworkClient", return_value=good_net),
            patch("unifi_mcp.clients.protect.ProtectClient", return_value=failing_prot),
            patch("unifi_mcp.clients.site_manager.SiteManagerClient", return_value=good_sm),
            caplog.at_level(logging.WARNING, logger="unifi_mcp.server"),
        ):
            gen = server_lifespan._fn(None)
            async with aclosing(gen):
                await gen.__anext__()
                with pytest.raises(StopAsyncIteration):
                    await gen.__anext__()

        disabled_warns = [r for r in caplog.records if "protect tools disabled" in r.getMessage()]
        assert disabled_warns
        msg = disabled_warns[0].getMessage()
        assert "backend is unreachable" in msg, f"expected fallback WARN shape; got {msg!r}"

    async def test_register_client_close_failure_does_not_mask_original_error(self, monkeypatch, caplog):
        """If validate_connection raises UniFiAuthError and then close() itself
        raises, the original auth failure context must still reach the logs —
        and the lifespan must keep running (not crash on the close failure).
        """
        _setup_env_for_lifespan(monkeypatch)
        monkeypatch.delenv("UNIFI_PROTECT_API", raising=False)
        monkeypatch.delenv("UNIFI_SITE_MANAGER_API", raising=False)

        failing_net = AsyncMock()
        failing_net.validate_connection.side_effect = UniFiAuthError("bad key", status_code=401)
        failing_net.close.side_effect = RuntimeError("socket reset during close")

        import logging

        with (
            patch("unifi_mcp.clients.network.NetworkClient", return_value=failing_net),
            caplog.at_level(logging.WARNING, logger="unifi_mcp.server"),
        ):
            gen = server_lifespan._fn(None)
            async with aclosing(gen):
                context = await gen.__anext__()
                assert "network" not in context.clients
                with pytest.raises(StopAsyncIteration):
                    await gen.__anext__()

        # The original auth error was logged at exception-level.
        auth_logs = [r for r in caplog.records if "Failed to connect" in r.getMessage()]
        assert auth_logs, f"expected the original auth failure to be logged; got {caplog.records!r}"
        # The close-phase RuntimeError was also logged but didn't propagate.
        close_logs = [r for r in caplog.records if "Error closing" in r.getMessage()]
        assert close_logs, "expected the close failure to be logged (not swallowed silently)"

    async def test_unreachable_api_disables_its_tools(self, monkeypatch):
        """#87: when validate_connection returns False for Protect, every
        protect_* tool must be hidden via server.disable(tags={"protect"}),
        not left registered where they'd KeyError on client lookup.
        """
        _setup_env_for_lifespan(monkeypatch)

        net_client = _make_validating_client()
        failing_prot = _make_validating_client(valid=False)
        sm_client = _make_validating_client()

        server = create_server()  # registers all tools for all three APIs
        with (
            patch("unifi_mcp.clients.network.NetworkClient", return_value=net_client),
            patch("unifi_mcp.clients.protect.ProtectClient", return_value=failing_prot),
            patch("unifi_mcp.clients.site_manager.SiteManagerClient", return_value=sm_client),
        ):
            gen = server_lifespan._fn(server)
            async with aclosing(gen):
                await gen.__anext__()
                # While yielded, protect tools should be disabled.
                tool_names = {t.name for t in await server.list_tools()}
                assert not any(n.startswith("unifi_protect_") for n in tool_names), (
                    f"Expected unifi_protect_* tools disabled, still present: "
                    f"{sorted(n for n in tool_names if n.startswith('unifi_protect_'))}"
                )
                # Reachable APIs' tools stay registered.
                assert any(n.startswith("unifi_network_") for n in tool_names)
                assert any(n.startswith("unifi_site_manager_") for n in tool_names)
                with pytest.raises(StopAsyncIteration):
                    await gen.__anext__()

    @pytest.mark.parametrize("api_name", ["network", "protect", "site_manager"])
    async def test_disabled_tool_warn_includes_exception_class_for_each_api(self, monkeypatch, caplog, api_name):
        """Locks the operator-visible contract from #108 item 2: every API
        that fails validation must emit a WARN that names the exception
        class, not just the API name. Parametrized so adding a fourth API
        without diagnostic wiring fails a test instead of shipping silently.
        """
        import logging

        _setup_env_for_lifespan(monkeypatch)

        failing = AsyncMock()
        failing.validate_connection.side_effect = UniFiAuthError("HTTP 401: bad key", status_code=401)

        healthy = {
            name: _make_validating_client() for name in ("network", "protect", "site_manager") if name != api_name
        }
        patches = {
            "network": ("unifi_mcp.clients.network.NetworkClient", healthy.get("network")),
            "protect": ("unifi_mcp.clients.protect.ProtectClient", healthy.get("protect")),
            "site_manager": ("unifi_mcp.clients.site_manager.SiteManagerClient", healthy.get("site_manager")),
        }
        patches[api_name] = (patches[api_name][0], failing)

        with (
            patch(patches["network"][0], return_value=patches["network"][1]),
            patch(patches["protect"][0], return_value=patches["protect"][1]),
            patch(patches["site_manager"][0], return_value=patches["site_manager"][1]),
            caplog.at_level(logging.WARNING, logger="unifi_mcp.server"),
        ):
            gen = server_lifespan._fn(None)
            async with aclosing(gen):
                await gen.__anext__()
                with pytest.raises(StopAsyncIteration):
                    await gen.__anext__()

        disabled = [
            r for r in caplog.records if f"{api_name} tools disabled" in r.getMessage() and r.levelno == logging.WARNING
        ]
        assert disabled, f"expected '{api_name} tools disabled' WARN; got {[r.getMessage() for r in caplog.records]!r}"
        msg = disabled[0].getMessage()
        assert "UniFiAuthError" in msg, f"expected exception class in WARN for {api_name}; got {msg!r}"
        assert "HTTP 401" in msg, f"expected exception message text in WARN for {api_name}; got {msg!r}"

    async def test_protect_client_constructed_with_independent_host(self, monkeypatch, tmp_path):
        """#108 item 3: when UNIFI_PROTECT_HOST differs from UNIFI_NETWORK_HOST,
        the ProtectClient must be built against the Protect host — mirrors the
        audit topology (UCG on .1, UCK-G2-Plus on .220) that the suite didn't
        previously exercise end-to-end.
        """
        monkeypatch.chdir(tmp_path)  # isolate from any .env that pre-sets these vars
        monkeypatch.setenv("UNIFI_MODE", "readonly")
        monkeypatch.setenv("UNIFI_NETWORK_HOST", "10.0.0.1")
        monkeypatch.setenv("UNIFI_NETWORK_API", "n")
        monkeypatch.setenv("UNIFI_PROTECT_HOST", "10.0.0.2")
        monkeypatch.setenv("UNIFI_PROTECT_PORT", "7443")
        monkeypatch.setenv("UNIFI_PROTECT_API", "p")
        monkeypatch.delenv("UNIFI_SITE_MANAGER_API", raising=False)

        seen: dict[str, str] = {}

        def _capture_protect(*, base_url: str, **_: Any) -> AsyncMock:
            seen["protect"] = base_url
            return _make_validating_client()

        def _capture_network(*, base_url: str, **_: Any) -> AsyncMock:
            seen["network"] = base_url
            return _make_validating_client()

        with (
            patch("unifi_mcp.clients.network.NetworkClient", side_effect=_capture_network),
            patch("unifi_mcp.clients.protect.ProtectClient", side_effect=_capture_protect),
        ):
            gen = server_lifespan._fn(None)
            async with aclosing(gen):
                await gen.__anext__()
                with pytest.raises(StopAsyncIteration):
                    await gen.__anext__()

        assert seen["protect"] == "https://10.0.0.2:7443", seen
        assert seen["network"] == "https://10.0.0.1:443", seen

    async def test_protect_port_alone_does_not_leak_onto_network_base_url(self, monkeypatch, tmp_path):
        """#108 item 3 negative: setting only UNIFI_PROTECT_PORT (no HOST)
        must leave the Network base URL untouched. Protect inherits the
        Network *host* but uses its own explicit port; Network's port stays
        at the default.
        """
        monkeypatch.chdir(tmp_path)  # isolate from any .env leaking UNIFI_PROTECT_HOST
        monkeypatch.setenv("UNIFI_MODE", "readonly")
        monkeypatch.setenv("UNIFI_NETWORK_HOST", "10.0.0.1")
        monkeypatch.setenv("UNIFI_NETWORK_API", "n")
        monkeypatch.setenv("UNIFI_PROTECT_PORT", "7443")
        monkeypatch.setenv("UNIFI_PROTECT_API", "p")
        monkeypatch.delenv("UNIFI_PROTECT_HOST", raising=False)
        monkeypatch.delenv("UNIFI_SITE_MANAGER_API", raising=False)

        seen: dict[str, str] = {}

        def _capture_protect(*, base_url: str, **_: Any) -> AsyncMock:
            seen["protect"] = base_url
            return _make_validating_client()

        def _capture_network(*, base_url: str, **_: Any) -> AsyncMock:
            seen["network"] = base_url
            return _make_validating_client()

        with (
            patch("unifi_mcp.clients.network.NetworkClient", side_effect=_capture_network),
            patch("unifi_mcp.clients.protect.ProtectClient", side_effect=_capture_protect),
        ):
            gen = server_lifespan._fn(None)
            async with aclosing(gen):
                await gen.__anext__()
                with pytest.raises(StopAsyncIteration):
                    await gen.__anext__()

        assert seen["network"] == "https://10.0.0.1:443", f"Protect port must not affect Network base URL; got {seen!r}"
        assert seen["protect"] == "https://10.0.0.1:7443", (
            f"Protect should inherit Network host and use its own explicit port; got {seen!r}"
        )

    async def test_old_firmware_disables_only_integration_tag(self, monkeypatch):
        """#408/#409: an old-firmware 404 from the Network Integration API must
        deregister only the ``network_integration``-tagged tools (the 28
        ``unifi_network_list_*`` / ``get_*`` Integration reads). The legacy
        ``{"network"}``-tagged tools share the ``unifi_network_`` name prefix
        but a different tag, so they must survive.

        The legacy NetworkClient and the NetworkIntegrationClient are both
        constructed against the Network key/host; here the legacy one validates
        and the Integration one fails, mirroring old firmware.
        """
        _setup_env_for_lifespan(monkeypatch)
        monkeypatch.delenv("UNIFI_PROTECT_API", raising=False)
        monkeypatch.delenv("UNIFI_SITE_MANAGER_API", raising=False)

        net_client = _make_validating_client()
        failing_ni = _make_validating_client(valid=False)

        server = create_server()
        with (
            patch("unifi_mcp.clients.network.NetworkClient", return_value=net_client),
            patch(
                "unifi_mcp.clients.network_integration.NetworkIntegrationClient",
                return_value=failing_ni,
            ),
        ):
            gen = server_lifespan._fn(server)
            async with aclosing(gen):
                await gen.__anext__()
                tools = await server.list_tools()
                by_tag = {t.name: set(t.tags) for t in tools}
                # Legacy network reads survive (e.g. list_devices is {"network"}).
                assert "unifi_network_list_devices" in by_tag
                # Every remaining unifi_network_ tool is the legacy {"network"}
                # tag — no {"network_integration"} tool is still registered.
                ni_left = [n for n, tags in by_tag.items() if "network_integration" in tags]
                assert ni_left == [], f"integration tools should be disabled, still present: {ni_left}"
                with pytest.raises(StopAsyncIteration):
                    await gen.__anext__()

    async def test_unreachable_api_does_not_disable_others(self, monkeypatch):
        """Disabling one API's tools must not touch other APIs' tools."""
        _setup_env_for_lifespan(monkeypatch)

        net_client = _make_validating_client(valid=False)
        prot_client = _make_validating_client()
        sm_client = _make_validating_client()

        server = create_server()
        with (
            patch("unifi_mcp.clients.network.NetworkClient", return_value=net_client),
            patch("unifi_mcp.clients.protect.ProtectClient", return_value=prot_client),
            patch("unifi_mcp.clients.site_manager.SiteManagerClient", return_value=sm_client),
        ):
            gen = server_lifespan._fn(server)
            async with aclosing(gen):
                await gen.__anext__()
                tool_names = {t.name for t in await server.list_tools()}
                # Network disabled:
                assert not any(n.startswith("unifi_network_") for n in tool_names)
                # Protect and Site Manager still visible:
                assert any(n.startswith("unifi_protect_") for n in tool_names)
                assert any(n.startswith("unifi_site_manager_") for n in tool_names)
                with pytest.raises(StopAsyncIteration):
                    await gen.__anext__()


# ── create_server shape verification (independent of lifespan) ─────────────


class TestCreateServer:
    def test_readonly_sets_name_and_instructions(self):
        cfg = _as_config()
        server = create_server(cfg)
        assert server.name == "unifi-mcp"

    def test_with_no_config_uses_env(self, monkeypatch):
        for var in ("UNIFI_NETWORK_API", "UNIFI_PROTECT_API", "UNIFI_SITE_MANAGER_API"):
            monkeypatch.delenv(var, raising=False)
        # Clearing config forces create_server to read env; that should still build
        # a server even with zero APIs configured.
        server = create_server()
        assert server.name == "unifi-mcp"


# ── Explicit guards survive python -O (asserts stripped) ───────────────────


class TestEnabledWithoutKeyGuards:
    """Replaces the previous ``assert config.unifi_*_api is not None`` checks.

    The ``*_enabled`` properties read the same field, so in normal use these
    branches are unreachable. Under ``python -O`` an ``assert`` would vanish
    and the lifespan would dereference ``None`` deep inside the client
    constructor; the explicit ``RuntimeError`` keeps the failure mode loud.
    """

    @pytest.mark.parametrize(
        ("api", "env_var"),
        [
            ("network", "UNIFI_NETWORK_API"),
            ("protect", "UNIFI_PROTECT_API"),
            ("site_manager", "UNIFI_SITE_MANAGER_API"),
        ],
    )
    async def test_runtime_error_when_enabled_but_key_missing(self, monkeypatch, tmp_path, api, env_var):
        from unifi_mcp.config import UniFiConfig

        _setup_env_for_lifespan(monkeypatch, tmp_path)
        monkeypatch.delenv(env_var, raising=False)

        property_name = f"{api}_enabled"
        monkeypatch.setattr(UniFiConfig, property_name, property(lambda _self: True))

        expected = f"unifi_{api}_api must be set when {api}_enabled is True"
        gen = server_lifespan._fn(None)
        async with aclosing(gen):
            with pytest.raises(RuntimeError, match=expected):
                await gen.__anext__()


# ── Guard against accidental .env dependence during tests ──────────────────


def test_env_suite_preserved():
    # Quick sanity: these tests shouldn't mutate the real process env when
    # executed without monkeypatch. UNIFI_MODE may be set by the user's shell;
    # we just assert the test environment didn't leak anything unexpected.
    assert os.environ.get("UNIFI_MODE", "readonly") in {"readonly", "readwrite"}
