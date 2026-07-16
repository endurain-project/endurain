"""Integration tests for sign_up_tokens router endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import auth._internal.password_hasher as auth_password_hasher
import auth.sign_up_tokens.router as sign_up_tokens_router
import core.apprise as core_apprise
import core.database as core_database
import websocket.manager as websocket_manager

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
def mock_email_service() -> MagicMock:
    """
    Return a mock AppriseService with is_configured returning True.

    Returns:
        MagicMock: Mock email service.
    """
    svc = MagicMock(spec=core_apprise.AppriseService)
    svc.is_configured.return_value = True
    return svc


@pytest.fixture
def mock_ws_manager() -> MagicMock:
    """
    Return a mock WebSocketManager.

    Returns:
        MagicMock: Mock WebSocket manager.
    """
    return MagicMock(spec=websocket_manager.WebSocketManager)


@pytest.fixture
def signup_app(
    mock_db,
    mock_email_service,
    mock_ws_manager,
    password_hasher,
) -> FastAPI:
    """
    Create a minimal FastAPI app for sign_up_tokens router tests.

    Args:
        mock_db: Mock database session.
        mock_email_service: Mock email service.
        mock_ws_manager: Mock WebSocket manager.
        password_hasher: Real PasswordHasher instance.

    Returns:
        FastAPI: Configured test application.
    """
    app = FastAPI()
    app.include_router(
        sign_up_tokens_router.router,
        prefix="/sign-up",
    )

    app.dependency_overrides[core_database.get_db] = lambda: mock_db
    app.dependency_overrides[core_apprise.get_email_service] = lambda: mock_email_service
    app.dependency_overrides[websocket_manager.get_websocket_manager] = lambda: mock_ws_manager
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

    @patch(
        "auth.sign_up_tokens.router.sign_up_tokens_utils.send_sign_up_email",
        new_callable=AsyncMock,
    )
    @patch("auth.sign_up_tokens.router.users_utils.create_user_default_data")
    @patch("auth.sign_up_tokens.router.users_crud.create_signup_user")
    @patch("auth.sign_up_tokens.router.server_settings_utils.get_server_settings_or_404")
    def test_signup_success_no_verification_no_approval(
        self,
        mock_settings,
        mock_create_user,
        mock_create_default,
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
        mock_create_default.return_value = None

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

    @patch(
        "auth.sign_up_tokens.router.sign_up_tokens_utils.send_sign_up_email",
        new_callable=AsyncMock,
    )
    @patch("auth.sign_up_tokens.router.users_utils.create_user_default_data")
    @patch("auth.sign_up_tokens.router.users_crud.create_signup_user")
    @patch("auth.sign_up_tokens.router.server_settings_utils.get_server_settings_or_404")
    def test_signup_success_email_verification_required(
        self,
        mock_settings,
        mock_create_user,
        mock_create_default,
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
        mock_create_default.return_value = None
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

    @patch(
        "auth.sign_up_tokens.router.sign_up_tokens_utils.send_sign_up_email",
        new_callable=AsyncMock,
    )
    @patch("auth.sign_up_tokens.router.users_utils.create_user_default_data")
    @patch("auth.sign_up_tokens.router.users_crud.create_signup_user")
    @patch("auth.sign_up_tokens.router.server_settings_utils.get_server_settings_or_404")
    def test_signup_email_send_fails_includes_warning_in_message(
        self,
        mock_settings,
        mock_create_user,
        mock_create_default,
        mock_send_email,
        signup_client,
    ) -> None:
        """
        Returns 201 even when email sending fails; message
        includes a note that email send failed.
        """
        mock_settings.return_value = MagicMock(
            signup_enabled=True,
            signup_require_email_verification=True,
            signup_require_admin_approval=False,
        )
        mock_create_user.return_value = MagicMock(id=3)
        mock_create_default.return_value = None
        mock_send_email.return_value = False

        response = signup_client.post(
            "/sign-up/sign-up/request",
            json={
                "name": "Fail User",
                "username": "failuser",
                "email": "fail@example.com",
                "password": "SecurePass1!",
                "preferred_language": "en",
            },
        )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert "Failed" in data["message"]

    @patch("auth.sign_up_tokens.router.server_settings_utils.get_server_settings_or_404")
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

    @patch("auth.sign_up_tokens.router.server_settings_utils.get_server_settings_or_404")
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

    @patch("auth.sign_up_tokens.router.users_crud.create_signup_user")
    @patch("auth.sign_up_tokens.router.server_settings_utils.get_server_settings_or_404")
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

    @patch(
        "auth.sign_up_tokens.router.sign_up_tokens_utils.send_sign_up_email",
        new_callable=AsyncMock,
    )
    @patch("auth.sign_up_tokens.router.users_utils.create_user_default_data")
    @patch("auth.sign_up_tokens.router.users_crud.create_signup_user")
    @patch("auth.sign_up_tokens.router.server_settings_utils.get_server_settings_or_404")
    def test_signup_admin_approval_required_returns_flag(
        self,
        mock_settings,
        mock_create_user,
        mock_create_default,
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
        mock_create_default.return_value = None

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

    @patch(
        "auth.sign_up_tokens.router.sign_up_tokens_utils.send_sign_up_email",
        new_callable=AsyncMock,
    )
    @patch("auth.sign_up_tokens.router.users_utils.create_user_default_data")
    @patch("auth.sign_up_tokens.router.users_crud.create_signup_user")
    @patch("auth.sign_up_tokens.router.server_settings_utils.get_server_settings_or_404")
    def test_signup_propagates_503_when_send_sign_up_email_raises(
        self,
        mock_settings,
        mock_create_user,
        mock_create_default,
        mock_send_email,
        signup_client,
    ) -> None:
        """
        Returns 503 when email verification is required and
        send_sign_up_email raises HTTPException 503 (email
        service not configured at send time).
        """
        mock_settings.return_value = MagicMock(
            signup_enabled=True,
            signup_require_email_verification=True,
            signup_require_admin_approval=False,
        )
        mock_create_user.return_value = MagicMock(id=5)
        mock_create_default.return_value = None
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

    @patch(
        "auth.sign_up_tokens.router.notifications_utils.create_admin_new_sign_up_approval_request_notification",
        new_callable=AsyncMock,
    )
    @patch(
        "auth.sign_up_tokens.router.sign_up_tokens_utils.send_sign_up_admin_approval_email",
        new_callable=AsyncMock,
    )
    @patch("auth.sign_up_tokens.router.users_crud.get_user_by_id")
    @patch("auth.sign_up_tokens.router.users_crud.verify_user_email")
    @patch("auth.sign_up_tokens.router.sign_up_tokens_utils.use_sign_up_token")
    @patch("auth.sign_up_tokens.router.server_settings_utils.get_server_settings_or_404")
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
        mock_use_token.return_value = 10
        mock_verify_email.return_value = None
        mock_get_user.return_value = MagicMock(id=10)
        mock_send_admin_email.return_value = None
        mock_notify.return_value = None
        mock_email_service.is_configured.return_value = True

        response = signup_client.post(
            "/sign-up/sign-up/confirm",
            json={"token": "valid-verification-token"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "verified" in data["message"].lower()
        assert data["admin_approval_required"] is None

    @patch("auth.sign_up_tokens.router.sign_up_tokens_utils.use_sign_up_token")
    @patch("auth.sign_up_tokens.router.server_settings_utils.get_server_settings_or_404")
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

    @patch("auth.sign_up_tokens.router.server_settings_utils.get_server_settings_or_404")
    def test_verify_email_not_enabled_returns_412(
        self,
        mock_settings,
        signup_client,
    ) -> None:
        """
        Returns 412 when email verification is not enabled on
        the server.
        """
        mock_settings.return_value = MagicMock(
            signup_require_email_verification=False,
        )

        response = signup_client.post(
            "/sign-up/sign-up/confirm",
            json={"token": "any-token"},
        )

        assert response.status_code == status.HTTP_412_PRECONDITION_FAILED

    @patch("auth.sign_up_tokens.router.server_settings_utils.get_server_settings_or_404")
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

    @patch(
        "auth.sign_up_tokens.router.notifications_utils.create_admin_new_sign_up_approval_request_notification",
        new_callable=AsyncMock,
    )
    @patch(
        "auth.sign_up_tokens.router.sign_up_tokens_utils.send_sign_up_admin_approval_email",
        new_callable=AsyncMock,
    )
    @patch("auth.sign_up_tokens.router.users_crud.get_user_by_id")
    @patch("auth.sign_up_tokens.router.users_crud.verify_user_email")
    @patch("auth.sign_up_tokens.router.sign_up_tokens_utils.use_sign_up_token")
    @patch("auth.sign_up_tokens.router.server_settings_utils.get_server_settings_or_404")
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
        mock_use_token.return_value = 11
        mock_verify_email.return_value = None
        mock_get_user.return_value = MagicMock(id=11)
        mock_send_admin_email.return_value = None
        mock_notify.return_value = None
        mock_email_service.is_configured.return_value = True

        response = signup_client.post(
            "/sign-up/sign-up/confirm",
            json={"token": "valid-verification-token"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["admin_approval_required"] is True

    @patch("auth.sign_up_tokens.router.users_crud.verify_user_email")
    @patch("auth.sign_up_tokens.router.sign_up_tokens_utils.use_sign_up_token")
    @patch("auth.sign_up_tokens.router.server_settings_utils.get_server_settings_or_404")
    def test_verify_email_skips_notifications_when_email_not_configured(
        self,
        mock_settings,
        mock_use_token,
        mock_verify_email,
        signup_client,
        mock_email_service,
        mock_ws_manager,
    ) -> None:
        """
        Returns 200 and skips admin email and websocket notification
        when email_service.is_configured() is False.

        The `if email_service.is_configured():` block in the router
        is bypassed entirely; no AttributeError or side-effect
        from admin notification helpers should occur.
        """
        mock_settings.return_value = MagicMock(
            signup_require_email_verification=True,
            signup_require_admin_approval=False,
        )
        mock_use_token.return_value = 20
        mock_verify_email.return_value = None
        mock_email_service.is_configured.return_value = False

        response = signup_client.post(
            "/sign-up/sign-up/confirm",
            json={"token": "valid-token"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "verified" in data["message"].lower()
        assert data["admin_approval_required"] is None

    @patch(
        "auth.sign_up_tokens.router.sign_up_tokens_utils.send_sign_up_admin_approval_email",
        new_callable=AsyncMock,
    )
    @patch("auth.sign_up_tokens.router.users_crud.get_user_by_id")
    @patch("auth.sign_up_tokens.router.users_crud.verify_user_email")
    @patch("auth.sign_up_tokens.router.sign_up_tokens_utils.use_sign_up_token")
    @patch("auth.sign_up_tokens.router.server_settings_utils.get_server_settings_or_404")
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
        mock_use_token.return_value = 99
        mock_verify_email.return_value = None
        mock_get_user.return_value = None
        mock_email_service.is_configured.return_value = True
        # Simulate the AttributeError raised when None.name is accessed
        mock_send_admin_email.side_effect = AttributeError("'NoneType' object has no attribute 'name'")

        response = signup_client.post(
            "/sign-up/sign-up/confirm",
            json={"token": "valid-token"},
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @patch(
        "auth.sign_up_tokens.router.notifications_utils.create_admin_new_sign_up_approval_request_notification",
        new_callable=AsyncMock,
    )
    @patch(
        "auth.sign_up_tokens.router.sign_up_tokens_utils.send_sign_up_admin_approval_email",
        new_callable=AsyncMock,
    )
    @patch("auth.sign_up_tokens.router.users_crud.get_user_by_id")
    @patch("auth.sign_up_tokens.router.users_crud.verify_user_email")
    @patch("auth.sign_up_tokens.router.sign_up_tokens_utils.use_sign_up_token")
    @patch("auth.sign_up_tokens.router.server_settings_utils.get_server_settings_or_404")
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
        Returns 500 when create_admin_new_sign_up_approval_request_
        notification raises HTTPException 500.
        """
        mock_settings.return_value = MagicMock(
            signup_require_email_verification=True,
            signup_require_admin_approval=False,
        )
        mock_use_token.return_value = 30
        mock_verify_email.return_value = None
        mock_get_user.return_value = MagicMock(id=30)
        mock_send_admin_email.return_value = None
        mock_email_service.is_configured.return_value = True
        mock_notify.side_effect = HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Notification creation failed",
        )

        response = signup_client.post(
            "/sign-up/sign-up/confirm",
            json={"token": "valid-token"},
        )

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    @patch(
        "auth.sign_up_tokens.router.notifications_utils.create_admin_new_sign_up_approval_request_notification",
        new_callable=AsyncMock,
    )
    @patch(
        "auth.sign_up_tokens.router.sign_up_tokens_utils.send_sign_up_admin_approval_email",
        new_callable=AsyncMock,
    )
    @patch("auth.sign_up_tokens.router.users_crud.get_user_by_id")
    @patch("auth.sign_up_tokens.router.users_crud.verify_user_email")
    @patch("auth.sign_up_tokens.router.sign_up_tokens_utils.use_sign_up_token")
    @patch("auth.sign_up_tokens.router.server_settings_utils.get_server_settings_or_404")
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
        Returns 500 when create_admin_new_sign_up_approval_request_
        notification raises RuntimeError (e.g. websocket failure).

        FastAPI converts unhandled RuntimeError to a 500 response;
        raise_server_exceptions=False allows asserting the status.
        """
        mock_settings.return_value = MagicMock(
            signup_require_email_verification=True,
            signup_require_admin_approval=False,
        )
        mock_use_token.return_value = 31
        mock_verify_email.return_value = None
        mock_get_user.return_value = MagicMock(id=31)
        mock_send_admin_email.return_value = None
        mock_email_service.is_configured.return_value = True
        mock_notify.side_effect = RuntimeError("WebSocket broadcast failed")

        response = signup_client.post(
            "/sign-up/sign-up/confirm",
            json={"token": "valid-token"},
        )

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
