"""Integration tests for sign_up_tokens router endpoints."""

import uuid
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
import modules.auth.sign_up_tokens.schema as sign_up_schema
from tests._helpers.auth import MOCK_USER_ID
from tests.auth.sign_up_tokens.ids import tid

_USER_1 = uuid.UUID("00000000-0000-4000-8000-000000000001")
_USER_2 = uuid.UUID("00000000-0000-4000-8000-000000000002")
_USER_4 = uuid.UUID("00000000-0000-4000-8000-000000000004")
_USER_5 = uuid.UUID("00000000-0000-4000-8000-000000000005")
_USER_10 = uuid.UUID("00000000-0000-4000-8000-000000000010")
_USER_11 = uuid.UUID("00000000-0000-4000-8000-000000000011")
_USER_20 = uuid.UUID("00000000-0000-4000-8000-000000000020")
_USER_99 = uuid.UUID("00000000-0000-4000-8000-000000000099")

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

    @pytest.fixture(autouse=True)
    def _free_username(self):
        with patch("modules.auth.sign_up_tokens.service.users_integration.get_user_by_username", return_value=None):
            yield

    @patch("modules.auth.sign_up_tokens.service.request_sign_up_verification_email")
    @patch("modules.auth.sign_up_tokens.service.users_integration.stage_signup_user")
    @patch("modules.auth.sign_up_tokens.service.server_settings_integration.get_server_settings")
    def test_signup_success_no_verification_no_approval(
        self,
        mock_settings,
        mock_create_user,
        mock_send_email,
        signup_client,
    ) -> None:
        """
        Returns 200 with login message when neither email
        verification nor admin approval is required.
        """
        mock_settings.return_value = MagicMock(
            signup_enabled=True,
            signup_require_email_verification=False,
            signup_require_admin_approval=False,
        )
        mock_create_user.return_value = MagicMock(id=_USER_1, pending_admin_approval=False)

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

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data == {"next_step": "sign_in"}

    @patch("modules.auth.sign_up_tokens.service.request_sign_up_verification_email")
    @patch("modules.auth.sign_up_tokens.service.users_integration.stage_signup_user")
    @patch("modules.auth.sign_up_tokens.service.server_settings_integration.get_server_settings")
    def test_signup_success_email_verification_required(
        self,
        mock_settings,
        mock_create_user,
        mock_send_email,
        signup_client,
    ) -> None:
        """
        Returns 200 with email_verification_required=True and
        success message when server requires email verification.
        """
        mock_settings.return_value = MagicMock(
            signup_enabled=True,
            signup_require_email_verification=True,
            signup_require_admin_approval=False,
        )
        mock_create_user.return_value = MagicMock(id=_USER_2)
        mock_send_email.return_value = True

        response = signup_client.post(
            "/sign-up/sign-up/request",
            json={
                "name": "Email User",
                "username": "emailuser",
                "email": "emailuser@example.com",
                "preferred_language": "en",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data == {"next_step": "check_email"}

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

    def test_confirm_sign_up_missing_password_returns_422(self, signup_client) -> None:
        """Returns 422 when the body carries no password: a sign-up link always chooses one."""
        response = signup_client.post("/sign-up/sign-up/confirm", json={"token": "valid-token"})

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    @patch("modules.auth.sign_up_tokens.service.users_integration.stage_signup_user")
    def test_signup_with_profile_fields_returns_422(self, mock_create_user, signup_client) -> None:
        """Sign-up takes only the account fields; profile details are set after signing in."""
        response = signup_client.post(
            "/sign-up/sign-up/request",
            json={
                "name": "Test User",
                "username": "testuser",
                "email": "test@example.com",
                "password": "SecurePass1!",
                "units": "imperial",
            },
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        mock_create_user.assert_not_called()

    @patch("modules.auth.sign_up_tokens.service.users_integration.stage_signup_user")
    @patch("modules.auth.sign_up_tokens.service.server_settings_integration.get_server_settings")
    def test_signup_duplicate_user_propagates_conflict(
        self,
        mock_settings,
        mock_create_user,
        signup_client,
    ) -> None:
        """
        Propagates 409 (or other HTTP error) raised by
        stage_signup_user when username/email already exists.
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

    @patch("modules.auth.sign_up_tokens.service.request_sign_up_admin_approval")
    @patch("modules.auth.sign_up_tokens.service.request_sign_up_verification_email")
    @patch("modules.auth.sign_up_tokens.service.users_integration.stage_signup_user")
    @patch("modules.auth.sign_up_tokens.service.server_settings_integration.get_server_settings")
    def test_signup_admin_approval_required_returns_flag(
        self,
        mock_settings,
        mock_create_user,
        mock_send_email,
        mock_request_approval,
        signup_client,
    ) -> None:
        """
        Returns 200 with admin_approval_required=True when server
        requires admin approval, and asks the administrators for it.
        """
        mock_settings.return_value = MagicMock(
            signup_enabled=True,
            signup_require_email_verification=False,
            signup_require_admin_approval=True,
        )
        mock_create_user.return_value = MagicMock(id=_USER_4, pending_admin_approval=True)

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

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data == {"next_step": "await_approval"}
        mock_request_approval.assert_called_once()
        assert mock_request_approval.call_args.args[0] == _USER_4

    @patch("modules.auth.sign_up_tokens.service.request_sign_up_verification_email")
    @patch("modules.auth.sign_up_tokens.service.users_integration.stage_signup_user")
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
        mock_create_user.return_value = MagicMock(id=_USER_5)
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
                "preferred_language": "en",
            },
        )

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


# ---------------------------------------------------------------------------
# POST /sign-up/sign-up/confirm
# ---------------------------------------------------------------------------


class TestConfirmSignUpEndpoint:
    """Tests for POST /sign-up/sign-up/confirm."""

    @pytest.fixture(autouse=True)
    def not_deactivated(self):
        with patch("modules.auth.sign_up_tokens.service.users_integration.is_deactivated", return_value=False):
            yield

    @pytest.fixture(autouse=True)
    def password_boundaries(self):
        with (
            patch("modules.auth.sign_up_tokens.service.credentials_integration") as credentials,
            patch("modules.auth.sign_up_tokens.service.sessions_integration"),
            patch("modules.auth.sign_up_tokens.service.password_reset_tokens_integration"),
            patch("modules.auth.sign_up_tokens.service.users_schema.normalize_access_type", return_value="regular"),
        ):
            credentials.validate_and_hash_password_for_user.return_value = "hashed"
            yield credentials

    @patch("modules.auth.sign_up_tokens.service.request_sign_up_admin_approval_emails")
    @patch("modules.auth.sign_up_tokens.service.users_integration.get_user")
    @patch("modules.auth.sign_up_tokens.service.users_integration.stage_email_verification")
    @patch("modules.auth.sign_up_tokens.service.verify_sign_up_token")
    @patch("modules.auth.sign_up_tokens.service.server_settings_integration.get_server_settings")
    def test_confirm_sign_up_success_no_admin_approval(
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
        Returns 200 with success message when email verification
        succeeds and admin approval is not required.
        """
        mock_settings.return_value = MagicMock(
            signup_require_email_verification=True,
            signup_require_admin_approval=False,
        )
        mock_use_token.return_value = MagicMock(user_id=_USER_10, previous_email=None)
        mock_verify_email.return_value = None
        mock_get_user.return_value = MagicMock(id=_USER_10, active=False)
        mock_send_admin_email.return_value = None
        mock_email_service.return_value = True

        response = signup_client.post(
            "/sign-up/sign-up/confirm",
            json={"token": "valid-verification-token", "password": "ChosenPass1!"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data == {"next_step": "sign_in"}

    @patch("modules.auth.sign_up_tokens.service.verify_sign_up_token")
    @patch("modules.auth.sign_up_tokens.service.server_settings_integration.get_server_settings")
    def test_confirm_sign_up_invalid_token_returns_400(
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
            json={"token": "invalid-token", "password": "ChosenPass1!"},
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @patch("modules.auth.sign_up_tokens.service.users_integration.get_user")
    @patch("modules.auth.sign_up_tokens.service.verify_sign_up_token")
    @patch("modules.auth.sign_up_tokens.service.server_settings_integration.get_server_settings")
    def test_confirm_sign_up_not_enabled_returns_403(
        self,
        mock_settings,
        mock_use_token,
        mock_get_user,
        signup_client,
    ) -> None:
        """
        Returns 403 with its own problem type when a sign-up is verified but email verification is not enabled on
        the server.
        """
        mock_settings.return_value = MagicMock(
            signup_require_email_verification=False,
        )
        mock_use_token.return_value = MagicMock(user_id=_USER_10, previous_email=None)
        mock_get_user.return_value = MagicMock(id=_USER_10, active=False)

        response = signup_client.post(
            "/sign-up/sign-up/confirm",
            json={"token": "any-token", "password": "ChosenPass1!"},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.json()["type"] == "urn:endurain:error:email-verification-disabled"

    @patch("modules.auth.sign_up_tokens.service.server_settings_integration.get_server_settings")
    def test_confirm_sign_up_missing_token_returns_422(
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

    @patch("modules.auth.sign_up_tokens.service.request_sign_up_admin_approval_emails")
    @patch("modules.auth.sign_up_tokens.service.users_integration.get_user")
    @patch("modules.auth.sign_up_tokens.service.users_integration.stage_email_verification")
    @patch("modules.auth.sign_up_tokens.service.verify_sign_up_token")
    @patch("modules.auth.sign_up_tokens.service.server_settings_integration.get_server_settings")
    def test_confirm_sign_up_with_admin_approval_sets_flag(
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
        Returns admin_approval_required=True in response when
        server requires admin approval after email verification.
        """
        mock_settings.return_value = MagicMock(
            signup_require_email_verification=True,
            signup_require_admin_approval=True,
        )
        mock_use_token.return_value = MagicMock(user_id=_USER_11, previous_email=None)
        mock_verify_email.return_value = None
        mock_get_user.return_value = MagicMock(id=_USER_11, active=False)
        mock_send_admin_email.return_value = None
        mock_email_service.return_value = True

        response = signup_client.post(
            "/sign-up/sign-up/confirm",
            json={"token": "valid-verification-token", "password": "ChosenPass1!"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data == {"next_step": "await_approval"}

    @patch("modules.auth.sign_up_tokens.service.users_integration.get_user")
    @patch("modules.auth.sign_up_tokens.service.users_integration.stage_email_verification")
    @patch("modules.auth.sign_up_tokens.service.verify_sign_up_token")
    @patch("modules.auth.sign_up_tokens.service.server_settings_integration.get_server_settings")
    def test_confirm_sign_up_skips_notifications_when_email_not_configured(
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
        mock_use_token.return_value = MagicMock(user_id=_USER_20, previous_email=None)
        mock_verify_email.return_value = None
        mock_get_user.return_value = MagicMock(id=_USER_20, active=False)
        mock_email_service.return_value = False

        response = signup_client.post(
            "/sign-up/sign-up/confirm",
            json={"token": "valid-token", "password": "ChosenPass1!"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data == {"next_step": "sign_in"}

    @patch("modules.auth.sign_up_tokens.service.request_sign_up_admin_approval_emails")
    @patch("modules.auth.sign_up_tokens.service.users_integration.get_user")
    @patch("modules.auth.sign_up_tokens.service.users_integration.stage_email_verification")
    @patch("modules.auth.sign_up_tokens.service.verify_sign_up_token")
    @patch("modules.auth.sign_up_tokens.service.server_settings_integration.get_server_settings")
    def test_confirm_sign_up_returns_500_when_get_user_by_id_returns_none(
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
        mock_use_token.return_value = MagicMock(user_id=_USER_99, previous_email=None)
        mock_verify_email.return_value = None
        mock_get_user.return_value = None
        mock_email_service.return_value = True
        # Simulate the AttributeError raised when None.name is accessed
        mock_send_admin_email.side_effect = AttributeError("'NoneType' object has no attribute 'name'")

        response = signup_client.post(
            "/sign-up/sign-up/confirm",
            json={"token": "valid-token", "password": "ChosenPass1!"},
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestSignUpPasswordOverHttp:
    """The password rides the verification step, never the sign-up request, when verification is required."""

    @patch("modules.auth.sign_up_tokens.service.users_integration.stage_signup_user")
    @patch("modules.auth.sign_up_tokens.service.server_settings_integration.get_server_settings")
    def test_a_password_in_the_sign_up_request_is_refused_when_verification_is_required(
        self, mock_settings, mock_create_user, signup_client
    ) -> None:
        mock_settings.return_value = MagicMock(
            signup_enabled=True, signup_require_email_verification=True, signup_require_admin_approval=False
        )

        response = signup_client.post(
            "/sign-up/sign-up/request",
            json={
                "name": "Victim",
                "username": "victim",
                "email": "victim@example.com",
                "password": "AttackerPass1!",
                "preferred_language": "en",
            },
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        mock_create_user.assert_not_called()


class TestConfirmEmailChangeEndpoint:
    """Tests for POST /sign-up/email-change/confirm."""

    @patch("modules.auth.sign_up_tokens.service.sign_up_event_publishers")
    @patch("modules.auth.sign_up_tokens.service.users_integration")
    @patch("modules.auth.sign_up_tokens.service.verify_sign_up_token")
    @patch("modules.auth.sign_up_tokens.service.server_settings_integration.get_server_settings")
    def test_a_confirmed_change_answers_sign_in(
        self, mock_settings, mock_use_token, mock_users, _publishers, signup_client
    ) -> None:
        mock_settings.return_value = MagicMock(
            signup_require_email_verification=False, signup_require_admin_approval=True
        )
        mock_use_token.return_value = MagicMock(
            id=tid("t"), user_id=_USER_10, email="new@example.com", previous_email="old@example.com"
        )
        mock_users.get_user.return_value = MagicMock(id=_USER_10, active=True)

        response = signup_client.post("/sign-up/email-change/confirm", json={"token": "valid-token"})

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"next_step": "sign_in"}
        mock_use_token.assert_called_once()
        assert mock_use_token.call_args.kwargs == {"email_change": True}

    @patch("modules.auth.sign_up_tokens.service.verify_sign_up_token")
    @patch("modules.auth.sign_up_tokens.service.server_settings_integration.get_server_settings")
    def test_an_unusable_token_answers_400(self, mock_settings, mock_use_token, signup_client) -> None:
        mock_settings.return_value = MagicMock()
        mock_use_token.side_effect = core_exceptions.InvalidInputError("Invalid or expired sign up token")

        response = signup_client.post("/sign-up/email-change/confirm", json={"token": "bad"})

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_a_password_is_not_accepted(self, signup_client) -> None:
        response = signup_client.post(
            "/sign-up/email-change/confirm", json={"token": "valid-token", "password": "ChosenPass1!"}
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    def test_a_missing_token_answers_422(self, signup_client) -> None:
        assert signup_client.post("/sign-up/email-change/confirm", json={}).status_code == 422


class TestResendEndpoint:
    """Tests for POST /sign-up/sign-up/resend."""

    @patch("modules.auth.sign_up_tokens.public_router.sign_up_service.resend_sign_up_verification_email")
    def test_answers_with_the_service_next_step(self, mock_resend, signup_client):
        mock_resend.return_value = sign_up_schema.SignUpRead(next_step=sign_up_schema.SignUpNextStep.CHECK_EMAIL)

        response = signup_client.post("/sign-up/sign-up/resend", json={"email": "u@example.com"})

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"next_step": "check_email"}
        assert mock_resend.call_args.args[0] == "u@example.com"

    def test_rejects_an_invalid_email(self, signup_client):
        response = signup_client.post("/sign-up/sign-up/resend", json={"email": "nope"})

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


class TestSignUpOffEndpoints:
    """With sign-up off, the resend route and a pending sign-up's confirmation answer like the request route."""

    @pytest.fixture(autouse=True)
    def sign_up_off(self):
        with patch(
            "modules.auth.sign_up_tokens.service.server_settings_integration.get_server_settings",
            return_value=MagicMock(signup_enabled=False, signup_require_email_verification=True),
        ):
            yield

    @pytest.mark.parametrize(
        ("path", "body"),
        [
            ("/sign-up/sign-up/request", {"name": "N", "username": "nobody", "email": "u@example.com"}),
            ("/sign-up/sign-up/resend", {"email": "u@example.com"}),
        ],
    )
    def test_the_request_and_resend_routes_refuse_alike(self, signup_client, path, body) -> None:
        body = body | {"preferred_language": "en"} if path.endswith("request") else body

        response = signup_client.post(path, json=body)

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.json()["type"] == "urn:endurain:error:permission-denied"
        assert "not enabled" in response.json()["detail"].lower()

    @patch("modules.auth.sign_up_tokens.service.credentials_integration")
    @patch("modules.auth.sign_up_tokens.service.users_integration")
    @patch("modules.auth.sign_up_tokens.service.verify_sign_up_token")
    def test_a_pending_sign_up_confirmation_is_refused_alike(
        self, claim, mock_users, _credentials, signup_client
    ) -> None:
        claim.return_value = MagicMock(user_id=_USER_10)
        mock_users.get_user.return_value = MagicMock(id=_USER_10, active=False)
        mock_users.is_deactivated.return_value = False

        response = signup_client.post("/sign-up/sign-up/confirm", json={"token": "tok", "password": "ChosenPass1!"})

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.json()["type"] == "urn:endurain:error:permission-denied"
        assert "not enabled" in response.json()["detail"].lower()

    @patch("modules.auth.sign_up_tokens.service.sign_up_event_publishers")
    @patch("modules.auth.sign_up_tokens.service.users_integration")
    @patch("modules.auth.sign_up_tokens.service.verify_sign_up_token")
    def test_an_email_change_is_still_confirmed(self, mock_use_token, mock_users, _publishers, signup_client) -> None:
        mock_use_token.return_value = MagicMock(
            id=tid("t"), user_id=_USER_10, email="new@example.com", previous_email="old@example.com"
        )
        mock_users.get_user.return_value = MagicMock(id=_USER_10, active=True)

        response = signup_client.post("/sign-up/email-change/confirm", json={"token": "valid-token"})

        assert response.status_code == status.HTTP_200_OK


class TestCancelEmailChangeEndpoint:
    @patch("modules.auth.sign_up_tokens.service.cancel_email_change")
    def test_a_valid_link_answers_200_with_what_happened(self, cancel, signup_client) -> None:
        cancel.return_value = sign_up_schema.EmailChangeCancelRead(change_applied=True, email_restored=False)

        response = signup_client.post("/sign-up/email-change/cancel", json={"token": "7.1.abc"})

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"change_applied": True, "email_restored": False}
        assert cancel.call_args.args[0] == "7.1.abc"

    @patch(
        "modules.auth.sign_up_tokens.service.cancel_email_change",
        side_effect=core_exceptions.InvalidInputError("Invalid or expired link"),
    )
    def test_a_refused_link_answers_400(self, _cancel, signup_client) -> None:
        response = signup_client.post("/sign-up/email-change/cancel", json={"token": "bad"})

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_an_extra_field_is_refused(self, signup_client) -> None:
        response = signup_client.post("/sign-up/email-change/cancel", json={"token": "x", "user_id": str(MOCK_USER_ID)})

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
