"""Timeout messages identify the phase without reflecting transport secrets."""

from __future__ import annotations

import httpx
import pytest
import respx
from fastmcp.exceptions import ToolError

from unifi_mcp.clients.network import NetworkClient
from unifi_mcp.errors import UniFiTimeoutError
from unifi_mcp.tools._error_adapter import handle_client_error


@pytest.mark.parametrize("kind", [httpx.ReadTimeout, httpx.ConnectTimeout, httpx.WriteTimeout, httpx.PoolTimeout])
@respx.mock
async def test_phase_is_visible_and_raw_transport_text_is_not_reflected(kind):
    route = respx.get("https://192.0.2.1/proxy/network/api/s/default/stat/health").mock(
        side_effect=kind("SYNTHETIC-PRIVATE-TIMEOUT")
    )
    client = NetworkClient("https://192.0.2.1", "synthetic-key", max_retries=1)
    try:
        with pytest.raises(UniFiTimeoutError) as caught:
            await client.get_health()
        assert str(caught.value) == f"HTTP {kind.__name__} during GET"
        assert "SYNTHETIC-PRIVATE-TIMEOUT" not in str(caught.value)
        assert route.call_count == 1
        with pytest.raises(ToolError) as tool:
            handle_client_error(caught.value)
        assert kind.__name__ in str(tool.value)
        assert "controller did not respond" not in str(tool.value)
        assert "SYNTHETIC-PRIVATE-TIMEOUT" not in str(tool.value)
    finally:
        await client.close()


async def test_retry_warning_does_not_reflect_transport_message(caplog):
    import logging

    import respx

    from unifi_mcp.clients.network import NetworkClient

    client = NetworkClient("https://192.0.2.1", "synthetic-key", max_retries=2)
    with respx.mock as router:
        route = router.get("https://192.0.2.1/proxy/network/api/s/default/stat/health").mock(
            side_effect=httpx.ReadTimeout("SYNTHETIC-PRIVATE-TIMEOUT")
        )
        with caplog.at_level(logging.WARNING), pytest.raises(UniFiTimeoutError):
            await client.get_health()
        assert route.call_count == 2
        assert "ReadTimeout" in caplog.text
        assert "SYNTHETIC-PRIVATE-TIMEOUT" not in caplog.text
    await client.close()
