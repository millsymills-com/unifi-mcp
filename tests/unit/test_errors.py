"""Tests for the UniFi exception hierarchy and handle_client_error mapping."""

from __future__ import annotations

import asyncio
import subprocess
import sys

import pytest
from fastmcp.exceptions import ToolError

from unifi_mcp.errors import (
    UniFiAuthError,
    UniFiBadRequestError,
    UniFiConnectionError,
    UniFiDeviceAlreadyAdoptedError,
    UniFiError,
    UniFiNotFoundError,
    UniFiRateLimitError,
    UniFiReadOnlyError,
    UniFiServerError,
    UniFiTimeoutError,
    UniFiUnsupportedError,
    handle_client_error,
)
from unifi_mcp.tools._error_adapter import handle_client_error as direct_handle_client_error


@pytest.mark.parametrize(
    "import_statement",
    [
        "from unifi_mcp.errors import handle_client_error",
        "import unifi_mcp.clients.base",
        "import unifi_mcp.clients.network",
        "import unifi_mcp.clients.network_integration",
        "import unifi_mcp.clients.protect",
        "import unifi_mcp.clients.site_manager",
        "import unifi_mcp.clients._pinning",
    ],
)
def test_transport_imports_do_not_load_fastmcp(import_statement: str) -> None:
    code = f"import sys; {import_statement}; assert 'fastmcp' not in sys.modules"
    # Statements come only from the fixed parametrized list above.
    subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, text=True)  # noqa: S603


class TestExceptionHierarchy:
    def test_unifi_error_stores_status_code(self):
        err = UniFiError("boom", status_code=500)
        assert err.status_code == 500
        assert str(err) == "boom"

    def test_unifi_error_default_status_code_is_none(self):
        err = UniFiError("boom")
        assert err.status_code is None

    @pytest.mark.parametrize(
        "subclass",
        [
            UniFiAuthError,
            UniFiBadRequestError,
            UniFiDeviceAlreadyAdoptedError,
            UniFiNotFoundError,
            UniFiRateLimitError,
            UniFiServerError,
            UniFiConnectionError,
            UniFiTimeoutError,
            UniFiReadOnlyError,
        ],
    )
    def test_subclasses_inherit_from_unifi_error(self, subclass):
        assert issubclass(subclass, UniFiError)

    def test_timeout_is_a_connection_error(self):
        # Existing callers catch UniFiConnectionError; keep that invariant.
        assert issubclass(UniFiTimeoutError, UniFiConnectionError)


class TestHandleClientError:
    @pytest.mark.parametrize(
        "error",
        [
            UniFiAuthError("bad key", status_code=401),
            UniFiBadRequestError("bad payload", status_code=400),
            UniFiNotFoundError("missing", status_code=404),
            UniFiUnsupportedError("unsupported"),
            UniFiRateLimitError("slow", status_code=429, retry_after=2),
            UniFiServerError("upstream", status_code=502),
            UniFiTimeoutError("timeout"),
            UniFiConnectionError("offline"),
            UniFiReadOnlyError("blocked"),
            UniFiDeviceAlreadyAdoptedError("adopted"),
            UniFiError("generic", status_code=418),
            RuntimeError("private internal detail"),
        ],
    )
    def test_legacy_and_direct_mapping_agree(self, error):
        with pytest.raises(ToolError) as legacy:
            handle_client_error(error)
        with pytest.raises(ToolError) as direct:
            direct_handle_client_error(error)
        assert str(legacy.value) == str(direct.value)
        assert legacy.value.__cause__ is error
        assert direct.value.__cause__ is error

    @pytest.mark.parametrize("error", [asyncio.CancelledError(), KeyboardInterrupt(), SystemExit(2), GeneratorExit()])
    def test_legacy_and_direct_mapping_preserve_control_flow(self, error):
        for mapper in (handle_client_error, direct_handle_client_error):
            with pytest.raises(type(error)) as raised:
                mapper(error)
            assert raised.value is error

    def test_auth_error_maps(self):
        with pytest.raises(ToolError, match="Authentication failed"):
            handle_client_error(UniFiAuthError("bad key", status_code=401))

    def test_bad_request_error_maps(self):
        with pytest.raises(ToolError, match="Invalid request"):
            handle_client_error(UniFiBadRequestError("malformed", status_code=400))

    def test_not_found_error_maps(self):
        with pytest.raises(ToolError, match="Resource not found"):
            handle_client_error(UniFiNotFoundError("missing", status_code=404))

    def test_rate_limit_error_maps(self):
        with pytest.raises(ToolError, match="Rate limit exceeded"):
            handle_client_error(UniFiRateLimitError("slow down", status_code=429))

    def test_server_error_maps(self):
        with pytest.raises(ToolError, match="UniFi server error"):
            handle_client_error(UniFiServerError("upstream", status_code=502))

    def test_timeout_error_maps_before_connection_error(self):
        # UniFiTimeoutError is a subclass of UniFiConnectionError; the handler
        # must reach the timeout branch first so the message is specific.
        with pytest.raises(ToolError, match="Request timed out"):
            handle_client_error(UniFiTimeoutError("timed out"))

    def test_connection_error_maps(self):
        with pytest.raises(ToolError, match="Connection failed"):
            handle_client_error(UniFiConnectionError("DNS failed"))

    def test_readonly_error_maps(self):
        with pytest.raises(ToolError, match="Write operation blocked"):
            handle_client_error(UniFiReadOnlyError("not allowed"))

    def test_device_already_adopted_error_maps(self):
        with pytest.raises(ToolError, match="Device already adopted"):
            handle_client_error(UniFiDeviceAlreadyAdoptedError("aa:bb:cc:dd:ee:ff"))

    def test_generic_unifi_error_maps(self):
        with pytest.raises(ToolError, match="UniFi API error"):
            handle_client_error(UniFiError("generic", status_code=418))

    def test_unexpected_error_maps_to_safe_message(self):
        """Unexpected errors must not echo ``str(error)`` to the agent —
        otherwise programmer bugs that build context-rich exceptions leak
        details into agent transcripts (#148).
        """
        sensitive_context = "sensitive-context-from-bug"
        with pytest.raises(ToolError) as exc_info:
            handle_client_error(RuntimeError(sensitive_context))
        msg = str(exc_info.value)
        assert "Unexpected internal error" in msg
        assert sensitive_context not in msg
        # The original exception is preserved on __cause__ for operator logs.
        assert isinstance(exc_info.value.__cause__, RuntimeError)
        assert str(exc_info.value.__cause__) == sensitive_context

    def test_error_chain_preserved(self):
        original = UniFiAuthError("bad key", status_code=401)
        with pytest.raises(ToolError) as exc_info:
            handle_client_error(original)
        assert exc_info.value.__cause__ is original
