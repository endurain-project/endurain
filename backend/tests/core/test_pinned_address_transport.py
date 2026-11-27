"""Tests for the transport that dials only the addresses the SSRF guard checked."""

import socket
import threading
from collections.abc import Iterator
from contextlib import closing, contextmanager
from unittest.mock import patch

import httpx2
import pytest

import core.network as core_network


def _answers(*ips: str):
    # socket.getaddrinfo is process-wide, so the answer carries the port asked for: a connect that
    # resolved a name again would land here too.
    return patch(
        "core.network.socket.getaddrinfo",
        side_effect=lambda host, port, *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", (ip, port or 0)) for ip in ips
        ],
    )


def _allowlist(*entries: str):
    return patch.object(core_network.core_config.settings, "SSRF_ALLOWED_HOSTS", list(entries))


class _RecordingTransport(httpx2.BaseTransport):
    """Inner transport that records what it was asked to dial instead of connecting."""

    def __init__(self, failing_hosts: frozenset[str] = frozenset()) -> None:
        self.dialed: list[tuple[str, dict, str]] = []
        self._failing_hosts = failing_hosts

    def handle_request(self, request: httpx2.Request) -> httpx2.Response:
        self.dialed.append((request.url.host, dict(request.extensions), request.headers["host"]))
        if request.url.host in self._failing_hosts:
            raise httpx2.ConnectError("refused", request=request)
        return httpx2.Response(200, request=request)


def _client(inner: httpx2.BaseTransport) -> httpx2.Client:
    return httpx2.Client(transport=core_network.PinnedAddressTransport(purpose="test", transport=inner))


class TestPinnedAddressTransport:
    def test_dials_the_checked_address_even_if_the_name_later_resolves_privately(self):
        inner = _RecordingTransport()
        with (
            patch(
                "core.network.socket.getaddrinfo",
                side_effect=[
                    [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("8.8.8.8", 0))],
                    [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("169.254.169.254", 0))],
                ],
            ) as resolver,
            _allowlist(),
        ):
            _client(inner).get("https://idp.example.com/jwks")

        assert [host for host, _, _ in inner.dialed] == ["8.8.8.8"]
        assert resolver.call_count == 1

    def test_keeps_the_hostname_for_the_host_header_and_tls_server_name(self):
        inner = _RecordingTransport()
        with _answers("8.8.8.8"), _allowlist():
            response = _client(inner).get("https://idp.example.com:8443/jwks")

        _, extensions, host_header = inner.dialed[0]
        assert extensions["sni_hostname"] == "idp.example.com"
        assert host_header == "idp.example.com:8443"
        assert str(response.request.url) == "https://idp.example.com:8443/jwks"

    def test_refuses_a_private_address_without_dialing(self):
        inner = _RecordingTransport()
        with _answers("10.0.0.1"), _allowlist(), pytest.raises(httpx2.ConnectError) as exc:
            _client(inner).get("https://idp.example.com/jwks")

        assert "non-public" in str(exc.value)
        assert inner.dialed == []

    def test_refuses_one_private_answer_among_public_ones(self):
        inner = _RecordingTransport()
        with _answers("8.8.8.8", "127.0.0.1"), _allowlist(), pytest.raises(httpx2.ConnectError):
            _client(inner).get("https://idp.example.com/jwks")

        assert inner.dialed == []

    def test_refuses_plain_http_to_a_public_host(self):
        inner = _RecordingTransport()
        with _answers("8.8.8.8"), _allowlist(), pytest.raises(httpx2.ConnectError):
            _client(inner).get("http://idp.example.com/jwks")

        assert inner.dialed == []

    def test_dials_an_allowlisted_private_address(self):
        inner = _RecordingTransport()
        with _answers("10.0.0.5"), _allowlist("10.0.0.0/8"):
            _client(inner).get("http://idp.internal/jwks")

        assert inner.dialed[0][0] == "10.0.0.5"

    def test_falls_back_to_the_next_checked_address_when_one_does_not_connect(self):
        inner = _RecordingTransport(failing_hosts=frozenset({"8.8.8.8"}))
        with _answers("8.8.8.8", "8.8.4.4"), _allowlist():
            _client(inner).get("https://idp.example.com/jwks")

        assert [host for host, _, _ in inner.dialed] == ["8.8.8.8", "8.8.4.4"]

    def test_raises_the_connect_error_when_no_checked_address_connects(self):
        inner = _RecordingTransport(failing_hosts=frozenset({"8.8.8.8", "8.8.4.4"}))
        with _answers("8.8.8.8", "8.8.4.4"), _allowlist(), pytest.raises(httpx2.ConnectError):
            _client(inner).get("https://idp.example.com/jwks")


@contextmanager
def _local_server() -> Iterator[tuple[int, list[bytes]]]:
    requests: list[bytes] = []
    with closing(socket.socket()) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)

        def serve() -> None:
            conn, _ = listener.accept()
            with conn:
                requests.append(conn.recv(4096))
                conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok")

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        yield listener.getsockname()[1], requests
        thread.join(timeout=5)


def test_connects_to_the_pinned_address_and_sends_the_original_host_header():
    with (
        _local_server() as (port, requests),
        _answers("127.0.0.1"),
        _allowlist("127.0.0.0/8"),
        httpx2.Client(transport=core_network.PinnedAddressTransport(purpose="test")) as client,
    ):
        response = client.get(f"http://idp.internal:{port}/jwks")

    assert response.text == "ok"
    assert f"Host: idp.internal:{port}".encode() in requests[0]
