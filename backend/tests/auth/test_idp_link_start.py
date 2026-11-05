"""Starting an identity-provider link: the route authenticates, binds the browser and puts no credential in a URL."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import core.config as core_config
import core.database as core_database
import core.exceptions as core_exceptions
import modules.auth.account_security.identity_link_service as identity_link_service
import modules.auth.account_security.identity_links_router as identity_links_router
import modules.auth.dependencies as auth_dependencies
import modules.auth.identity_providers.contracts as idp_contracts
import modules.auth.identity_providers.dependencies as idp_dependencies

SESSION_ID = "11111111-2222-3333-4444-555555555555"
URL = core_config.ROOT_PATH + "/profile/identity-providers/3/link"


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(identity_links_router.router, prefix=core_config.ROOT_PATH + "/profile/identity-providers")
    core_exceptions.register_exception_handlers(app)
    app.dependency_overrides[core_database.get_db] = lambda: MagicMock()
    app.dependency_overrides[auth_dependencies.get_sub_from_access_token] = lambda: 7
    app.dependency_overrides[auth_dependencies.get_sid_from_access_token] = lambda: SESSION_ID
    app.dependency_overrides[auth_dependencies.check_scopes] = lambda: None
    app.dependency_overrides[auth_dependencies.get_step_up_attempts] = lambda: MagicMock()
    return TestClient(app)


def test_the_route_returns_the_url_and_binds_the_browser(client):
    flow = idp_contracts.BrowserFlowStart(
        authorization_url="https://idp.example.com/authorize", browser_binding="binding-secret"
    )
    with patch.object(identity_link_service, "start_idp_link", return_value=flow) as start:
        response = client.post(URL, json={"current_password": "pw", "redirect": "/settings/security"})

    assert response.status_code == 200
    assert response.json() == {"authorization_url": "https://idp.example.com/authorize"}
    assert response.cookies.get(idp_dependencies.BINDING_COOKIE_NAME) == "binding-secret"
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert start.call_args.args[0] == 3
    assert start.call_args.args[1].redirect == "/settings/security"
    assert start.call_args.args[3:5] == (7, SESSION_ID)


def test_the_old_token_route_and_unauthenticated_get_are_gone(client):
    assert client.post(URL + "/token", json={"current_password": "pw"}).status_code == 404
    assert client.get(URL, params={"link_token": "x"}).status_code == 405


@pytest.mark.parametrize(
    "body",
    [{"current_password": "pw", "redirect": ""}, {"current_password": "pw", "link_token": "x"}],
    ids=["empty-redirect", "unknown-field"],
)
def test_a_malformed_request_is_refused(client, body):
    with patch.object(identity_link_service, "start_idp_link") as start:
        response = client.post(URL, json=body)

    assert response.status_code == 422
    start.assert_not_called()


def test_a_refused_start_is_answered_as_a_problem(client):
    with patch.object(
        identity_link_service, "start_idp_link", side_effect=core_exceptions.ConflictError("already linked")
    ):
        response = client.post(URL, json={"current_password": "pw"})

    assert response.status_code == 409
