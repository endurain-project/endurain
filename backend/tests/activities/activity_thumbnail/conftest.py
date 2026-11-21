"""An owner, a follower and a stranger, the shared activities the tests read, and a real tile server to render from."""

import io
import socket
import ssl
import threading
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from PIL import Image

import core.config as core_config
import modules.activities.activity.constants as activity_constants
import modules.activities.activity.schema as activity_schema
from tests._factories.activities import make_activity
from tests._factories.followers import make_follow
from tests._factories.server_settings import edit_server_settings
from tests._factories.users import make_user


@pytest.fixture
def people(committed_sessions):
    """An owner, an accepted follower of the owner and a stranger, committed."""
    with committed_sessions() as db:
        owner = make_user(db, timezone="UTC")
        follower = make_user(db, timezone="UTC")
        stranger = make_user(db, timezone="UTC")
        make_follow(db, follower.id, owner.id, accepted=True)
        db.commit()
    return SimpleNamespace(owner=owner, follower=follower, stranger=stranger)


@pytest.fixture
def make_owned_activity(committed_sessions, people) -> Callable[..., activity_schema.ActivityRead]:
    """Return a function that commits one of the owner's activities, with the children its ``stage`` callable adds."""

    def make(
        visibility: activity_constants.ActivityVisibility = activity_constants.ActivityVisibility.PRIVATE,
        stage: Callable[..., object] | None = None,
        **overrides: object,
    ) -> activity_schema.ActivityRead:
        with committed_sessions() as db:
            activity = make_activity(db, people.owner.id, visibility=visibility, **overrides)
            if stage is not None:
                stage(db, activity)
            db.commit()
        return activity

    return make


@pytest.fixture
def public_links(committed_sessions) -> None:
    """Turn public shareable links on for the server."""
    with committed_sessions() as db:
        edit_server_settings(db, public_shareable_links=True)
        db.commit()


class TileServer:
    """A real HTTP tile server on the loopback interface, answering every tile with a small PNG.

    Attributes:
        port: The port it listens on.
        status: The status every tile request is answered with.
        requests: ``(path, headers)`` of each request, in arrival order.
        on_request: Called with the request path before the answer, for a test that changes the world mid-render.
    """

    def __init__(self, tls: ssl.SSLContext | None = None) -> None:
        buffer = io.BytesIO()
        Image.new("RGB", (256, 256), (180, 200, 220)).save(buffer, "PNG")
        self._tile = buffer.getvalue()
        self.status = 200
        self.requests: list[tuple[str, dict[str, str]]] = []
        self.on_request: Callable[[str], None] | None = None
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                outer.requests.append((self.path, {k.lower(): v for k, v in self.headers.items()}))
                if outer.on_request is not None:
                    outer.on_request(self.path)
                self.send_response(outer.status)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(outer._tile)))
                self.end_headers()
                self.wfile.write(outer._tile)

            def log_message(self, *args: object) -> None:
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.scheme = "http"
        if tls is not None:
            self._server.socket = tls.wrap_socket(self._server.socket, server_side=True)
            self.scheme = "https"
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def url(self, host: str = "127.0.0.1") -> str:
        """Return the tile URL template of this server under a host name."""
        return f"{self.scheme}://{host}:{self.port}/{{z}}/{{x}}/{{y}}.png"

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)


def _self_signed_certificate(directory: Path, host: str) -> Path:
    """Write a self-signed certificate and key for ``host`` into one PEM file and return its path."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, host)])
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(host)]), critical=False)
        .sign(key, hashes.SHA256())
    )
    path = directory / "tiles.pem"
    path.write_bytes(
        key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        + certificate.public_bytes(serialization.Encoding.PEM)
    )
    return path


def _serve(monkeypatch, tls: ssl.SSLContext | None) -> Iterator[TileServer]:
    """Run a tile server the outbound-network policy allows, with the host names the tests use resolving to it."""
    server = TileServer(tls)
    server.start()
    monkeypatch.setattr(core_config.settings, "SSRF_ALLOWED_HOSTS", ["127.0.0.0/8"])
    real_getaddrinfo = socket.getaddrinfo
    names = {"tiles.stadiamaps.com", "notstadiamaps.com", "tiles.example.test"}

    def getaddrinfo(host, *args, **kwargs):
        return real_getaddrinfo("127.0.0.1" if host in names else host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    yield server
    server.stop()


@pytest.fixture
def tile_server(monkeypatch) -> Iterator[TileServer]:
    """A loopback tile server over plain HTTP."""
    yield from _serve(monkeypatch, None)


@pytest.fixture
def tls_tile_server(monkeypatch, tmp_path) -> Iterator[TileServer]:
    """A loopback tile server over TLS, with a certificate for ``tiles.example.test`` the process trusts."""
    pem = _self_signed_certificate(tmp_path, "tiles.example.test")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(pem)
    monkeypatch.setenv("SSL_CERT_FILE", str(pem))
    yield from _serve(monkeypatch, context)
