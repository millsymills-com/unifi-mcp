"""Unit tests for the ``verify_ssl`` code path in ``BaseUniFiClient``.

All live runs ship ``UNIFI_*_VERIFY_SSL=false`` because UniFi controllers
present self-signed certs by default, so the production-shaped ``verify=True``
path has no integration coverage. A regression that quietly disabled
verification entirely (e.g. forcing ``verify=False`` regardless of the
constructor argument) would not be caught by ``respx``-backed tests because
``respx`` intercepts at the transport layer and never performs a real TLS
handshake.

This module spins up a local HTTPS server backed by an in-process self-signed
CA + leaf cert, then drives ``BaseUniFiClient`` through four branches:

1. ``verify_ssl=<CA-bundle-path>`` -> request succeeds (custom trust honored).
2. ``verify_ssl=True`` with system default trust -> request raises a
   TLS-related ``UniFiConnectionError`` (httpx maps SSL handshake failures
   to ``ConnectError``, which the client maps to its own type). Must not
   silently succeed.
3. ``verify_ssl=False`` -> request succeeds (sanity check existing behavior).
4. ``verify_ssl=<root-only bundle>`` against a root->intermediate->leaf chain
   -> request succeeds only if the client builds the chain from the
   server-presented intermediate; a paired negative control omits the
   intermediate and must fail.

See #248.
"""

from __future__ import annotations

import datetime
import http.server
import json
import ssl
import threading
from contextlib import contextmanager
from ipaddress import IPv4Address
from typing import TYPE_CHECKING, Any

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from unifi_mcp.clients.base import BaseUniFiClient
from unifi_mcp.errors import UniFiConnectionError

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

_CANNED_BODY = {"data": [{"_id": "abc", "name": "fake-device"}], "meta": {"rc": "ok"}}


class _ConcreteClient(BaseUniFiClient):
    """Minimal concrete subclass so the abstract base can be instantiated."""

    async def validate_connection(self) -> bool:
        return True


def _new_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _ca_key_usage() -> x509.KeyUsage:
    return x509.KeyUsage(
        digital_signature=False,
        content_commitment=False,
        key_encipherment=False,
        data_encipherment=False,
        key_agreement=False,
        key_cert_sign=True,
        crl_sign=True,
        encipher_only=False,
        decipher_only=False,
    )


def _build_ca_cert(
    *,
    subject: x509.Name,
    issuer: x509.Name,
    public_key: rsa.RSAPublicKey,
    signing_key: rsa.RSAPrivateKey,
    now: datetime.datetime,
    path_length: int | None,
    authority_ski: x509.SubjectKeyIdentifier | None = None,
) -> x509.Certificate:
    """Build a CA certificate (``ca=True``) shared by the self-signed and cross-signed cases.

    Self-signed roots pass ``issuer == subject``, ``signing_key`` matching
    ``public_key``, and no ``authority_ski``. A cross-signed intermediate passes
    its parent's name as ``issuer``, the parent's key as ``signing_key``, and the
    parent's SKI as ``authority_ski`` so an Authority Key Identifier is emitted.
    """
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(public_key)
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=1))
        .not_valid_after(now + datetime.timedelta(hours=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=path_length), critical=True)
        .add_extension(_ca_key_usage(), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(public_key), critical=False)
    )
    if authority_ski is not None:
        builder = builder.add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_subject_key_identifier(authority_ski),
            critical=False,
        )
    return builder.sign(signing_key, hashes.SHA256())


def _sign_leaf_cert(
    *,
    server_ip: str,
    issuer: x509.Name,
    public_key: rsa.RSAPublicKey,
    signing_key: rsa.RSAPrivateKey,
    now: datetime.datetime,
    authority_ski: x509.SubjectKeyIdentifier,
) -> x509.Certificate:
    """Build a leaf (``ca=False``) cert with a ``server_ip`` SAN, signed by its issuer.

    Shared by the two- and three-tier generators: in the two-tier case the
    issuer is the self-signed CA; in the three-tier case it is the intermediate.
    """
    return (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, server_ip)]))
        .issuer_name(issuer)
        .public_key(public_key)
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=1))
        .not_valid_after(now + datetime.timedelta(hours=1))
        .add_extension(x509.SubjectAlternativeName([x509.IPAddress(IPv4Address(server_ip))]), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(public_key), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_subject_key_identifier(authority_ski), critical=False)
        .sign(signing_key, hashes.SHA256())
    )


def _generate_ca_and_server_cert(
    server_ip: str,
) -> tuple[bytes, bytes, bytes]:
    """Generate a self-signed CA, a leaf cert with ``server_ip`` SAN, and the leaf key.

    Returns ``(ca_pem, server_cert_pem, server_key_pem)`` ready to be written
    to disk and passed to ``ssl.SSLContext.load_cert_chain`` / httpx's
    ``verify=<path>`` parameter.
    """
    ca_key = _new_key()
    ca_subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "unifi-mcp-test-ca")])
    now = datetime.datetime.now(datetime.UTC)
    ca_ski = x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key())
    ca_cert = _build_ca_cert(
        subject=ca_subject,
        issuer=ca_subject,
        public_key=ca_key.public_key(),
        signing_key=ca_key,
        now=now,
        path_length=None,
    )

    server_key = _new_key()
    server_cert = _sign_leaf_cert(
        server_ip=server_ip,
        issuer=ca_subject,
        public_key=server_key.public_key(),
        signing_key=ca_key,
        now=now,
        authority_ski=ca_ski,
    )

    ca_pem = ca_cert.public_bytes(serialization.Encoding.PEM)
    server_cert_pem = server_cert.public_bytes(serialization.Encoding.PEM)
    server_key_pem = server_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return ca_pem, server_cert_pem, server_key_pem


def _generate_three_tier_chain(server_ip: str) -> tuple[bytes, bytes, bytes, bytes]:
    """Generate a root CA -> intermediate CA -> leaf chain bound to ``server_ip``.

    Returns ``(root_pem, intermediate_pem, leaf_cert_pem, leaf_key_pem)``: a
    leaf signed by an intermediate, the intermediate signed by a self-issued
    root. Unlike ``_generate_ca_and_server_cert`` (leaf signed directly by the
    trust anchor), this three-tier shape forces a client to build the chain
    from the server-presented intermediate up to a root-only trust anchor.
    """
    now = datetime.datetime.now(datetime.UTC)

    root_key = _new_key()
    root_subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "unifi-mcp-test-root-ca")])
    root_ski = x509.SubjectKeyIdentifier.from_public_key(root_key.public_key())
    root_cert = _build_ca_cert(
        subject=root_subject,
        issuer=root_subject,
        public_key=root_key.public_key(),
        signing_key=root_key,
        now=now,
        path_length=None,
    )

    int_key = _new_key()
    int_subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "unifi-mcp-test-intermediate-ca")])
    int_ski = x509.SubjectKeyIdentifier.from_public_key(int_key.public_key())
    int_cert = _build_ca_cert(
        subject=int_subject,
        issuer=root_subject,
        public_key=int_key.public_key(),
        signing_key=root_key,
        now=now,
        # path_length=0: this intermediate may sign leaves but no further CAs.
        path_length=0,
        authority_ski=root_ski,
    )

    leaf_key = _new_key()
    leaf_cert = _sign_leaf_cert(
        server_ip=server_ip,
        issuer=int_subject,
        public_key=leaf_key.public_key(),
        signing_key=int_key,
        now=now,
        authority_ski=int_ski,
    )

    enc = serialization.Encoding.PEM
    leaf_key_pem = leaf_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return (
        root_cert.public_bytes(enc),
        int_cert.public_bytes(enc),
        leaf_cert.public_bytes(enc),
        leaf_key_pem,
    )


class _CannedJSONHandler(http.server.BaseHTTPRequestHandler):
    """Returns a canned UniFi-shaped JSON body for any GET; suppresses logs."""

    def do_GET(self) -> None:
        body = json.dumps(_CANNED_BODY).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002, ARG002 — http.server API
        # Suppress stderr noise; tests assert on client behaviour, not server logs.
        return


class _LocalHTTPSServer:
    """Background thread running an ``http.server`` with TLS wrapping.

    Bound to ``127.0.0.1`` on an OS-assigned port (bind to port 0, read back).
    The server's ``SSLContext`` is built from the leaf cert + key pair signed
    by the in-test CA so a client trusting that CA can complete the handshake.
    """

    def __init__(self, cert_path: Path, key_path: Path) -> None:
        self._server = http.server.HTTPServer(("127.0.0.1", 0), _CannedJSONHandler)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))
        self._server.socket = ctx.wrap_socket(self._server.socket, server_side=True)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def port(self) -> int:
        port: int = self._server.server_address[1]
        return port

    @property
    def base_url(self) -> str:
        return f"https://127.0.0.1:{self.port}"

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)


@contextmanager
def _running_https_server(cert_pem: bytes, key_pem: bytes, tmp_path: Path, *, name: str) -> Iterator[_LocalHTTPSServer]:
    """Start a local HTTPS server presenting ``cert_pem`` and tear it down on exit.

    ``cert_pem`` is whatever the server should send during the handshake — a
    bare leaf, or a leaf concatenated with its issuing intermediate (standard
    chain order, leaf first). ``name`` disambiguates the on-disk PEM filenames
    so a single test can stand up more than one server without clobbering.
    """
    cert_path = tmp_path / f"{name}-cert.pem"
    key_path = tmp_path / f"{name}-key.pem"
    cert_path.write_bytes(cert_pem)
    key_path.write_bytes(key_pem)
    server = _LocalHTTPSServer(cert_path=cert_path, key_path=key_path)
    server.start()
    try:
        yield server
    finally:
        server.stop()


@pytest.fixture
def tls_server(tmp_path: Path) -> Iterator[tuple[_LocalHTTPSServer, Path]]:
    """Stand up a local HTTPS server signed by an in-test CA.

    Yields the running server and the path to the CA-bundle PEM. Both are torn
    down at the end of the test so successive runs in the same process don't
    leak threads or sockets.
    """
    # SAN binds to the loopback IP, not a port, so the HTTPS server is free to
    # pick whichever ephemeral port the OS hands out.
    ca_pem, server_cert_pem, server_key_pem = _generate_ca_and_server_cert("127.0.0.1")

    ca_path = tmp_path / "ca.pem"
    ca_path.write_bytes(ca_pem)

    with _running_https_server(server_cert_pem, server_key_pem, tmp_path, name="tls-server") as server:
        yield server, ca_path


class TestVerifySslTrue:
    """``verify_ssl`` accepts a path to a custom CA bundle.

    httpx forwards path-typed values straight to ssl's ``load_verify_locations``,
    so an operator can ship a private-CA bundle file and the client honours it.
    """

    async def test_custom_ca_bundle_path_completes_handshake(
        self,
        tls_server: tuple[_LocalHTTPSServer, Path],
    ) -> None:
        server, ca_path = tls_server
        # ``verify_ssl`` is typed ``bool`` on the constructor (production callers
        # only ever pass bools from ``UniFiConfig``), but the value flows straight
        # through to httpx, which also accepts a CA-bundle path string. Casting
        # via ``Any`` keeps this test honest without widening the public type.
        verify_arg: Any = str(ca_path)
        client = _ConcreteClient(
            base_url=server.base_url,
            api_key="test-key",
            verify_ssl=verify_arg,
            timeout=5,
            max_retries=1,
        )
        try:
            result = await client.get("any-path")
            assert result == _CANNED_BODY
        finally:
            await client.close()


class TestVerifySslTrueWithoutCustomCa:
    """``verify_ssl=True`` with the system default trust store rejects our self-signed cert.

    httpx maps SSL handshake failures to ``httpx.ConnectError``, which
    ``BaseUniFiClient._request`` then maps to ``UniFiConnectionError``. The
    important property is *not silently succeed*: a regression that disabled
    verification would let the request through and the body would deserialize.
    """

    async def test_system_trust_rejects_self_signed_cert(
        self,
        tls_server: tuple[_LocalHTTPSServer, Path],
    ) -> None:
        server, _ca_path = tls_server
        # ``verify_ssl=True`` -> httpx builds a default SSLContext that consults
        # the system CA store, which does NOT contain our in-test CA.
        client = _ConcreteClient(
            base_url=server.base_url,
            api_key="test-key",
            verify_ssl=True,
            timeout=5,
            max_retries=1,
        )
        try:
            with pytest.raises(UniFiConnectionError) as exc_info:
                await client.get("any-path")
            # Sanity-check the error chain points at TLS: the underlying cause
            # should be an httpx ConnectError wrapping an ssl.SSLError.
            inner = exc_info.value.__cause__
            assert inner is not None, "expected wrapped httpx exception in __cause__"
            assert _exception_chain_mentions_tls(inner), (
                f"expected TLS verification failure in exception chain; got {inner!r}"
            )
        finally:
            await client.close()


class TestVerifySslFalse:
    """``verify_ssl=False`` skips chain validation entirely — sanity check.

    All current live runs depend on this branch; if it broke, every deployment
    would lose its API surface. Keep a smoke test guarding it.
    """

    async def test_verify_disabled_completes_handshake(
        self,
        tls_server: tuple[_LocalHTTPSServer, Path],
    ) -> None:
        server, _ca_path = tls_server
        client = _ConcreteClient(
            base_url=server.base_url,
            api_key="test-key",
            verify_ssl=False,
            timeout=5,
            max_retries=1,
        )
        try:
            result = await client.get("any-path")
            assert result == _CANNED_BODY
        finally:
            await client.close()


class TestVerifySslIntermediateChain:
    """``verify_ssl=<root-only bundle>`` must validate a full root->intermediate->leaf chain.

    Controllers fronted by a real PKI (Let's Encrypt, a corporate CA) present a
    leaf signed by an *intermediate*, and the trust anchor shipped to the client
    is the *root* only — the client builds the chain from the intermediate the
    server presents. The two-tier verify_ssl tests sign the leaf directly with
    the trust anchor, so a regression in intermediate-chain building (which only
    manifests against a publicly-rooted cert) would slip through them.

    Two tests pin the three-tier path: the positive case proves chain building
    works against a root-only bundle, and the negative case (server omits the
    intermediate) proves the positive one genuinely required the intermediate
    rather than passing via some lenient fallback.

    The positive case is parametrized over how the server orders the CA certs
    *after* the leaf. The leaf must come first on the wire (it holds the key the
    server presents — ``ssl.load_cert_chain`` rejects any other first cert with
    ``KEY_VALUES_MISMATCH``), but real controllers behind a proxy often append
    the root or emit the trailing CA certs out of order. OpenSSL's path builder
    treats those trailing certs as an unordered pool, so all three orderings
    must validate against the same root-only bundle.
    """

    @pytest.mark.parametrize(
        "trailing_order",
        [
            pytest.param(("intermediate",), id="canonical"),
            pytest.param(("intermediate", "root"), id="root-appended"),
            pytest.param(("root", "intermediate"), id="ca-out-of-order"),
        ],
    )
    async def test_full_chain_validates_against_root_only_bundle(
        self,
        tmp_path: Path,
        trailing_order: tuple[str, ...],
    ) -> None:
        root_pem, intermediate_pem, leaf_pem, leaf_key_pem = _generate_three_tier_chain("127.0.0.1")
        root_path = tmp_path / "root.pem"
        root_path.write_bytes(root_pem)

        # Leaf always first (server key matches it); the trailing CA certs vary
        # per param. The client trusts only the root, so a working chain builder
        # must bridge the gap regardless of trailing-cert order.
        trailing_pems = {"intermediate": intermediate_pem, "root": root_pem}
        server_chain_pem = leaf_pem + b"".join(trailing_pems[name] for name in trailing_order)
        with _running_https_server(server_chain_pem, leaf_key_pem, tmp_path, name="full-chain") as server:
            verify_arg: Any = str(root_path)
            client = _ConcreteClient(
                base_url=server.base_url,
                api_key="test-key",
                verify_ssl=verify_arg,
                timeout=5,
                max_retries=1,
            )
            try:
                result = await client.get("any-path")
                assert result == _CANNED_BODY
            finally:
                await client.close()

    async def test_missing_intermediate_breaks_chain(self, tmp_path: Path) -> None:
        root_pem, _intermediate_pem, leaf_pem, leaf_key_pem = _generate_three_tier_chain("127.0.0.1")
        root_path = tmp_path / "root.pem"
        root_path.write_bytes(root_pem)

        # Server presents the leaf ONLY — no intermediate. Trusting just the
        # root, the client cannot bridge leaf -> root, so verification must
        # fail. This control proves the positive test above exercised real
        # intermediate-chain building, not a lenient fallback that would also
        # accept an incomplete chain.
        with _running_https_server(leaf_pem, leaf_key_pem, tmp_path, name="leaf-only") as server:
            verify_arg: Any = str(root_path)
            client = _ConcreteClient(
                base_url=server.base_url,
                api_key="test-key",
                verify_ssl=verify_arg,
                timeout=5,
                # A TLS failure maps to ConnectError, which is retryable; max_retries=1
                # collapses tenacity to one attempt so the test fails fast without backoff.
                max_retries=1,
            )
            try:
                with pytest.raises(UniFiConnectionError) as exc_info:
                    await client.get("any-path")
                inner = exc_info.value.__cause__
                assert inner is not None, "expected wrapped httpx exception in __cause__"
                assert _exception_chain_mentions_tls(inner), (
                    f"expected TLS chain-build failure in exception chain; got {inner!r}"
                )
            finally:
                await client.close()


def _exception_chain_mentions_tls(exc: BaseException) -> bool:
    """Walk ``__cause__``/``__context__`` and look for a TLS-flavoured error.

    httpx wraps the stdlib ``ssl.SSLError`` (or ``ssl.SSLCertVerificationError``)
    inside its own ``ConnectError`` when verification fails. We assert on the
    string form because the precise chain layout differs across httpx versions.
    """
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, ssl.SSLError):
            return True
        message = f"{type(current).__name__}: {current}"
        if any(token in message for token in ("CERTIFICATE_VERIFY_FAILED", "self-signed", "self signed", "SSL")):
            return True
        current = current.__cause__ or current.__context__
    return False
