"""The property-test subtree uses the same offline DNS/TCP policy as unit tests."""

import socket

import pytest


def test_property_scope_refuses_unmocked_resolution():
    with pytest.raises(AssertionError, match="unmocked DNS/TCP access"):
        socket.getaddrinfo("fixture.invalid", 443)
