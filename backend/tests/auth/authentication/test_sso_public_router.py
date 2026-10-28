"""Tests for the SSO token-exchange route."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import core.database as core_db
import core.exceptions as core_exceptions
import modules.auth.authentication.sso_public_router as sso_public_router

_VERIFIER = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
_SERVICE = "modules.auth.authentication.service"


@pytest.fixture(autouse=True)
def _session_policy(session_policy):
    """Serve the default session policy instead of reading it from the database."""
    with patch(f"{_SERVICE}.server_settings_integration.get_session_policy", return_value=session_policy):
        yield


def _client(mock_db) -> TestClient:
    app = FastAPI()
    app.include_router(sso_public_router.router, prefix="/api/v1/public/idp")
    app.add_exception_handler(core_exceptions.DomainError, core_exceptions.domain_error_handler)
    app.dependency_overrides[core_db.get_db] = lambda: mock_db
    return TestClient(app)


def _session_and_state(client_type: str = "mobile") -> tuple[MagicMock, MagicMock]:
    session = MagicMock()
    session.user_id = 42
    session.tokens_exchanged = False
    oauth_state = MagicMock()
    oauth_state.id = "oauth-state-id"
    oauth_state.code_challenge = _VERIFIER
    oauth_state.code_challenge_method = "S256"
    oauth_state.client_type = client_type
    return session, oauth_state


class TestTokenExchange:
    @patch(f"{_SERVICE}.sessions_integration.get_session_with_oauth_state", return_value=None)
    def test_session_not_found(self, _mock_get_session, mock_db):
        response = _client(mock_db).post("/api/v1/public/idp/session/unknown/tokens", json={"code_verifier": _VERIFIER})

        assert response.status_code == 404

    @patch(f"{_SERVICE}.sessions_integration.get_session_with_oauth_state")
    def test_a_session_without_oauth_state_is_not_eligible(self, mock_get_session, mock_db):
        mock_get_session.return_value = (_session_and_state()[0], None)

        response = _client(mock_db).post("/api/v1/public/idp/session/s/tokens", json={"code_verifier": _VERIFIER})

        assert response.status_code == 404

    @patch(f"{_SERVICE}.sessions_integration.get_session_with_oauth_state")
    def test_replay_is_refused(self, mock_get_session, mock_db):
        session, oauth_state = _session_and_state()
        session.tokens_exchanged = True
        mock_get_session.return_value = (session, oauth_state)

        response = _client(mock_db).post("/api/v1/public/idp/session/s/tokens", json={"code_verifier": _VERIFIER})

        assert response.status_code == 409
        mock_db.commit.assert_not_called()

    @patch(f"{_SERVICE}.users_integration.require_user")
    @patch(f"{_SERVICE}.users_integration.require_active_user")
    @patch(f"{_SERVICE}.create_tokens")
    @patch(f"{_SERVICE}.sessions_integration.claim_session_for_token_exchange", return_value=True)
    @patch(f"{_SERVICE}.auth_computation.validate_pkce_verifier")
    @patch(f"{_SERVICE}.sessions_integration.get_session_with_oauth_state")
    def test_success_retrieves_user_from_session(
        self,
        mock_get_session,
        mock_validate_pkce,
        mock_claim_session,
        mock_create_tokens,
        mock_check_active,
        mock_require_user,
        mock_db,
    ):
        mock_get_session.return_value = _session_and_state()
        user = MagicMock()
        mock_require_user.return_value = user
        mock_create_tokens.return_value = (
            None,
            MagicMock(),
            "access-token",
            MagicMock(),
            "refresh-token",
            "csrf-token",
        )
        mock_create_tokens.return_value[1].__sub__.return_value.total_seconds.return_value = 900
        mock_create_tokens.return_value[3].__sub__.return_value.total_seconds.return_value = 604800

        response = _client(mock_db).post(
            "/api/v1/public/idp/session/session-id/tokens",
            json={"code_verifier": _VERIFIER},
            headers={"X-Client-Type": "mobile"},
        )

        assert response.status_code == 200
        mock_validate_pkce.assert_called_once()
        mock_require_user.assert_called_once_with(42, mock_db)
        mock_check_active.assert_called_once_with(user)
        mock_claim_session.assert_called_once()
        mock_db.commit.assert_called_once()
        assert response.json()["refresh_token"] == "refresh-token"

    @patch(f"{_SERVICE}.sessions_integration.claim_session_for_token_exchange")
    @patch(f"{_SERVICE}.create_tokens")
    @patch(f"{_SERVICE}.auth_computation.validate_pkce_verifier")
    @patch(f"{_SERVICE}.sessions_integration.get_session_with_oauth_state")
    def test_client_type_mismatch_does_not_mint_tokens_or_claim_session(
        self, mock_get_session, _mock_validate_pkce, mock_create_tokens, mock_claim_session, mock_db
    ):
        mock_get_session.return_value = _session_and_state("mobile")

        response = _client(mock_db).post(
            "/api/v1/public/idp/session/session-id/tokens",
            json={"code_verifier": _VERIFIER},
            headers={"X-Client-Type": "web"},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "client_type does not match the OAuth state"
        mock_create_tokens.assert_not_called()
        mock_claim_session.assert_not_called()

    @patch(f"{_SERVICE}.sessions_integration.claim_session_for_token_exchange", return_value=False)
    @patch(f"{_SERVICE}.create_tokens")
    @patch(f"{_SERVICE}.users_integration.require_active_user")
    @patch(f"{_SERVICE}.users_integration.require_user")
    @patch(f"{_SERVICE}.auth_computation.validate_pkce_verifier")
    @patch(f"{_SERVICE}.sessions_integration.get_session_with_oauth_state")
    def test_losing_the_claim_race_is_refused(
        self, mock_get_session, _validate, _require_user, _require_active, mock_create_tokens, _claim, mock_db
    ):
        mock_get_session.return_value = _session_and_state()
        mock_create_tokens.return_value = (None, MagicMock(), "a", MagicMock(), "r", "c")

        response = _client(mock_db).post("/api/v1/public/idp/session/s/tokens", json={"code_verifier": _VERIFIER})

        assert response.status_code == 409
        mock_db.commit.assert_not_called()
