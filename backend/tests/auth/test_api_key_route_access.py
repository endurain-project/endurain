"""An API key reaches every route whose scopes it holds, and never one that needs a signed-in session."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import APIRouter, Depends, FastAPI, Security
from fastapi.testclient import TestClient

import core.database as core_database
import core.exceptions as core_exceptions
import modules.auth.dependencies as auth_dependencies
from modules.auth.contracts import AccessTokenCred, ApiKeyCred, Principal
from tests._helpers.auth import MOCK_USER_ID

_RESOLVE_KEY = "modules.auth.dependencies.authentication_integration.resolve_from_api_key"
_RESOLVE_TOKEN = "modules.auth.dependencies.authentication_integration.resolve_from_access_token"


def _principal(credential, scopes: set[str]) -> Principal:
    return Principal(
        user_id=MOCK_USER_ID,
        username="runner",
        email="runner@example.com",
        is_active=True,
        is_superuser=False,
        scopes=frozenset(scopes),
        credential=credential,
    )


def _key(scopes: set[str]) -> Principal:
    return _principal(ApiKeyCred(api_key_id="key-1", key_prefix="abcd1234"), scopes)


def _token(scopes: set[str]) -> Principal:
    return _principal(AccessTokenCred(session_id="sid-1"), scopes)


@pytest.fixture
def client() -> TestClient:
    router = APIRouter()

    @router.get("/gears", dependencies=[Security(auth_dependencies.check_scopes, scopes=["gears:read"])])
    def read_gears(user_id: auth_dependencies.CurrentUserId, scopes: auth_dependencies.CurrentScopes) -> dict:
        return {"user_id": user_id, "scopes": sorted(scopes)}

    @router.get("/ticket", dependencies=[Security(auth_dependencies.check_scopes, scopes=["notifications:read"])])
    def issue_ticket(session_id: auth_dependencies.CurrentSessionId) -> dict:
        return {"session_id": session_id}

    app = FastAPI()
    core_exceptions.register_exception_handlers(app)
    app.include_router(router, dependencies=[Depends(auth_dependencies.authenticate)])
    app.dependency_overrides[core_database.get_db] = lambda: MagicMock()
    return TestClient(app)


class TestApiKeyReachesItsScopes:
    def test_a_key_holding_the_routes_scope_is_served_as_its_owner(self, client):
        with patch(_RESOLVE_KEY, return_value=_key({"gears:read"})):
            response = client.get("/gears", headers={"X-API-Key": "endurain_key"})

        assert response.status_code == 200
        assert response.json() == {"user_id": str(MOCK_USER_ID), "scopes": ["gears:read"]}

    def test_a_key_without_the_routes_scope_is_403_insufficient_scope(self, client):
        with patch(_RESOLVE_KEY, return_value=_key({"health:read"})):
            response = client.get("/gears", headers={"X-API-Key": "endurain_key"})

        assert response.status_code == 403
        assert 'error="insufficient_scope"' in response.headers["WWW-Authenticate"]
        assert response.json()["missing_scopes"] == ["gears:read"]

    def test_a_bearer_token_still_reaches_the_route(self, client):
        with patch(_RESOLVE_TOKEN, return_value=_token({"gears:read"})):
            response = client.get("/gears", headers={"Authorization": "Bearer token"})

        assert response.status_code == 200

    def test_a_bearer_token_wins_over_an_api_key(self, client):
        with patch(_RESOLVE_TOKEN, return_value=_token({"gears:read"})), patch(_RESOLVE_KEY) as resolve_key:
            response = client.get("/gears", headers={"Authorization": "Bearer token", "X-API-Key": "endurain_key"})

        assert response.status_code == 200
        resolve_key.assert_not_called()

    def test_a_request_without_credentials_is_401(self, client):
        response = client.get("/gears")

        assert response.status_code == 401

    def test_the_credential_is_resolved_once_per_request(self, client):
        with patch(_RESOLVE_KEY, return_value=_key({"gears:read"})) as resolve_key:
            client.get("/gears", headers={"X-API-Key": "endurain_key"})

        resolve_key.assert_called_once()


class TestSessionOnlyRoutes:
    def test_a_key_is_refused_with_403_where_a_signed_in_session_is_needed(self, client):
        with patch(_RESOLVE_KEY, return_value=_key({"notifications:read"})):
            response = client.get("/ticket", headers={"X-API-Key": "endurain_key"})

        assert response.status_code == 403
        assert "signed-in session" in response.json()["detail"]

    def test_a_session_token_gets_its_session_id(self, client):
        with patch(_RESOLVE_TOKEN, return_value=_token({"notifications:read"})):
            response = client.get("/ticket", headers={"Authorization": "Bearer token"})

        assert response.json() == {"session_id": "sid-1"}
