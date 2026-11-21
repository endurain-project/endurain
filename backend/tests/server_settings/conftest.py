"""Fixtures for the server-settings tests: an administrator signed in on the production application."""

import socket
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import core.config as core_config
import modules.server_settings.schema as server_settings_schema
from tests._factories.users import PASSWORD, make_admin

API = core_config.ROOT_PATH
SETTINGS_URL = f"{API}/server-settings"
MAIL_URL = f"{API}/server-settings/email/settings"
STEP_UP = {"current_password": PASSWORD}

#: The host name the DNS fake resolves to a private address.
INTERNAL_HOST = "internal.example.org"
_PUBLIC_ADDRESS = "93.184.216.34"
_PRIVATE_ADDRESS = "10.0.0.5"


@pytest.fixture
def dns(monkeypatch) -> SimpleNamespace:
    """Resolve every host name to a public address, ``INTERNAL_HOST`` to a private one, and record the lookups.

    The resolver is a third party the checks on a saved URL or host ask; the lookups are what the test inspects.
    """
    real = socket.getaddrinfo
    state = SimpleNamespace(names=[], on_lookup=None)

    def resolve(name, *args, **kwargs):
        if not isinstance(name, str) or name == "localhost":
            return real(name, *args, **kwargs)
        state.names.append(name)
        if state.on_lookup is not None:
            state.on_lookup(name)
        address = _PRIVATE_ADDRESS if name == INTERNAL_HOST else _PUBLIC_ADDRESS
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 0))]

    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    return state


@pytest.fixture
def admin(committed_sessions):
    """A committed administrator with a local password."""
    with committed_sessions() as db:
        created = make_admin(db, timezone="UTC", preferred_language="en")
        db.commit()
    return created


@pytest.fixture
def admin_client(sign_in, admin) -> TestClient:
    """A client signed in as the administrator."""
    return sign_in(admin).client


def editable_settings(client: TestClient, **changes: object) -> dict:
    """The body of a ``PUT /server-settings`` that re-sends the stored settings, with the given changes."""
    current = client.get(SETTINGS_URL).json()
    body = {
        name: value for name, value in current.items() if name in server_settings_schema.ServerSettingsEdit.model_fields
    }
    return {**body, "step_up": None, **changes}


def put_settings(client: TestClient, *, at: int = 1, **changes: object):
    """Save the settings with the changes, holding the ETag of version ``at``."""
    return client.put(SETTINGS_URL, json=editable_settings(client, **changes), headers={"If-Match": f'"{at}"'})
