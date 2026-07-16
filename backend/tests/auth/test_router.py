"""Integration tests for auth.router endpoints."""

from datetime import UTC
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import auth._internal.internal_dependencies as auth_security
import auth._internal.password_hasher as auth_password_hasher
import auth._internal.security_stores as auth_security_stores
import auth._internal.token_manager as auth_token_manager
import auth.identity_service as auth_identity_service
import auth.router as auth_router
import core.database as core_database

# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


class FakeFailedLoginStore:
    """In-memory FailedLoginStore double for testing."""

    def __init__(self):
        """Initialize empty state."""
        self._locked = False
        self._lockout_time = None

    def is_locked_out(self, username: str) -> bool:
        """Return locked state."""
        return self._locked

    def get_lockout_time(self, username: str):
        """Return lockout time."""
        return self._lockout_time

    def record_failed_attempt(self, username: str) -> int:
        """Record a failed attempt."""
        return 1

    def reset_attempts(self, username: str) -> None:
        """Reset attempts."""
        pass


class FakePendingMFAStore:
    """In-memory PendingMFAStore double for testing."""

    def __init__(self):
        """Initialize empty state."""
        self._store = {}
        self._locked = False
        self._lockout_time = None

    def is_locked_out(self, username: str) -> bool:
        """Return locked state."""
        return self._locked

    def get_lockout_time(self, username: str):
        """Return lockout time."""
        return self._lockout_time

    def add_pending_login(self, username: str, user_id: int):
        """Add pending login."""
        self._store[username] = user_id

    def get_pending_login(self, username: str):
        """Get pending login."""
        return self._store.get(username)

    def claim_pending_login(self, username: str):
        """Claim pending login."""
        return self._store.pop(username, None)

    def record_failed_attempt(self, username: str) -> int:
        """Record failed MFA attempt."""
        return 1

    def reset_attempts(self, username: str) -> None:
        """Reset MFA failed attempts."""
        pass


@pytest.fixture
def mock_db():
    """Return a mock SQLAlchemy session."""
    return MagicMock(spec=Session)


@pytest.fixture
def fake_failed_login_store():
    """Return a FakeFailedLoginStore instance."""
    return FakeFailedLoginStore()


@pytest.fixture
def fake_pending_mfa_store():
    """Return a FakePendingMFAStore instance."""
    return FakePendingMFAStore()


@pytest.fixture
def mock_identity_service():
    """Return an IdentityService test double."""
    service = MagicMock()
    return service


@pytest.fixture
def auth_app(
    mock_db,
    mock_identity_service,
    password_hasher,
    token_manager,
    fake_failed_login_store,
    fake_pending_mfa_store,
):
    """Create a FastAPI app with auth router and overrides."""
    app = FastAPI()
    app.include_router(auth_router.router, prefix="/auth")

    app.state._client_type = "web"

    def _client_type():
        return app.state._client_type

    app.dependency_overrides[core_database.get_db] = lambda: mock_db
    app.dependency_overrides[auth_identity_service.get_identity_service] = lambda: mock_identity_service
    app.dependency_overrides[auth_password_hasher.get_password_hasher] = lambda: password_hasher
    app.dependency_overrides[auth_token_manager.get_token_manager] = lambda: token_manager
    app.dependency_overrides[auth_security.header_client_type_scheme] = _client_type
    app.dependency_overrides[auth_security_stores.get_failed_login_attempts] = lambda: fake_failed_login_store
    app.dependency_overrides[auth_security_stores.get_pending_mfa_store] = lambda: fake_pending_mfa_store

    return app


@pytest.fixture
def auth_client(auth_app):
    """Return a TestClient for the auth app."""
    return TestClient(auth_app)


# ------------------------------------------------------------------
# POST /auth/login
# ------------------------------------------------------------------


class TestLoginEndpoint:
    """Tests for POST /auth/login endpoint."""

    @patch("auth.router.auth_utils.complete_login")
    @patch("auth.router.mfa_service.is_mfa_enabled_for_user")
    @patch("auth.router.users_utils.check_user_is_active")
    @patch("auth.router.auth_utils.authenticate_user")
    def test_login_web_success(
        self,
        mock_auth,
        mock_check_active,
        mock_mfa_check,
        mock_complete_login,
        auth_client,
        auth_app,
    ):
        """Web login returns access_token and csrf_token."""
        mock_user = MagicMock()
        mock_user.id = 1
        mock_auth.return_value = mock_user
        mock_check_active.return_value = None
        mock_mfa_check.return_value = False
        mock_complete_login.return_value = {
            "session_id": "sid-1",
            "access_token": "at-1",
            "csrf_token": "csrf-1",
            "token_type": "bearer",
            "expires_in": 900,
            "refresh_token_expires_in": 604800,
        }

        response = auth_client.post(
            "/auth/login",
            data={"username": "testuser", "password": "Password1!"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["access_token"] == "at-1"
        assert data["csrf_token"] == "csrf-1"
        assert data["token_type"] == "bearer"

    @patch("auth.router.auth_utils.complete_login")
    @patch("auth.router.mfa_service.is_mfa_enabled_for_user")
    @patch("auth.router.users_utils.check_user_is_active")
    @patch("auth.router.auth_utils.authenticate_user")
    def test_login_mobile_success(
        self,
        mock_auth,
        mock_check_active,
        mock_mfa_check,
        mock_complete_login,
        auth_client,
        auth_app,
    ):
        """Mobile login returns refresh_token in body."""
        auth_app.state._client_type = "mobile"
        mock_user = MagicMock()
        mock_user.id = 1
        mock_auth.return_value = mock_user
        mock_check_active.return_value = None
        mock_mfa_check.return_value = False
        mock_complete_login.return_value = {
            "session_id": "sid-1",
            "access_token": "at-1",
            "refresh_token": "rt-1",
            "token_type": "bearer",
            "expires_in": 900,
            "refresh_token_expires_in": 604800,
        }

        response = auth_client.post(
            "/auth/login",
            data={"username": "testuser", "password": "Password1!"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["refresh_token"] == "rt-1"

    @patch("auth.router.auth_utils.authenticate_user")
    def test_login_invalid_credentials_returns_401(self, mock_auth, auth_client, auth_app):
        """Invalid credentials raise 401."""
        mock_auth.side_effect = HTTPException(status_code=401, detail="Unable to authenticate")

        response = auth_client.post(
            "/auth/login",
            data={"username": "baduser", "password": "WrongPass1!"},
        )

        assert response.status_code == 401

    @patch("auth.router.users_utils.check_user_is_active")
    @patch("auth.router.auth_utils.authenticate_user")
    def test_login_inactive_user_returns_403(
        self,
        mock_auth,
        mock_check_active,
        auth_client,
        auth_app,
    ):
        """Inactive user raises 403."""
        mock_user = MagicMock()
        mock_auth.return_value = mock_user
        mock_check_active.side_effect = HTTPException(status_code=403, detail="User is not active")

        response = auth_client.post(
            "/auth/login",
            data={"username": "inactive", "password": "Password1!"},
        )

        assert response.status_code == 403

    def test_login_locked_out_returns_429(
        self,
        auth_client,
        auth_app,
        fake_failed_login_store,
    ):
        """Locked out account returns 429."""
        from datetime import datetime, timedelta

        fake_failed_login_store._locked = True
        fake_failed_login_store._lockout_time = datetime.now(UTC) + timedelta(minutes=5)

        response = auth_client.post(
            "/auth/login",
            data={"username": "locked", "password": "Password1!"},
        )

        assert response.status_code == 429
        assert "locked" in response.json()["detail"].lower()

    @patch("auth.router.mfa_service.is_mfa_enabled_for_user")
    @patch("auth.router.users_utils.check_user_is_active")
    @patch("auth.router.auth_utils.authenticate_user")
    def test_login_mfa_required_returns_202(
        self,
        mock_auth,
        mock_check_active,
        mock_mfa_check,
        auth_client,
        auth_app,
    ):
        """MFA required returns 202 for web client."""
        mock_user = MagicMock()
        mock_user.id = 1
        mock_auth.return_value = mock_user
        mock_check_active.return_value = None
        mock_mfa_check.return_value = True

        response = auth_client.post(
            "/auth/login",
            data={"username": "mfauser", "password": "Password1!"},
        )

        assert response.status_code == 202
        data = response.json()
        assert data["mfa_required"] is True
        assert data["username"] == "mfauser"

    def test_login_partial_pkce_returns_400(self, auth_client, auth_app):
        """Partial PKCE params on mobile returns 400."""
        auth_app.state._client_type = "mobile"

        response = auth_client.post(
            "/auth/login?code_challenge=abc",
            data={"username": "user", "password": "Password1!"},
        )

        assert response.status_code == 400
        assert "together" in response.json()["detail"]

    @patch("auth.router.auth_utils.create_mobile_pkce_session_response")
    @patch("auth.router.mfa_service.is_mfa_enabled_for_user")
    @patch("auth.router.users_utils.check_user_is_active")
    @patch("auth.router.auth_utils.authenticate_user")
    def test_login_mobile_pkce_returns_session_response(
        self,
        mock_auth,
        mock_check_active,
        mock_mfa_check,
        mock_pkce,
        auth_client,
        auth_app,
    ):
        """Mobile with PKCE returns session_id for exchange."""
        auth_app.state._client_type = "mobile"
        mock_user = MagicMock()
        mock_user.id = 1
        mock_auth.return_value = mock_user
        mock_check_active.return_value = None
        mock_mfa_check.return_value = False
        mock_pkce.return_value = {
            "session_id": "pkce-sid",
            "mfa_required": False,
            "message": "Complete authentication...",
        }

        challenge = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
        response = auth_client.post(
            f"/auth/login?code_challenge={challenge}&code_challenge_method=S256",
            data={"username": "user", "password": "Password1!"},
        )

        assert response.status_code == 200
        assert response.json()["session_id"] == "pkce-sid"

    def test_login_store_unavailable_on_is_locked_out_returns_503(
        self,
        auth_client,
        auth_app,
        fake_failed_login_store,
    ):
        """
        503 when is_locked_out raises AuthSecurityStoreUnavailableError.

        Args:
            auth_client: TestClient for the auth app.
            auth_app: FastAPI test application.
            fake_failed_login_store: In-memory failed login store.

        Returns:
            None.

        Raises:
            AssertionError: If response status is not 503.
        """
        fake_failed_login_store.is_locked_out = MagicMock(
            side_effect=(auth_security_stores.AuthSecurityStoreUnavailableError("Redis down"))
        )

        response = auth_client.post(
            "/auth/login",
            data={"username": "user", "password": "Password1!"},
        )

        assert response.status_code == 503
        assert "unavailable" in response.json()["detail"].lower()

    @patch("auth.router.auth_utils.authenticate_user")
    def test_login_store_unavailable_on_record_failed_returns_503(
        self,
        mock_auth,
        auth_client,
        auth_app,
        fake_failed_login_store,
    ):
        """
        503 when record_failed_attempt raises after 401 auth error.

        Args:
            mock_auth: Mock for authenticate_user.
            auth_client: TestClient for the auth app.
            auth_app: FastAPI test application.
            fake_failed_login_store: In-memory failed login store.

        Returns:
            None.

        Raises:
            AssertionError: If response status is not 503.
        """
        mock_auth.side_effect = HTTPException(status_code=401, detail="Unable to authenticate")
        fake_failed_login_store.record_failed_attempt = MagicMock(
            side_effect=(auth_security_stores.AuthSecurityStoreUnavailableError("Redis down"))
        )

        response = auth_client.post(
            "/auth/login",
            data={"username": "user", "password": "WrongPass1!"},
        )

        assert response.status_code == 503
        assert "unavailable" in response.json()["detail"].lower()

    @patch("auth.router.auth_utils.complete_login")
    @patch("auth.router.mfa_service.is_mfa_enabled_for_user")
    @patch("auth.router.users_utils.check_user_is_active")
    @patch("auth.router.auth_utils.authenticate_user")
    def test_login_store_unavailable_on_reset_attempts_returns_503(
        self,
        mock_auth,
        mock_check_active,
        mock_mfa_check,
        mock_complete_login,
        auth_client,
        auth_app,
        fake_failed_login_store,
    ):
        """503 when reset_attempts raises after successful login with no MFA."""
        mock_user = MagicMock()
        mock_user.id = 1
        mock_auth.return_value = mock_user
        mock_check_active.return_value = None
        mock_mfa_check.return_value = False
        fake_failed_login_store.reset_attempts = MagicMock(
            side_effect=auth_security_stores.AuthSecurityStoreUnavailableError("Redis down"),
        )
        response = auth_client.post(
            "/auth/login",
            data={"username": "testuser", "password": "Password1!"},
        )
        assert response.status_code == 503
        assert "unavailable" in response.json()["detail"].lower()

    @patch("auth.router.auth_utils.complete_login")
    @patch("auth.router.mfa_service.is_mfa_enabled_for_user")
    @patch("auth.router.users_utils.check_user_is_active")
    @patch("auth.router.auth_utils.authenticate_user")
    def test_login_store_unavailable_on_add_pending_returns_503(
        self,
        mock_auth,
        mock_check_active,
        mock_mfa_check,
        mock_complete_login,
        auth_client,
        auth_app,
        fake_pending_mfa_store,
    ):
        mock_user = MagicMock()
        mock_user.id = 1
        mock_auth.return_value = mock_user
        mock_check_active.return_value = None
        mock_mfa_check.return_value = True
        fake_pending_mfa_store.add_pending_login = MagicMock(
            side_effect=auth_security_stores.AuthSecurityStoreUnavailableError("Redis down"),
        )
        response = auth_client.post(
            "/auth/login",
            data={"username": "mfauser", "password": "Password1!"},
        )
        assert response.status_code == 503

    @patch("auth.router.mfa_service.is_mfa_enabled_for_user")
    @patch("auth.router.users_utils.check_user_is_active")
    @patch("auth.router.auth_utils.authenticate_user")
    def test_login_mfa_required_mobile_returns_dict(
        self,
        mock_auth,
        mock_check_active,
        mock_mfa_check,
        auth_client,
        auth_app,
    ):
        auth_app.state._client_type = "mobile"
        mock_user = MagicMock()
        mock_user.id = 1
        mock_auth.return_value = mock_user
        mock_check_active.return_value = None
        mock_mfa_check.return_value = True
        response = auth_client.post(
            "/auth/login",
            data={"username": "mfauser", "password": "Password1!"},
        )
        assert response.status_code == 200
        assert response.json()["mfa_required"] is True


# ------------------------------------------------------------------
# POST /auth/mfa/verify
# ------------------------------------------------------------------


class TestMFAVerifyEndpoint:
    """Tests for POST /auth/mfa/verify endpoint."""

    @patch("auth.router.auth_utils.complete_login")
    @patch("auth.router.users_utils.check_user_is_active")
    @patch("auth.router.users_crud.get_user_by_id")
    @patch("auth.router.mfa_service.verify_user_mfa")
    def test_mfa_verify_success(
        self,
        mock_verify_mfa,
        mock_get_user,
        mock_check_active,
        mock_complete_login,
        auth_client,
        auth_app,
        fake_pending_mfa_store,
    ):
        """Valid MFA code completes login."""
        fake_pending_mfa_store.add_pending_login("testuser", 1)
        mock_verify_mfa.return_value = True
        mock_user = MagicMock()
        mock_user.id = 1
        mock_get_user.return_value = mock_user
        mock_check_active.return_value = None
        mock_complete_login.return_value = {
            "session_id": "sid-mfa",
            "access_token": "at-mfa",
            "csrf_token": "csrf-mfa",
            "token_type": "bearer",
            "expires_in": 900,
            "refresh_token_expires_in": 604800,
        }

        response = auth_client.post(
            "/auth/mfa/verify",
            json={
                "username": "testuser",
                "mfa_code": "123456",
            },
        )

        assert response.status_code == 200
        assert response.json()["access_token"] == "at-mfa"

    @patch("auth.router.mfa_service.verify_user_mfa")
    def test_mfa_verify_invalid_code_returns_400(
        self,
        mock_verify_mfa,
        auth_client,
        auth_app,
        fake_pending_mfa_store,
    ):
        """Invalid MFA code returns 400."""
        fake_pending_mfa_store.add_pending_login("testuser", 1)
        mock_verify_mfa.return_value = False

        response = auth_client.post(
            "/auth/mfa/verify",
            json={
                "username": "testuser",
                "mfa_code": "000000",
            },
        )

        assert response.status_code == 400
        assert "Invalid MFA code" in response.json()["detail"]

    @patch("auth.router.auth_utils.complete_login")
    @patch("auth.router.users_utils.check_user_is_active")
    @patch("auth.router.users_crud.get_user_by_id")
    def test_mfa_verify_backup_code_calls_utils_directly(
        self,
        mock_get_user,
        mock_check_active,
        mock_complete_login,
        auth_client,
        auth_app,
        fake_pending_mfa_store,
        mock_identity_service,
    ):
        """Backup-code MFA login calls mfa_backup_codes.utils directly (not via IdentityService)."""
        fake_pending_mfa_store.add_pending_login("testuser", 1)
        mock_mfa = MagicMock()
        mock_mfa.mfa_enabled = True
        mock_mfa.mfa_secret = "encrypted-secret"
        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.auth_mfa = mock_mfa
        mock_get_user.return_value = mock_user
        mock_check_active.return_value = None
        mock_complete_login.return_value = {
            "session_id": "sid-backup",
            "access_token": "at-backup",
            "csrf_token": "csrf-backup",
            "token_type": "bearer",
            "expires_in": 900,
            "refresh_token_expires_in": 604800,
        }

        with patch(
            "auth.mfa.service.mfa_backup_codes_utils.verify_and_consume_backup_code",
            return_value=True,
        ) as mock_backup_verify:
            response = auth_client.post(
                "/auth/mfa/verify",
                json={
                    "username": "testuser",
                    "mfa_code": "A3K9-7BDF",
                },
            )

        assert response.status_code == 200
        assert response.json()["access_token"] == "at-backup"
        mock_backup_verify.assert_called_once_with(
            1,
            "A3K9-7BDF",
            mock_identity_service,
            mock_backup_verify.call_args[0][3],
        )

    def test_mfa_verify_no_pending_login_returns_400(
        self,
        auth_client,
        auth_app,
        fake_pending_mfa_store,
    ):
        """No pending MFA login returns 400."""
        # No pending login stored
        response = auth_client.post(
            "/auth/mfa/verify",
            json={
                "username": "unknown",
                "mfa_code": "123456",
            },
        )

        assert response.status_code == 400
        assert "No pending MFA" in response.json()["detail"]

    def test_mfa_verify_locked_out_returns_429(
        self,
        auth_client,
        auth_app,
        fake_pending_mfa_store,
    ):
        """MFA lockout returns 429."""
        from datetime import datetime, timedelta

        fake_pending_mfa_store._locked = True
        fake_pending_mfa_store._lockout_time = datetime.now(UTC) + timedelta(minutes=5)

        response = auth_client.post(
            "/auth/mfa/verify",
            json={
                "username": "lockeduser",
                "mfa_code": "123456",
            },
        )

        assert response.status_code == 429

    def test_mfa_verify_store_unavailable_on_get_pending_returns_503(
        self,
        auth_client,
        auth_app,
        fake_pending_mfa_store,
    ):
        """
        503 when get_pending_login raises AuthSecurityStoreUnavailableError.

        Args:
            auth_client: TestClient for the auth app.
            auth_app: FastAPI test application.
            fake_pending_mfa_store: In-memory MFA pending store.

        Returns:
            None.

        Raises:
            AssertionError: If response status is not 503.
        """
        fake_pending_mfa_store.get_pending_login = MagicMock(
            side_effect=(auth_security_stores.AuthSecurityStoreUnavailableError("Redis down"))
        )

        response = auth_client.post(
            "/auth/mfa/verify",
            json={"username": "testuser", "mfa_code": "123456"},
        )

        assert response.status_code == 503
        assert "unavailable" in response.json()["detail"].lower()

    def test_mfa_verify_store_unavailable_on_is_locked_out_returns_503(
        self,
        auth_client,
        auth_app,
        fake_pending_mfa_store,
    ):
        """503 when is_locked_out raises AuthSecurityStoreUnavailableError."""
        fake_pending_mfa_store.is_locked_out = MagicMock(
            side_effect=auth_security_stores.AuthSecurityStoreUnavailableError("Redis down"),
        )
        response = auth_client.post(
            "/auth/mfa/verify",
            json={"username": "testuser", "mfa_code": "123456"},
        )
        assert response.status_code == 503
        assert "unavailable" in response.json()["detail"].lower()

    @patch("auth.router.mfa_service.verify_user_mfa")
    def test_mfa_verify_store_unavailable_on_record_failed_returns_503(
        self,
        mock_verify_mfa,
        auth_client,
        auth_app,
        fake_pending_mfa_store,
    ):
        """503 when record_failed_attempt raises after invalid MFA code."""
        fake_pending_mfa_store.add_pending_login("testuser", 1)
        mock_verify_mfa.return_value = False
        fake_pending_mfa_store.record_failed_attempt = MagicMock(
            side_effect=auth_security_stores.AuthSecurityStoreUnavailableError("Redis down"),
        )
        response = auth_client.post(
            "/auth/mfa/verify",
            json={"username": "testuser", "mfa_code": "000000"},
        )
        assert response.status_code == 503
        assert "unavailable" in response.json()["detail"].lower()

    @patch("auth.router.mfa_service.verify_user_mfa")
    def test_mfa_verify_store_unavailable_on_claim_pending_returns_503(
        self,
        mock_verify_mfa,
        auth_client,
        auth_app,
        fake_pending_mfa_store,
    ):
        """503 when claim_pending_login raises after valid MFA code."""
        fake_pending_mfa_store.add_pending_login("testuser", 1)
        mock_verify_mfa.return_value = True
        fake_pending_mfa_store.claim_pending_login = MagicMock(
            side_effect=auth_security_stores.AuthSecurityStoreUnavailableError("Redis down"),
        )
        response = auth_client.post(
            "/auth/mfa/verify",
            json={"username": "testuser", "mfa_code": "123456"},
        )
        assert response.status_code == 503
        assert "unavailable" in response.json()["detail"].lower()

    @patch("auth.router.users_crud.get_user_by_id")
    @patch("auth.router.mfa_service.verify_user_mfa")
    def test_mfa_verify_user_not_found_returns_401(
        self,
        mock_verify_mfa,
        mock_get_user,
        auth_client,
        auth_app,
        fake_pending_mfa_store,
    ):
        """401 when user is not found after MFA verification."""
        fake_pending_mfa_store.add_pending_login("testuser", 1)
        mock_verify_mfa.return_value = True
        mock_get_user.return_value = None
        response = auth_client.post(
            "/auth/mfa/verify",
            json={"username": "testuser", "mfa_code": "123456"},
        )
        assert response.status_code == 401
        assert "Unable to authenticate" in response.json()["detail"]

    @patch("auth.router.users_utils.check_user_is_active")
    @patch("auth.router.users_crud.get_user_by_id")
    @patch("auth.router.mfa_service.verify_user_mfa")
    def test_mfa_verify_store_unavailable_on_reset_returns_503(
        self,
        mock_verify_mfa,
        mock_get_user,
        mock_check_active,
        auth_client,
        auth_app,
        fake_pending_mfa_store,
    ):
        """503 when reset_attempts raises after successful MFA."""
        fake_pending_mfa_store.add_pending_login("testuser", 1)
        mock_verify_mfa.return_value = True
        mock_user = MagicMock()
        mock_user.id = 1
        mock_get_user.return_value = mock_user
        mock_check_active.return_value = None
        fake_pending_mfa_store.reset_attempts = MagicMock(
            side_effect=auth_security_stores.AuthSecurityStoreUnavailableError("Redis down"),
        )
        response = auth_client.post(
            "/auth/mfa/verify",
            json={"username": "testuser", "mfa_code": "123456"},
        )
        assert response.status_code == 503
        assert "unavailable" in response.json()["detail"].lower()

    @patch("auth.router.auth_utils.create_mobile_pkce_session_response")
    @patch("auth.router.users_utils.check_user_is_active")
    @patch("auth.router.users_crud.get_user_by_id")
    @patch("auth.router.mfa_service.verify_user_mfa")
    def test_mfa_verify_mobile_pkce_returns_session_response(
        self,
        mock_verify_mfa,
        mock_get_user,
        mock_check_active,
        mock_pkce,
        auth_client,
        auth_app,
        fake_pending_mfa_store,
    ):
        """Mobile PKCE flow after MFA returns session response."""
        auth_app.state._client_type = "mobile"
        fake_pending_mfa_store.add_pending_login("testuser", 1)
        mock_verify_mfa.return_value = True
        mock_user = MagicMock()
        mock_user.id = 1
        mock_get_user.return_value = mock_user
        mock_check_active.return_value = None
        mock_pkce.return_value = {
            "session_id": "pkce-sid-mfa",
            "mfa_required": False,
            "message": "Complete authentication...",
        }
        challenge = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
        response = auth_client.post(
            f"/auth/mfa/verify?code_challenge={challenge}&code_challenge_method=S256",
            json={"username": "testuser", "mfa_code": "123456"},
        )
        assert response.status_code == 200
        assert response.json()["session_id"] == "pkce-sid-mfa"


# ------------------------------------------------------------------
# POST /auth/refresh
# ------------------------------------------------------------------


class TestRefreshEndpoint:
    """Tests for POST /auth/refresh endpoint."""

    @patch("auth.router.idp_utils.refresh_idp_tokens_if_needed")
    @patch("auth.router.auth_sessions_utils.edit_session")
    @patch("auth.router.auth_utils.create_tokens")
    @patch("auth.router.auth_utils.set_refresh_token_cookie")
    @patch("auth.router.auth_sessions_rotated_tokens_utils.store_rotated_token")
    @patch("auth.router.auth_sessions_rotated_tokens_utils.check_token_reuse")
    @patch("auth.router.users_utils.check_user_is_active")
    @patch("auth.router.users_crud.get_user_by_id")
    @patch("auth.router.auth_sessions_utils.validate_session_timeout")
    @patch("auth.router.auth_sessions_crud.get_session_by_id_not_expired")
    def test_refresh_web_success(
        self,
        mock_get_session,
        mock_validate_timeout,
        mock_get_user,
        mock_check_active,
        mock_check_reuse,
        mock_store_rotated,
        mock_set_cookie,
        mock_create_tokens,
        mock_edit_session,
        mock_idp_refresh,
        auth_client,
        auth_app,
        password_hasher,
    ):
        """Web refresh returns new access_token and csrf_token."""
        from datetime import datetime, timedelta

        now = datetime.now(UTC)
        mock_session = MagicMock()
        mock_session.id = "sid-1"
        mock_session.user_id = 1
        mock_session.refresh_token = password_hasher.hash_password("mock_refresh_token")
        mock_session.csrf_token_hash = None
        mock_session.token_family_id = "fam-1"
        mock_session.rotation_count = 0
        mock_get_session.return_value = mock_session
        mock_validate_timeout.return_value = None
        mock_check_reuse.return_value = (False, False)

        mock_user = MagicMock()
        mock_user.id = 1
        mock_get_user.return_value = mock_user
        mock_check_active.return_value = None

        mock_create_tokens.return_value = (
            "sid-1",
            now + timedelta(minutes=15),
            "new-at",
            now + timedelta(days=7),
            "new-rt",
            "new-csrf",
        )
        mock_edit_session.return_value = None
        mock_idp_refresh.return_value = None

        # Need to override refresh-specific dependencies
        app = auth_app
        app.dependency_overrides[auth_security.validate_refresh_token] = lambda: None
        app.dependency_overrides[auth_security.get_sub_from_refresh_token] = lambda: 1
        app.dependency_overrides[auth_security.get_sid_from_refresh_token] = lambda: "sid-1"
        app.dependency_overrides[auth_security.get_and_return_refresh_token] = lambda: "mock_refresh_token"
        app.dependency_overrides[auth_security.header_csrf_token_scheme] = lambda: None

        response = auth_client.post("/auth/refresh")

        assert response.status_code == 200
        data = response.json()
        assert data["access_token"] == "new-at"
        assert data["csrf_token"] == "new-csrf"
        assert data["token_type"] == "bearer"

    @patch("auth.router.auth_sessions_crud.get_session_by_id_not_expired")
    def test_refresh_session_not_found_returns_404(self, mock_get_session, auth_client, auth_app):
        """Missing session returns 404."""
        mock_get_session.return_value = None

        app = auth_app
        app.dependency_overrides[auth_security.validate_refresh_token] = lambda: None
        app.dependency_overrides[auth_security.get_sub_from_refresh_token] = lambda: 1
        app.dependency_overrides[auth_security.get_sid_from_refresh_token] = lambda: "nonexistent"
        app.dependency_overrides[auth_security.get_and_return_refresh_token] = lambda: "rt"
        app.dependency_overrides[auth_security.header_csrf_token_scheme] = lambda: None

        response = auth_client.post("/auth/refresh")

        assert response.status_code == 404
        assert "Session not found" in response.json()["detail"]

    @patch("auth.router.auth_sessions_utils.validate_session_timeout")
    @patch("auth.router.auth_sessions_crud.get_session_by_id_not_expired")
    def test_refresh_session_owner_mismatch_returns_401(
        self,
        mock_get_session,
        mock_validate_timeout,
        auth_client,
        auth_app,
    ):
        """Session owned by a different user than the token sub returns 401."""
        mock_session = MagicMock()
        mock_session.id = "sid-1"
        # Session belongs to user 999, but the refresh token's sub is 1.
        mock_session.user_id = 999
        mock_get_session.return_value = mock_session

        app = auth_app
        app.dependency_overrides[auth_security.validate_refresh_token] = lambda: None
        app.dependency_overrides[auth_security.get_sub_from_refresh_token] = lambda: 1
        app.dependency_overrides[auth_security.get_sid_from_refresh_token] = lambda: "sid-1"
        app.dependency_overrides[auth_security.get_and_return_refresh_token] = lambda: "rt"
        app.dependency_overrides[auth_security.header_csrf_token_scheme] = lambda: None

        response = auth_client.post("/auth/refresh")

        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid refresh token"
        # The owner check must short-circuit before session-timeout validation.
        mock_validate_timeout.assert_not_called()

    @patch("auth.router.auth_sessions_rotated_tokens_utils.invalidate_token_family")
    @patch("auth.router.auth_sessions_rotated_tokens_utils.check_token_reuse")
    @patch("auth.router.auth_sessions_utils.validate_session_timeout")
    @patch("auth.router.auth_sessions_crud.get_session_by_id_not_expired")
    def test_refresh_token_reuse_returns_401(
        self,
        mock_get_session,
        mock_validate_timeout,
        mock_check_reuse,
        mock_invalidate,
        auth_client,
        auth_app,
    ):
        """Token reuse detected invalidates family and returns 401."""
        mock_session = MagicMock()
        mock_session.id = "sid-1"
        mock_session.user_id = 1
        mock_session.refresh_token = "hashed-rt"
        mock_session.csrf_token_hash = None
        mock_session.token_family_id = "fam-1"
        mock_get_session.return_value = mock_session
        mock_validate_timeout.return_value = None
        mock_check_reuse.return_value = (True, False)

        app = auth_app
        app.dependency_overrides[auth_security.validate_refresh_token] = lambda: None
        app.dependency_overrides[auth_security.get_sub_from_refresh_token] = lambda: 1
        app.dependency_overrides[auth_security.get_sid_from_refresh_token] = lambda: "sid-1"
        app.dependency_overrides[auth_security.get_and_return_refresh_token] = lambda: "reused-token"
        app.dependency_overrides[auth_security.header_csrf_token_scheme] = lambda: None

        response = auth_client.post("/auth/refresh")

        assert response.status_code == 401
        assert "reuse" in response.json()["detail"].lower()
        mock_invalidate.assert_called_once()

    @patch("auth.router.idp_utils.refresh_idp_tokens_if_needed")
    @patch("auth.router.auth_sessions_utils.edit_session")
    @patch("auth.router.auth_utils.create_tokens")
    @patch("auth.router.auth_utils.set_refresh_token_cookie")
    @patch("auth.router.auth_sessions_rotated_tokens_utils.store_rotated_token")
    @patch("auth.router.auth_sessions_rotated_tokens_utils.check_token_reuse")
    @patch("auth.router.users_utils.check_user_is_active")
    @patch("auth.router.users_crud.get_user_by_id")
    @patch("auth.router.auth_sessions_utils.validate_session_timeout")
    @patch("auth.router.auth_sessions_utils.verify_csrf_token")
    @patch("auth.router.auth_sessions_crud.get_session_by_id_not_expired")
    def test_refresh_web_valid_csrf_token_succeeds(
        self,
        mock_get_session,
        mock_verify_csrf,
        mock_validate_timeout,
        mock_get_user,
        mock_check_active,
        mock_check_reuse,
        mock_store_rotated,
        mock_set_cookie,
        mock_create_tokens,
        mock_edit_session,
        mock_idp_refresh,
        auth_client,
        auth_app,
        password_hasher,
    ):
        """
        Valid X-CSRF-Token with stored hash allows web refresh.

        Args:
            mock_get_session: Mock for get_session_by_id_not_expired.
            mock_verify_csrf: Mock for verify_csrf_token.
            mock_validate_timeout: Mock for validate_session_timeout.
            mock_get_user: Mock for get_user_by_id.
            mock_check_active: Mock for check_user_is_active.
            mock_check_reuse: Mock for check_token_reuse.
            mock_store_rotated: Mock for store_rotated_token.
            mock_set_cookie: Mock for set_refresh_token_cookie.
            mock_create_tokens: Mock for create_tokens.
            mock_edit_session: Mock for edit_session.
            mock_idp_refresh: Mock for refresh_idp_tokens_if_needed.
            auth_client: TestClient for the auth app.
            auth_app: FastAPI test application.
            password_hasher: Real password hasher fixture.

        Returns:
            None.

        Raises:
            AssertionError: If response status is not 200.
        """
        from datetime import datetime, timedelta

        now = datetime.now(UTC)
        mock_session = MagicMock()
        mock_session.id = "sid-csrf-1"
        mock_session.user_id = 1
        mock_session.refresh_token = password_hasher.hash_password("mock_rt")
        mock_session.csrf_token_hash = "stored-hmac"
        mock_session.token_family_id = "fam-1"
        mock_session.rotation_count = 0
        mock_get_session.return_value = mock_session
        mock_validate_timeout.return_value = None
        mock_verify_csrf.return_value = True
        mock_check_reuse.return_value = (False, False)
        mock_get_user.return_value = MagicMock(id=1)
        mock_check_active.return_value = None
        mock_create_tokens.return_value = (
            "sid-csrf-1",
            now + timedelta(minutes=15),
            "new-at",
            now + timedelta(days=7),
            "new-rt",
            "new-csrf",
        )
        mock_edit_session.return_value = None
        mock_idp_refresh.return_value = None

        app = auth_app
        app.dependency_overrides[auth_security.validate_refresh_token] = lambda: None
        app.dependency_overrides[auth_security.get_sub_from_refresh_token] = lambda: 1
        app.dependency_overrides[auth_security.get_sid_from_refresh_token] = lambda: "sid-csrf-1"
        app.dependency_overrides[auth_security.get_and_return_refresh_token] = lambda: "mock_rt"
        app.dependency_overrides[auth_security.header_csrf_token_scheme] = lambda: "valid-csrf"

        response = auth_client.post("/auth/refresh")

        assert response.status_code == 200
        mock_verify_csrf.assert_called_once_with("valid-csrf", "stored-hmac")

    @patch("auth.router.auth_sessions_rotated_tokens_utils.store_rotated_token")
    @patch("auth.router.auth_sessions_utils.edit_session")
    @patch("auth.router.auth_sessions_utils.validate_session_timeout")
    @patch("auth.router.auth_sessions_utils.verify_csrf_token")
    @patch("auth.router.auth_sessions_crud.get_session_by_id_not_expired")
    def test_refresh_web_invalid_csrf_returns_403_no_side_effects(
        self,
        mock_get_session,
        mock_verify_csrf,
        mock_validate_timeout,
        mock_edit_session,
        mock_store_rotated,
        auth_client,
        auth_app,
    ):
        """
        Invalid X-CSRF-Token returns 403; no rotation side effects.

        Args:
            mock_get_session: Mock for get_session_by_id_not_expired.
            mock_verify_csrf: Mock for verify_csrf_token.
            mock_validate_timeout: Mock for validate_session_timeout.
            mock_edit_session: Mock for edit_session.
            mock_store_rotated: Mock for store_rotated_token.
            auth_client: TestClient for the auth app.
            auth_app: FastAPI test application.

        Returns:
            None.

        Raises:
            AssertionError: If status is not 403 or side effects called.
        """
        mock_session = MagicMock()
        mock_session.id = "sid-bad-csrf"
        mock_session.user_id = 1
        mock_session.refresh_token = "some-hashed-token"
        mock_session.csrf_token_hash = "stored-hmac"
        mock_get_session.return_value = mock_session
        mock_validate_timeout.return_value = None
        mock_verify_csrf.return_value = False

        app = auth_app
        app.dependency_overrides[auth_security.validate_refresh_token] = lambda: None
        app.dependency_overrides[auth_security.get_sub_from_refresh_token] = lambda: 1
        app.dependency_overrides[auth_security.get_sid_from_refresh_token] = lambda: "sid-bad-csrf"
        app.dependency_overrides[auth_security.get_and_return_refresh_token] = lambda: "any-rt"
        app.dependency_overrides[auth_security.header_csrf_token_scheme] = lambda: "wrong-csrf"

        response = auth_client.post("/auth/refresh")

        assert response.status_code == 403
        assert "CSRF" in response.json()["detail"]
        mock_store_rotated.assert_not_called()
        mock_edit_session.assert_not_called()

    @patch("auth.router.idp_utils.refresh_idp_tokens_if_needed")
    @patch("auth.router.auth_sessions_utils.edit_session")
    @patch("auth.router.auth_utils.create_tokens")
    @patch("auth.router.auth_utils.set_refresh_token_cookie")
    @patch("auth.router.auth_sessions_rotated_tokens_utils.store_rotated_token")
    @patch("auth.router.auth_sessions_rotated_tokens_utils.check_token_reuse")
    @patch("auth.router.users_utils.check_user_is_active")
    @patch("auth.router.users_crud.get_user_by_id")
    @patch("auth.router.auth_sessions_utils.validate_session_timeout")
    @patch("auth.router.auth_sessions_crud.get_session_by_id_not_expired")
    def test_refresh_missing_csrf_with_stored_hash_succeeds(
        self,
        mock_get_session,
        mock_validate_timeout,
        mock_get_user,
        mock_check_active,
        mock_check_reuse,
        mock_store_rotated,
        mock_set_cookie,
        mock_create_tokens,
        mock_edit_session,
        mock_idp_refresh,
        auth_client,
        auth_app,
        password_hasher,
    ):
        """
        No CSRF header with stored hash succeeds (page reload bootstrap).

        Args:
            mock_get_session: Mock for get_session_by_id_not_expired.
            mock_validate_timeout: Mock for validate_session_timeout.
            mock_get_user: Mock for get_user_by_id.
            mock_check_active: Mock for check_user_is_active.
            mock_check_reuse: Mock for check_token_reuse.
            mock_store_rotated: Mock for store_rotated_token.
            mock_set_cookie: Mock for set_refresh_token_cookie.
            mock_create_tokens: Mock for create_tokens.
            mock_edit_session: Mock for edit_session.
            mock_idp_refresh: Mock for refresh_idp_tokens_if_needed.
            auth_client: TestClient for the auth app.
            auth_app: FastAPI test application.
            password_hasher: Real password hasher fixture.

        Returns:
            None.

        Raises:
            AssertionError: If response status is not 200.
        """
        from datetime import datetime, timedelta

        now = datetime.now(UTC)
        mock_session = MagicMock()
        mock_session.id = "sid-reload"
        mock_session.user_id = 1
        mock_session.refresh_token = password_hasher.hash_password("mock_rt")
        mock_session.csrf_token_hash = "stored-hmac"
        mock_session.token_family_id = "fam-1"
        mock_session.rotation_count = 0
        mock_get_session.return_value = mock_session
        mock_validate_timeout.return_value = None
        mock_check_reuse.return_value = (False, False)
        mock_get_user.return_value = MagicMock(id=1)
        mock_check_active.return_value = None
        mock_create_tokens.return_value = (
            "sid-reload",
            now + timedelta(minutes=15),
            "new-at",
            now + timedelta(days=7),
            "new-rt",
            "new-csrf",
        )
        mock_edit_session.return_value = None
        mock_idp_refresh.return_value = None

        app = auth_app
        app.dependency_overrides[auth_security.validate_refresh_token] = lambda: None
        app.dependency_overrides[auth_security.get_sub_from_refresh_token] = lambda: 1
        app.dependency_overrides[auth_security.get_sid_from_refresh_token] = lambda: "sid-reload"
        app.dependency_overrides[auth_security.get_and_return_refresh_token] = lambda: "mock_rt"
        # No CSRF header: simulates page reload bootstrap
        app.dependency_overrides[auth_security.header_csrf_token_scheme] = lambda: None

        response = auth_client.post("/auth/refresh")

        assert response.status_code == 200
        assert response.json()["access_token"] == "new-at"

    @patch("auth.router.auth_sessions_utils.verify_csrf_token")
    @patch("auth.router.idp_utils.refresh_idp_tokens_if_needed")
    @patch("auth.router.auth_sessions_utils.edit_session")
    @patch("auth.router.auth_utils.create_tokens")
    @patch("auth.router.auth_utils.set_refresh_token_cookie")
    @patch("auth.router.auth_sessions_rotated_tokens_utils.store_rotated_token")
    @patch("auth.router.auth_sessions_rotated_tokens_utils.check_token_reuse")
    @patch("auth.router.users_utils.check_user_is_active")
    @patch("auth.router.users_crud.get_user_by_id")
    @patch("auth.router.auth_sessions_utils.validate_session_timeout")
    @patch("auth.router.auth_sessions_crud.get_session_by_id_not_expired")
    def test_refresh_mobile_bypasses_csrf_with_stored_hash(
        self,
        mock_get_session,
        mock_validate_timeout,
        mock_get_user,
        mock_check_active,
        mock_check_reuse,
        mock_store_rotated,
        mock_set_cookie,
        mock_create_tokens,
        mock_edit_session,
        mock_idp_refresh,
        mock_verify_csrf,
        auth_client,
        auth_app,
        password_hasher,
    ):
        """
        Mobile client skips CSRF check even when session hash is set.

        Args:
            mock_get_session: Mock for get_session_by_id_not_expired.
            mock_validate_timeout: Mock for validate_session_timeout.
            mock_get_user: Mock for get_user_by_id.
            mock_check_active: Mock for check_user_is_active.
            mock_check_reuse: Mock for check_token_reuse.
            mock_store_rotated: Mock for store_rotated_token.
            mock_set_cookie: Mock for set_refresh_token_cookie.
            mock_create_tokens: Mock for create_tokens.
            mock_edit_session: Mock for edit_session.
            mock_idp_refresh: Mock for refresh_idp_tokens_if_needed.
            mock_verify_csrf: Mock for verify_csrf_token.
            auth_client: TestClient for the auth app.
            auth_app: FastAPI test application.
            password_hasher: Real password hasher fixture.

        Returns:
            None.

        Raises:
            AssertionError: If CSRF was called or status is not 200.
        """
        from datetime import datetime, timedelta

        auth_app.state._client_type = "mobile"
        now = datetime.now(UTC)
        mock_session = MagicMock()
        mock_session.id = "sid-mob-csrf"
        mock_session.user_id = 1
        mock_session.refresh_token = password_hasher.hash_password("mock_rt")
        mock_session.csrf_token_hash = "stored-hmac"
        mock_session.token_family_id = "fam-1"
        mock_session.rotation_count = 0
        mock_get_session.return_value = mock_session
        mock_validate_timeout.return_value = None
        mock_check_reuse.return_value = (False, False)
        mock_get_user.return_value = MagicMock(id=1)
        mock_check_active.return_value = None
        mock_create_tokens.return_value = (
            "sid-mob-csrf",
            now + timedelta(minutes=15),
            "new-at",
            now + timedelta(days=7),
            "new-rt",
            None,
        )
        mock_edit_session.return_value = None
        mock_idp_refresh.return_value = None

        app = auth_app
        app.dependency_overrides[auth_security.validate_refresh_token] = lambda: None
        app.dependency_overrides[auth_security.get_sub_from_refresh_token] = lambda: 1
        app.dependency_overrides[auth_security.get_sid_from_refresh_token] = lambda: "sid-mob-csrf"
        app.dependency_overrides[auth_security.get_and_return_refresh_token] = lambda: "mock_rt"
        app.dependency_overrides[auth_security.header_csrf_token_scheme] = lambda: "any-csrf-value"

        response = auth_client.post("/auth/refresh")

        assert response.status_code == 200
        mock_verify_csrf.assert_not_called()
        mock_set_cookie.assert_not_called()
        assert "refresh_token" in response.json()

    @patch("auth.router.auth_sessions_utils.validate_session_timeout")
    @patch("auth.router.auth_sessions_crud.get_session_by_id_not_expired")
    def test_refresh_pending_pkce_no_refresh_token_returns_401(
        self,
        mock_get_session,
        mock_validate_timeout,
        auth_client,
        auth_app,
    ):
        """
        Session without refresh_token (pending PKCE) returns 401.

        Args:
            mock_get_session: Mock for get_session_by_id_not_expired.
            mock_validate_timeout: Mock for validate_session_timeout.
            auth_client: TestClient for the auth app.
            auth_app: FastAPI test application.

        Returns:
            None.

        Raises:
            AssertionError: If response status is not 401.
        """
        mock_session = MagicMock()
        mock_session.id = "sid-pkce"
        mock_session.user_id = 1
        mock_session.refresh_token = None
        mock_session.csrf_token_hash = None
        mock_get_session.return_value = mock_session
        mock_validate_timeout.return_value = None

        app = auth_app
        app.dependency_overrides[auth_security.validate_refresh_token] = lambda: None
        app.dependency_overrides[auth_security.get_sub_from_refresh_token] = lambda: 1
        app.dependency_overrides[auth_security.get_sid_from_refresh_token] = lambda: "sid-pkce"
        app.dependency_overrides[auth_security.get_and_return_refresh_token] = lambda: "rt"
        app.dependency_overrides[auth_security.header_csrf_token_scheme] = lambda: None

        response = auth_client.post("/auth/refresh")

        assert response.status_code == 401
        assert "PKCE" in response.json()["detail"]

    @patch("auth.router.auth_sessions_rotated_tokens_utils.store_rotated_token")
    @patch("auth.router.auth_sessions_utils.edit_session")
    @patch("auth.router.auth_sessions_rotated_tokens_utils.check_token_reuse")
    @patch("auth.router.auth_sessions_utils.validate_session_timeout")
    @patch("auth.router.auth_sessions_crud.get_session_by_id_not_expired")
    def test_refresh_wrong_hash_returns_401_no_side_effects(
        self,
        mock_get_session,
        mock_validate_timeout,
        mock_check_reuse,
        mock_edit_session,
        mock_store_rotated,
        auth_client,
        auth_app,
        password_hasher,
    ):
        """
        Wrong refresh token hash returns 401 without rotation side effects.

        Args:
            mock_get_session: Mock for get_session_by_id_not_expired.
            mock_validate_timeout: Mock for validate_session_timeout.
            mock_check_reuse: Mock for check_token_reuse.
            mock_edit_session: Mock for edit_session.
            mock_store_rotated: Mock for store_rotated_token.
            auth_client: TestClient for the auth app.
            auth_app: FastAPI test application.
            password_hasher: Real password hasher fixture.

        Returns:
            None.

        Raises:
            AssertionError: If status not 401 or side effects called.
        """
        mock_session = MagicMock()
        mock_session.id = "sid-bad-rt"
        mock_session.user_id = 1
        mock_session.refresh_token = password_hasher.hash_password("real_token")
        mock_session.csrf_token_hash = None
        mock_session.token_family_id = "fam-1"
        mock_session.rotation_count = 0
        mock_get_session.return_value = mock_session
        mock_validate_timeout.return_value = None
        mock_check_reuse.return_value = (False, False)

        app = auth_app
        app.dependency_overrides[auth_security.validate_refresh_token] = lambda: None
        app.dependency_overrides[auth_security.get_sub_from_refresh_token] = lambda: 1
        app.dependency_overrides[auth_security.get_sid_from_refresh_token] = lambda: "sid-bad-rt"
        app.dependency_overrides[auth_security.get_and_return_refresh_token] = lambda: "wrong_token"
        app.dependency_overrides[auth_security.header_csrf_token_scheme] = lambda: None

        response = auth_client.post("/auth/refresh")

        assert response.status_code == 401
        assert "Invalid refresh token" in response.json()["detail"]
        mock_store_rotated.assert_not_called()
        mock_edit_session.assert_not_called()

    @patch("auth.router.auth_sessions_rotated_tokens_utils.store_rotated_token")
    @patch("auth.router.auth_sessions_utils.edit_session")
    @patch("auth.router.users_utils.check_user_is_active")
    @patch("auth.router.users_crud.get_user_by_id")
    @patch("auth.router.auth_sessions_rotated_tokens_utils.check_token_reuse")
    @patch("auth.router.auth_sessions_utils.validate_session_timeout")
    @patch("auth.router.auth_sessions_crud.get_session_by_id_not_expired")
    def test_refresh_missing_user_returns_401(
        self,
        mock_get_session,
        mock_validate_timeout,
        mock_check_reuse,
        mock_get_user,
        mock_check_active,
        mock_edit_session,
        mock_store_rotated,
        auth_client,
        auth_app,
        password_hasher,
    ):
        """
        User not found during token refresh returns 401.

        Args:
            mock_get_session: Mock for get_session_by_id_not_expired.
            mock_validate_timeout: Mock for validate_session_timeout.
            mock_check_reuse: Mock for check_token_reuse.
            mock_get_user: Mock for get_user_by_id.
            mock_check_active: Mock for check_user_is_active.
            mock_edit_session: Mock for edit_session.
            mock_store_rotated: Mock for store_rotated_token.
            auth_client: TestClient for the auth app.
            auth_app: FastAPI test application.
            password_hasher: Real password hasher fixture.

        Returns:
            None.

        Raises:
            AssertionError: If response status is not 401.
        """
        mock_session = MagicMock()
        mock_session.id = "sid-no-user"
        mock_session.user_id = 1
        mock_session.refresh_token = password_hasher.hash_password("mock_rt")
        mock_session.csrf_token_hash = None
        mock_session.token_family_id = "fam-1"
        mock_session.rotation_count = 0
        mock_get_session.return_value = mock_session
        mock_validate_timeout.return_value = None
        mock_check_reuse.return_value = (False, False)
        mock_get_user.return_value = None

        app = auth_app
        app.dependency_overrides[auth_security.validate_refresh_token] = lambda: None
        app.dependency_overrides[auth_security.get_sub_from_refresh_token] = lambda: 1
        app.dependency_overrides[auth_security.get_sid_from_refresh_token] = lambda: "sid-no-user"
        app.dependency_overrides[auth_security.get_and_return_refresh_token] = lambda: "mock_rt"
        app.dependency_overrides[auth_security.header_csrf_token_scheme] = lambda: None

        response = auth_client.post("/auth/refresh")

        assert response.status_code == 401
        assert "authenticate" in response.json()["detail"].lower()

    @patch("auth.router.idp_utils.refresh_idp_tokens_if_needed")
    @patch("auth.router.auth_sessions_utils.edit_session")
    @patch("auth.router.auth_utils.create_tokens")
    @patch("auth.router.auth_utils.set_refresh_token_cookie")
    @patch("auth.router.auth_sessions_rotated_tokens_utils.store_rotated_token")
    @patch("auth.router.auth_sessions_rotated_tokens_utils.check_token_reuse")
    @patch("auth.router.users_utils.check_user_is_active")
    @patch("auth.router.users_crud.get_user_by_id")
    @patch("auth.router.auth_sessions_utils.validate_session_timeout")
    @patch("auth.router.auth_sessions_crud.get_session_by_id_not_expired")
    def test_refresh_mobile_success_includes_refresh_token_no_cookie(
        self,
        mock_get_session,
        mock_validate_timeout,
        mock_get_user,
        mock_check_active,
        mock_check_reuse,
        mock_store_rotated,
        mock_set_cookie,
        mock_create_tokens,
        mock_edit_session,
        mock_idp_refresh,
        auth_client,
        auth_app,
        password_hasher,
    ):
        """
        Mobile refresh returns refresh_token in body without cookie.

        Args:
            mock_get_session: Mock for get_session_by_id_not_expired.
            mock_validate_timeout: Mock for validate_session_timeout.
            mock_get_user: Mock for get_user_by_id.
            mock_check_active: Mock for check_user_is_active.
            mock_check_reuse: Mock for check_token_reuse.
            mock_store_rotated: Mock for store_rotated_token.
            mock_set_cookie: Mock for set_refresh_token_cookie.
            mock_create_tokens: Mock for create_tokens.
            mock_edit_session: Mock for edit_session.
            mock_idp_refresh: Mock for refresh_idp_tokens_if_needed.
            auth_client: TestClient for the auth app.
            auth_app: FastAPI test application.
            password_hasher: Real password hasher fixture.

        Returns:
            None.

        Raises:
            AssertionError: If refresh_token missing or cookie was set.
        """
        from datetime import datetime, timedelta

        auth_app.state._client_type = "mobile"
        now = datetime.now(UTC)
        mock_session = MagicMock()
        mock_session.id = "sid-mob"
        mock_session.user_id = 1
        mock_session.refresh_token = password_hasher.hash_password("mock_rt")
        mock_session.csrf_token_hash = None
        mock_session.token_family_id = "fam-1"
        mock_session.rotation_count = 0
        mock_get_session.return_value = mock_session
        mock_validate_timeout.return_value = None
        mock_check_reuse.return_value = (False, False)
        mock_get_user.return_value = MagicMock(id=1)
        mock_check_active.return_value = None
        mock_create_tokens.return_value = (
            "sid-mob",
            now + timedelta(minutes=15),
            "new-at",
            now + timedelta(days=7),
            "new-rt",
            None,
        )
        mock_edit_session.return_value = None
        mock_idp_refresh.return_value = None

        app = auth_app
        app.dependency_overrides[auth_security.validate_refresh_token] = lambda: None
        app.dependency_overrides[auth_security.get_sub_from_refresh_token] = lambda: 1
        app.dependency_overrides[auth_security.get_sid_from_refresh_token] = lambda: "sid-mob"
        app.dependency_overrides[auth_security.get_and_return_refresh_token] = lambda: "mock_rt"
        app.dependency_overrides[auth_security.header_csrf_token_scheme] = lambda: None

        response = auth_client.post("/auth/refresh")

        assert response.status_code == 200
        data = response.json()
        assert "refresh_token" in data
        assert data["refresh_token"] == "new-rt"
        mock_set_cookie.assert_not_called()

    @patch("auth.router.auth_utils.mint_access_token")
    @patch("auth.router.auth_sessions_rotated_tokens_utils.get_grace_replay_token")
    @patch("auth.router.auth_utils.create_tokens")
    @patch("auth.router.auth_sessions_utils.edit_session")
    @patch("auth.router.auth_sessions_rotated_tokens_utils.store_rotated_token")
    @patch("auth.router.auth_sessions_rotated_tokens_utils.check_token_reuse")
    @patch("auth.router.users_utils.check_user_is_active")
    @patch("auth.router.users_crud.get_user_by_id")
    @patch("auth.router.auth_sessions_utils.validate_session_timeout")
    @patch("auth.router.auth_sessions_crud.get_session_by_id_not_expired")
    def test_refresh_in_grace_replay_mobile_returns_replayed_token(
        self,
        mock_get_session,
        mock_validate_timeout,
        mock_get_user,
        mock_check_active,
        mock_check_reuse,
        mock_store_rotated,
        mock_edit_session,
        mock_create_tokens,
        mock_get_replay,
        mock_mint_access,
        auth_client,
        auth_app,
        password_hasher,
    ):
        """In-grace replay (mobile) returns the stored replacement token."""
        from datetime import datetime, timedelta

        auth_app.state._client_type = "mobile"
        now = datetime.now(UTC)
        mock_session = MagicMock()
        mock_session.id = "sid-replay-mob"
        mock_session.user_id = 1
        mock_session.refresh_token = password_hasher.hash_password("current_rt")
        mock_session.csrf_token_hash = None
        mock_session.token_family_id = "fam-1"
        mock_session.rotation_count = 1
        mock_get_session.return_value = mock_session
        mock_validate_timeout.return_value = None
        # Presented token was already rotated but is still within grace.
        mock_check_reuse.return_value = (True, True)
        mock_get_replay.return_value = ("replayed-rt", now + timedelta(days=7))
        mock_get_user.return_value = MagicMock(id=1)
        mock_check_active.return_value = None
        mock_mint_access.return_value = (now + timedelta(minutes=15), "replayed-at")

        app = auth_app
        app.dependency_overrides[auth_security.validate_refresh_token] = lambda: None
        app.dependency_overrides[auth_security.get_sub_from_refresh_token] = lambda: 1
        app.dependency_overrides[auth_security.get_sid_from_refresh_token] = lambda: "sid-replay-mob"
        app.dependency_overrides[auth_security.get_and_return_refresh_token] = lambda: "old_rotated_rt"
        app.dependency_overrides[auth_security.header_csrf_token_scheme] = lambda: None

        response = auth_client.post("/auth/refresh")

        assert response.status_code == 200
        data = response.json()
        assert data["access_token"] == "replayed-at"
        assert data["refresh_token"] == "replayed-rt"
        # Replay must be idempotent: no re-rotation side effects.
        mock_store_rotated.assert_not_called()
        mock_edit_session.assert_not_called()
        mock_create_tokens.assert_not_called()
        mock_mint_access.assert_called_once()

    @patch("auth.router.auth_sessions_utils.update_session_csrf_token")
    @patch("auth.router.auth_utils.set_refresh_token_cookie")
    @patch("auth.router.auth_utils.mint_access_token")
    @patch("auth.router.auth_sessions_rotated_tokens_utils.get_grace_replay_token")
    @patch("auth.router.auth_utils.create_tokens")
    @patch("auth.router.auth_sessions_utils.edit_session")
    @patch("auth.router.auth_sessions_rotated_tokens_utils.store_rotated_token")
    @patch("auth.router.auth_sessions_rotated_tokens_utils.check_token_reuse")
    @patch("auth.router.users_utils.check_user_is_active")
    @patch("auth.router.users_crud.get_user_by_id")
    @patch("auth.router.auth_sessions_utils.validate_session_timeout")
    @patch("auth.router.auth_sessions_crud.get_session_by_id_not_expired")
    def test_refresh_in_grace_replay_web_mints_fresh_csrf(
        self,
        mock_get_session,
        mock_validate_timeout,
        mock_get_user,
        mock_check_active,
        mock_check_reuse,
        mock_store_rotated,
        mock_edit_session,
        mock_create_tokens,
        mock_get_replay,
        mock_mint_access,
        mock_set_cookie,
        mock_update_csrf,
        auth_client,
        auth_app,
        password_hasher,
    ):
        """In-grace replay (web) mints a fresh access token and CSRF token."""
        from datetime import datetime, timedelta

        now = datetime.now(UTC)
        mock_session = MagicMock()
        mock_session.id = "sid-replay-web"
        mock_session.user_id = 1
        mock_session.refresh_token = password_hasher.hash_password("current_rt")
        mock_session.csrf_token_hash = "stored-hmac"
        mock_session.token_family_id = "fam-1"
        mock_session.rotation_count = 1
        mock_get_session.return_value = mock_session
        mock_validate_timeout.return_value = None
        mock_check_reuse.return_value = (True, True)
        mock_get_replay.return_value = ("replayed-rt", now + timedelta(days=7))
        mock_get_user.return_value = MagicMock(id=1)
        mock_check_active.return_value = None
        mock_mint_access.return_value = (now + timedelta(minutes=15), "replayed-at")
        mock_set_cookie.return_value = None
        mock_update_csrf.return_value = None

        app = auth_app
        app.dependency_overrides[auth_security.validate_refresh_token] = lambda: None
        app.dependency_overrides[auth_security.get_sub_from_refresh_token] = lambda: 1
        app.dependency_overrides[auth_security.get_sid_from_refresh_token] = lambda: "sid-replay-web"
        app.dependency_overrides[auth_security.get_and_return_refresh_token] = lambda: "old_rotated_rt"
        # No CSRF header: page-reload bootstrap / lost rotation response.
        app.dependency_overrides[auth_security.header_csrf_token_scheme] = lambda: None

        response = auth_client.post("/auth/refresh")

        assert response.status_code == 200
        data = response.json()
        assert data["access_token"] == "replayed-at"
        # A fresh CSRF token is minted and bound to the session.
        assert data["csrf_token"]
        mock_update_csrf.assert_called_once()
        assert mock_update_csrf.call_args.args[0] == "sid-replay-web"
        # Refresh token is unchanged: delivered via cookie, no re-rotation.
        mock_set_cookie.assert_called_once()
        mock_store_rotated.assert_not_called()
        mock_edit_session.assert_not_called()
        mock_create_tokens.assert_not_called()

    @patch("auth.router.auth_sessions_rotated_tokens_utils.get_grace_replay_token")
    @patch("auth.router.auth_sessions_utils.edit_session")
    @patch("auth.router.auth_sessions_rotated_tokens_utils.store_rotated_token")
    @patch("auth.router.auth_sessions_rotated_tokens_utils.check_token_reuse")
    @patch("auth.router.auth_sessions_utils.validate_session_timeout")
    @patch("auth.router.auth_sessions_crud.get_session_by_id_not_expired")
    def test_refresh_in_grace_replay_missing_replacement_returns_401(
        self,
        mock_get_session,
        mock_validate_timeout,
        mock_check_reuse,
        mock_store_rotated,
        mock_edit_session,
        mock_get_replay,
        auth_client,
        auth_app,
        password_hasher,
    ):
        """In-grace replay with no stored replacement returns 401."""
        mock_session = MagicMock()
        mock_session.id = "sid-replay-none"
        mock_session.user_id = 1
        mock_session.refresh_token = password_hasher.hash_password("current_rt")
        mock_session.csrf_token_hash = None
        mock_session.token_family_id = "fam-1"
        mock_session.rotation_count = 1
        mock_get_session.return_value = mock_session
        mock_validate_timeout.return_value = None
        mock_check_reuse.return_value = (True, True)
        mock_get_replay.return_value = None

        app = auth_app
        app.dependency_overrides[auth_security.validate_refresh_token] = lambda: None
        app.dependency_overrides[auth_security.get_sub_from_refresh_token] = lambda: 1
        app.dependency_overrides[auth_security.get_sid_from_refresh_token] = lambda: "sid-replay-none"
        app.dependency_overrides[auth_security.get_and_return_refresh_token] = lambda: "old_rotated_rt"
        app.dependency_overrides[auth_security.header_csrf_token_scheme] = lambda: None

        response = auth_client.post("/auth/refresh")

        assert response.status_code == 401
        assert "Invalid refresh token" in response.json()["detail"]
        mock_store_rotated.assert_not_called()
        mock_edit_session.assert_not_called()


# ------------------------------------------------------------------
# POST /auth/logout
# ------------------------------------------------------------------


class TestLogoutEndpoint:
    """Tests for POST /auth/logout endpoint."""

    @patch("auth.router.idp_utils.clear_all_idp_tokens")
    @patch("auth.router.auth_sessions_crud.delete_session")
    @patch("auth.router.auth_sessions_crud.get_session_by_id_not_expired")
    def test_logout_success(
        self,
        mock_get_session,
        mock_delete_session,
        mock_clear_idp,
        auth_client,
        auth_app,
        password_hasher,
    ):
        """Successful logout deletes session."""
        mock_session = MagicMock()
        mock_session.id = "sid-1"
        mock_session.refresh_token = password_hasher.hash_password("mock_refresh_token")
        mock_get_session.return_value = mock_session
        mock_delete_session.return_value = None
        mock_clear_idp.return_value = None

        app = auth_app
        app.dependency_overrides[auth_security.validate_refresh_token] = lambda: None
        app.dependency_overrides[auth_security.get_sub_from_refresh_token] = lambda: 1
        app.dependency_overrides[auth_security.get_sid_from_refresh_token] = lambda: "sid-1"
        app.dependency_overrides[auth_security.get_and_return_refresh_token] = lambda: "mock_refresh_token"

        response = auth_client.post("/auth/logout")

        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        mock_delete_session.assert_called_once()

    @patch("auth.router.auth_sessions_crud.get_session_by_id_not_expired")
    def test_logout_invalid_refresh_token_returns_401(
        self,
        mock_get_session,
        auth_client,
        auth_app,
        password_hasher,
    ):
        """Invalid refresh token returns 401."""
        mock_session = MagicMock()
        mock_session.id = "sid-1"
        mock_session.refresh_token = password_hasher.hash_password("real_token")
        mock_get_session.return_value = mock_session

        app = auth_app
        app.dependency_overrides[auth_security.validate_refresh_token] = lambda: None
        app.dependency_overrides[auth_security.get_sub_from_refresh_token] = lambda: 1
        app.dependency_overrides[auth_security.get_sid_from_refresh_token] = lambda: "sid-1"
        app.dependency_overrides[auth_security.get_and_return_refresh_token] = lambda: "wrong_token"

        response = auth_client.post("/auth/logout")

        assert response.status_code == 401
        assert "Invalid refresh token" in response.json()["detail"]

    @patch("auth.router.auth_utils.clear_refresh_token_cookies")
    @patch("auth.router.auth_sessions_crud.delete_session")
    @patch("auth.router.auth_sessions_crud.get_session_by_id_not_expired")
    def test_logout_missing_session_is_idempotent_success(
        self,
        mock_get_session,
        mock_delete_session,
        mock_clear_cookies,
        auth_client,
        auth_app,
    ):
        """
        Missing session returns 200; delete_session is not called.

        Args:
            mock_get_session: Mock for get_session_by_id_not_expired.
            mock_delete_session: Mock for delete_session.
            mock_clear_cookies: Mock for clear_refresh_token_cookies.
            auth_client: TestClient for the auth app.
            auth_app: FastAPI test application.

        Returns:
            None.

        Raises:
            AssertionError: If status not 200 or delete was called.
        """
        mock_get_session.return_value = None

        app = auth_app
        app.dependency_overrides[auth_security.validate_refresh_token] = lambda: None
        app.dependency_overrides[auth_security.get_sub_from_refresh_token] = lambda: 1
        app.dependency_overrides[auth_security.get_sid_from_refresh_token] = lambda: "nonexistent"
        app.dependency_overrides[auth_security.get_and_return_refresh_token] = lambda: "rt"

        response = auth_client.post("/auth/logout")

        assert response.status_code == 200
        mock_delete_session.assert_not_called()

    @patch("auth.router.auth_sessions_crud.get_session_by_id_not_expired")
    def test_logout_pending_pkce_no_refresh_token_returns_401(
        self,
        mock_get_session,
        auth_client,
        auth_app,
    ):
        """
        Session without refresh_token (pending PKCE) returns 401.

        Args:
            mock_get_session: Mock for get_session_by_id_not_expired.
            auth_client: TestClient for the auth app.
            auth_app: FastAPI test application.

        Returns:
            None.

        Raises:
            AssertionError: If response status is not 401.
        """
        mock_session = MagicMock()
        mock_session.id = "sid-pkce"
        mock_session.refresh_token = None
        mock_get_session.return_value = mock_session

        app = auth_app
        app.dependency_overrides[auth_security.validate_refresh_token] = lambda: None
        app.dependency_overrides[auth_security.get_sub_from_refresh_token] = lambda: 1
        app.dependency_overrides[auth_security.get_sid_from_refresh_token] = lambda: "sid-pkce"
        app.dependency_overrides[auth_security.get_and_return_refresh_token] = lambda: "rt"

        response = auth_client.post("/auth/logout")

        assert response.status_code == 401
        assert "PKCE" in response.json()["detail"]

    @patch("auth.router.auth_utils.clear_refresh_token_cookies")
    @patch("auth.router.idp_utils.clear_all_idp_tokens")
    @patch("auth.router.auth_sessions_crud.delete_session")
    @patch("auth.router.auth_sessions_crud.get_session_by_id_not_expired")
    def test_logout_web_clears_refresh_cookies(
        self,
        mock_get_session,
        mock_delete_session,
        mock_clear_idp,
        mock_clear_cookies,
        auth_client,
        auth_app,
        password_hasher,
    ):
        """
        Web logout calls clear_refresh_token_cookies on response.

        Args:
            mock_get_session: Mock for get_session_by_id_not_expired.
            mock_delete_session: Mock for delete_session.
            mock_clear_idp: Mock for clear_all_idp_tokens.
            mock_clear_cookies: Mock for clear_refresh_token_cookies.
            auth_client: TestClient for the auth app.
            auth_app: FastAPI test application.
            password_hasher: Real password hasher fixture.

        Returns:
            None.

        Raises:
            AssertionError: If status not 200 or cookies not cleared.
        """
        mock_session = MagicMock()
        mock_session.id = "sid-web"
        mock_session.refresh_token = password_hasher.hash_password("mock_rt")
        mock_get_session.return_value = mock_session
        mock_delete_session.return_value = None
        mock_clear_idp.return_value = None

        app = auth_app
        app.dependency_overrides[auth_security.validate_refresh_token] = lambda: None
        app.dependency_overrides[auth_security.get_sub_from_refresh_token] = lambda: 1
        app.dependency_overrides[auth_security.get_sid_from_refresh_token] = lambda: "sid-web"
        app.dependency_overrides[auth_security.get_and_return_refresh_token] = lambda: "mock_rt"

        response = auth_client.post("/auth/logout")

        assert response.status_code == 200
        mock_clear_cookies.assert_called_once()

    @patch("auth.router.auth_utils.clear_refresh_token_cookies")
    @patch("auth.router.idp_utils.clear_all_idp_tokens")
    @patch("auth.router.auth_sessions_crud.delete_session")
    @patch("auth.router.auth_sessions_crud.get_session_by_id_not_expired")
    def test_logout_mobile_succeeds_without_cookie_clearing(
        self,
        mock_get_session,
        mock_delete_session,
        mock_clear_idp,
        mock_clear_cookies,
        auth_client,
        auth_app,
        password_hasher,
    ):
        """
        Mobile logout returns 200 without clearing refresh cookies.

        Args:
            mock_get_session: Mock for get_session_by_id_not_expired.
            mock_delete_session: Mock for delete_session.
            mock_clear_idp: Mock for clear_all_idp_tokens.
            mock_clear_cookies: Mock for clear_refresh_token_cookies.
            auth_client: TestClient for the auth app.
            auth_app: FastAPI test application.
            password_hasher: Real password hasher fixture.

        Returns:
            None.

        Raises:
            AssertionError: If status not 200 or cookies were cleared.
        """
        auth_app.state._client_type = "mobile"
        mock_session = MagicMock()
        mock_session.id = "sid-mob"
        mock_session.refresh_token = password_hasher.hash_password("mock_rt")
        mock_get_session.return_value = mock_session
        mock_delete_session.return_value = None
        mock_clear_idp.return_value = None

        app = auth_app
        app.dependency_overrides[auth_security.validate_refresh_token] = lambda: None
        app.dependency_overrides[auth_security.get_sub_from_refresh_token] = lambda: 1
        app.dependency_overrides[auth_security.get_sid_from_refresh_token] = lambda: "sid-mob"
        app.dependency_overrides[auth_security.get_and_return_refresh_token] = lambda: "mock_rt"

        response = auth_client.post("/auth/logout")

        assert response.status_code == 200
        mock_clear_cookies.assert_not_called()

    @patch("auth.router.auth_sessions_crud.get_session_by_id_not_expired")
    def test_logout_invalid_client_type_returns_403(
        self,
        mock_get_session,
        auth_client,
        auth_app,
    ):
        """
        Invalid client_type on logout returns 403.

        Args:
            mock_get_session: Mock for get_session_by_id_not_expired.
            auth_client: TestClient for the auth app.
            auth_app: FastAPI test application.

        Returns:
            None.

        Raises:
            AssertionError: If response status is not 403.
        """
        auth_app.state._client_type = "tablet"
        mock_get_session.return_value = None

        app = auth_app
        app.dependency_overrides[auth_security.validate_refresh_token] = lambda: None
        app.dependency_overrides[auth_security.get_sub_from_refresh_token] = lambda: 1
        app.dependency_overrides[auth_security.get_sid_from_refresh_token] = lambda: "sid-1"
        app.dependency_overrides[auth_security.get_and_return_refresh_token] = lambda: "rt"

        response = auth_client.post("/auth/logout")

        assert response.status_code == 403
        assert "client type" in response.json()["detail"].lower()

    @patch("auth.router.auth_utils.clear_refresh_token_cookies")
    @patch("auth.router.auth_sessions_crud.delete_session")
    @patch("auth.router.auth_sessions_crud.get_session_by_id_not_expired")
    def test_logout_missing_session_is_idempotent_success_mobile(
        self,
        mock_get_session,
        mock_delete_session,
        mock_clear_cookies,
        auth_client,
        auth_app,
    ):
        auth_app.state._client_type = "mobile"
        mock_get_session.return_value = None

        app = auth_app
        app.dependency_overrides[auth_security.validate_refresh_token] = lambda: None
        app.dependency_overrides[auth_security.get_sub_from_refresh_token] = lambda: 1
        app.dependency_overrides[auth_security.get_sid_from_refresh_token] = lambda: "nonexistent"
        app.dependency_overrides[auth_security.get_and_return_refresh_token] = lambda: "rt"

        response = auth_client.post("/auth/logout")
        assert response.status_code == 200
        mock_delete_session.assert_not_called()
        mock_clear_cookies.assert_not_called()
