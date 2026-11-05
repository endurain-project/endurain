"""``X-Client-Type`` is strictly ``web`` or ``mobile`` on every route, and an MFA user always gets the challenge."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

import core.database as core_database
import core.exceptions as core_exceptions
import modules.auth.access_tokens.service as auth_token_manager
import modules.auth.authentication.failed_login_store as failed_login_store
import modules.auth.authentication.public_router as auth_public_router
import modules.auth.authentication.schema as auth_schema
import modules.auth.authentication.service as authentication_service
import modules.auth.credentials.password_hasher as auth_password_hasher
import modules.auth.dependencies as auth_dependencies
import modules.auth.mfa.dependencies as mfa_dependencies

_SERVICE = "modules.auth.authentication.service"
_USER = SimpleNamespace(id=5, username="alice", active=True, access_type="regular")


def _app(mock_db) -> FastAPI:
    app = FastAPI()
    core_exceptions.register_exception_handlers(app)
    app.include_router(auth_public_router.router, prefix="/api/v1/auth")
    app.dependency_overrides[core_database.get_db] = lambda: mock_db
    app.dependency_overrides[auth_password_hasher.get_password_hasher] = lambda: MagicMock()
    app.dependency_overrides[auth_token_manager.get_token_manager] = lambda: MagicMock()
    app.dependency_overrides[failed_login_store.get_failed_login_attempts] = lambda: MagicMock(
        is_locked_out=MagicMock(return_value=False)
    )
    app.dependency_overrides[mfa_dependencies.get_pending_mfa_store] = lambda: MagicMock()

    @app.get("/protected", dependencies=[Depends(auth_dependencies.validate_access_token)])
    def _protected():
        return {}

    return app


class TestUnknownClientType:
    def test_login_answers_400_for_an_unknown_client_type(self, mock_db):
        client = TestClient(_app(mock_db))

        response = client.post(
            "/api/v1/auth/login",
            data={"username": "alice", "password": "secret"},
            headers={"X-Client-Type": "ios"},
        )

        assert response.status_code == 400, response.text
        assert "web or mobile" in response.json()["detail"]

    def test_an_authenticated_route_answers_400_for_an_unknown_client_type(self, mock_db):
        client = TestClient(_app(mock_db))

        response = client.get("/protected", headers={"X-Client-Type": "ios", "Authorization": "Bearer not-a-jwt"})

        assert response.status_code == 400, response.text


class TestMfaUserAlwaysGetsTheChallenge:
    @pytest.mark.parametrize("client_type", ["web", "mobile", "ios"])
    def test_the_challenge_is_returned_and_failed_attempts_are_kept(self, mock_db, client_type):
        failed = MagicMock(is_locked_out=MagicMock(return_value=False))
        pending = MagicMock(add_pending_login=MagicMock(return_value="challenge"))
        with (
            patch(f"{_SERVICE}.authenticate_user", return_value=_USER),
            patch(f"{_SERVICE}.server_settings_integration.get_server_settings"),
            patch(f"{_SERVICE}.credentials_integration.allows_password_sign_in", return_value=True),
            patch(f"{_SERVICE}.mfa_integration.is_mfa_enabled_for_user", return_value=True),
        ):
            outcome = authentication_service.login_for_access_token(
                "127.0.0.1",
                "agent",
                "alice",
                "secret",
                client_type,
                failed,
                pending,
                MagicMock(),
                MagicMock(),
                mock_db,
                device_id=None,
            )

        assert isinstance(outcome.body, auth_schema.MFARequiredRead)
        failed.reset_attempts.assert_not_called()
