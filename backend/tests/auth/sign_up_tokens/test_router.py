"""Integration tests for sign_up_tokens router endpoints."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient
from jasil.backends.state_memory import MemoryState
from sqlalchemy.orm import Session

import core.database as core_database
import core.dependencies as core_dependencies
import core.exceptions as core_exceptions
import modules.auth.credentials.password_hasher as auth_password_hasher
import modules.auth.sign_up_tokens.public_router as sign_up_tokens_router

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db() -> MagicMock:
    """
    Return a mock SQLAlchemy session.

    Returns:
        MagicMock: Mock database session.
    """
    return MagicMock(spec=Session)


@pytest.fixture
def mock_email_service():
    """
    Patch ``is_mail_configured`` to return True; tests flip ``return_value``.

    Yields:
        MagicMock: The patched ``is_mail_configured`` function.
    """
    with patch(
        "modules.auth.sign_up_tokens.service.server_settings_integration.is_mail_configured", return_value=True
    ) as is_configured:
        yield is_configured


@pytest.fixture
def signup_app(
    mock_db,
    mock_email_service,
    password_hasher,
) -> FastAPI:
    """
    Create a minimal FastAPI app for sign_up_tokens router tests.

    Args:
        mock_db: Mock database session.
        mock_email_service: Patched mail-configured check.
        password_hasher: Real PasswordHasher instance.

    Returns:
        FastAPI: Configured test application.
    """
    app = FastAPI()
    core_exceptions.register_exception_handlers(app)
    app.include_router(
        sign_up_tokens_router.router,
        prefix="/sign-up",
    )

    app.dependency_overrides[core_database.get_db] = lambda: mock_db
    app.dependency_overrides[core_dependencies.get_platform_state] = lambda: MemoryState()
    app.dependency_overrides[auth_password_hasher.get_password_hasher] = lambda: password_hasher

    return app


@pytest.fixture
def signup_client(signup_app: FastAPI) -> TestClient:
    """
    Return a TestClient for the sign_up_tokens test app.

    Args:
        signup_app: Configured test application.

    Returns:
        TestClient: HTTP test client.
    """
    return TestClient(signup_app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# POST /sign-up/sign-up/request
# ---------------------------------------------------------------------------


class TestSignupEndpoint:
    """Tests for POST /sign-up/sign-up/request."""

    @patch("modules.auth.sign_up_tokens.service.request_sign_up_verification_email")
    @patch("modules.auth.sign_up_tokens.service.users_integration.create_signup_user")
    @patch("modules.auth.sign_up_tokens.service.server_settings_integration.get_server_settings")
    def test_signup_success_no_verification_no_approval(
        self,
        mock_settings,
        mock_create_user,
        mock_send_email,
        signup_client,
    ) -> None:
        """
        Returns 201 with login message when neither email
        verification nor admin approval is required.
        """
        mock_settings.return_value = MagicMock(
            signup_enabled=True,
            signup_require_email_verification=False,
            signup_require_admin_approval=False,
        )
        mock_create_user.return_value = MagicMock(id=1)

        response = signup_client.post(
            "/sign-up/sign-up/request",
            json={
                "name": "Test User",
                "username": "testuser",
                "email": "test@example.com",
                "password": "SecurePass1!",
                "preferred_language": "en",
            },
        )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert "message" in data
        assert "log in" in data["message"].lower()
        assert data["email_verification_required"] is None
        assert data["admin_approval_required"] is None

    @patch("modules.auth.sign_up_tokens.service.request_sign_up_verification_email")
    @patch("modules.auth.sign_up_tokens.service.users_integration.create_signup_user")
    @patch("modules.auth.sign_up_tokens.service.server_settings_integration.get_server_settings")
    def test_signup_success_email_verification_required(
        self,
        mock_settings,
        mock_create_user,
        mock_send_email,
        signup_client,
    ) -> None:
        """
        Returns 201 with email_verification_required=True and
        success message when server requires email verification.
        """
        mock_settings.return_value = MagicMock(
            signup_enabled=True,
            signup_require_email_verification=True,
            signup_require_admin_approval=False,
        )
        mock_create_user.return_value = MagicMock(id=2)
        mock_send_email.return_value = True

        response = signup_client.post(
            "/sign-up/sign-up/request",
            json={
                "name": "Email User",
                "username": "emailuser",
                "email": "emailuser@example.com",
                "password": "SecurePass1!",
                "preferred_language": "en",
            },
        )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["email_verification_required"] is True

    @patch("modules.auth.sign_up_tokens.service.server_settings_integration.get_server_settings")
    def test_signup_disabled_returns_403(
        self,
        mock_settings,
        signup_client,
    ) -> None:
        """
        Returns 403 when sign-up is disabled in server settings.
        """
        mock_settings.return_value = MagicMock(
            signup_enabled=False,
        )

        response = signup_client.post(
            "/sign-up/sign-up/request",
            json={
                "name": "Blocked User",
                "username": "blocked",
                "email": "blocked@example.com",
                "password": "SecurePass1!",
                "preferred_language": "en",
            },
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "not enabled" in response.json()["detail"].lower()

    @patch("modules.auth.sign_up_tokens.service.server_settings_integration.get_server_settings")
    def test_signup_missing_required_fields_returns_422(
        self,
        mock_settings,
        signup_client,
    ) -> None:
        """
        Returns 422 when required user fields are absent.
        """
        mock_settings.return_value = MagicMock(signup_enabled=True)

        response = signup_client.post(
            "/sign-up/sign-up/request",
            json={},
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    @patch("modules.auth.sign_up_tokens.service.users_integration.create_signup_user")
    @patch("modules.auth.sign_up_tokens.service.server_settings_integration.get_server_settings")
    def test_signup_duplicate_user_propagates_conflict(
        self,
        mock_settings,
        mock_create_user,
        signup_client,
    ) -> None:
        """
        Propagates 409 (or other HTTP error) raised by
        create_signup_user when username/email already exists.
        """
        mock_settings.return_value = MagicMock(
            signup_enabled=True,
            signup_require_email_verification=False,
            signup_require_admin_approval=False,
        )
        mock_create_user.side_effect = HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already exists",
        )

        response = signup_client.post(
            "/sign-up/sign-up/request",
            json={
                "name": "Dup User",
                "username": "existing",
                "email": "dup@example.com",
                "password": "SecurePass1!",
                "preferred_language": "en",
            },
        )

        assert response.status_code == status.HTTP_409_CONFLICT

    @patch("modules.auth.sign_up_tokens.service.request_sign_up_verification_email")
    @patch("modules.auth.sign_up_tokens.service.users_integration.create_signup_user")
    @patch("modules.auth.sign_up_tokens.service.server_settings_integration.get_server_settings")
    def test_signup_admin_approval_required_returns_flag(
        self,
        mock_settings,
        mock_create_user,
        mock_send_email,
        signup_client,
    ) -> None:
        """
        Returns 201 with admin_approval_required=True when server
        requires admin approval.
        """
        mock_settings.return_value = MagicMock(
            signup_enabled=True,
            signup_require_email_verification=False,
            signup_require_admin_approval=True,
        )
        mock_create_user.return_value = MagicMock(id=4)

        response = signup_client.post(
            "/sign-up/sign-up/request",
            json={
                "name": "Admin User",
                "username": "adminuser",
                "email": "admin@example.com",
                "password": "SecurePass1!",
                "preferred_language": "en",
            },
        )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["admin_approval_required"] is True

    @patch("modules.auth.sign_up_tokens.service.request_sign_up_verification_email")
    @patch("modules.auth.sign_up_tokens.service.users_integration.create_signup_user")
    @patch("modules.auth.sign_up_tokens.service.server_settings_integration.get_server_settings")
    def test_signup_propagates_503_when_request_verification_email_raises(
        self,
        mock_settings,
        mock_create_user,
        mock_send_email,
        signup_client,
    ) -> None:
        """
        Returns 503 when email verification is required and
        request_sign_up_verification_email raises HTTPException 503 (email
        service not configured at send time).
        """
        mock_settings.return_value = MagicMock(
            signup_enabled=True,
            signup_require_email_verification=True,
            signup_require_admin_approval=False,
        )
        mock_create_user.return_value = MagicMock(id=5)
        mock_send_email.side_effect = HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email service is not configured",
        )

        response = signup_client.post(
            "/sign-up/sign-up/request",
            json={
                "name": "Service User",
                "username": "svcuser",
                "email": "svc@example.com",
                "password": "SecurePass1!",
                "preferred_language": "en",
            },
        )

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


# ---------------------------------------------------------------------------
# POST /sign-up/sign-up/confirm
# ---------------------------------------------------------------------------


class TestVerifyEmailEndpoint:
    """Tests for POST /sign-up/sign-up/confirm."""

    @pytest.fixture(autouse=True)
    def not_deactivated(self):
        with patch("modules.auth.sign_up_tokens.service.users_integration.is_deactivated", return_value=False):
            yield

    @patch("modules.auth.sign_up_tokens.service.notifications_integration.create_admin_sign_up_approval_notifications")
    @patch("modules.auth.sign_up_tokens.service.request_sign_up_admin_approval_emails")
    @patch("modules.auth.sign_up_tokens.service.users_integration.get_user")
    @patch("modules.auth.sign_up_tokens.service.users_integration.stage_email_verification")
    @patch("modules.auth.sign_up_tokens.service.verify_sign_up_token")
    @patch("modules.auth.sign_up_tokens.service.server_settings_integration.get_server_settings")
    def test_verify_email_success_no_admin_approval(
        self,
        mock_settings,
        mock_use_token,
        mock_verify_email,
        mock_get_user,
        mock_send_admin_email,
        mock_notify,
        signup_client,
        mock_email_service,
    ) -> None:
        """
        Returns 200 with success message when email verification
        succeeds and admin approval is not required.
        """
        mock_settings.return_value = MagicMock(
            signup_require_email_verification=True,
            signup_require_admin_approval=False,
        )
        mock_use_token.return_value = MagicMock(user_id=10, previous_email=None)
        mock_verify_email.return_value = None
        mock_get_user.return_value = MagicMock(id=10, active=False)
        mock_send_admin_email.return_value = None
        mock_notify.return_value = []
        mock_email_service.return_value = True

        response = signup_client.post(
            "/sign-up/sign-up/confirm",
            json={"token": "valid-verification-token"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "verified" in data["message"].lower()
        assert data["admin_approval_required"] is None

    @patch("modules.auth.sign_up_tokens.service.verify_sign_up_token")
    @patch("modules.auth.sign_up_tokens.service.server_settings_integration.get_server_settings")
    def test_verify_email_invalid_token_returns_400(
        self,
        mock_settings,
        mock_use_token,
        signup_client,
    ) -> None:
        """
        Returns 400 when the token is invalid or expired.
        """
        mock_settings.return_value = MagicMock(
            signup_require_email_verification=True,
            signup_require_admin_approval=False,
        )
        mock_use_token.side_effect = HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired token",
        )

        response = signup_client.post(
            "/sign-up/sign-up/confirm",
            json={"token": "invalid-token"},
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @patch("modules.auth.sign_up_tokens.service.notifications_integration.create_admin_sign_up_approval_notifications")
    @patch("modules.auth.sign_up_tokens.service.request_sign_up_admin_approval_emails")
    @patch("modules.auth.sign_up_tokens.service.users_integration.get_user")
    @patch("modules.auth.sign_up_tokens.service.users_integration.stage_email_verification")
    @patch("modules.auth.sign_up_tokens.service.verify_sign_up_token")
    @patch("modules.auth.sign_up_tokens.service.server_settings_integration.get_server_settings")
    def test_verify_email_of_an_active_account_skips_the_sign_up_flow(
        self,
        mock_settings,
        mock_use_token,
        mock_verify_email,
        mock_get_user,
        mock_send_admin_email,
        mock_notify,
        signup_client,
    ) -> None:
        """
        An already active account confirming a changed address is verified without asking an
        admin to approve it, and without needing the sign-up policy to require verification.
        """
        mock_settings.return_value = MagicMock(
            signup_require_email_verification=False,
            signup_require_admin_approval=True,
        )
        mock_use_token.return_value = MagicMock(user_id=10, previous_email=None)
        mock_get_user.return_value = MagicMock(id=10, active=True)

        response = signup_client.post(
            "/sign-up/sign-up/confirm",
            json={"token": "valid-verification-token"},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["admin_approval_required"] is None
        mock_verify_email.assert_called_once()
        mock_send_admin_email.assert_not_called()
        mock_notify.assert_not_called()

    @patch("modules.auth.sign_up_tokens.service.users_integration.get_user")
    @patch("modules.auth.sign_up_tokens.service.verify_sign_up_token")
    @patch("modules.auth.sign_up_tokens.service.server_settings_integration.get_server_settings")
    def test_verify_email_not_enabled_returns_412(
        self,
        mock_settings,
        mock_use_token,
        mock_get_user,
        signup_client,
    ) -> None:
        """
        Returns 412 when a sign-up is verified but email verification is not enabled on
        the server.
        """
        mock_settings.return_value = MagicMock(
            signup_require_email_verification=False,
        )
        mock_use_token.return_value = MagicMock(user_id=10, previous_email=None)
        mock_get_user.return_value = MagicMock(id=10, active=False)

        response = signup_client.post(
            "/sign-up/sign-up/confirm",
            json={"token": "any-token"},
        )

        assert response.status_code == status.HTTP_412_PRECONDITION_FAILED

    @patch("modules.auth.sign_up_tokens.service.server_settings_integration.get_server_settings")
    def test_verify_email_missing_token_returns_422(
        self,
        mock_settings,
        signup_client,
    ) -> None:
        """
        Returns 422 when the token field is absent.
        """
        mock_settings.return_value = MagicMock(
            signup_require_email_verification=True,
        )

        response = signup_client.post(
            "/sign-up/sign-up/confirm",
            json={},
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    @patch("modules.auth.sign_up_tokens.service.notifications_integration.create_admin_sign_up_approval_notifications")
    @patch("modules.auth.sign_up_tokens.service.request_sign_up_admin_approval_emails")
    @patch("modules.auth.sign_up_tokens.service.users_integration.get_user")
    @patch("modules.auth.sign_up_tokens.service.users_integration.stage_email_verification")
    @patch("modules.auth.sign_up_tokens.service.verify_sign_up_token")
    @patch("modules.auth.sign_up_tokens.service.server_settings_integration.get_server_settings")
    def test_verify_email_with_admin_approval_sets_flag(
        self,
        mock_settings,
        mock_use_token,
        mock_verify_email,
        mock_get_user,
        mock_send_admin_email,
        mock_notify,
        signup_client,
        mock_email_service,
    ) -> None:
        """
        Returns admin_approval_required=True in response when
        server requires admin approval after email verification.
        """
        mock_settings.return_value = MagicMock(
            signup_require_email_verification=True,
            signup_require_admin_approval=True,
        )
        mock_use_token.return_value = MagicMock(user_id=11, previous_email=None)
        mock_verify_email.return_value = None
        mock_get_user.return_value = MagicMock(id=11, active=False)
        mock_send_admin_email.return_value = None
        mock_notify.return_value = []
        mock_email_service.return_value = True

        response = signup_client.post(
            "/sign-up/sign-up/confirm",
            json={"token": "valid-verification-token"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["admin_approval_required"] is True

    @patch("modules.auth.sign_up_tokens.service.users_integration.get_user")
    @patch("modules.auth.sign_up_tokens.service.users_integration.stage_email_verification")
    @patch("modules.auth.sign_up_tokens.service.verify_sign_up_token")
    @patch("modules.auth.sign_up_tokens.service.server_settings_integration.get_server_settings")
    def test_verify_email_skips_notifications_when_email_not_configured(
        self,
        mock_settings,
        mock_use_token,
        mock_verify_email,
        mock_get_user,
        signup_client,
        mock_email_service,
    ) -> None:
        """
        Returns 200 and skips admin email and websocket notification
        when mail is not configured.

        The `if core_mail.is_mail_configured():` block in the router
        is bypassed entirely; no AttributeError or side-effect
        from admin notification helpers should occur.
        """
        mock_settings.return_value = MagicMock(
            signup_require_email_verification=True,
            signup_require_admin_approval=False,
        )
        mock_use_token.return_value = MagicMock(user_id=20, previous_email=None)
        mock_verify_email.return_value = None
        mock_get_user.return_value = MagicMock(id=20, active=False)
        mock_email_service.return_value = False

        response = signup_client.post(
            "/sign-up/sign-up/confirm",
            json={"token": "valid-token"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "verified" in data["message"].lower()
        assert data["admin_approval_required"] is None

    @patch("modules.auth.sign_up_tokens.service.request_sign_up_admin_approval_emails")
    @patch("modules.auth.sign_up_tokens.service.users_integration.get_user")
    @patch("modules.auth.sign_up_tokens.service.users_integration.stage_email_verification")
    @patch("modules.auth.sign_up_tokens.service.verify_sign_up_token")
    @patch("modules.auth.sign_up_tokens.service.server_settings_integration.get_server_settings")
    def test_verify_email_returns_500_when_get_user_by_id_returns_none(
        self,
        mock_settings,
        mock_use_token,
        mock_verify_email,
        mock_get_user,
        mock_send_admin_email,
        signup_client,
        mock_email_service,
    ) -> None:
        """
        When get_user_by_id returns None the router now raises an explicit
        404 instead of letting AttributeError propagate as a 500.
        """
        mock_settings.return_value = MagicMock(
            signup_require_email_verification=True,
            signup_require_admin_approval=False,
        )
        mock_use_token.return_value = MagicMock(user_id=99, previous_email=None)
        mock_verify_email.return_value = None
        mock_get_user.return_value = None
        mock_email_service.return_value = True
        # Simulate the AttributeError raised when None.name is accessed
        mock_send_admin_email.side_effect = AttributeError("'NoneType' object has no attribute 'name'")

        response = signup_client.post(
            "/sign-up/sign-up/confirm",
            json={"token": "valid-token"},
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @patch("modules.auth.sign_up_tokens.service.notifications_integration.create_admin_sign_up_approval_notifications")
    @patch("modules.auth.sign_up_tokens.service.request_sign_up_admin_approval_emails")
    @patch("modules.auth.sign_up_tokens.service.users_integration.get_user")
    @patch("modules.auth.sign_up_tokens.service.users_integration.stage_email_verification")
    @patch("modules.auth.sign_up_tokens.service.verify_sign_up_token")
    @patch("modules.auth.sign_up_tokens.service.server_settings_integration.get_server_settings")
    def test_verify_email_returns_500_when_notification_raises_http500(
        self,
        mock_settings,
        mock_use_token,
        mock_verify_email,
        mock_get_user,
        mock_send_admin_email,
        mock_notify,
        signup_client,
        mock_email_service,
    ) -> None:
        """
        Returns 500 when create_admin_sign_up_approval_notifications raises HTTPException 500.
        """
        mock_settings.return_value = MagicMock(
            signup_require_email_verification=True,
            signup_require_admin_approval=True,
        )
        mock_use_token.return_value = MagicMock(user_id=30, previous_email=None)
        mock_verify_email.return_value = None
        mock_get_user.return_value = MagicMock(id=30, active=False)
        mock_send_admin_email.return_value = None
        mock_email_service.return_value = True
        mock_notify.side_effect = HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Notification creation failed",
        )

        response = signup_client.post(
            "/sign-up/sign-up/confirm",
            json={"token": "valid-token"},
        )

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    @patch("modules.auth.sign_up_tokens.service.notifications_integration.create_admin_sign_up_approval_notifications")
    @patch("modules.auth.sign_up_tokens.service.request_sign_up_admin_approval_emails")
    @patch("modules.auth.sign_up_tokens.service.users_integration.get_user")
    @patch("modules.auth.sign_up_tokens.service.users_integration.stage_email_verification")
    @patch("modules.auth.sign_up_tokens.service.verify_sign_up_token")
    @patch("modules.auth.sign_up_tokens.service.server_settings_integration.get_server_settings")
    def test_verify_email_returns_500_when_notification_raises_runtime(
        self,
        mock_settings,
        mock_use_token,
        mock_verify_email,
        mock_get_user,
        mock_send_admin_email,
        mock_notify,
        signup_client,
        mock_email_service,
    ) -> None:
        """
        Returns 500 when create_admin_sign_up_approval_notifications raises RuntimeError (e.g. websocket failure).

        FastAPI converts unhandled RuntimeError to a 500 response;
        raise_server_exceptions=False allows asserting the status.
        """
        mock_settings.return_value = MagicMock(
            signup_require_email_verification=True,
            signup_require_admin_approval=True,
        )
        mock_use_token.return_value = MagicMock(user_id=31, previous_email=None)
        mock_verify_email.return_value = None
        mock_get_user.return_value = MagicMock(id=31, active=False)
        mock_send_admin_email.return_value = None
        mock_email_service.return_value = True
        mock_notify.side_effect = RuntimeError("WebSocket broadcast failed")

        response = signup_client.post(
            "/sign-up/sign-up/confirm",
            json={"token": "valid-token"},
        )

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
