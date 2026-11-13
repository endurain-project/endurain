"""Tests for the SSO token-exchange route."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import core.database as core_db
import core.exceptions as core_exceptions
import modules.auth.authentication.sso_public_router as sso_public_router
import modules.auth.mfa.dependencies as mfa_dependencies
import modules.auth.mfa.pending_login_store as pending_login_store
import modules.auth.oauth_state.constants as oauth_state_constants

_USER_ID = uuid.UUID(int=42)

IDP_ID = uuid.uuid4()

_VERIFIER = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
_SERVICE = "modules.auth.authentication.service"
_CLAIMED_EXPIRY = datetime(2999, 1, 1, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _session_policy(session_policy):
    """Serve the default session policy instead of reading it from the database."""
    with (
        patch(f"{_SERVICE}.server_settings_integration.get_session_policy", return_value=session_policy),
        patch(f"{_SERVICE}.mfa_integration.is_mfa_enabled_for_user", return_value=False),
    ):
        yield


def _pending_mfa_store(*, locked_out: bool = False) -> MagicMock:
    store = MagicMock()
    store.is_locked_out.return_value = locked_out
    store.record_failed_attempt.return_value = pending_login_store.FailedMfaRecord(count=1, account_locked_now=False)
    return store


def _client(mock_db, pending_mfa_store: MagicMock | None = None) -> TestClient:
    app = FastAPI()
    app.include_router(sso_public_router.router, prefix="/api/v1/auth")
    app.add_exception_handler(core_exceptions.DomainError, core_exceptions.domain_error_handler)
    app.dependency_overrides[core_db.get_db] = lambda: mock_db
    app.dependency_overrides[mfa_dependencies.get_pending_mfa_store] = lambda: pending_mfa_store or _pending_mfa_store()
    return TestClient(app, headers={"X-Client-Type": "mobile"})


def _session_and_state(client_type: str = "mobile", idp_id: uuid.UUID | None = IDP_ID) -> tuple[MagicMock, MagicMock]:
    session = MagicMock()
    session.user_id = _USER_ID
    session.tokens_exchanged = False
    session.expires_at = datetime.now(UTC) + timedelta(days=30)
    oauth_state = MagicMock()
    oauth_state.id = "oauth-state-id"
    oauth_state.code_challenge = _VERIFIER
    oauth_state.code_challenge_method = "S256"
    oauth_state.client_type = client_type
    oauth_state.idp_id = idp_id
    oauth_state.security_generation = 0
    oauth_state.purpose = oauth_state_constants.OAuthStatePurpose.LOGIN
    return session, oauth_state


class TestTokenExchange:
    @patch(f"{_SERVICE}.sessions_integration.get_session_with_oauth_state", return_value=None)
    def test_session_not_found(self, _mock_get_session, mock_db):
        response = _client(mock_db).post("/api/v1/auth/sessions/unknown/tokens", json={"code_verifier": _VERIFIER})

        assert response.status_code == 404

    @patch(f"{_SERVICE}.sessions_integration.get_session_with_oauth_state")
    def test_a_session_without_oauth_state_is_not_eligible(self, mock_get_session, mock_db):
        mock_get_session.return_value = (_session_and_state()[0], None)

        response = _client(mock_db).post("/api/v1/auth/sessions/s/tokens", json={"code_verifier": _VERIFIER})

        assert response.status_code == 404

    @patch(f"{_SERVICE}.users_integration.require_user")
    @patch(f"{_SERVICE}.users_integration.require_active_user")
    @patch("modules.auth.authentication.token_service.create_tokens")
    @patch(f"{_SERVICE}.sessions_integration.claim_session_for_token_exchange", return_value=_CLAIMED_EXPIRY)
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
        user.id = _USER_ID
        user.username = "testuser"
        mock_require_user.return_value = user
        mock_create_tokens.return_value = (
            None,
            datetime.now(UTC) + timedelta(minutes=15),
            "access-token",
            datetime.now(UTC) + timedelta(days=7),
            "refresh-token",
            "csrf-token",
        )

        response = _client(mock_db).post(
            "/api/v1/auth/sessions/session-id/tokens",
            json={"code_verifier": _VERIFIER},
            headers={"X-Client-Type": "mobile"},
        )

        assert response.status_code == 200
        mock_validate_pkce.assert_called_once()
        mock_require_user.assert_called_once_with(_USER_ID, mock_db)
        mock_check_active.assert_called_once_with(user)
        mock_claim_session.assert_called_once()
        mock_db.commit.assert_called_once()
        assert response.json()["refresh_token"] == "refresh-token"

    @patch(f"{_SERVICE}.sessions_integration.claim_session_for_token_exchange")
    @patch("modules.auth.authentication.token_service.create_tokens")
    @patch(f"{_SERVICE}.auth_computation.validate_pkce_verifier")
    @patch(f"{_SERVICE}.sessions_integration.get_session_with_oauth_state")
    def test_client_type_mismatch_does_not_mint_tokens_or_claim_session(
        self, mock_get_session, _mock_validate_pkce, mock_create_tokens, mock_claim_session, mock_db
    ):
        mock_get_session.return_value = _session_and_state("mobile")

        response = _client(mock_db).post(
            "/api/v1/auth/sessions/session-id/tokens",
            json={"code_verifier": _VERIFIER},
            headers={"X-Client-Type": "web"},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "Invalid code_verifier"
        mock_create_tokens.assert_not_called()
        mock_claim_session.assert_not_called()

    @patch(f"{_SERVICE}.users_integration.require_user")
    @patch(f"{_SERVICE}.users_integration.require_active_user")
    @patch("modules.auth.authentication.token_service.create_tokens")
    @patch(f"{_SERVICE}.sessions_integration.claim_session_for_token_exchange")
    @patch(f"{_SERVICE}.auth_computation.validate_pkce_verifier")
    @patch(f"{_SERVICE}.sessions_integration.get_session_with_oauth_state")
    def test_the_exchange_extends_the_session_and_tells_the_client_its_new_expiry(
        self, mock_get_session, _validate, mock_claim, mock_create_tokens, _active, _require_user, mock_db
    ):
        _require_user.return_value.id = _USER_ID
        _require_user.return_value.username = "testuser"
        session, state = _session_and_state()
        session.expires_at = datetime.now(UTC) + timedelta(minutes=10)
        mock_get_session.return_value = (session, state)
        refresh_exp = datetime.now(UTC) + timedelta(days=7)
        mock_create_tokens.return_value = (
            None,
            datetime.now(UTC) + timedelta(minutes=15),
            "access-token",
            refresh_exp,
            "refresh-token",
            "csrf-token",
        )
        # The absolute timeout puts the session's new expiry before the refresh token's.
        mock_claim.return_value = datetime.now(UTC) + timedelta(hours=2)

        response = _client(mock_db).post(
            "/api/v1/auth/sessions/session-id/tokens",
            json={"code_verifier": _VERIFIER},
            headers={"X-Client-Type": "mobile"},
        )

        assert response.status_code == 200
        assert mock_claim.call_args.args[2] == refresh_exp
        assert response.json()["refresh_token_expires_in"] == pytest.approx(2 * 3600, abs=2)

    @patch(f"{_SERVICE}.sessions_integration.claim_session_for_token_exchange", return_value=None)
    @patch("modules.auth.authentication.token_service.create_tokens")
    @patch(f"{_SERVICE}.users_integration.require_active_user")
    @patch(f"{_SERVICE}.users_integration.require_user")
    @patch(f"{_SERVICE}.auth_computation.validate_pkce_verifier")
    @patch(f"{_SERVICE}.sessions_integration.get_session_with_oauth_state")
    def test_losing_the_claim_race_is_refused(
        self, mock_get_session, _validate, _require_user, _require_active, mock_create_tokens, _claim, mock_db
    ):
        mock_get_session.return_value = _session_and_state()
        mock_create_tokens.return_value = (
            None,
            datetime.now(UTC) + timedelta(minutes=15),
            "a",
            datetime.now(UTC) + timedelta(days=7),
            "r",
            "c",
        )

        response = _client(mock_db).post("/api/v1/auth/sessions/s/tokens", json={"code_verifier": _VERIFIER})

        assert response.status_code == 404
        mock_db.commit.assert_not_called()


class TestTokenExchangeHeader:
    def test_the_client_type_header_is_required(self, mock_db):
        client = _client(mock_db)
        client.headers.pop("X-Client-Type")

        response = client.post("/api/v1/auth/sessions/s/tokens", json={"code_verifier": _VERIFIER})

        assert response.status_code == 422

    def test_the_old_path_is_gone(self, mock_db):
        response = _client(mock_db).post("/api/v1/public/idp/session/s/tokens", json={"code_verifier": _VERIFIER})

        assert response.status_code == 404


class TestTokenExchangeMfa:
    """An SSO session of an account with MFA enabled needs a valid MFA code to be exchanged."""

    def _post(self, mock_db, store, **body):
        return _client(mock_db, store).post(
            "/api/v1/auth/sessions/session-id/tokens",
            json={"code_verifier": _VERIFIER, **body},
            headers={"X-Client-Type": "mobile"},
        )

    @pytest.fixture
    def exchange(self, mock_db):
        user = MagicMock()
        user.id = _USER_ID
        user.username = "testuser"
        tokens = (
            None,
            datetime.now(UTC) + timedelta(minutes=15),
            "access-token",
            datetime.now(UTC) + timedelta(days=7),
            "refresh-token",
            "csrf-token",
        )
        with (
            patch(f"{_SERVICE}.sessions_integration.get_session_with_oauth_state") as get_session,
            patch(f"{_SERVICE}.auth_computation.validate_pkce_verifier") as validate_pkce,
            patch(f"{_SERVICE}.users_integration.require_user", return_value=user),
            patch(f"{_SERVICE}.users_integration.require_active_user"),
            patch(f"{_SERVICE}.mfa_integration.is_mfa_enabled_for_user", return_value=True),
            patch(f"{_SERVICE}.mfa_integration.verify_user_mfa", return_value=True) as verify,
            patch("modules.auth.authentication.token_service.create_tokens", return_value=tokens),
            patch(
                f"{_SERVICE}.sessions_integration.claim_session_for_token_exchange", return_value=_CLAIMED_EXPIRY
            ) as claim,
        ):
            get_session.return_value = _session_and_state()
            yield MagicMock(get_session=get_session, validate_pkce=validate_pkce, verify=verify, claim=claim)

    def test_a_missing_code_is_asked_for_without_using_up_the_session(self, mock_db, exchange):
        store = _pending_mfa_store()

        response = self._post(mock_db, store)

        assert response.status_code == 403
        assert response.json()["type"] == "urn:endurain:error:mfa-required"
        exchange.verify.assert_not_called()
        exchange.claim.assert_not_called()
        mock_db.commit.assert_not_called()

    def test_a_wrong_code_is_refused_and_counted(self, mock_db, exchange):
        store = _pending_mfa_store()
        exchange.verify.return_value = False

        response = self._post(mock_db, store, mfa_code="123456")

        assert response.status_code == 400
        assert response.json()["type"] == "urn:endurain:error:invalid-mfa-code"
        store.record_failed_attempt.assert_called_once_with("testuser", "testclient", user_id=_USER_ID)
        exchange.claim.assert_not_called()

    def test_a_locked_out_account_is_refused_before_the_code_is_checked(self, mock_db, exchange):
        store = _pending_mfa_store(locked_out=True)
        store.get_lockout_time.return_value = datetime.now(UTC) + timedelta(minutes=5)

        response = self._post(mock_db, store, mfa_code="123456")

        assert response.status_code == 429
        exchange.verify.assert_not_called()
        exchange.claim.assert_not_called()

    def test_a_valid_code_completes_the_exchange_and_clears_the_counter(self, mock_db, exchange):
        store = _pending_mfa_store()

        response = self._post(mock_db, store, mfa_code="123456")

        assert response.status_code == 200
        assert exchange.verify.call_args.args[:2] == (_USER_ID, "123456")
        assert exchange.verify.call_args.kwargs["replay_guard"] is store
        store.reset_attempts.assert_called_once_with("testuser", "testclient", user_id=_USER_ID)
        exchange.claim.assert_called_once()

    def test_the_pkce_check_comes_before_the_code_is_checked(self, mock_db, exchange):
        exchange.validate_pkce.side_effect = core_exceptions.InvalidInputError("bad verifier")

        response = self._post(mock_db, _pending_mfa_store(), mfa_code="123456")

        assert response.status_code == 400
        assert response.json()["type"] == "urn:endurain:error:invalid-input"
        exchange.verify.assert_not_called()

    def test_a_session_from_a_password_login_has_already_passed_mfa(self, mock_db, exchange):
        exchange.get_session.return_value = _session_and_state(idp_id=None)

        response = self._post(mock_db, _pending_mfa_store())

        assert response.status_code == 200
        exchange.verify.assert_not_called()
