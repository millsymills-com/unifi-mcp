"""FastMCP server creation, lifespan, and mode gating."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, TypedDict

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from pydantic import SecretStr

    from unifi_mcp.clients.base import BaseUniFiClient
    from unifi_mcp.clients.network import NetworkClient
    from unifi_mcp.clients.network_integration import NetworkIntegrationClient
    from unifi_mcp.clients.protect import ProtectClient
    from unifi_mcp.clients.site_manager import SiteManagerClient

import httpx
from fastmcp import FastMCP
from fastmcp.server.lifespan import lifespan

from unifi_mcp.config import UniFiConfig, get_config
from unifi_mcp.errors import UniFiError

logger = logging.getLogger(__name__)


def _require_api_key(api_name: str, secret: SecretStr | None) -> str:
    """Return the plaintext API key, raising if absent.

    The matching ``*_enabled`` property already guarantees the key is set, so
    this is a ``python -O``-proof guard rather than a user-facing error: under
    ``-O`` the previous ``assert`` would vanish and the lifespan would crash
    deep inside the client constructor on a ``None`` attribute access.
    """
    if secret is None:
        raise RuntimeError(f"unifi_{api_name}_api must be set when {api_name}_enabled is True")
    return secret.get_secret_value()


class APIClients(TypedDict, total=False):
    """Per-API clients keyed by short name. Keys may be absent when the API is disabled or failed validation."""

    network: NetworkClient
    network_integration: NetworkIntegrationClient
    protect: ProtectClient
    site_manager: SiteManagerClient


@dataclass
class ServerContext:
    """Lifespan context passed to all tools via ``ctx.lifespan_context``."""

    config: UniFiConfig
    clients: APIClients = field(default_factory=APIClients)


async def _safe_close(name: str, client: Any) -> None:
    """Close a client, swallowing and logging any exception.

    Used in failure/cleanup paths where a close() that raises must not
    mask the original failure (in _register_client) or abort the rest of
    the shutdown close-loop (in the lifespan's finally block).
    """
    try:
        await client.close()
    except Exception:
        logger.exception("Error closing %s client during cleanup", name)
    else:
        logger.info("Closed %s client", name)


async def _register_client(context: ServerContext, name: str, client: Any) -> BaseException | None:
    """Validate and register a client, closing it if validation fails.

    Returns the exception that caused registration to fail (or None on
    success). The caller uses this to include the failure class in the
    operator-visible WARN log at the end of the lifespan — a generic
    "validate_connection failed" doesn't distinguish auth failures from
    host unreachability from path mismatches.
    """
    try:
        valid = await client.validate_connection()
    except (UniFiError, httpx.HTTPError) as exc:
        logger.exception("Failed to connect to %s API — skipping", name)
        await _safe_close(name, client)
        return exc
    if valid:
        context.clients[name] = client  # type: ignore[literal-required]  # ty: ignore[invalid-key]
        logger.info("%s API client initialized", name)
        return None
    logger.warning("%s API validation returned False — skipping", name)
    await _safe_close(name, client)
    # validate_connection swallows the exception internally and returns
    # False; recover it from the client's _last_validation_error attr
    # (set by BaseUniFiClient subclasses on failure).
    stashed: BaseException | None = getattr(client, "_last_validation_error", None)
    return stashed


@lifespan  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]
async def server_lifespan(server: FastMCP) -> AsyncIterator[ServerContext]:
    """Initialize clients for configured APIs, validate, and yield context.

    Tools are registered up front in ``create_server`` based on which API keys
    are configured. This function runs on startup and additionally **disables
    the tag** of any API whose ``validate_connection()`` fails, so the served
    tool list reflects what is actually reachable instead of what is merely
    configured. Without this step, a configured-but-unreachable backend leaves
    its tools registered and every invocation raises ``KeyError`` inside the
    handler (see #87).
    """
    config = get_config()
    context = ServerContext(config=config)

    # Lazily import clients to avoid circular deps
    from unifi_mcp.clients.network import NetworkClient
    from unifi_mcp.clients.network_integration import NetworkIntegrationClient
    from unifi_mcp.clients.protect import ProtectClient
    from unifi_mcp.clients.site_manager import SiteManagerClient

    # Failure reasons captured per API, used in the WARN log below so
    # operators can distinguish auth / unreachability / path mismatch.
    failures: dict[str, BaseException | None] = {}

    if config.network_enabled:
        failures["network"] = await _register_client(
            context,
            "network",
            NetworkClient(
                base_url=config.network_base_url,
                api_key=_require_api_key("network", config.unifi_network_api),
                site=config.unifi_network_site,
                verify_ssl=config.unifi_network_verify_ssl,
                cert_fingerprint=config.unifi_network_cert_fingerprint,
                timeout=config.unifi_request_timeout,
                max_retries=config.unifi_max_retries,
            ),
        )

    if config.network_integration_enabled:
        failures["network_integration"] = await _register_client(
            context,
            "network_integration",
            NetworkIntegrationClient(
                base_url=config.network_integration_base_url,
                api_key=_require_api_key("network", config.unifi_network_api),
                site=config.unifi_network_integration_site,
                verify_ssl=config.unifi_network_verify_ssl,
                cert_fingerprint=config.unifi_network_cert_fingerprint,
                timeout=config.unifi_request_timeout,
                max_retries=config.unifi_max_retries,
            ),
        )

    if config.protect_enabled:
        failures["protect"] = await _register_client(
            context,
            "protect",
            ProtectClient(
                base_url=config.protect_base_url,
                api_key=_require_api_key("protect", config.unifi_protect_api),
                verify_ssl=config.unifi_protect_verify_ssl,
                cert_fingerprint=config.unifi_protect_cert_fingerprint,
                timeout=config.unifi_request_timeout,
                max_retries=config.unifi_max_retries,
            ),
        )

    if config.site_manager_enabled:
        failures["site_manager"] = await _register_client(
            context,
            "site_manager",
            SiteManagerClient(
                api_key=_require_api_key("site_manager", config.unifi_site_manager_api),
                timeout=config.unifi_request_timeout,
                max_retries=config.unifi_max_retries,
            ),
        )

    # For each configured-but-unreachable API, hide its tools so the agent
    # doesn't see tools that will raise KeyError at call time. Only disable
    # when the API was configured (had a key) — if it was never configured,
    # no tools were ever registered.
    for api_name, enabled in (
        ("network", config.network_enabled),
        ("network_integration", config.network_integration_enabled),
        ("protect", config.protect_enabled),
        ("site_manager", config.site_manager_enabled),
    ):
        if enabled and api_name not in context.clients:
            if server is not None:
                server.disable(tags={api_name})
            err = failures.get(api_name)
            if err is not None:
                guidance = getattr(err, "guidance", None)
                detail = f": {guidance}" if guidance else ""
                logger.warning(
                    "%s tools disabled — %s (HTTP %s)%s; see DEBUG log for details",
                    api_name,
                    type(err).__name__,
                    getattr(err, "status_code", None),
                    detail,
                )
                logger.debug("%s tools disabled — full exception", api_name, exc_info=err)
            else:
                logger.warning(
                    "%s tools disabled — validate_connection failed and the backend is unreachable",
                    api_name,
                )

    if not context.clients:
        logger.warning("No API clients initialized — server will have no tools")

    try:
        yield context
    finally:
        # Close each client independently — one client's close() failure
        # must never prevent the others from being closed. ``_safe_close``
        # swallows and logs each failure so the loop runs to completion and
        # no remaining client leaks its socket.
        clients_to_close: list[tuple[str, BaseUniFiClient]] = list(context.clients.items())  # type: ignore[arg-type]  # ty: ignore[invalid-assignment]
        for name, c in clients_to_close:
            await _safe_close(name, c)


def create_server(config: UniFiConfig | None = None) -> FastMCP:
    """Create and configure the FastMCP server."""
    if config is None:
        config = get_config()

    server = FastMCP(
        name="unifi-mcp",
        instructions=(
            "UniFi MCP server providing tools for UniFi Site Manager, "
            "Network, and Protect APIs. Use these tools to query and manage "
            "your UniFi network infrastructure."
        ),
        lifespan=server_lifespan,
    )

    # Register tools for configured APIs. register_all_tools handles the
    # read/write split internally; the explicit log here is for operators.
    from unifi_mcp.tools import register_all_tools

    register_all_tools(server, config)

    if not config.writes_enabled:
        logger.info("Read-only mode: write tools disabled")
    else:
        logger.info("Read-write mode: all tools enabled")

    return server
