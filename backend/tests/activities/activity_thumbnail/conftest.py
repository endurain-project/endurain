"""An owner, a follower and a stranger, the shared activities the tests read, and a real tile server to render from."""

import socket
import ssl
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

import core.config as core_config
import modules.activities.activity.constants as activity_constants
import modules.activities.activity.schema as activity_schema
from tests._factories.activities import make_activity
from tests._factories.followers import make_follow
from tests._factories.server_settings import edit_server_settings
from tests._factories.users import make_user
from tests._helpers.stand_ins import TileServer


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
