"""Subprocess MCP stdio transport coverage.

The rest of the integration suite (and every unit test) drives the server with
``fastmcp.Client(server)`` — an *in-process* transport that bypasses the JSON-RPC
framing, line buffering, and process boundary that real MCP clients use. This
module spawns the installed ``unifi-mcp`` console script as a real subprocess
and drives it through the MCP **stdio** transport, covering §4 of #97.

Five layers of coverage live here:

* ``test_stdio_handshake_no_apis_configured`` exercises the bare transport
  contract — handshake, ``serverInfo``, empty ``tools/list``, clean shutdown —
  with zero APIs configured.
* ``TestStdioModeFlip`` boots the subprocess against an in-test HTTPS mock that
  satisfies ``NetworkClient.validate_connection`` so Network tools actually
  register. The same subprocess shape is then driven once with
  ``UNIFI_MODE=readonly`` and once with ``UNIFI_MODE=readwrite`` to verify the
  write-tool tag gate over the real stdio boundary. This closes the most
  agent-doable slice of #43 acceptance criterion 3.
* ``TestStdioToolCallCancellation`` drives a tool call that hangs in the
  upstream HTTP request, then cancels the client task. It verifies that a
  cancellation crossing the real JSON-RPC stdio boundary surfaces as
  ``CancelledError`` and — critically — that the session stays usable
  afterwards. ``tests/unit/clients/test_cancellation.py`` only pins the
  ``BaseUniFiClient`` contract in-process; this is the missing transport-level
  slice of §4 in #97.
* ``TestStdioConcurrentToolCalls`` fires many tool calls simultaneously over the
  same session. The Network client re-uses one ``httpx.AsyncClient``, so every
  concurrent call shares its connection pool; a rendezvous mock that answers a
  request only once all of them have arrived proves the pool serves them
  simultaneously instead of serialising, and a unique per-response marker that
  maps one-to-one onto the results proves no cross-talk between in-flight calls.
  This is the "concurrent tool calls — no stress test" slice of §4 in #97.
* ``TestStdioToolListStability`` takes three ``tools/list`` snapshots on one
  session — back to back, then once more after a tool call — and asserts the
  served tool set is byte-for-byte identical each time. A tool appearing,
  vanishing, reordering, or changing schema mid-session would break clients
  that cache the list after ``initialize``. This is the "tool set stable across
  a session" slice of §4 in #97.

The subprocess is launched in a temp ``cwd`` so pydantic-settings doesn't pick
up the repo's ``.env`` and silently re-enable APIs (which would then fail
``validate_connection`` against unreachable hardware in CI).

Run manually with::

    uv run pytest tests/integration/test_stdio_transport.py -v -m integration
"""

from __future__ import annotations

import asyncio
import datetime
import http.server
import json
import os
import shutil
import ssl
import tempfile
import threading
from ipaddress import IPv4Address
from typing import TYPE_CHECKING, Any

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from fastmcp import Client
from fastmcp.client.messages import MessageHandler
from fastmcp.client.transports import StdioTransport

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    import mcp.types

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

# Env vars that must be scrubbed from the subprocess environment so the server
# starts with zero APIs configured. Leaving any of these set would (a) try to
# validate against real hardware that may not be reachable in CI, and (b)
# defeat the purpose of a transport-only test by changing the served tool set.
_API_ENV_VARS = (
    "UNIFI_NETWORK_API",
    "UNIFI_PROTECT_API",
    "UNIFI_SITE_MANAGER_API",
)

# Canned Network-API-shaped JSON returned for any GET against the mock host.
# ``validate_connection`` calls ``stat/sysinfo`` and only checks for a 2xx; the
# body shape just needs to deserialise as a dict so the client's response
# parser doesn't raise.
_CANNED_BODY = {"data": [{"version": "8.0.0"}], "meta": {"rc": "ok"}}

# A pair of known write-tool names that exist in the Network API surface (see
# ``tests/unit/test_server.py::test_write_tools_disabled_in_readonly_mode``).
# Used to assert visibility flips with ``UNIFI_MODE``. ``unifi_network_block_client``
# is single-target; ``unifi_network_create_wlan`` is the canonical creation
# tool — covering both reduces the chance of a single rename masking the gate.
_KNOWN_WRITE_TOOLS = frozenset(
    {
        "unifi_network_block_client",
        "unifi_network_create_wlan",
        "unifi_network_restart_device",
    }
)


def _server_env() -> dict[str, str]:
    """Build a minimal env for the subprocess with no UniFi APIs configured.

    Inherits ``PATH`` (so the ``unifi-mcp`` console script and its interpreter
    are discoverable) and ``HOME`` (some libs read it at import time), then
    forces ``UNIFI_MODE=readonly`` and explicitly excludes every API key. We
    do *not* copy the rest of the parent env because a developer running this
    locally is very likely to have ``UNIFI_*`` set in their shell.
    """
    env: dict[str, str] = {
        "UNIFI_MODE": "readonly",
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
    }
    for key in _API_ENV_VARS:
        env.pop(key, None)
    return env


async def test_stdio_handshake_no_apis_configured() -> None:
    """Spawn ``unifi-mcp`` over stdio, complete the handshake, list tools.

    With no API keys configured the server registers no tools and the lifespan
    logs "No API clients initialized — server will have no tools". The MCP
    handshake itself must still succeed: ``initialize`` returns ``serverInfo``,
    ``tools/list`` returns an empty list, and tearing down the client shuts
    the subprocess down cleanly.
    """
    command = shutil.which("unifi-mcp")
    if command is None:
        pytest.skip("unifi-mcp console script not on PATH; run `uv sync` first")

    with tempfile.TemporaryDirectory(prefix="unifi-mcp-stdio-test-") as cwd:
        transport = StdioTransport(
            command=command,
            args=[],
            env=_server_env(),
            cwd=cwd,
        )
        async with Client(transport) as client:
            assert client.is_connected(), "client failed to connect over stdio"

            init = client.initialize_result
            assert init is not None, "no InitializeResult captured after handshake"
            assert init.serverInfo is not None, "serverInfo missing from initialize result"
            assert init.serverInfo.name == "unifi-mcp", f"unexpected serverInfo.name: {init.serverInfo.name!r}"
            assert init.serverInfo.version, "serverInfo.version should be a non-empty string"

            tools = await client.list_tools()
            assert isinstance(tools, list), f"tools/list returned non-list: {type(tools)!r}"
            assert tools == [], (
                "expected zero tools with no APIs configured; "
                f"got {[t.name for t in tools]!r} — is the .env leaking through?"
            )

        # Leaving the ``async with`` closes the transport, which signals EOF on
        # the subprocess stdin and waits for it to exit. If shutdown were
        # broken the context manager would hang or raise; reaching this line
        # is itself the assertion that the server tore down cleanly.
        assert not client.is_connected(), "client still connected after context exit"


# ── Mode-flip subprocess coverage ──────────────────────────────────────────


def _generate_self_signed_cert(host_ip: str) -> tuple[bytes, bytes]:
    """Return ``(cert_pem, key_pem)`` for a self-signed leaf bound to ``host_ip``.

    Only the leaf is needed because the subprocess client runs with
    ``UNIFI_NETWORK_VERIFY_SSL=false`` — httpx skips chain validation
    entirely. The cert still needs a SAN that matches the dialled host
    in case future regressions tighten that branch.
    """
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, host_ip)])
    now = datetime.datetime.now(datetime.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=1))
        .not_valid_after(now + datetime.timedelta(hours=1))
        .add_extension(
            x509.SubjectAlternativeName([x509.IPAddress(IPv4Address(host_ip))]),
            critical=False,
        )
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    key_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return cert_pem, key_pem


class _ThreadedMockHTTPSServer:
    """Background ``ThreadingHTTPServer`` with TLS on 127.0.0.1, shared by the stdio mocks.

    Each request gets its own daemon thread, so a handler that blocks (the
    cancellation hang, the concurrency rendezvous) can't stall the
    ``stat/sysinfo`` startup probe or teardown. Subclasses attach any per-test
    state to ``self._server`` after calling ``super().__init__`` and override
    ``_pre_shutdown`` to release in-flight handlers before the server stops.

    Mirrors the fixture in ``tests/unit/clients/test_ssl_verification.py`` but is
    intentionally duplicated: the integration package shouldn't reach into
    ``tests/unit`` internals.
    """

    def __init__(
        self,
        handler_class: type[http.server.BaseHTTPRequestHandler],
        cert_path: Path,
        key_path: Path,
    ) -> None:
        self._server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler_class)
        self._server.daemon_threads = True
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))
        self._server.socket = ctx.wrap_socket(self._server.socket, server_side=True)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def port(self) -> int:
        port: int = self._server.server_address[1]
        return port

    def _pre_shutdown(self) -> None:
        """Hook for subclasses to release handlers blocked on an Event before shutdown."""

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._pre_shutdown()
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)


class _CannedNetworkHandler(http.server.BaseHTTPRequestHandler):
    """Returns a canned Network-API-shaped JSON body for any GET; suppresses logs.

    ``NetworkClient.validate_connection`` only requires a 2xx with a parseable
    JSON object on ``stat/sysinfo``. We answer every path the same way so the
    mock doesn't have to track the Network API's URL grammar.
    """

    def do_GET(self) -> None:
        body = json.dumps(_CANNED_BODY).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002, ARG002 — http.server API
        return


class _NetworkMockHTTPSServer(_ThreadedMockHTTPSServer):
    """Answers any Network-API GET with a canned 200 so ``validate_connection`` passes.

    Stateless: its only job is to make the subprocess register Network tools.
    """

    def __init__(self, cert_path: Path, key_path: Path) -> None:
        super().__init__(_CannedNetworkHandler, cert_path, key_path)


@pytest.fixture
def network_mock_server(tmp_path: Path) -> Iterator[_NetworkMockHTTPSServer]:
    """Stand up a self-signed HTTPS server that answers any Network-API GET with 200.

    Yields the running server bound to an ephemeral port on 127.0.0.1. The
    cert is regenerated per test (cheap with 2048-bit RSA) so a stale fixture
    can't carry stale material between runs.
    """
    cert_pem, key_pem = _generate_self_signed_cert("127.0.0.1")
    cert_path = tmp_path / "server.pem"
    key_path = tmp_path / "server.key"
    cert_path.write_bytes(cert_pem)
    key_path.write_bytes(key_pem)

    server = _NetworkMockHTTPSServer(cert_path=cert_path, key_path=key_path)
    server.start()
    try:
        yield server
    finally:
        server.stop()


def _mode_flip_env(*, mode: str, network_port: int) -> dict[str, str]:
    """Build a subprocess env with Network configured against ``network_port``.

    All Protect/Site-Manager keys are scrubbed so only Network tools register,
    keeping the served tool set deterministic. ``UNIFI_NETWORK_VERIFY_SSL`` is
    forced false so httpx accepts the in-test self-signed cert.
    """
    env: dict[str, str] = {
        "UNIFI_MODE": mode,
        "UNIFI_NETWORK_HOST": "127.0.0.1",
        "UNIFI_NETWORK_PORT": str(network_port),
        "UNIFI_NETWORK_API": "test-network-key",
        "UNIFI_NETWORK_VERIFY_SSL": "false",
        "UNIFI_NETWORK_SITE": "default",
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
    }
    # Belt-and-braces: scrubbed even though they were never added.
    for key in ("UNIFI_PROTECT_API", "UNIFI_SITE_MANAGER_API"):
        env.pop(key, None)
    return env


class TestStdioModeFlip:
    """Verify ``UNIFI_MODE`` gates write-tool visibility over real stdio.

    Two subprocess spawns: one in readonly mode (no write tools must appear),
    one in readwrite mode (known write tools must appear). The same mock HTTPS
    backend is used for both so the only varying axis is the env var under
    test. Progresses #43 acceptance criterion 3.
    """

    async def test_readonly_mode_hides_write_tools(
        self,
        network_mock_server: _NetworkMockHTTPSServer,
    ) -> None:
        command = shutil.which("unifi-mcp")
        if command is None:
            pytest.skip("unifi-mcp console script not on PATH; run `uv sync` first")

        with tempfile.TemporaryDirectory(prefix="unifi-mcp-stdio-readonly-") as cwd:
            transport = StdioTransport(
                command=command,
                args=[],
                env=_mode_flip_env(mode="readonly", network_port=network_mock_server.port),
                cwd=cwd,
            )
            async with Client(transport) as client:
                assert client.is_connected(), "client failed to connect over stdio"
                tools = await client.list_tools()

        tool_names = {t.name for t in tools}
        # If Network tools didn't register, the test is meaningless — the mock
        # backend or env wiring is broken, not the mode gate. Catch that here
        # so the failure message points at the right cause.
        assert any(name.startswith("unifi_network_") for name in tool_names), (
            f"no Network tools registered; mock backend or env wiring is broken — got tools: {sorted(tool_names)!r}"
        )
        leaked = tool_names & _KNOWN_WRITE_TOOLS
        assert not leaked, (
            f"write tools visible in readonly mode: {sorted(leaked)!r}; "
            "UNIFI_MODE gate is not being enforced over the stdio boundary"
        )

    async def test_readwrite_mode_exposes_write_tools(
        self,
        network_mock_server: _NetworkMockHTTPSServer,
    ) -> None:
        command = shutil.which("unifi-mcp")
        if command is None:
            pytest.skip("unifi-mcp console script not on PATH; run `uv sync` first")

        with tempfile.TemporaryDirectory(prefix="unifi-mcp-stdio-readwrite-") as cwd:
            transport = StdioTransport(
                command=command,
                args=[],
                env=_mode_flip_env(mode="readwrite", network_port=network_mock_server.port),
                cwd=cwd,
            )
            async with Client(transport) as client:
                assert client.is_connected(), "client failed to connect over stdio"
                tools = await client.list_tools()

        tool_names = {t.name for t in tools}
        present = tool_names & _KNOWN_WRITE_TOOLS
        assert present, (
            f"no known write tools visible in readwrite mode; expected at least one of "
            f"{sorted(_KNOWN_WRITE_TOOLS)!r}, got {sorted(tool_names)!r}"
        )


# ── Tool-call cancellation over stdio ───────────────────────────────────────

# The read tool whose call we cancel. It maps to ``NetworkClient.get_health``
# (``GET stat/health``), which the mock below hangs on. It registers in
# readonly mode, so no write gate is involved.
_HANGING_TOOL = "unifi_network_get_health"


class _CancellableNetworkHandler(http.server.BaseHTTPRequestHandler):
    """Canned 200 for any GET except ``stat/health``, which blocks until released.

    ``validate_connection`` hits ``stat/sysinfo`` at startup and must succeed
    fast, so only the health path hangs. The handler signals ``health_requested``
    the instant the hang begins (proving the tool call reached the upstream
    request server-side) and then waits on ``release`` — set during teardown so
    a hung handler thread can never outlive the test. The events live on the
    server instance so this stateless handler can reach them.
    """

    def do_GET(self) -> None:
        server: Any = self.server
        if "health" in self.path:
            server.health_requested.set()
            # Bounded wait: teardown sets ``release``; the timeout is a
            # backstop so a test bug can't wedge the handler thread forever.
            server.release.wait(timeout=30)
        body = json.dumps(_CANNED_BODY).encode("utf-8")
        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except OSError:
            # The subprocess closes the connection when the cancelled tool
            # task tears down its httpx request; writing the late response
            # then fails. That's expected, not a test failure.
            pass

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002, ARG002 — http.server API
        return


class _CancellableMockHTTPSServer(_ThreadedMockHTTPSServer):
    """Hangs on ``stat/health`` until ``release`` is set; every other GET answers 200.

    ``health_requested`` signals the instant a health request begins blocking
    (proving the tool call reached the upstream request server-side).
    """

    def __init__(self, cert_path: Path, key_path: Path) -> None:
        super().__init__(_CancellableNetworkHandler, cert_path, key_path)
        self._server.health_requested = threading.Event()  # type: ignore[attr-defined]
        self._server.release = threading.Event()  # type: ignore[attr-defined]

    @property
    def health_requested(self) -> threading.Event:
        return self._server.health_requested  # type: ignore[attr-defined,no-any-return]

    @property
    def release(self) -> threading.Event:
        return self._server.release  # type: ignore[attr-defined,no-any-return]

    def _pre_shutdown(self) -> None:
        # Release any in-flight health handler so its thread can exit instead of
        # sitting on the 30s backstop.
        self._server.release.set()  # type: ignore[attr-defined]


@pytest.fixture
def cancellation_mock_server(tmp_path: Path) -> Iterator[_CancellableMockHTTPSServer]:
    """HTTPS mock that hangs on ``stat/health`` until ``release`` is set."""
    cert_pem, key_pem = _generate_self_signed_cert("127.0.0.1")
    cert_path = tmp_path / "server.pem"
    key_path = tmp_path / "server.key"
    cert_path.write_bytes(cert_pem)
    key_path.write_bytes(key_pem)

    server = _CancellableMockHTTPSServer(cert_path=cert_path, key_path=key_path)
    server.start()
    try:
        yield server
    finally:
        server.stop()


class TestStdioToolCallCancellation:
    """Cancel an in-flight ``tools/call`` over the real stdio JSON-RPC boundary.

    Closes the transport-level slice of §4 in #97 that the in-process
    ``test_cancellation.py`` suite cannot reach.
    """

    async def test_cancel_in_flight_tool_call_keeps_session_usable(
        self,
        cancellation_mock_server: _CancellableMockHTTPSServer,
    ) -> None:
        """A cancelled tool call must surface ``CancelledError`` and leave the
        session healthy enough to serve a follow-up request.

        Sequence: call ``unifi_network_get_health`` (the mock hangs on
        ``stat/health``); once the mock confirms the upstream request arrived,
        cancel the awaiting client task; assert ``CancelledError`` propagates;
        then issue a fresh ``tools/list`` on the same session and assert it
        still answers — i.e. one cancelled call doesn't wedge the transport.
        """
        command = shutil.which("unifi-mcp")
        if command is None:
            pytest.skip("unifi-mcp console script not on PATH; run `uv sync` first")

        with tempfile.TemporaryDirectory(prefix="unifi-mcp-stdio-cancel-") as cwd:
            transport = StdioTransport(
                command=command,
                args=[],
                env=_mode_flip_env(mode="readonly", network_port=cancellation_mock_server.port),
                cwd=cwd,
            )
            async with Client(transport) as client:
                assert client.is_connected(), "client failed to connect over stdio"

                tool_names = {t.name for t in await client.list_tools()}
                assert _HANGING_TOOL in tool_names, (
                    f"{_HANGING_TOOL!r} did not register; mock backend or env wiring is broken — "
                    f"got tools: {sorted(tool_names)!r}"
                )

                call_task = asyncio.create_task(client.call_tool(_HANGING_TOOL, {}))

                # Wait until the upstream request is genuinely in-flight
                # server-side before cancelling. Polling the threading.Event
                # from the loop is a cheap flag read.
                for _ in range(200):
                    if cancellation_mock_server.health_requested.is_set():
                        break
                    await asyncio.sleep(0.05)
                else:  # pragma: no cover — only hit if the call never dispatched
                    call_task.cancel()
                    pytest.fail("tool call never reached the upstream stat/health request")

                call_task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await call_task

                # The session must still be alive: a fresh request over the
                # same stdio connection has to succeed. If cancellation had
                # wedged the transport this would hang (caught by the suite
                # timeout) or raise a connection error.
                tools_after = await client.list_tools()
                assert _HANGING_TOOL in {t.name for t in tools_after}, (
                    "session unusable after cancelling an in-flight tool call"
                )

            assert not client.is_connected(), "client still connected after context exit"


# ── Concurrent tool calls over stdio ────────────────────────────────────────

# Each concurrent call invokes this read tool (``NetworkClient.get_health`` →
# ``GET stat/health``). Firing many at once drives many simultaneous GETs through
# the one ``httpx.AsyncClient`` the Network client re-uses, exercising the shared
# connection pool §4 of #97 flags as never stress-tested. It registers in
# readonly mode, so no write gate is involved.
_CONCURRENT_TOOL = "unifi_network_get_health"

# Number of tool calls to fire at once. Above httpx's one-live-connection default
# so genuine parallelism is exercised, yet far below its max_connections cap
# (100, unset here) so the pool itself is not the bottleneck.
_CONCURRENCY = 8

# Client-side bound on the rendezvous. With a healthy pool all calls arrive
# within milliseconds and the gather resolves at once; if the pool (or the
# server) serialised calls the rendezvous could never fill and the first handler
# would sit on its 30s backstop, so this shorter bound trips first — turning a
# silent slowdown into an explicit failure.
_RENDEZVOUS_TIMEOUT = 10.0


def _result_payload(result: Any) -> Any:
    """Return a tool result's structured payload (``structured_content`` then ``data``).

    ``Client.call_tool`` raises on a tool error, so any result reaching here is a
    success; ``is not None`` precedence (not ``or``) keeps legitimately empty
    payloads from being skipped.
    """
    structured = getattr(result, "structured_content", None)
    if structured is not None:
        return structured
    return getattr(result, "data", None)


class _RendezvousNetworkHandler(http.server.BaseHTTPRequestHandler):
    """Canned 200 for any GET, but ``stat/health`` requests rendezvous first.

    Each health request claims a unique marker, bumps a shared counter, and then
    blocks on a release Event; only once ``_CONCURRENCY`` of them have arrived
    does the last set the Event, freeing them all to answer together. Progress is
    therefore possible *only* if the requests are genuinely in flight at the same
    time — serialised calls would never reach the target count and would each sit
    on the backstop. The unique marker embedded in each response lets the test
    prove no response crossed between in-flight calls. The ``stat/sysinfo``
    startup probe takes neither branch, so the server boots without touching the
    rendezvous.
    """

    def do_GET(self) -> None:
        server: Any = self.server
        body_obj: Any = _CANNED_BODY
        if "health" in self.path:
            with server.arrival_lock:
                # Zero-pad to a fixed width so no marker is a substring of
                # another (``req-1`` ⊂ ``req-10``). The substring-based bijection
                # check below would silently miscount otherwise once
                # ``_CONCURRENCY`` reaches double digits. Three digits cover the
                # pool's 100 max_connections cap.
                marker = f"req-{server.marker_seq:03d}"
                server.marker_seq += 1
                server.issued_markers.append(marker)
                server.arrivals += 1
                if server.arrivals >= _CONCURRENCY:
                    server.all_arrived.set()
            # Backstop so a never-completing rendezvous can't wedge the handler
            # thread forever. Longer than the client-side ``_RENDEZVOUS_TIMEOUT``
            # so that bound is what fails the test on a serialising pool.
            server.all_arrived.wait(timeout=30)
            # Tag this response with its unique marker so the test can verify a
            # bijection between issued markers and client results — a crossed
            # response would duplicate one marker and drop another.
            body_obj = {"data": [{"version": "8.0.0", "marker": marker}], "meta": {"rc": "ok"}}
        body = json.dumps(body_obj).encode("utf-8")
        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except OSError:
            # On the failure path the client tears down before a backstop-
            # released handler writes its late response, closing the socket;
            # the write then fails. Expected during teardown, not a test failure.
            pass

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002, ARG002 — http.server API
        return


class _RendezvousMockHTTPSServer(_ThreadedMockHTTPSServer):
    """Holds ``stat/health`` GETs until ``_CONCURRENCY`` arrive, tagging each with a unique marker.

    ``issued_markers`` records the marker handed to each health response so the
    test can assert the markers map one-to-one onto the client results.
    """

    def __init__(self, cert_path: Path, key_path: Path) -> None:
        super().__init__(_RendezvousNetworkHandler, cert_path, key_path)
        self._server.arrival_lock = threading.Lock()  # type: ignore[attr-defined]
        self._server.arrivals = 0  # type: ignore[attr-defined]
        self._server.all_arrived = threading.Event()  # type: ignore[attr-defined]
        self._server.marker_seq = 0  # type: ignore[attr-defined]
        self._server.issued_markers = []  # type: ignore[attr-defined]

    @property
    def arrivals(self) -> int:
        count: int = self._server.arrivals  # type: ignore[attr-defined]
        return count

    @property
    def issued_markers(self) -> list[str]:
        markers: list[str] = self._server.issued_markers  # type: ignore[attr-defined]
        return markers

    def _pre_shutdown(self) -> None:
        # Release any handler still waiting on the rendezvous so its thread can
        # exit instead of sitting on the 30s backstop.
        self._server.all_arrived.set()  # type: ignore[attr-defined]


@pytest.fixture
def rendezvous_mock_server(tmp_path: Path) -> Iterator[_RendezvousMockHTTPSServer]:
    """HTTPS mock that holds ``stat/health`` GETs until ``_CONCURRENCY`` arrive."""
    cert_pem, key_pem = _generate_self_signed_cert("127.0.0.1")
    cert_path = tmp_path / "server.pem"
    key_path = tmp_path / "server.key"
    cert_path.write_bytes(cert_pem)
    key_path.write_bytes(key_pem)

    server = _RendezvousMockHTTPSServer(cert_path=cert_path, key_path=key_path)
    server.start()
    try:
        yield server
    finally:
        server.stop()


class TestStdioConcurrentToolCalls:
    """Fire many ``tools/call`` simultaneously over the real stdio boundary.

    Closes the "concurrent tool calls — no stress test" slice of §4 in #97. The
    Network client re-uses one ``httpx.AsyncClient`` across calls, so every
    concurrent tool call shares its connection pool; this proves the pool serves
    simultaneous in-flight requests without serialising or corrupting them.
    """

    async def test_concurrent_calls_share_pool_without_corruption(
        self,
        rendezvous_mock_server: _RendezvousMockHTTPSServer,
    ) -> None:
        """``_CONCURRENCY`` simultaneous calls must all complete with well-formed,
        uniquely-marked results, then leave the session usable.

        The mock answers a health request only once all ``_CONCURRENCY`` have
        arrived, so the gather can resolve *only* if the calls are genuinely
        concurrent through the shared pool — a serialising pool (or a server that
        handles ``tools/call`` one at a time) stalls the rendezvous and trips
        ``_RENDEZVOUS_TIMEOUT``. Each upstream response carries a unique marker;
        asserting the markers map one-to-one onto the results detects a response
        crossing between in-flight calls (which would duplicate one marker and
        drop another).
        """
        command = shutil.which("unifi-mcp")
        if command is None:
            pytest.skip("unifi-mcp console script not on PATH; run `uv sync` first")

        with tempfile.TemporaryDirectory(prefix="unifi-mcp-stdio-concurrent-") as cwd:
            transport = StdioTransport(
                command=command,
                args=[],
                env=_mode_flip_env(mode="readonly", network_port=rendezvous_mock_server.port),
                cwd=cwd,
            )
            async with Client(transport) as client:
                assert client.is_connected(), "client failed to connect over stdio"

                tool_names = {t.name for t in await client.list_tools()}
                assert _CONCURRENT_TOOL in tool_names, (
                    f"{_CONCURRENT_TOOL!r} did not register; mock backend or env wiring is broken — "
                    f"got tools: {sorted(tool_names)!r}"
                )

                tasks = [asyncio.create_task(client.call_tool(_CONCURRENT_TOOL, {})) for _ in range(_CONCURRENCY)]
                try:
                    results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=_RENDEZVOUS_TIMEOUT)
                except TimeoutError:
                    for task in tasks:
                        task.cancel()
                    pytest.fail(
                        f"{_CONCURRENCY} concurrent calls failed to rendezvous within "
                        f"{_RENDEZVOUS_TIMEOUT}s — only {rendezvous_mock_server.arrivals} of "
                        f"{_CONCURRENCY} requests reached the upstream; tool calls are being "
                        "serialised rather than sharing the connection pool"
                    )

                payloads = [_result_payload(r) for r in results]
                assert all(p is not None for p in payloads), (
                    f"a concurrent call returned an empty payload: {payloads!r}"
                )
                serialized = [json.dumps(p) for p in payloads]
                assert all("8.0.0" in s for s in serialized), (
                    f"a payload is not the canned health body — wrong response routed back: {serialized!r}"
                )
                # Each upstream health response carried a unique marker. A clean
                # run is a bijection: every issued marker appears in exactly one
                # result and every result carries exactly one marker. A response
                # crossing between in-flight calls would duplicate one marker and
                # drop another, breaking it. (Inputs are identical, so a per-call
                # marker isn't predictable client-side; the bijection is the
                # observable no-cross-talk property.)
                issued = rendezvous_mock_server.issued_markers
                assert len(issued) == _CONCURRENCY, f"expected {_CONCURRENCY} issued markers, got {issued!r}"
                for marker in issued:
                    hits = [s for s in serialized if marker in s]
                    assert len(hits) == 1, (
                        f"marker {marker!r} appeared in {len(hits)} results — a response crossed "
                        f"between in-flight calls: {serialized!r}"
                    )
                for serial in serialized:
                    present = [marker for marker in issued if marker in serial]
                    assert len(present) == 1, (
                        f"a result carried {len(present)} markers (expected exactly 1): {serial!r}"
                    )

                # The session must still be alive after the burst: a fresh
                # request over the same stdio connection has to succeed.
                tools_after = await client.list_tools()
                assert _CONCURRENT_TOOL in {t.name for t in tools_after}, (
                    "session unusable after a burst of concurrent tool calls"
                )

            assert not client.is_connected(), "client still connected after context exit"


# ── tools/list stability across a session ───────────────────────────────────

# Invoked between ``tools/list`` snapshots so the stability assertion spans real
# session activity, not just idle back-to-back listing. Read tool, registers in
# readonly mode.
_PROBE_TOOL = "unifi_network_get_health"


class _ToolListChangeRecorder(MessageHandler):
    """Records any ``notifications/tools/list_changed`` the server emits.

    A stable session must never emit one: a caching client only refetches
    ``tools/list`` on this notification, so a spurious emission would desync it.
    """

    def __init__(self) -> None:
        super().__init__()
        self.changes: list[mcp.types.ToolListChangedNotification] = []

    async def on_tool_list_changed(self, message: mcp.types.ToolListChangedNotification) -> None:
        self.changes.append(message)


def _tool_fingerprint(tools: list[mcp.types.Tool]) -> dict[str, str]:
    """Map each tool name to a canonical description + input-schema fingerprint.

    Comparing fingerprints rather than bare names means a silent description or
    schema change between snapshots fails the stability check too, not just a
    tool appearing or vanishing. ``sort_keys`` makes the schema serialisation
    order-independent so equal schemas always compare equal.
    """
    return {
        tool.name: json.dumps(
            {"description": tool.description, "inputSchema": tool.inputSchema},
            sort_keys=True,
        )
        for tool in tools
    }


class TestStdioToolListStability:
    """Repeated ``tools/list`` on one session must return an identical tool set.

    §4 of #97 flags that nothing pins the tool set as stable across a session.
    A real MCP client caches the list after ``initialize`` and only refreshes on
    a ``notifications/tools/list_changed``; a set that silently drifts between
    listings would desync those clients. This drives three snapshots over the
    real stdio boundary — two back to back and one after a tool call — and
    asserts all three are byte-for-byte identical.
    """

    async def test_tool_set_stable_across_session(
        self,
        network_mock_server: _NetworkMockHTTPSServer,
    ) -> None:
        """Three ``tools/list`` snapshots on one session must be identical, even
        with a tool call between the second and third — and the server must never
        emit a ``tools/list_changed`` notification during the stable session."""
        command = shutil.which("unifi-mcp")
        if command is None:
            pytest.skip("unifi-mcp console script not on PATH; run `uv sync` first")

        recorder = _ToolListChangeRecorder()
        with tempfile.TemporaryDirectory(prefix="unifi-mcp-stdio-toollist-") as cwd:
            transport = StdioTransport(
                command=command,
                args=[],
                env=_mode_flip_env(mode="readonly", network_port=network_mock_server.port),
                cwd=cwd,
            )
            async with Client(transport, message_handler=recorder) as client:
                assert client.is_connected(), "client failed to connect over stdio"

                first = _tool_fingerprint(await client.list_tools())
                # A non-empty tool set is what makes "stable" a real assertion;
                # an empty set would pass vacuously. This also catches a broken
                # mock backend or env wiring rather than silently testing nothing.
                assert _PROBE_TOOL in first, (
                    f"{_PROBE_TOOL!r} did not register; mock backend or env wiring is broken — "
                    f"got tools: {sorted(first)!r}"
                )

                second = _tool_fingerprint(await client.list_tools())

                # Exercise the session, then snapshot again: a tool call must not
                # perturb the advertised tool set.
                await client.call_tool(_PROBE_TOOL, {})
                third = _tool_fingerprint(await client.list_tools())

            assert first == second, "tool set changed between back-to-back tools/list calls over stdio"
            assert first == third, "tool set changed after a tool call within the same session"

        # The equality check proves the served set never drifted; this proves the
        # server also never *told* a client it changed. A caching client refetches
        # only on this notification, so a spurious emission would desync it even
        # while the set is stable.
        assert recorder.changes == [], (
            f"server emitted {len(recorder.changes)} tools/list_changed notification(s) during a "
            "stable session; a caching client would needlessly refetch the tool list"
        )
        assert not client.is_connected(), "client still connected after context exit"
