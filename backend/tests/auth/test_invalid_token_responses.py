"""HTTP-level tests that only bearer-token failures answer 401 with the ``invalid-token`` problem type."""

from unittest.mock import MagicMock

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

import core.database as core_database
import core.exceptions as core_exceptions
import modules.auth.account_security.audit_actions as account_security_audit_actions
import modules.auth.account_security.step_up_service as step_up_service
import modules.auth.dependencies as auth_dependencies

INVALID_TOKEN = "urn:endurain:error:invalid-token"
UNAUTHORIZED = "urn:endurain:error:unauthorized"
# Three-part JWT signed with a different secret and already expired.
STALE_JWT = (
    "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9."
    "eyJzaWQiOiJzZXNzaW9uLWlkIiwic3ViIjoxLCJpYXQiOjE3NTk5NTMxODUsIm5iZiI6MTc1OTk1MzE4NSwiZXhwIjoxNzU5OTU0MDg1fQ."
    "VSizGzvIIi_EJYD_YmfZBEBE_9aJbhLW-25cD1kEOeM"
)


class _Store:
    """Step-up lockout store that never locks out."""

    def is_locked_out(self, key):
        return False

    def record_failed_attempt(self, key):
        return 1


@pytest.fixture
def client():
    app = FastAPI()
    core_exceptions.register_exception_handlers(app)
    app.dependency_overrides[core_database.get_db] = lambda: MagicMock()

    @app.get("/protected", dependencies=[Depends(auth_dependencies.validate_access_token)])
    def _protected():
        return {}

    @app.get("/protected-or-key", dependencies=[Depends(auth_dependencies.validate_access_token_or_api_key)])
    def _protected_or_key():
        return {}

    @app.post("/step-up")
    def _step_up():
        step_up_service._refuse_step_up(
            _Store(), "user:1", 1, "Invalid password", account_security_audit_actions.StepUpMethod.PASSWORD
        )

    return TestClient(app, headers={"X-Client-Type": "web"})


@pytest.mark.parametrize("token", ["not-a-jwt", STALE_JWT])
def test_bad_access_token_is_an_invalid_token(client, token):
    response = client.get("/protected", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert response.json()["type"] == INVALID_TOKEN
    assert response.headers["www-authenticate"] == 'Bearer error="invalid_token"'


@pytest.mark.parametrize("path", ["/protected", "/protected-or-key"])
def test_missing_credentials_are_an_invalid_token_with_a_bare_challenge(client, path):
    response = client.get(path)

    assert response.status_code == 401
    assert response.json()["type"] == INVALID_TOKEN
    assert response.headers["www-authenticate"] == "Bearer"


def test_wrong_step_up_password_is_not_an_invalid_token(client):
    response = client.post("/step-up")

    assert response.status_code == 401
    assert response.json()["type"] == UNAUTHORIZED
    assert response.headers["www-authenticate"] == "Bearer"
