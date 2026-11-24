"""Fixtures for the account-security tests."""

import socket

import pytest

#: The address the DNS fake resolves every host name to: a public one, so the provider URL checks pass.
_PUBLIC_ADDRESS = "93.184.216.34"


@pytest.fixture(autouse=True)
def _public_dns(monkeypatch) -> None:
    """Resolve every host name to a public address: DNS is a third party, and an identity-provider URL is checked."""
    real = socket.getaddrinfo

    def resolve(name, *args, **kwargs):
        if not isinstance(name, str) or name == "localhost":
            return real(name, *args, **kwargs)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (_PUBLIC_ADDRESS, 0))]

    monkeypatch.setattr(socket, "getaddrinfo", resolve)
