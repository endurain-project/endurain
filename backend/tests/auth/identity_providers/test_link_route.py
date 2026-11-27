"""The route a native app's system browser opens to start a link: it sets the binding and redirects to the provider."""

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jasil.backends.state_memory import MemoryState
from pydantic import ValidationError

import core.config as core_config
import core.database as core_db
import core.dependencies as core_dependencies
import core.exceptions as core_exceptions
import modules.auth.identity_providers.contracts as idp_contracts
import modules.auth.identity_providers.dependencies as idp_dependencies
import modules.auth.identity_providers.integration_service as idp_integration
import modules.auth.identity_providers.public_router as public_router

PREFIX = core_config.ROOT_PATH + "/public/idp"
PROVIDER_URL = "https://idp.example.com/authorize?state=abc"


@pytest.fixture
def state():
    return MemoryState()


@pytest.fixture
def client(state):
    app = FastAPI()
    core_exceptions.register_exception_handlers(app)
    app.include_router(public_router.router, prefix=PREFIX)
    app.dependency_overrides[core_db.get_db] = lambda: MagicMock()
    app.dependency_overrides[core_dependencies.get_platform_state] = lambda: state
    return TestClient(app, follow_redirects=False)


def _ticket(state, binding="binding-secret"):
    url = idp_integration.issue_link_ticket(state, PROVIDER_URL, binding)
    return url.rsplit("ticket=", 1)[1]


def test_the_ticket_binds_the_browser_and_sends_it_to_the_provider(client, state):
    response = client.get(f"{PREFIX}/link", params={"ticket": _ticket(state)})

    assert response.status_code == 307
    assert response.headers["location"] == PROVIDER_URL
    assert response.cookies.get(idp_dependencies.BINDING_COOKIE_NAME) == "binding-secret"
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=lax" in cookie


def test_a_ticket_starts_one_link(client, state):
    ticket = _ticket(state)

    assert client.get(f"{PREFIX}/link", params={"ticket": ticket}).status_code == 307
    second = client.get(f"{PREFIX}/link", params={"ticket": ticket})

    assert second.status_code == 400
    assert idp_dependencies.BINDING_COOKIE_NAME not in second.cookies


def test_an_unknown_ticket_is_refused_without_a_cookie(client):
    response = client.get(f"{PREFIX}/link", params={"ticket": "unknown"})

    assert response.status_code == 400
    assert "set-cookie" not in response.headers


def test_a_request_without_a_ticket_is_malformed(client):
    assert client.get(f"{PREFIX}/link").status_code == 422


def test_the_ticket_url_is_an_absolute_address_of_this_route(state):
    url = idp_integration.issue_link_ticket(state, PROVIDER_URL, "binding")

    assert url.startswith(f"{core_config.settings.ENDURAIN_HOST}{PREFIX}/link?ticket=")


def test_the_ticket_contract_is_frozen():
    ticket = idp_contracts.LinkTicket(authorization_url=PROVIDER_URL, browser_binding="b")

    with pytest.raises(ValidationError):
        ticket.browser_binding = "other"  # type: ignore[misc]
