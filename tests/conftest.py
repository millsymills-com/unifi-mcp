"""Shared test fixtures for unifi-mcp."""

from __future__ import annotations

import os
import socket
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastmcp import FastMCP

from unifi_mcp.clients.network import NetworkClient
from unifi_mcp.clients.protect import ProtectClient
from unifi_mcp.clients.site_manager import SITE_MANAGER_BASE_URL, SiteManagerClient
from unifi_mcp.config import UniFiConfig, UniFiMode, get_config


@pytest.fixture(autouse=True)
def _isolate_offline_config(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch):
    """Make unit/property inputs independent of operator environment and dotenv."""
    test_dir = request.path.relative_to(request.config.rootpath).parts[:2]
    if test_dir not in (("tests", "unit"), ("tests", "property")):
        return
    for name in tuple(os.environ):
        if name.upper().startswith("UNIFI_"):
            monkeypatch.delenv(name)
    monkeypatch.setitem(UniFiConfig.model_config, "env_file", None)


@pytest.fixture
def _offline_tcp_ports() -> set[int]:
    return set()


@pytest.fixture
def allow_loopback_tcp(_offline_tcp_ports):
    """Permit only an explicitly registered test-owned 127.0.0.1 TCP port."""

    def allow(port):
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError("a test-owned loopback TCP port must be an integer from 1 to 65535")
        _offline_tcp_ports.add(port)

    return allow


@pytest.fixture(autouse=True)
def _block_offline_network(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch, _offline_tcp_ports):
    """Refuse offline DNS/TCP except fixture-registered loopback endpoints."""
    test_dir = request.path.relative_to(request.config.rootpath).parts[:2]
    if test_dir not in (("tests", "unit"), ("tests", "property")):
        return

    def allowed(address):
        return (
            isinstance(address, tuple)
            and len(address) >= 2
            and address[0] in ("127.0.0.1", b"127.0.0.1")
            and type(address[1]) is int
            and address[1] in _offline_tcp_ports
        )

    def refuse(*_args, **_kwargs):
        raise AssertionError("unmocked DNS/TCP access in an offline unit/property test")

    def guard(original, *, method=False):
        def checked(*args, **kwargs):
            index = 1 if method else 0
            address = args[index] if len(args) > index else kwargs.get("address")
            if not allowed(address):
                refuse()
            return original(*args, **kwargs)

        return checked

    original_resolve = socket.getaddrinfo

    def resolve(host, port, *args, **kwargs):
        if not allowed((host, port)):
            refuse()
        return original_resolve(host, port, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", guard(socket.create_connection))
    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    for name in ("gethostbyname", "gethostbyname_ex"):
        monkeypatch.setattr(socket, name, refuse)
    for name in ("connect", "connect_ex"):
        monkeypatch.setattr(socket.socket, name, guard(getattr(socket.socket, name), method=True))


@pytest.fixture(autouse=True)
def _clear_config_cache():
    """Reset the process-wide ``get_config`` cache between tests.

    ``get_config`` is ``lru_cache``-d so the TLS audit fires once per
    process (#190). Tests mutate env vars between cases, so the cache
    has to be cleared in both directions to keep them isolated.
    """
    get_config.cache_clear()
    yield
    get_config.cache_clear()


@dataclass
class FakeLifespanContext:
    """Stand-in for ServerContext when exercising tool handlers outside a real lifespan."""

    clients: dict[str, Any] = field(default_factory=dict)
    config: UniFiConfig | None = None


@pytest.fixture
def readonly_config() -> UniFiConfig:
    """A UniFiConfig with all three APIs configured and UNIFI_MODE=readonly."""
    return UniFiConfig(
        _env_file=None,
        unifi_mode=UniFiMode.READONLY,
        unifi_network_api="test-net-key",
        unifi_protect_api="test-prot-key",
        unifi_site_manager_api="test-sm-key",
    )


@pytest.fixture
def readwrite_config() -> UniFiConfig:
    """A UniFiConfig with all three APIs configured and UNIFI_MODE=readwrite."""
    return UniFiConfig(
        _env_file=None,
        unifi_mode=UniFiMode.READWRITE,
        unifi_network_api="test-net-key",
        unifi_protect_api="test-prot-key",
        unifi_site_manager_api="test-sm-key",
    )


@pytest.fixture
def network_client() -> NetworkClient:
    """A NetworkClient pointed at a synthetic controller URL for respx-based tests."""
    return NetworkClient(
        base_url="https://10.0.0.1:443",
        api_key="test-net-key",
        site="default",
        timeout=5,
        max_retries=1,
    )


@pytest.fixture
def protect_client() -> ProtectClient:
    """A ProtectClient pointed at a synthetic controller URL for respx-based tests."""
    return ProtectClient(
        base_url="https://10.0.0.1:443",
        api_key="test-prot-key",
        timeout=5,
        max_retries=1,
    )


@pytest.fixture
def site_manager_client() -> SiteManagerClient:
    """A SiteManagerClient (base URL is fixed to the UniFi cloud API)."""
    return SiteManagerClient(api_key="test-sm-key", timeout=5, max_retries=1)


SITE_MANAGER_API_PREFIX = f"{SITE_MANAGER_BASE_URL}/v1/"


def build_fake_ctx(config: UniFiConfig, **clients: Any) -> AsyncMock:
    """Build a fake Context with the given config and named clients."""
    ctx = AsyncMock()
    ctx.lifespan_context = FakeLifespanContext(clients=dict(clients), config=config)
    return ctx


@pytest.fixture
def mcp_server() -> FastMCP:
    """A bare FastMCP server for tests that just need a namespace to register tools on."""
    return FastMCP(name="test-server")
