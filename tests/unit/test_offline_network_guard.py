"""Offline DNS/TCP vetoes and explicitly mocked HTTP positive controls."""

import socket

import httpx
import pytest
import respx


@pytest.mark.parametrize(
    "operation",
    [
        lambda: socket.create_connection(("127.0.0.1", 1)),
        lambda: socket.getaddrinfo("fixture.invalid", 443),
        lambda: socket.gethostbyname("fixture.invalid"),
        lambda: socket.gethostbyname_ex("fixture.invalid"),
    ],
    ids=["create-connection", "getaddrinfo", "gethostbyname", "gethostbyname-ex"],
)
def test_offline_dns_and_connection_operations_are_refused(operation):
    with pytest.raises(AssertionError, match="unmocked DNS/TCP access"):
        operation()


@pytest.mark.parametrize("method", ["connect", "connect_ex"])
def test_direct_tcp_connections_are_refused(method):
    with socket.socket() as sock, pytest.raises(AssertionError, match="unmocked DNS/TCP access"):
        getattr(sock, method)(("127.0.0.1", 1))


def test_unmocked_http_transport_refuses_instead_of_reaching_a_host():
    with httpx.Client(trust_env=False) as client, pytest.raises(AssertionError, match="unmocked DNS/TCP access"):
        client.get("http://127.0.0.1:1/synthetic")


@respx.mock
async def test_explicit_respx_mock_still_exercises_http_request_contract():
    route = respx.get("https://fixture.invalid/synthetic").respond(200, json={"ok": True})
    async with httpx.AsyncClient(trust_env=False) as client:
        result = await client.get("https://fixture.invalid/synthetic")
    assert result.json() == {"ok": True}
    assert route.call_count == 1


async def test_explicit_mock_transport_remains_usable():
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={"ok": True})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond), trust_env=False) as client:
        response = await client.get("https://fixture.invalid/synthetic")
    assert response.json() == {"ok": True}
    assert len(requests) == 1
    assert requests[0].url.path == "/synthetic"


@pytest.mark.parametrize("port", [0, -1, 65536, True, "443"])
def test_loopback_registration_requires_a_valid_integer_port(allow_loopback_tcp, port):
    with pytest.raises(ValueError, match="test-owned loopback TCP port"):
        allow_loopback_tcp(port)


def test_loopback_permission_is_limited_to_the_registered_host_and_port(allow_loopback_tcp):
    allow_loopback_tcp(65534)
    with socket.socket() as sock:
        for address in (("127.0.0.1", 1), ("192.0.2.1", 65534)):
            with pytest.raises(AssertionError, match="unmocked DNS/TCP access"):
                sock.connect(address)
    with pytest.raises(AssertionError, match="unmocked DNS/TCP access"):
        socket.create_connection(address=("127.0.0.1", 1))
