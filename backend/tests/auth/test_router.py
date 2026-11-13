"""Integration tests for auth.router endpoints."""

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import core.config as core_config
import core.database as core_database
import core.exceptions as core_exceptions
import modules.auth.access_tokens.integration_service as access_tokens_integration
import modules.auth.access_tokens.service as auth_token_manager
import modules.auth.authentication.dependencies as authentication_dependencies
import modules.auth.authentication.failed_login_store as failed_login_store
import modules.auth.authentication.public_router as auth_router
import modules.auth.authentication.schema as auth_schema
import modules.auth.constants as auth_constants
import modules.auth.credentials.integration_service as auth_credentials_crud
import modules.auth.credentials.password_hasher as auth_password_hasher
import modules.auth.lockout.contracts as lockout_contracts
import modules.auth.mfa.dependencies as auth_mfa_dependencies
import modules.auth.mfa.pending_login_store as pending_login_store
from tests._helpers.auth import MOCK_USER_ID, pending_login

_SID_SID_1 = uuid.UUID("a103482d-8b28-53a0-bbde-23e8bbcd7815")
_SID_PKCE_SID = uuid.UUID("88129621-7a82-59f4-9585-8abda4f2ea89")
_SID_PKCE_SID_MFA = uuid.UUID("fdea084b-2b5b-582c-8c67-0910f0f406d9")
_SID_SID_MFA = uuid.UUID("a9460394-e2e9-5af5-9f85-8a65c9a4295c")
_SID_SID_BACKUP = uuid.UUID("d36bd6fe-f9ce-5417-927c-59728d5bba33")
_SID_SID_CSRF_1 = uuid.UUID("81ef82fa-b164-5935-87d6-c65fb448d481")
_SID_SID_MOB = uuid.UUID("3ec4c6e3-f70f-5426-b682-aa226cf02cf0")
_SID_SID_MOB_CSRF = uuid.UUID("4435a82f-adaf-5d3d-a9cd-1181ca9c3693")
_SID_SID_RACE = uuid.UUID("02c86fa9-ad90-53b8-b4b2-0be6f8651d57")
_SID_SID_RELOAD = uuid.UUID("b0221cba-7fc7-5fce-8ebf-aa96f2e5da03")
_SID_SID_REPLAY_MOB = uuid.UUID("3f6a95fa-9890-5972-b0e6-4ec968d2d95e")
_SID_SID_REPLAY_WEB = uuid.UUID("b0d3c0b9-294a-58bb-a488-7538aaa92ceb")
_SID_SID_IDP = uuid.UUID("5e0f16b8-1bcd-56cb-bdf3-a70f82306bd5")
_SID_SID_BAD_CSRF = uuid.UUID("134d9066-73aa-55c6-bf5c-3e31b6e69fd5")
_SID_SID_BAD_RT = uuid.UUID("dfce86e1-c357-534b-8fc1-38a5373a4d16")
_SID_SID_NO_USER = uuid.UUID("f0e70a5d-4306-5767-ac4a-ff1757c4e326")
_SID_SID_PKCE = uuid.UUID("1af5f8bb-ab0c-5341-9a74-5c76bbb43819")
_SID_SID_REPLAY_NONE = uuid.UUID("656509db-3136-535b-b795-43005ef2ee3d")
_SID_SID_WEB = uuid.UUID("084838ff-00f5-5479-adb5-952a097e95d9")
_SID_NONEXISTENT = uuid.UUID("0634f0c1-9773-5f79-b235-1e474984e00a")

_USER_ID_1 = uuid.UUID(int=1)
_USER_ID_999 = uuid.UUID(int=999)


@pytest.fixture(autouse=True)
def _session_policy(session_policy):
    """Serve the default session policy instead of reading it from the database."""
    with patch(
        "modules.auth.authentication.service.server_settings_integration.get_session_policy",
        return_value=session_policy,
    ):
        yield


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


class FakeFailedLoginStore:
    """In-memory FailedLoginStore double for testing."""

    def __init__(self):
        """Initialize empty state."""
        self._locked = False
        self._lockout_time = None

    def is_locked_out(
        self, username: str, ip_address: str, *, user_id: uuid.UUID | None, known_device: bool = False
    ) -> bool:
        """Return locked state."""
        return self._locked

    def get_lockout_time(
        self, username: str, ip_address: str, *, user_id: uuid.UUID | None, known_device: bool = False
    ):
        """Return lockout time."""
        return self._lockout_time

    def record_failed_attempt(
        self, username: str, ip_address: str, *, user_id: uuid.UUID | None
    ) -> failed_login_store.FailedLoginRecord:
        """Record a failed attempt."""
        return failed_login_store.FailedLoginRecord(client_count=1, account_locked_now=False)

    def reset_attempts(self, username: str, ip_address: str, *, user_id: uuid.UUID) -> None:
        """Reset attempts."""
        pass


#: A well-formed challenge no login issued.
UNKNOWN_CHALLENGE = "u" * 43


class FakePendingMFAStore:
    """In-memory PendingMFAStore double for testing."""

    def __init__(self):
        """Initialize empty state."""
        self._store = {}
        self._locked = False
        self._lockout_time = None

    def is_locked_out(
        self, username: str, ip_address: str, *, user_id: uuid.UUID | None, known_device: bool = False
    ) -> bool:
        """Return locked state."""
        return self._locked

    def get_lockout_time(
        self, username: str, ip_address: str, *, user_id: uuid.UUID | None, known_device: bool = False
    ):
        """Return lockout time."""
        return self._lockout_time

    def add_pending_login(self, pending) -> str:
        """Add a pending login and return its challenge."""
        challenge = secrets.token_urlsafe(32)
        self._store[challenge] = pending
        return challenge

    def get_pending_login(self, challenge: str):
        """Get pending login."""
        return self._store.get(challenge)

    def claim_pending_login(self, challenge: str):
        """Claim pending login."""
        return self._store.pop(challenge, None)

    def record_wrong_code(self, challenge: str) -> bool:
        """Leave the challenge live."""
        return False

    def record_failed_attempt(
        self, username: str, ip_address: str, *, user_id: uuid.UUID | None
    ) -> pending_login_store.FailedMfaRecord:
        """Record failed MFA attempt."""
        return pending_login_store.FailedMfaRecord(count=1, account_locked_now=False)

    def reset_attempts(self, username: str, ip_address: str, *, user_id: uuid.UUID) -> None:
        """Reset MFA failed attempts."""
        pass


@pytest.fixture
def fake_failed_login_store():
    """Return a FakeFailedLoginStore instance."""
    return FakeFailedLoginStore()


@pytest.fixture
def fake_pending_mfa_store():
    """Return a FakePendingMFAStore instance."""
    return FakePendingMFAStore()


@pytest.fixture
def auth_app(
    mock_db,
    password_hasher,
    token_manager,
    fake_failed_login_store,
    fake_pending_mfa_store,
):
    """Create a FastAPI app with auth router and overrides."""
    app = FastAPI()
    app.add_exception_handler(core_exceptions.DomainError, core_exceptions.domain_error_handler)
    app.add_exception_handler(
        authentication_dependencies.ClearRefreshTokenCookieError,
        authentication_dependencies.clear_refresh_token_cookie_exception_handler,
    )
    app.include_router(auth_router.router, prefix="/auth")

    app.state._client_type = "web"

    def _client_type():
        return app.state._client_type

    app.dependency_overrides[core_database.get_db] = lambda: mock_db
    app.dependency_overrides[auth_password_hasher.get_password_hasher] = lambda: password_hasher
    app.dependency_overrides[auth_token_manager.get_token_manager] = lambda: token_manager
    app.dependency_overrides[auth_router.authentication_dependencies.get_client_type] = _client_type
    app.dependency_overrides[failed_login_store.get_failed_login_attempts] = lambda: fake_failed_login_store
    app.dependency_overrides[auth_mfa_dependencies.get_pending_mfa_store] = lambda: fake_pending_mfa_store
    app.dependency_overrides[authentication_dependencies.get_exp_from_refresh_token] = lambda: (
        datetime.now(UTC) + timedelta(days=7)
    )

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

    @pytest.fixture(autouse=True)
    def _local_login_enabled(self):
        """Serve server settings that allow password sign-in instead of reading them from the database."""
        with (
            patch(
                "modules.auth.authentication.service.server_settings_integration.get_server_settings",
                return_value=MagicMock(local_login_enabled=True),
            ),
            patch(
                "modules.auth.authentication.service.credentials_integration.is_password_change_required",
                return_value=False,
            ),
            patch("modules.auth.authentication.service.users_integration.get_user_by_username", return_value=None),
        ):
            yield

    @patch("modules.auth.authentication.service.complete_login")
    @patch("modules.auth.authentication.service.mfa_integration.is_mfa_enabled_for_user")
    @patch("modules.auth.authentication.service.users_integration.require_active_user")
    @patch("modules.auth.authentication.service.authenticate_user")
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
        mock_user.id = _USER_ID_1
        mock_auth.return_value = mock_user
        mock_check_active.return_value = None
        mock_mfa_check.return_value = False
        mock_complete_login.return_value = auth_schema.AuthOutcome(
            {
                "next_step": "tokens",
                "session_id": _SID_SID_1,
                "access_token": "at-1",
                "csrf_token": "csrf-1",
                "token_type": "bearer",
                "expires_in": 900,
                "refresh_token_expires_in": 604800,
            }
        )

        response = auth_client.post(
            "/auth/login",
            data={"username": "testuser", "password": "Password1!"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["access_token"] == "at-1"
        assert data["csrf_token"] == "csrf-1"
        assert data["token_type"] == "bearer"

    @patch("modules.auth.authentication.service.authenticate_user")
    def test_login_invalid_credentials_returns_401(self, mock_auth, auth_client, auth_app):
        """Invalid credentials raise 401."""
        mock_auth.side_effect = core_exceptions.UnauthenticatedError("Unable to authenticate")

        response = auth_client.post(
            "/auth/login",
            data={"username": "baduser", "password": "WrongPass1!"},
        )

        assert response.status_code == 401

    @patch("modules.auth.authentication.service.authenticate_user")
    def test_login_inactive_user_answers_like_a_wrong_password(
        self,
        mock_auth,
        auth_client,
        auth_app,
        fake_failed_login_store,
    ):
        """A correct password for an inactive account must not be told apart from a wrong one."""
        mock_auth.return_value = MagicMock(active=False)

        inactive = auth_client.post("/auth/login", data={"username": "inactive", "password": "Password1!"})
        mock_auth.side_effect = core_exceptions.UnauthenticatedError(
            "Unable to authenticate with provided credentials", scheme="Bearer"
        )
        wrong = auth_client.post("/auth/login", data={"username": "inactive", "password": "WrongPass1!"})

        assert (inactive.status_code, inactive.json()["detail"]) == (wrong.status_code, wrong.json()["detail"])
        assert inactive.status_code == 401

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

    @patch("modules.auth.authentication.service.mfa_integration.is_mfa_enabled_for_user")
    @patch("modules.auth.authentication.service.users_integration.require_active_user")
    @patch("modules.auth.authentication.service.authenticate_user")
    def test_login_mfa_required_returns_200(
        self,
        mock_auth,
        mock_check_active,
        mock_mfa_check,
        auth_client,
        auth_app,
        fake_pending_mfa_store,
    ):
        """MFA required answers 200, like every other login outcome."""
        mock_user = MagicMock()
        mock_user.id = _USER_ID_1
        mock_auth.return_value = mock_user
        mock_check_active.return_value = None
        mock_mfa_check.return_value = True

        response = auth_client.post(
            "/auth/login",
            data={"username": "mfauser", "password": "Password1!"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["next_step"] == "mfa"
        assert set(data) == {"next_step", "mfa_challenge"}
        # The only handle /auth/mfa/verify accepts, so nobody who did not sign in can submit codes.
        assert fake_pending_mfa_store.get_pending_login(data["mfa_challenge"]).user_id == _USER_ID_1

    def test_login_partial_pkce_returns_422(self, auth_client, auth_app):
        """A mobile login with only one PKCE field is refused as a validation failure."""
        auth_app.state._client_type = "mobile"

        response = auth_client.post(
            "/auth/login",
            data={
                "username": "user",
                "password": "Password1!",
                "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
            },
        )

        assert response.status_code == 422
        assert [error["loc"] for error in response.json()["detail"]] == [["body", "code_challenge_method"]]

    @patch("modules.auth.authentication.service.create_mobile_pkce_session_response")
    @patch("modules.auth.authentication.service.mfa_integration.is_mfa_enabled_for_user")
    @patch("modules.auth.authentication.service.users_integration.require_active_user")
    @patch("modules.auth.authentication.service.authenticate_user")
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
        mock_user.id = _USER_ID_1
        mock_auth.return_value = mock_user
        mock_check_active.return_value = None
        mock_mfa_check.return_value = False
        mock_pkce.return_value = auth_schema.MobileSessionRead(next_step="exchange", session_id=_SID_PKCE_SID)

        challenge = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
        response = auth_client.post(
            "/auth/login",
            data={
                "username": "user",
                "password": "Password1!",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            },
        )

        assert response.status_code == 200
        assert response.json()["session_id"] == str(_SID_PKCE_SID)

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
            side_effect=(lockout_contracts.AuthSecurityStoreUnavailableError("Redis down"))
        )

        response = auth_client.post(
            "/auth/login",
            data={"username": "user", "password": "Password1!"},
        )

        assert response.status_code == 503
        assert "unavailable" in response.json()["detail"].lower()

    @patch("modules.auth.authentication.service.authenticate_user")
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
        mock_auth.side_effect = core_exceptions.UnauthenticatedError("Unable to authenticate")
        fake_failed_login_store.record_failed_attempt = MagicMock(
            side_effect=(lockout_contracts.AuthSecurityStoreUnavailableError("Redis down"))
        )

        response = auth_client.post(
            "/auth/login",
            data={"username": "user", "password": "WrongPass1!"},
        )

        assert response.status_code == 503
        assert "unavailable" in response.json()["detail"].lower()

    @patch("modules.auth.authentication.service.complete_login")
    @patch("modules.auth.authentication.service.mfa_integration.is_mfa_enabled_for_user")
    @patch("modules.auth.authentication.service.users_integration.require_active_user")
    @patch("modules.auth.authentication.service.authenticate_user")
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
        mock_user.id = _USER_ID_1
        mock_auth.return_value = mock_user
        mock_check_active.return_value = None
        mock_mfa_check.return_value = False
        fake_failed_login_store.reset_attempts = MagicMock(
            side_effect=lockout_contracts.AuthSecurityStoreUnavailableError("Redis down"),
        )
        response = auth_client.post(
            "/auth/login",
            data={"username": "testuser", "password": "Password1!"},
        )
        assert response.status_code == 503
        assert "unavailable" in response.json()["detail"].lower()

    @patch("modules.auth.authentication.service.complete_login")
    @patch("modules.auth.authentication.service.mfa_integration.is_mfa_enabled_for_user")
    @patch("modules.auth.authentication.service.users_integration.require_active_user")
    @patch("modules.auth.authentication.service.authenticate_user")
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
        mock_user.id = _USER_ID_1
        mock_auth.return_value = mock_user
        mock_check_active.return_value = None
        mock_mfa_check.return_value = True
        fake_pending_mfa_store.add_pending_login = MagicMock(
            side_effect=lockout_contracts.AuthSecurityStoreUnavailableError("Redis down"),
        )
        response = auth_client.post(
            "/auth/login",
            data={"username": "mfauser", "password": "Password1!"},
        )
        assert response.status_code == 503

    @patch("modules.auth.authentication.service.mfa_integration.is_mfa_enabled_for_user")
    @patch("modules.auth.authentication.service.users_integration.require_active_user")
    @patch("modules.auth.authentication.service.authenticate_user")
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
        mock_user.id = _USER_ID_1
        mock_auth.return_value = mock_user
        mock_check_active.return_value = None
        mock_mfa_check.return_value = True
        response = auth_client.post(
            "/auth/login",
            data={
                "username": "mfauser",
                "password": "Password1!",
                "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                "code_challenge_method": "S256",
            },
        )
        assert response.status_code == 200
        assert response.json()["next_step"] == "mfa"
        assert len(response.json()["mfa_challenge"]) >= 43


# ------------------------------------------------------------------
# POST /auth/mfa/verify
# ------------------------------------------------------------------


class TestMFAVerifyEndpoint:
    """Tests for POST /auth/mfa/verify endpoint."""

    @pytest.fixture(autouse=True)
    def challenged_user(self):
        """The account a challenge names, read before its code is checked."""
        with (
            patch("modules.auth.authentication.service.users_integration.get_user") as get_user,
            patch(
                "modules.auth.authentication.service.credentials_integration.is_password_change_required",
                return_value=False,
            ),
        ):
            get_user.return_value = MagicMock(id=_USER_ID_1, username="testuser", active=True)
            yield get_user

    @patch("modules.auth.authentication.service.complete_login")
    @patch("modules.auth.authentication.service.users_integration.require_active_user")
    @patch("modules.auth.authentication.service.users_integration.get_user")
    @patch("modules.auth.authentication.service.mfa_integration.verify_user_mfa")
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
        challenge = fake_pending_mfa_store.add_pending_login(pending_login(_USER_ID_1, client_network="testclient"))
        mock_verify_mfa.return_value = True
        mock_user = MagicMock()
        mock_user.id = _USER_ID_1
        mock_user.username = "testuser"
        mock_get_user.return_value = mock_user
        mock_check_active.return_value = None
        mock_complete_login.return_value = auth_schema.AuthOutcome(
            {
                "next_step": "tokens",
                "session_id": _SID_SID_MFA,
                "access_token": "at-mfa",
                "csrf_token": "csrf-mfa",
                "token_type": "bearer",
                "expires_in": 900,
                "refresh_token_expires_in": 604800,
            }
        )

        response = auth_client.post(
            "/auth/mfa/verify",
            json={
                "mfa_challenge": challenge,
                "mfa_code": "123456",
            },
        )

        assert response.status_code == 200
        assert response.json()["access_token"] == "at-mfa"
        replay = auth_client.post("/auth/mfa/verify", json={"mfa_challenge": challenge, "mfa_code": "123456"})
        assert replay.status_code == 401

    @patch("modules.auth.authentication.service.mfa_integration.verify_user_mfa")
    def test_mfa_verify_invalid_code_returns_400(
        self,
        mock_verify_mfa,
        auth_client,
        auth_app,
        fake_pending_mfa_store,
    ):
        """Invalid MFA code returns 400."""
        challenge = fake_pending_mfa_store.add_pending_login(pending_login(_USER_ID_1, client_network="testclient"))
        mock_verify_mfa.return_value = False

        response = auth_client.post(
            "/auth/mfa/verify",
            json={
                "mfa_challenge": challenge,
                "mfa_code": "000000",
            },
        )

        assert response.status_code == 400
        assert response.json()["type"] == "urn:endurain:error:invalid-mfa-code"
        assert "Invalid MFA code" in response.json()["detail"]

    @patch("modules.auth.authentication.service.complete_login")
    @patch("modules.auth.authentication.service.users_integration.require_active_user")
    @patch("modules.auth.authentication.service.users_integration.require_user")
    @patch("modules.auth.authentication.service.users_integration.get_user")
    def test_mfa_verify_backup_code_calls_utils_directly(
        self,
        mock_get_user,
        mock_require_user,
        mock_check_active,
        mock_complete_login,
        auth_client,
        auth_app,
        fake_pending_mfa_store,
        mock_db,
    ):
        """Backup-code MFA login calls mfa_backup_codes.utils directly (through the credentials integration)."""
        challenge = fake_pending_mfa_store.add_pending_login(pending_login(_USER_ID_1, client_network="testclient"))
        mock_mfa = MagicMock()
        mock_mfa.mfa_enabled = True
        mock_mfa.mfa_secret = "encrypted-secret"
        mock_user = MagicMock()
        mock_user.id = _USER_ID_1
        mock_user.username = "testuser"
        mock_user.auth_mfa = mock_mfa
        mock_get_user.return_value = mock_user
        mock_require_user.return_value = mock_user
        mock_check_active.return_value = None
        mock_complete_login.return_value = auth_schema.AuthOutcome(
            {
                "next_step": "tokens",
                "session_id": _SID_SID_BACKUP,
                "access_token": "at-backup",
                "csrf_token": "csrf-backup",
                "token_type": "bearer",
                "expires_in": 900,
                "refresh_token_expires_in": 604800,
            }
        )

        with (
            patch(
                "modules.auth.mfa.service.auth_mfa_crud.get_totp_factor",
                return_value=MagicMock(id=_USER_ID_1, credential="encrypted-secret"),
            ),
            patch(
                "modules.auth.mfa.service.mfa_backup_codes_integration.verify_and_consume_backup_code",
                return_value=True,
            ) as mock_backup_verify,
        ):
            response = auth_client.post(
                "/auth/mfa/verify",
                json={
                    "mfa_challenge": challenge,
                    "mfa_code": "A3K9-7BDF",
                },
            )

        assert response.status_code == 200
        assert response.json()["access_token"] == "at-backup"
        mock_backup_verify.assert_called_once_with(
            _USER_ID_1,
            "A3K9-7BDF",
            auth_credentials_crud.get_password_hasher(),
            mock_db,
        )

    def test_mfa_verify_unknown_challenge_is_401_and_counts_against_no_account(
        self,
        auth_client,
        auth_app,
        fake_pending_mfa_store,
    ):
        """An unknown challenge is a dead sign-in, not a wrong code, and counts against no account."""
        fake_pending_mfa_store.record_failed_attempt = MagicMock(
            return_value=pending_login_store.FailedMfaRecord(count=1, account_locked_now=False)
        )

        response = auth_client.post(
            "/auth/mfa/verify",
            json={"mfa_challenge": UNKNOWN_CHALLENGE, "mfa_code": "123456"},
        )

        assert response.status_code == 401
        assert response.json()["detail"] == "Unable to authenticate with provided credentials"
        fake_pending_mfa_store.record_failed_attempt.assert_not_called()

    def test_mfa_verify_requires_the_challenge(self, auth_client, auth_app):
        response = auth_client.post("/auth/mfa/verify", json={"username": "testuser", "mfa_code": "123456"})

        assert response.status_code == 422

    def test_mfa_verify_locked_out_returns_429(
        self,
        auth_client,
        auth_app,
        fake_pending_mfa_store,
    ):
        """MFA lockout returns 429."""
        from datetime import datetime, timedelta

        challenge = fake_pending_mfa_store.add_pending_login(pending_login(_USER_ID_1, client_network="testclient"))
        fake_pending_mfa_store._locked = True
        fake_pending_mfa_store._lockout_time = datetime.now(UTC) + timedelta(minutes=5)

        response = auth_client.post(
            "/auth/mfa/verify",
            json={
                "mfa_challenge": challenge,
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
            side_effect=(lockout_contracts.AuthSecurityStoreUnavailableError("Redis down"))
        )

        response = auth_client.post(
            "/auth/mfa/verify",
            json={"mfa_challenge": UNKNOWN_CHALLENGE, "mfa_code": "123456"},
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
        challenge = fake_pending_mfa_store.add_pending_login(pending_login(_USER_ID_1, client_network="testclient"))
        fake_pending_mfa_store.is_locked_out = MagicMock(
            side_effect=lockout_contracts.AuthSecurityStoreUnavailableError("Redis down"),
        )
        response = auth_client.post(
            "/auth/mfa/verify",
            json={"mfa_challenge": challenge, "mfa_code": "123456"},
        )
        assert response.status_code == 503
        assert "unavailable" in response.json()["detail"].lower()

    @patch("modules.auth.authentication.service.mfa_integration.verify_user_mfa")
    def test_mfa_verify_store_unavailable_on_record_failed_returns_503(
        self,
        mock_verify_mfa,
        auth_client,
        auth_app,
        fake_pending_mfa_store,
    ):
        """503 when record_failed_attempt raises after invalid MFA code."""
        challenge = fake_pending_mfa_store.add_pending_login(pending_login(_USER_ID_1, client_network="testclient"))
        mock_verify_mfa.return_value = False
        fake_pending_mfa_store.record_failed_attempt = MagicMock(
            side_effect=lockout_contracts.AuthSecurityStoreUnavailableError("Redis down"),
        )
        response = auth_client.post(
            "/auth/mfa/verify",
            json={"mfa_challenge": challenge, "mfa_code": "000000"},
        )
        assert response.status_code == 503
        assert "unavailable" in response.json()["detail"].lower()

    @patch("modules.auth.authentication.service.mfa_integration.verify_user_mfa")
    def test_mfa_verify_store_unavailable_on_claim_pending_returns_503(
        self,
        mock_verify_mfa,
        auth_client,
        auth_app,
        fake_pending_mfa_store,
    ):
        """503 when claim_pending_login raises after valid MFA code."""
        challenge = fake_pending_mfa_store.add_pending_login(pending_login(_USER_ID_1, client_network="testclient"))
        mock_verify_mfa.return_value = True
        fake_pending_mfa_store.claim_pending_login = MagicMock(
            side_effect=lockout_contracts.AuthSecurityStoreUnavailableError("Redis down"),
        )
        response = auth_client.post(
            "/auth/mfa/verify",
            json={"mfa_challenge": challenge, "mfa_code": "123456"},
        )
        assert response.status_code == 503
        assert "unavailable" in response.json()["detail"].lower()

    @patch("modules.auth.authentication.service.users_integration.get_user")
    @patch("modules.auth.authentication.service.mfa_integration.verify_user_mfa")
    def test_mfa_verify_user_not_found_returns_401(
        self,
        mock_verify_mfa,
        mock_get_user,
        auth_client,
        auth_app,
        fake_pending_mfa_store,
    ):
        """401 when user is not found after MFA verification."""
        challenge = fake_pending_mfa_store.add_pending_login(pending_login(_USER_ID_1, client_network="testclient"))
        mock_verify_mfa.return_value = True
        mock_get_user.return_value = None
        response = auth_client.post(
            "/auth/mfa/verify",
            json={"mfa_challenge": challenge, "mfa_code": "123456"},
        )
        assert response.status_code == 401
        assert "Unable to authenticate" in response.json()["detail"]

    @patch("modules.auth.authentication.service.users_integration.require_active_user")
    @patch("modules.auth.authentication.service.users_integration.get_user")
    @patch("modules.auth.authentication.service.mfa_integration.verify_user_mfa")
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
        challenge = fake_pending_mfa_store.add_pending_login(pending_login(_USER_ID_1, client_network="testclient"))
        mock_verify_mfa.return_value = True
        mock_user = MagicMock()
        mock_user.id = _USER_ID_1
        mock_user.username = "testuser"
        mock_get_user.return_value = mock_user
        mock_check_active.return_value = None
        fake_pending_mfa_store.reset_attempts = MagicMock(
            side_effect=lockout_contracts.AuthSecurityStoreUnavailableError("Redis down"),
        )
        response = auth_client.post(
            "/auth/mfa/verify",
            json={"mfa_challenge": challenge, "mfa_code": "123456"},
        )
        assert response.status_code == 503
        assert "unavailable" in response.json()["detail"].lower()

    @patch("modules.auth.authentication.service.create_mobile_pkce_session_response")
    @patch("modules.auth.authentication.service.users_integration.require_active_user")
    @patch("modules.auth.authentication.service.users_integration.get_user")
    @patch("modules.auth.authentication.service.mfa_integration.verify_user_mfa")
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
        pkce_challenge = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
        challenge = fake_pending_mfa_store.add_pending_login(
            pending_login(
                _USER_ID_1, auth_constants.ClientType.MOBILE, pkce_challenge, "S256", client_network="testclient"
            )
        )
        mock_verify_mfa.return_value = True
        mock_user = MagicMock()
        mock_user.id = _USER_ID_1
        mock_user.username = "testuser"
        mock_get_user.return_value = mock_user
        mock_check_active.return_value = None
        mock_pkce.return_value = auth_schema.MobileSessionRead(next_step="exchange", session_id=_SID_PKCE_SID_MFA)
        response = auth_client.post("/auth/mfa/verify", json={"mfa_challenge": challenge, "mfa_code": "123456"})
        assert response.status_code == 200
        assert response.json()["session_id"] == str(_SID_PKCE_SID_MFA)
        assert mock_pkce.call_args.args[3:5] == (pkce_challenge, "S256")


# ------------------------------------------------------------------
# POST /auth/refresh
# ------------------------------------------------------------------


class TestRefreshEndpoint:
    """Tests for POST /auth/refresh endpoint."""

    @patch("modules.auth.authentication.refresh_service.identity_providers_integration.request_idp_token_refresh")
    @patch("modules.auth.authentication.service.sessions_integration.edit_session")
    @patch("modules.auth.authentication.token_service.create_tokens")
    @patch("modules.auth.authentication.dependencies.set_refresh_token_cookie")
    @patch("modules.auth.authentication.refresh_service.rotated_refresh_tokens_integration.store_rotated_token")
    @patch("modules.auth.authentication.refresh_service.rotated_refresh_tokens_integration.check_token_reuse")
    @patch("modules.auth.authentication.service.users_integration.require_active_user")
    @patch("modules.auth.authentication.service.users_integration.get_user")
    @patch("modules.auth.authentication.service.sessions_integration.validate_session_timeout")
    @patch("modules.auth.authentication.service.sessions_integration.lock_live_session")
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
        mock_session.expires_at = datetime.now(UTC) + timedelta(days=30)
        mock_session.id = _SID_SID_1
        mock_session.user_id = _USER_ID_1
        mock_session.client_type = "web"
        mock_session.refresh_token = password_hasher.hash_password("mock_refresh_token")
        mock_session.csrf_token_hash = None
        mock_session.token_family_id = uuid.UUID("00000000-0000-4000-8000-0000000000f1")
        mock_session.rotation_count = 0
        mock_get_session.return_value = mock_session
        mock_validate_timeout.return_value = None
        mock_check_reuse.return_value = (False, False)

        mock_user = MagicMock()
        mock_user.id = _USER_ID_1
        mock_get_user.return_value = mock_user
        mock_check_active.return_value = None

        mock_create_tokens.return_value = (
            _SID_SID_1,
            now + timedelta(minutes=15),
            "new-at",
            now + timedelta(days=7),
            "new-rt",
            "new-csrf",
        )
        mock_edit_session.return_value = MagicMock(expires_at=datetime.now(UTC) + timedelta(days=30))
        mock_idp_refresh.return_value = None

        # Need to override refresh-specific dependencies
        app = auth_app
        app.dependency_overrides[authentication_dependencies.validate_refresh_token] = lambda: None
        app.dependency_overrides[authentication_dependencies.get_sub_from_refresh_token] = lambda: _USER_ID_1
        app.dependency_overrides[authentication_dependencies.get_sid_from_refresh_token] = lambda: _SID_SID_1
        app.dependency_overrides[authentication_dependencies.get_and_return_refresh_token] = lambda: (
            "mock_refresh_token"
        )
        app.dependency_overrides[authentication_dependencies.get_csrf_token] = lambda: None

        response = auth_client.post("/auth/refresh")

        assert response.status_code == 200
        data = response.json()
        assert data["access_token"] == "new-at"
        assert data["csrf_token"] == "new-csrf"
        assert data["token_type"] == "bearer"

    @patch("modules.auth.authentication.service.sessions_integration.lock_live_session")
    def test_refresh_session_not_found_returns_401_and_clears_the_cookie(self, mock_get_session, auth_client, auth_app):
        """A gone session is an invalid token, and the browser drops its refresh cookie."""
        mock_get_session.return_value = None

        app = auth_app
        app.dependency_overrides[authentication_dependencies.validate_refresh_token] = lambda: None
        app.dependency_overrides[authentication_dependencies.get_sub_from_refresh_token] = lambda: _USER_ID_1
        app.dependency_overrides[authentication_dependencies.get_sid_from_refresh_token] = lambda: _SID_NONEXISTENT
        app.dependency_overrides[authentication_dependencies.get_and_return_refresh_token] = lambda: "rt"
        app.dependency_overrides[authentication_dependencies.get_csrf_token] = lambda: None

        response = auth_client.post("/auth/refresh")

        assert response.status_code == 401
        assert response.json()["type"] == "urn:endurain:error:invalid-token"
        assert any("endurain_refresh_token=" in cookie for cookie in response.headers.get_list("set-cookie"))

    @patch("modules.auth.authentication.service.sessions_integration.validate_session_timeout")
    @patch("modules.auth.authentication.service.sessions_integration.lock_live_session")
    def test_refresh_session_owner_mismatch_returns_401(
        self,
        mock_get_session,
        mock_validate_timeout,
        auth_client,
        auth_app,
    ):
        """Session owned by a different user than the token sub returns 401."""
        mock_session = MagicMock()
        mock_session.expires_at = datetime.now(UTC) + timedelta(days=30)
        mock_session.id = _SID_SID_1
        # Session belongs to user 999, but the refresh token's sub is 1.
        mock_session.user_id = _USER_ID_999
        mock_get_session.return_value = mock_session

        app = auth_app
        app.dependency_overrides[authentication_dependencies.validate_refresh_token] = lambda: None
        app.dependency_overrides[authentication_dependencies.get_sub_from_refresh_token] = lambda: _USER_ID_1
        app.dependency_overrides[authentication_dependencies.get_sid_from_refresh_token] = lambda: _SID_SID_1
        app.dependency_overrides[authentication_dependencies.get_and_return_refresh_token] = lambda: "rt"
        app.dependency_overrides[authentication_dependencies.get_csrf_token] = lambda: None

        response = auth_client.post("/auth/refresh")

        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid refresh token"
        assert response.json()["type"] == "urn:endurain:error:invalid-token"
        assert any("endurain_refresh_token=" in cookie for cookie in response.headers.get_list("set-cookie"))
        # The owner check must short-circuit before session-timeout validation.
        mock_validate_timeout.assert_not_called()

    @patch("modules.auth.authentication.service.sessions_integration.validate_session_timeout")
    @patch("modules.auth.authentication.service.sessions_integration.lock_live_session")
    def test_refresh_of_a_session_of_another_client_type_returns_401_and_clears_the_cookie(
        self,
        mock_get_session,
        mock_validate_timeout,
        auth_client,
        auth_app,
    ):
        """A web request presenting a mobile session's refresh token is refused like any invalid token."""
        mock_session = MagicMock()
        mock_session.expires_at = datetime.now(UTC) + timedelta(days=30)
        mock_session.id = _SID_SID_1
        mock_session.user_id = _USER_ID_1
        mock_session.client_type = "mobile"
        mock_get_session.return_value = mock_session

        app = auth_app
        app.dependency_overrides[authentication_dependencies.validate_refresh_token] = lambda: None
        app.dependency_overrides[authentication_dependencies.get_sub_from_refresh_token] = lambda: _USER_ID_1
        app.dependency_overrides[authentication_dependencies.get_sid_from_refresh_token] = lambda: _SID_SID_1
        app.dependency_overrides[authentication_dependencies.get_and_return_refresh_token] = lambda: "rt"
        app.dependency_overrides[authentication_dependencies.get_csrf_token] = lambda: None

        response = auth_client.post("/auth/refresh")

        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid refresh token"
        assert response.json()["type"] == "urn:endurain:error:invalid-token"
        assert any("endurain_refresh_token=" in cookie for cookie in response.headers.get_list("set-cookie"))
        mock_validate_timeout.assert_not_called()

    @patch("modules.auth.authentication.service.sessions_integration.invalidate_token_family")
    @patch("modules.auth.authentication.refresh_service.rotated_refresh_tokens_integration.check_token_reuse")
    @patch("modules.auth.authentication.service.sessions_integration.validate_session_timeout")
    @patch("modules.auth.authentication.service.sessions_integration.lock_live_session")
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
        mock_session.expires_at = datetime.now(UTC) + timedelta(days=30)
        mock_session.id = _SID_SID_1
        mock_session.user_id = _USER_ID_1
        mock_session.client_type = "web"
        mock_session.refresh_token = "hashed-rt"
        mock_session.csrf_token_hash = None
        mock_session.token_family_id = uuid.UUID("00000000-0000-4000-8000-0000000000f1")
        mock_get_session.return_value = mock_session
        mock_validate_timeout.return_value = None
        mock_check_reuse.return_value = (True, False)

        app = auth_app
        app.dependency_overrides[authentication_dependencies.validate_refresh_token] = lambda: None
        app.dependency_overrides[authentication_dependencies.get_sub_from_refresh_token] = lambda: _USER_ID_1
        app.dependency_overrides[authentication_dependencies.get_sid_from_refresh_token] = lambda: _SID_SID_1
        app.dependency_overrides[authentication_dependencies.get_and_return_refresh_token] = lambda: "reused-token"
        app.dependency_overrides[authentication_dependencies.get_csrf_token] = lambda: None

        response = auth_client.post("/auth/refresh")

        assert response.status_code == 401
        assert "reuse" in response.json()["detail"].lower()
        assert "all sessions" not in response.json()["detail"].lower()
        assert any("endurain_refresh_token=" in cookie for cookie in response.headers.get_list("set-cookie"))
        mock_invalidate.assert_called_once()

    @patch("modules.auth.authentication.refresh_service.identity_providers_integration.request_idp_token_refresh")
    @patch("modules.auth.authentication.service.sessions_integration.edit_session")
    @patch("modules.auth.authentication.token_service.create_tokens")
    @patch("modules.auth.authentication.dependencies.set_refresh_token_cookie")
    @patch("modules.auth.authentication.refresh_service.rotated_refresh_tokens_integration.store_rotated_token")
    @patch("modules.auth.authentication.refresh_service.rotated_refresh_tokens_integration.check_token_reuse")
    @patch("modules.auth.authentication.service.users_integration.require_active_user")
    @patch("modules.auth.authentication.service.users_integration.get_user")
    @patch("modules.auth.authentication.service.sessions_integration.validate_session_timeout")
    @patch("modules.auth.authentication.service.sessions_integration.verify_csrf_token")
    @patch("modules.auth.authentication.service.sessions_integration.lock_live_session")
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
            mock_idp_refresh: Mock for request_idp_token_refresh.
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
        mock_session.expires_at = datetime.now(UTC) + timedelta(days=30)
        mock_session.id = _SID_SID_CSRF_1
        mock_session.user_id = _USER_ID_1
        mock_session.client_type = "web"
        mock_session.refresh_token = password_hasher.hash_password("mock_rt")
        mock_session.csrf_token_hash = "stored-hmac"
        mock_session.token_family_id = uuid.UUID("00000000-0000-4000-8000-0000000000f1")
        mock_session.rotation_count = 0
        mock_get_session.return_value = mock_session
        mock_validate_timeout.return_value = None
        mock_verify_csrf.return_value = True
        mock_check_reuse.return_value = (False, False)
        mock_get_user.return_value = MagicMock(id=_USER_ID_1)
        mock_check_active.return_value = None
        mock_create_tokens.return_value = (
            _SID_SID_CSRF_1,
            now + timedelta(minutes=15),
            "new-at",
            now + timedelta(days=7),
            "new-rt",
            "new-csrf",
        )
        mock_edit_session.return_value = MagicMock(expires_at=datetime.now(UTC) + timedelta(days=30))
        mock_idp_refresh.return_value = None

        app = auth_app
        app.dependency_overrides[authentication_dependencies.validate_refresh_token] = lambda: None
        app.dependency_overrides[authentication_dependencies.get_sub_from_refresh_token] = lambda: _USER_ID_1
        app.dependency_overrides[authentication_dependencies.get_sid_from_refresh_token] = lambda: _SID_SID_CSRF_1
        app.dependency_overrides[authentication_dependencies.get_and_return_refresh_token] = lambda: "mock_rt"
        app.dependency_overrides[authentication_dependencies.get_csrf_token] = lambda: "valid-csrf"

        response = auth_client.post("/auth/refresh")

        assert response.status_code == 200
        mock_verify_csrf.assert_called_once_with("valid-csrf", "stored-hmac")

    @patch("modules.auth.authentication.refresh_service.rotated_refresh_tokens_integration.store_rotated_token")
    @patch("modules.auth.authentication.service.sessions_integration.edit_session")
    @patch("modules.auth.authentication.service.sessions_integration.validate_session_timeout")
    @patch("modules.auth.authentication.service.sessions_integration.verify_csrf_token")
    @patch("modules.auth.authentication.service.sessions_integration.lock_live_session")
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
        mock_session.expires_at = datetime.now(UTC) + timedelta(days=30)
        mock_session.id = _SID_SID_BAD_CSRF
        mock_session.user_id = _USER_ID_1
        mock_session.client_type = "web"
        mock_session.refresh_token = "some-hashed-token"
        mock_session.csrf_token_hash = "stored-hmac"
        mock_get_session.return_value = mock_session
        mock_validate_timeout.return_value = None
        mock_verify_csrf.return_value = False

        app = auth_app
        app.dependency_overrides[authentication_dependencies.validate_refresh_token] = lambda: None
        app.dependency_overrides[authentication_dependencies.get_sub_from_refresh_token] = lambda: _USER_ID_1
        app.dependency_overrides[authentication_dependencies.get_sid_from_refresh_token] = lambda: _SID_SID_BAD_CSRF
        app.dependency_overrides[authentication_dependencies.get_and_return_refresh_token] = lambda: "any-rt"
        app.dependency_overrides[authentication_dependencies.get_csrf_token] = lambda: "wrong-csrf"

        response = auth_client.post("/auth/refresh")

        assert response.status_code == 403
        assert "CSRF" in response.json()["detail"]
        mock_store_rotated.assert_not_called()
        mock_edit_session.assert_not_called()

    @patch("modules.auth.authentication.refresh_service.identity_providers_integration.request_idp_token_refresh")
    @patch("modules.auth.authentication.service.sessions_integration.edit_session")
    @patch("modules.auth.authentication.token_service.create_tokens")
    @patch("modules.auth.authentication.dependencies.set_refresh_token_cookie")
    @patch("modules.auth.authentication.refresh_service.rotated_refresh_tokens_integration.store_rotated_token")
    @patch("modules.auth.authentication.refresh_service.rotated_refresh_tokens_integration.check_token_reuse")
    @patch("modules.auth.authentication.service.users_integration.require_active_user")
    @patch("modules.auth.authentication.service.users_integration.get_user")
    @patch("modules.auth.authentication.service.sessions_integration.validate_session_timeout")
    @patch("modules.auth.authentication.service.sessions_integration.lock_live_session")
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
            mock_idp_refresh: Mock for request_idp_token_refresh.
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
        mock_session.expires_at = datetime.now(UTC) + timedelta(days=30)
        mock_session.id = _SID_SID_RELOAD
        mock_session.user_id = _USER_ID_1
        mock_session.client_type = "web"
        mock_session.refresh_token = password_hasher.hash_password("mock_rt")
        mock_session.csrf_token_hash = "stored-hmac"
        mock_session.token_family_id = uuid.UUID("00000000-0000-4000-8000-0000000000f1")
        mock_session.rotation_count = 0
        mock_get_session.return_value = mock_session
        mock_validate_timeout.return_value = None
        mock_check_reuse.return_value = (False, False)
        mock_get_user.return_value = MagicMock(id=_USER_ID_1)
        mock_check_active.return_value = None
        mock_create_tokens.return_value = (
            _SID_SID_RELOAD,
            now + timedelta(minutes=15),
            "new-at",
            now + timedelta(days=7),
            "new-rt",
            "new-csrf",
        )
        mock_edit_session.return_value = MagicMock(expires_at=datetime.now(UTC) + timedelta(days=30))
        mock_idp_refresh.return_value = None

        app = auth_app
        app.dependency_overrides[authentication_dependencies.validate_refresh_token] = lambda: None
        app.dependency_overrides[authentication_dependencies.get_sub_from_refresh_token] = lambda: _USER_ID_1
        app.dependency_overrides[authentication_dependencies.get_sid_from_refresh_token] = lambda: _SID_SID_RELOAD
        app.dependency_overrides[authentication_dependencies.get_and_return_refresh_token] = lambda: "mock_rt"
        # No CSRF header: simulates page reload bootstrap
        app.dependency_overrides[authentication_dependencies.get_csrf_token] = lambda: None

        response = auth_client.post("/auth/refresh")

        assert response.status_code == 200
        assert response.json()["access_token"] == "new-at"

    @patch("modules.auth.authentication.service.sessions_integration.verify_csrf_token")
    @patch("modules.auth.authentication.refresh_service.identity_providers_integration.request_idp_token_refresh")
    @patch("modules.auth.authentication.service.sessions_integration.edit_session")
    @patch("modules.auth.authentication.token_service.create_tokens")
    @patch("modules.auth.authentication.dependencies.set_refresh_token_cookie")
    @patch("modules.auth.authentication.refresh_service.rotated_refresh_tokens_integration.store_rotated_token")
    @patch("modules.auth.authentication.refresh_service.rotated_refresh_tokens_integration.check_token_reuse")
    @patch("modules.auth.authentication.service.users_integration.require_active_user")
    @patch("modules.auth.authentication.service.users_integration.get_user")
    @patch("modules.auth.authentication.service.sessions_integration.validate_session_timeout")
    @patch("modules.auth.authentication.service.sessions_integration.lock_live_session")
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
            mock_idp_refresh: Mock for request_idp_token_refresh.
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
        mock_session.expires_at = datetime.now(UTC) + timedelta(days=30)
        mock_session.id = _SID_SID_MOB_CSRF
        mock_session.user_id = _USER_ID_1
        mock_session.client_type = "mobile"
        mock_session.refresh_token = password_hasher.hash_password("mock_rt")
        mock_session.csrf_token_hash = "stored-hmac"
        mock_session.token_family_id = uuid.UUID("00000000-0000-4000-8000-0000000000f1")
        mock_session.rotation_count = 0
        mock_get_session.return_value = mock_session
        mock_validate_timeout.return_value = None
        mock_check_reuse.return_value = (False, False)
        mock_get_user.return_value = MagicMock(id=_USER_ID_1)
        mock_check_active.return_value = None
        mock_create_tokens.return_value = (
            _SID_SID_MOB_CSRF,
            now + timedelta(minutes=15),
            "new-at",
            now + timedelta(days=7),
            "new-rt",
            None,
        )
        mock_edit_session.return_value = MagicMock(expires_at=datetime.now(UTC) + timedelta(days=30))
        mock_idp_refresh.return_value = None

        app = auth_app
        app.dependency_overrides[authentication_dependencies.validate_refresh_token] = lambda: None
        app.dependency_overrides[authentication_dependencies.get_sub_from_refresh_token] = lambda: _USER_ID_1
        app.dependency_overrides[authentication_dependencies.get_sid_from_refresh_token] = lambda: _SID_SID_MOB_CSRF
        app.dependency_overrides[authentication_dependencies.get_and_return_refresh_token] = lambda: "mock_rt"
        app.dependency_overrides[authentication_dependencies.get_csrf_token] = lambda: "any-csrf-value"

        response = auth_client.post("/auth/refresh")

        assert response.status_code == 200
        mock_verify_csrf.assert_not_called()
        mock_set_cookie.assert_not_called()
        assert "refresh_token" in response.json()

    @patch("modules.auth.authentication.service.sessions_integration.validate_session_timeout")
    @patch("modules.auth.authentication.service.sessions_integration.lock_live_session")
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
        mock_session.expires_at = datetime.now(UTC) + timedelta(days=30)
        mock_session.id = _SID_SID_PKCE
        mock_session.user_id = _USER_ID_1
        mock_session.client_type = "web"
        mock_session.refresh_token = None
        mock_session.csrf_token_hash = None
        mock_get_session.return_value = mock_session
        mock_validate_timeout.return_value = None

        app = auth_app
        app.dependency_overrides[authentication_dependencies.validate_refresh_token] = lambda: None
        app.dependency_overrides[authentication_dependencies.get_sub_from_refresh_token] = lambda: _USER_ID_1
        app.dependency_overrides[authentication_dependencies.get_sid_from_refresh_token] = lambda: _SID_SID_PKCE
        app.dependency_overrides[authentication_dependencies.get_and_return_refresh_token] = lambda: "rt"
        app.dependency_overrides[authentication_dependencies.get_csrf_token] = lambda: None

        response = auth_client.post("/auth/refresh")

        assert response.status_code == 401
        assert "PKCE" in response.json()["detail"]

    @patch("modules.auth.authentication.refresh_service.rotated_refresh_tokens_integration.store_rotated_token")
    @patch("modules.auth.authentication.service.sessions_integration.edit_session")
    @patch("modules.auth.authentication.refresh_service.rotated_refresh_tokens_integration.check_token_reuse")
    @patch("modules.auth.authentication.service.sessions_integration.validate_session_timeout")
    @patch("modules.auth.authentication.service.sessions_integration.lock_live_session")
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
        mock_session.expires_at = datetime.now(UTC) + timedelta(days=30)
        mock_session.id = _SID_SID_BAD_RT
        mock_session.user_id = _USER_ID_1
        mock_session.client_type = "web"
        mock_session.refresh_token = password_hasher.hash_password("real_token")
        mock_session.csrf_token_hash = None
        mock_session.token_family_id = uuid.UUID("00000000-0000-4000-8000-0000000000f1")
        mock_session.rotation_count = 0
        mock_get_session.return_value = mock_session
        mock_validate_timeout.return_value = None
        mock_check_reuse.return_value = (False, False)

        app = auth_app
        app.dependency_overrides[authentication_dependencies.validate_refresh_token] = lambda: None
        app.dependency_overrides[authentication_dependencies.get_sub_from_refresh_token] = lambda: _USER_ID_1
        app.dependency_overrides[authentication_dependencies.get_sid_from_refresh_token] = lambda: _SID_SID_BAD_RT
        app.dependency_overrides[authentication_dependencies.get_and_return_refresh_token] = lambda: "wrong_token"
        app.dependency_overrides[authentication_dependencies.get_csrf_token] = lambda: None

        response = auth_client.post("/auth/refresh")

        assert response.status_code == 401
        assert "Invalid refresh token" in response.json()["detail"]
        mock_store_rotated.assert_not_called()
        mock_edit_session.assert_not_called()

    @patch("modules.auth.authentication.refresh_service.rotated_refresh_tokens_integration.store_rotated_token")
    @patch("modules.auth.authentication.service.sessions_integration.edit_session")
    @patch("modules.auth.authentication.service.users_integration.require_active_user")
    @patch("modules.auth.authentication.service.users_integration.get_user")
    @patch("modules.auth.authentication.refresh_service.rotated_refresh_tokens_integration.check_token_reuse")
    @patch("modules.auth.authentication.service.sessions_integration.validate_session_timeout")
    @patch("modules.auth.authentication.service.sessions_integration.lock_live_session")
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
        mock_session.expires_at = datetime.now(UTC) + timedelta(days=30)
        mock_session.id = _SID_SID_NO_USER
        mock_session.user_id = _USER_ID_1
        mock_session.client_type = "web"
        mock_session.refresh_token = password_hasher.hash_password("mock_rt")
        mock_session.csrf_token_hash = None
        mock_session.token_family_id = uuid.UUID("00000000-0000-4000-8000-0000000000f1")
        mock_session.rotation_count = 0
        mock_get_session.return_value = mock_session
        mock_validate_timeout.return_value = None
        mock_check_reuse.return_value = (False, False)
        mock_get_user.return_value = None

        app = auth_app
        app.dependency_overrides[authentication_dependencies.validate_refresh_token] = lambda: None
        app.dependency_overrides[authentication_dependencies.get_sub_from_refresh_token] = lambda: _USER_ID_1
        app.dependency_overrides[authentication_dependencies.get_sid_from_refresh_token] = lambda: _SID_SID_NO_USER
        app.dependency_overrides[authentication_dependencies.get_and_return_refresh_token] = lambda: "mock_rt"
        app.dependency_overrides[authentication_dependencies.get_csrf_token] = lambda: None

        response = auth_client.post("/auth/refresh")

        assert response.status_code == 401
        assert "authenticate" in response.json()["detail"].lower()

    @patch("modules.auth.authentication.refresh_service.identity_providers_integration.request_idp_token_refresh")
    @patch("modules.auth.authentication.service.sessions_integration.edit_session")
    @patch("modules.auth.authentication.token_service.create_tokens")
    @patch("modules.auth.authentication.dependencies.set_refresh_token_cookie")
    @patch("modules.auth.authentication.refresh_service.rotated_refresh_tokens_integration.store_rotated_token")
    @patch("modules.auth.authentication.refresh_service.rotated_refresh_tokens_integration.check_token_reuse")
    @patch("modules.auth.authentication.service.users_integration.require_active_user")
    @patch("modules.auth.authentication.service.users_integration.get_user")
    @patch("modules.auth.authentication.service.sessions_integration.validate_session_timeout")
    @patch("modules.auth.authentication.service.sessions_integration.lock_live_session")
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
            mock_idp_refresh: Mock for request_idp_token_refresh.
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
        mock_session.expires_at = datetime.now(UTC) + timedelta(days=30)
        mock_session.id = _SID_SID_MOB
        mock_session.user_id = _USER_ID_1
        mock_session.client_type = "mobile"
        mock_session.refresh_token = password_hasher.hash_password("mock_rt")
        mock_session.csrf_token_hash = None
        mock_session.token_family_id = uuid.UUID("00000000-0000-4000-8000-0000000000f1")
        mock_session.rotation_count = 0
        mock_get_session.return_value = mock_session
        mock_validate_timeout.return_value = None
        mock_check_reuse.return_value = (False, False)
        mock_get_user.return_value = MagicMock(id=_USER_ID_1)
        mock_check_active.return_value = None
        mock_create_tokens.return_value = (
            _SID_SID_MOB,
            now + timedelta(minutes=15),
            "new-at",
            now + timedelta(days=7),
            "new-rt",
            None,
        )
        mock_edit_session.return_value = MagicMock(expires_at=datetime.now(UTC) + timedelta(days=30))
        mock_idp_refresh.return_value = None

        app = auth_app
        app.dependency_overrides[authentication_dependencies.validate_refresh_token] = lambda: None
        app.dependency_overrides[authentication_dependencies.get_sub_from_refresh_token] = lambda: _USER_ID_1
        app.dependency_overrides[authentication_dependencies.get_sid_from_refresh_token] = lambda: _SID_SID_MOB
        app.dependency_overrides[authentication_dependencies.get_and_return_refresh_token] = lambda: "mock_rt"
        app.dependency_overrides[authentication_dependencies.get_csrf_token] = lambda: None

        response = auth_client.post("/auth/refresh")

        assert response.status_code == 200
        data = response.json()
        assert "refresh_token" in data
        assert data["refresh_token"] == "new-rt"
        mock_set_cookie.assert_not_called()

    @patch("modules.auth.authentication.token_service.mint_access_token")
    @patch("modules.auth.authentication.refresh_service.rotated_refresh_tokens_integration.get_grace_replay_token")
    @patch("modules.auth.authentication.token_service.create_tokens")
    @patch("modules.auth.authentication.service.sessions_integration.edit_session")
    @patch("modules.auth.authentication.refresh_service.rotated_refresh_tokens_integration.store_rotated_token")
    @patch("modules.auth.authentication.refresh_service.rotated_refresh_tokens_integration.check_token_reuse")
    @patch("modules.auth.authentication.service.users_integration.require_active_user")
    @patch("modules.auth.authentication.service.users_integration.get_user")
    @patch("modules.auth.authentication.service.sessions_integration.validate_session_timeout")
    @patch("modules.auth.authentication.service.sessions_integration.lock_live_session")
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
        mock_session.expires_at = datetime.now(UTC) + timedelta(days=30)
        mock_session.id = _SID_SID_REPLAY_MOB
        mock_session.user_id = _USER_ID_1
        mock_session.client_type = "mobile"
        mock_session.refresh_token = password_hasher.hash_password("current_rt")
        mock_session.csrf_token_hash = None
        mock_session.token_family_id = uuid.UUID("00000000-0000-4000-8000-0000000000f1")
        mock_session.rotation_count = 1
        mock_get_session.return_value = mock_session
        mock_validate_timeout.return_value = None
        # Presented token was already rotated but is still within grace.
        mock_check_reuse.return_value = (True, True)
        mock_get_replay.return_value = ("replayed-rt", now + timedelta(days=7))
        mock_get_user.return_value = MagicMock(id=_USER_ID_1)
        mock_check_active.return_value = None
        mock_mint_access.return_value = (now + timedelta(minutes=15), "replayed-at")

        app = auth_app
        app.dependency_overrides[authentication_dependencies.validate_refresh_token] = lambda: None
        app.dependency_overrides[authentication_dependencies.get_sub_from_refresh_token] = lambda: _USER_ID_1
        app.dependency_overrides[authentication_dependencies.get_sid_from_refresh_token] = lambda: _SID_SID_REPLAY_MOB
        app.dependency_overrides[authentication_dependencies.get_and_return_refresh_token] = lambda: "old_rotated_rt"
        app.dependency_overrides[authentication_dependencies.get_csrf_token] = lambda: None

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

    @patch("modules.auth.authentication.token_service.mint_access_token")
    @patch("modules.auth.authentication.refresh_service.rotated_refresh_tokens_integration.get_grace_replay_token")
    @patch("modules.auth.authentication.token_service.create_tokens")
    @patch("modules.auth.authentication.service.sessions_integration.edit_session")
    @patch("modules.auth.authentication.refresh_service.rotated_refresh_tokens_integration.store_rotated_token")
    @patch("modules.auth.authentication.refresh_service.rotated_refresh_tokens_integration.check_token_reuse")
    @patch("modules.auth.authentication.service.users_integration.require_active_user")
    @patch("modules.auth.authentication.service.users_integration.get_user")
    @patch("modules.auth.authentication.service.sessions_integration.validate_session_timeout")
    @patch("modules.auth.authentication.service.sessions_integration.lock_live_session")
    def test_refresh_losing_a_concurrent_rotation_replays_the_winners_token(
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
        """Two refreshes with one token: the one whose rotation record collides gets the winner's replacement."""
        from datetime import datetime, timedelta

        auth_app.state._client_type = "mobile"
        now = datetime.now(UTC)
        mock_session = MagicMock()
        mock_session.expires_at = datetime.now(UTC) + timedelta(days=30)
        mock_session.id = _SID_SID_RACE
        mock_session.user_id = _USER_ID_1
        mock_session.client_type = "mobile"
        mock_session.refresh_token = password_hasher.hash_password("old_rt")
        mock_session.csrf_token_hash = None
        mock_session.token_family_id = uuid.UUID("00000000-0000-4000-8000-0000000000f1")
        mock_session.rotation_count = 1
        mock_get_session.return_value = mock_session
        mock_validate_timeout.return_value = None
        # Nothing is recorded when this request first checks, because the winner has not committed yet; once
        # it has, the same client is inside the grace window.
        mock_check_reuse.side_effect = [(False, False), (True, True)]
        mock_create_tokens.return_value = (_SID_SID_RACE, now, "loser-at", now, "loser-rt", None)
        mock_store_rotated.side_effect = core_exceptions.ConflictError("already rotated")
        mock_get_replay.return_value = ("winner-rt", now + timedelta(days=7))
        mock_get_user.return_value = MagicMock(id=_USER_ID_1)
        mock_check_active.return_value = None
        mock_mint_access.return_value = (now + timedelta(minutes=15), "replayed-at")

        app = auth_app
        app.dependency_overrides[authentication_dependencies.validate_refresh_token] = lambda: None
        app.dependency_overrides[authentication_dependencies.get_sub_from_refresh_token] = lambda: _USER_ID_1
        app.dependency_overrides[authentication_dependencies.get_sid_from_refresh_token] = lambda: _SID_SID_RACE
        app.dependency_overrides[authentication_dependencies.get_and_return_refresh_token] = lambda: "old_rt"
        app.dependency_overrides[authentication_dependencies.get_csrf_token] = lambda: None

        response = auth_client.post("/auth/refresh")

        assert response.status_code == 200
        assert response.json()["refresh_token"] == "winner-rt"
        # The loser never rotates the session, so only the winner's token is live.
        mock_edit_session.assert_not_called()

    @patch("modules.auth.authentication.service.sessions_integration.update_session_csrf_token")
    @patch("modules.auth.authentication.dependencies.set_refresh_token_cookie")
    @patch("modules.auth.authentication.token_service.mint_access_token")
    @patch("modules.auth.authentication.refresh_service.rotated_refresh_tokens_integration.get_grace_replay_token")
    @patch("modules.auth.authentication.token_service.create_tokens")
    @patch("modules.auth.authentication.service.sessions_integration.edit_session")
    @patch("modules.auth.authentication.refresh_service.rotated_refresh_tokens_integration.store_rotated_token")
    @patch("modules.auth.authentication.refresh_service.rotated_refresh_tokens_integration.check_token_reuse")
    @patch("modules.auth.authentication.service.users_integration.require_active_user")
    @patch("modules.auth.authentication.service.users_integration.get_user")
    @patch("modules.auth.authentication.service.sessions_integration.validate_session_timeout")
    @patch("modules.auth.authentication.service.sessions_integration.lock_live_session")
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
        mock_session.expires_at = datetime.now(UTC) + timedelta(days=30)
        mock_session.id = _SID_SID_REPLAY_WEB
        mock_session.user_id = _USER_ID_1
        mock_session.client_type = "web"
        mock_session.refresh_token = password_hasher.hash_password("current_rt")
        mock_session.csrf_token_hash = "stored-hmac"
        mock_session.token_family_id = uuid.UUID("00000000-0000-4000-8000-0000000000f1")
        mock_session.rotation_count = 1
        mock_get_session.return_value = mock_session
        mock_validate_timeout.return_value = None
        mock_check_reuse.return_value = (True, True)
        mock_get_replay.return_value = ("replayed-rt", now + timedelta(days=7))
        mock_get_user.return_value = MagicMock(id=_USER_ID_1)
        mock_check_active.return_value = None
        mock_mint_access.return_value = (now + timedelta(minutes=15), "replayed-at")
        mock_set_cookie.return_value = None
        mock_update_csrf.return_value = None

        app = auth_app
        app.dependency_overrides[authentication_dependencies.validate_refresh_token] = lambda: None
        app.dependency_overrides[authentication_dependencies.get_sub_from_refresh_token] = lambda: _USER_ID_1
        app.dependency_overrides[authentication_dependencies.get_sid_from_refresh_token] = lambda: _SID_SID_REPLAY_WEB
        app.dependency_overrides[authentication_dependencies.get_and_return_refresh_token] = lambda: "old_rotated_rt"
        # No CSRF header: page-reload bootstrap / lost rotation response.
        app.dependency_overrides[authentication_dependencies.get_csrf_token] = lambda: None

        response = auth_client.post("/auth/refresh")

        assert response.status_code == 200
        data = response.json()
        assert data["access_token"] == "replayed-at"
        # A fresh CSRF token is minted and bound to the session.
        assert data["csrf_token"]
        mock_update_csrf.assert_called_once()
        assert mock_update_csrf.call_args.args[0] == _SID_SID_REPLAY_WEB
        # Refresh token is unchanged: delivered via cookie, no re-rotation.
        mock_set_cookie.assert_called_once()
        mock_store_rotated.assert_not_called()
        mock_edit_session.assert_not_called()
        mock_create_tokens.assert_not_called()

    @patch("modules.auth.authentication.refresh_service.rotated_refresh_tokens_integration.get_grace_replay_token")
    @patch("modules.auth.authentication.service.sessions_integration.edit_session")
    @patch("modules.auth.authentication.refresh_service.rotated_refresh_tokens_integration.store_rotated_token")
    @patch("modules.auth.authentication.refresh_service.rotated_refresh_tokens_integration.check_token_reuse")
    @patch("modules.auth.authentication.service.sessions_integration.validate_session_timeout")
    @patch("modules.auth.authentication.service.sessions_integration.lock_live_session")
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
        mock_session.expires_at = datetime.now(UTC) + timedelta(days=30)
        mock_session.id = _SID_SID_REPLAY_NONE
        mock_session.user_id = _USER_ID_1
        mock_session.client_type = "web"
        mock_session.refresh_token = password_hasher.hash_password("current_rt")
        mock_session.csrf_token_hash = None
        mock_session.token_family_id = uuid.UUID("00000000-0000-4000-8000-0000000000f1")
        mock_session.rotation_count = 1
        mock_get_session.return_value = mock_session
        mock_validate_timeout.return_value = None
        mock_check_reuse.return_value = (True, True)
        mock_get_replay.return_value = None

        app = auth_app
        app.dependency_overrides[authentication_dependencies.validate_refresh_token] = lambda: None
        app.dependency_overrides[authentication_dependencies.get_sub_from_refresh_token] = lambda: _USER_ID_1
        app.dependency_overrides[authentication_dependencies.get_sid_from_refresh_token] = lambda: _SID_SID_REPLAY_NONE
        app.dependency_overrides[authentication_dependencies.get_and_return_refresh_token] = lambda: "old_rotated_rt"
        app.dependency_overrides[authentication_dependencies.get_csrf_token] = lambda: None

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

    @pytest.fixture(autouse=True)
    def _signed_in_with_no_provider(self):
        with patch(
            "modules.auth.authentication.service.identity_providers_integration.read_end_session", return_value=None
        ):
            yield

    @patch("modules.auth.authentication.service.sessions_integration.delete_session")
    @patch("modules.auth.authentication.service.sessions_integration.get_session_by_id_not_expired")
    def test_logout_success(
        self,
        mock_get_session,
        mock_delete_session,
        auth_client,
        auth_app,
        password_hasher,
    ):
        """Successful logout deletes session."""
        mock_session = MagicMock()
        mock_session.expires_at = datetime.now(UTC) + timedelta(days=30)
        mock_session.id = _SID_SID_1
        mock_session.refresh_token = password_hasher.hash_password("mock_refresh_token")
        mock_get_session.return_value = mock_session
        mock_delete_session.return_value = None

        app = auth_app
        app.dependency_overrides[authentication_dependencies.get_logout_target] = lambda: (
            authentication_dependencies.LogoutTarget(MOCK_USER_ID, _SID_SID_1, "mock_refresh_token")
        )

        response = auth_client.post("/auth/logout")

        assert response.status_code == 200
        assert response.json() == {"idp_logout_url": None}
        assert response.headers["cache-control"] == "no-store"
        mock_delete_session.assert_called_once()

    @patch("modules.auth.authentication.service.sessions_integration.delete_session")
    @patch("modules.auth.authentication.service.sessions_integration.get_session_by_id_not_expired")
    def test_logout_with_a_token_the_session_does_not_hold_ends_nothing(
        self,
        mock_get_session,
        mock_delete_session,
        auth_client,
        auth_app,
        password_hasher,
    ):
        """A token that is not the session's stored one answers 200 and the session stays."""
        mock_session = MagicMock()
        mock_session.expires_at = datetime.now(UTC) + timedelta(days=30)
        mock_session.id = _SID_SID_1
        mock_session.refresh_token = password_hasher.hash_password("real_token")
        mock_get_session.return_value = mock_session

        app = auth_app
        app.dependency_overrides[authentication_dependencies.get_logout_target] = lambda: (
            authentication_dependencies.LogoutTarget(MOCK_USER_ID, _SID_SID_1, "wrong_token")
        )

        response = auth_client.post("/auth/logout")

        assert response.status_code == 200
        assert response.json() == {"idp_logout_url": None}
        mock_delete_session.assert_not_called()

    @patch("modules.auth.authentication.dependencies.clear_refresh_token_cookies")
    @patch("modules.auth.authentication.service.sessions_integration.delete_session")
    @patch("modules.auth.authentication.service.sessions_integration.get_session_by_id_not_expired")
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
        app.dependency_overrides[authentication_dependencies.get_logout_target] = lambda: (
            authentication_dependencies.LogoutTarget(MOCK_USER_ID, uuid.uuid4(), "rt")
        )

        response = auth_client.post("/auth/logout")

        assert response.status_code == 200
        assert response.json() == {"idp_logout_url": None}
        mock_delete_session.assert_not_called()

    @patch("modules.auth.authentication.service.sessions_integration.delete_session")
    @patch("modules.auth.authentication.service.sessions_integration.get_session_by_id_not_expired")
    def test_logout_pending_pkce_no_refresh_token_ends_nothing(
        self,
        mock_get_session,
        mock_delete_session,
        auth_client,
        auth_app,
    ):
        """
        Session without refresh_token (pending PKCE) answers 200 and is not deleted.

        Args:
            mock_get_session: Mock for get_session_by_id_not_expired.
            mock_delete_session: Mock for delete_session.
            auth_client: TestClient for the auth app.
            auth_app: FastAPI test application.

        Returns:
            None.

        Raises:
            AssertionError: If response status is not 200 or the session was deleted.
        """
        mock_session = MagicMock()
        mock_session.expires_at = datetime.now(UTC) + timedelta(days=30)
        mock_session.id = _SID_SID_PKCE
        mock_session.refresh_token = None
        mock_get_session.return_value = mock_session

        app = auth_app
        app.dependency_overrides[authentication_dependencies.get_logout_target] = lambda: (
            authentication_dependencies.LogoutTarget(MOCK_USER_ID, _SID_SID_PKCE, "rt")
        )

        response = auth_client.post("/auth/logout")

        assert response.status_code == 200
        assert response.json() == {"idp_logout_url": None}
        mock_delete_session.assert_not_called()

    @patch("modules.auth.authentication.dependencies.clear_refresh_token_cookies")
    @patch("modules.auth.authentication.service.sessions_integration.delete_session")
    @patch("modules.auth.authentication.service.sessions_integration.get_session_by_id_not_expired")
    def test_logout_web_clears_refresh_cookies(
        self,
        mock_get_session,
        mock_delete_session,
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
        mock_session.expires_at = datetime.now(UTC) + timedelta(days=30)
        mock_session.id = _SID_SID_WEB
        mock_session.refresh_token = password_hasher.hash_password("mock_rt")
        mock_get_session.return_value = mock_session
        mock_delete_session.return_value = None

        app = auth_app
        app.dependency_overrides[authentication_dependencies.get_logout_target] = lambda: (
            authentication_dependencies.LogoutTarget(MOCK_USER_ID, _SID_SID_WEB, "mock_rt")
        )

        response = auth_client.post("/auth/logout")

        assert response.status_code == 200
        assert response.json() == {"idp_logout_url": None}
        mock_clear_cookies.assert_called_once()

    @patch("modules.auth.authentication.dependencies.clear_refresh_token_cookies")
    @patch("modules.auth.authentication.service.sessions_integration.delete_session")
    @patch("modules.auth.authentication.service.sessions_integration.get_session_by_id_not_expired")
    def test_logout_mobile_succeeds_without_cookie_clearing(
        self,
        mock_get_session,
        mock_delete_session,
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
        mock_session.expires_at = datetime.now(UTC) + timedelta(days=30)
        mock_session.id = _SID_SID_MOB
        mock_session.refresh_token = password_hasher.hash_password("mock_rt")
        mock_get_session.return_value = mock_session
        mock_delete_session.return_value = None

        app = auth_app
        app.dependency_overrides[authentication_dependencies.get_logout_target] = lambda: (
            authentication_dependencies.LogoutTarget(MOCK_USER_ID, _SID_SID_MOB, "mock_rt")
        )

        response = auth_client.post("/auth/logout")

        assert response.status_code == 200
        assert response.json() == {"idp_logout_url": None}
        mock_clear_cookies.assert_not_called()

    @patch("modules.auth.authentication.dependencies.clear_refresh_token_cookies")
    @patch("modules.auth.authentication.service.sessions_integration.delete_session")
    @patch("modules.auth.authentication.service.sessions_integration.get_session_by_id_not_expired")
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
        app.dependency_overrides[authentication_dependencies.get_logout_target] = lambda: (
            authentication_dependencies.LogoutTarget(MOCK_USER_ID, uuid.uuid4(), "rt")
        )

        response = auth_client.post("/auth/logout")
        assert response.status_code == 200
        assert response.json() == {"idp_logout_url": None}
        mock_delete_session.assert_not_called()
        mock_clear_cookies.assert_not_called()

    @staticmethod
    def _signed_in_session(auth_app, password_hasher, session_id=_SID_SID_IDP):
        mock_session = MagicMock()
        mock_session.expires_at = datetime.now(UTC) + timedelta(days=30)
        mock_session.id = session_id
        mock_session.refresh_token = password_hasher.hash_password("rt")
        auth_app.dependency_overrides[authentication_dependencies.get_logout_target] = lambda: (
            authentication_dependencies.LogoutTarget(MOCK_USER_ID, session_id, "rt")
        )
        return mock_session

    @patch("modules.auth.authentication.service.identity_providers_integration.end_session_url")
    @patch("modules.auth.authentication.service.identity_providers_integration.read_end_session")
    @patch("modules.auth.authentication.service.sessions_integration.delete_session")
    @patch("modules.auth.authentication.service.sessions_integration.get_session_by_id_not_expired")
    def test_logout_of_a_web_idp_session_answers_the_provider_url_without_caching(
        self,
        mock_get_session,
        mock_delete_session,
        mock_read,
        mock_url,
        auth_client,
        auth_app,
        password_hasher,
    ):
        mock_get_session.return_value = self._signed_in_session(auth_app, password_hasher)
        mock_read.return_value = "end-session-request"
        mock_url.return_value = "https://idp.example.com/out?id_token_hint=abc"

        response = auth_client.post("/auth/logout")

        assert response.status_code == 200
        assert response.json() == {"idp_logout_url": "https://idp.example.com/out?id_token_hint=abc"}
        assert response.headers["cache-control"] == "no-store"
        assert mock_read.call_args.args[0] == _SID_SID_IDP
        assert mock_url.call_args.args[0] == "end-session-request"
        assert mock_url.call_args.args[1] == f"{core_config.settings.ENDURAIN_HOST}/login"

    @patch("modules.auth.authentication.service.identity_providers_integration.end_session_url")
    @patch("modules.auth.authentication.service.identity_providers_integration.read_end_session")
    @patch("modules.auth.authentication.service.sessions_integration.delete_session")
    @patch("modules.auth.authentication.service.sessions_integration.get_session_by_id_not_expired")
    def test_logout_of_a_mobile_idp_session_asks_for_a_url_without_a_return_address(
        self,
        mock_get_session,
        mock_delete_session,
        mock_read,
        mock_url,
        auth_client,
        auth_app,
        password_hasher,
    ):
        auth_app.state._client_type = "mobile"
        mock_get_session.return_value = self._signed_in_session(auth_app, password_hasher)
        mock_read.return_value = "end-session-request"
        mock_url.return_value = "https://idp.example.com/out"

        response = auth_client.post("/auth/logout")

        assert response.json() == {"idp_logout_url": "https://idp.example.com/out"}
        assert mock_url.call_args.args[1] is None

    @patch("modules.auth.authentication.service.identity_providers_integration.end_session_url")
    @patch("modules.auth.authentication.service.identity_providers_integration.read_end_session")
    @patch("modules.auth.authentication.service.sessions_integration.get_session_by_id_not_expired")
    def test_logout_of_a_missing_session_asks_no_provider(
        self, mock_get_session, mock_read, mock_url, auth_client, auth_app
    ):
        mock_get_session.return_value = None
        auth_app.dependency_overrides[authentication_dependencies.get_logout_target] = lambda: (
            authentication_dependencies.LogoutTarget(MOCK_USER_ID, uuid.uuid4(), "rt")
        )

        response = auth_client.post("/auth/logout")

        assert response.json() == {"idp_logout_url": None}
        mock_read.assert_not_called()
        mock_url.assert_not_called()

    # --- idempotent logout: a token problem answers the normal success and ends nothing ---

    @staticmethod
    def _refresh_token(token_manager, sample_user_read, *, ttl=timedelta(days=1)):
        return token_manager.create_token(
            _SID_SID_1,
            sample_user_read,
            auth_constants.ClientType.WEB,
            auth_token_manager.TokenType.REFRESH,
            ttl,
        )[1]

    @staticmethod
    def _cookie_is_cleared(response) -> bool:
        cleared = [
            value
            for value in response.headers.get_list("set-cookie")
            if value.startswith(f"{authentication_dependencies.REFRESH_TOKEN_COOKIE_NAME}=")
        ]
        return len(cleared) == 1 and "Max-Age=0" in cleared[0]

    @pytest.mark.parametrize("problem", ["missing", "malformed", "expired", "wrong_audience"])
    @patch("modules.auth.authentication.service.sessions_integration.delete_session")
    @patch("modules.auth.authentication.service.sessions_integration.get_session_by_id_not_expired")
    def test_web_logout_with_an_unusable_token_succeeds_and_clears_the_cookie(
        self, mock_get_session, mock_delete_session, problem, auth_client, token_manager, sample_user_read
    ):
        tokens = {
            "missing": None,
            "malformed": "not-a-jwt",
            "expired": self._refresh_token(token_manager, sample_user_read, ttl=timedelta(seconds=-120)),
            "wrong_audience": token_manager.create_token(
                _SID_SID_1,
                sample_user_read,
                auth_constants.ClientType.WEB,
                auth_token_manager.TokenType.ACCESS,
                timedelta(days=1),
            )[1],
        }
        headers = {}
        if tokens[problem] is not None:
            headers["Cookie"] = f"{authentication_dependencies.REFRESH_TOKEN_COOKIE_NAME}={tokens[problem]}"

        response = auth_client.post("/auth/logout", headers=headers)

        assert response.status_code == 200
        assert response.json() == {"idp_logout_url": None}
        assert response.headers["cache-control"] == "no-store"
        assert self._cookie_is_cleared(response)
        mock_get_session.assert_not_called()
        mock_delete_session.assert_not_called()

    @patch("modules.auth.authentication.service.sessions_integration.delete_session")
    @patch("modules.auth.authentication.service.sessions_integration.get_session_by_id_not_expired")
    def test_web_logout_of_a_revoked_token_succeeds_and_clears_the_cookie(
        self, mock_get_session, mock_delete_session, auth_client, token_manager, sample_user_read, password_hasher
    ):
        session = MagicMock(id=_SID_SID_1, refresh_token=password_hasher.hash_password("a-newer-token"))
        mock_get_session.return_value = session
        token = self._refresh_token(token_manager, sample_user_read)

        response = auth_client.post(
            "/auth/logout", headers={"Cookie": f"{authentication_dependencies.REFRESH_TOKEN_COOKIE_NAME}={token}"}
        )

        assert response.status_code == 200
        assert response.json() == {"idp_logout_url": None}
        assert self._cookie_is_cleared(response)
        mock_delete_session.assert_not_called()

    @pytest.mark.parametrize("authorization", [None, "Bearer not-a-jwt"])
    @patch("modules.auth.authentication.service.sessions_integration.delete_session")
    def test_mobile_logout_with_an_unusable_token_succeeds(
        self, mock_delete_session, authorization, auth_client, auth_app
    ):
        auth_app.state._client_type = "mobile"
        headers = {"Authorization": authorization} if authorization else {}

        response = auth_client.post("/auth/logout", headers=headers)

        assert response.status_code == 200
        assert response.json() == {"idp_logout_url": None}
        assert response.headers["cache-control"] == "no-store"
        assert not response.headers.get_list("set-cookie")
        mock_delete_session.assert_not_called()

    @patch("modules.auth.authentication.service.sessions_integration.delete_session")
    @patch("modules.auth.authentication.service.sessions_integration.get_session_by_id_not_expired")
    def test_mobile_logout_reads_the_refresh_token_from_the_body(
        self,
        mock_get_session,
        mock_delete_session,
        auth_client,
        auth_app,
        token_manager,
        sample_user_read,
        password_hasher,
    ):
        auth_app.state._client_type = "mobile"
        auth_app.dependency_overrides[access_tokens_integration.get_token_manager] = lambda: token_manager
        token = self._mobile_refresh_token(token_manager, sample_user_read)
        mock_get_session.return_value = MagicMock(id=_SID_SID_1, refresh_token=password_hasher.hash_password(token))

        response = auth_client.post("/auth/logout", json={"refresh_token": token})

        assert response.status_code == 200
        mock_delete_session.assert_called_once()

    @patch("modules.auth.authentication.service.sessions_integration.delete_session")
    def test_mobile_logout_ignores_a_refresh_token_in_the_authorization_header(
        self, mock_delete_session, auth_client, auth_app, token_manager, sample_user_read
    ):
        auth_app.state._client_type = "mobile"
        auth_app.dependency_overrides[access_tokens_integration.get_token_manager] = lambda: token_manager
        token = self._mobile_refresh_token(token_manager, sample_user_read)

        response = auth_client.post("/auth/logout", headers={"Authorization": f"Bearer {token}"})

        assert response.status_code == 200
        assert response.json() == {"idp_logout_url": None}
        mock_delete_session.assert_not_called()

    @patch("modules.auth.authentication.service.sessions_integration.delete_session")
    def test_mobile_logout_with_an_unusable_body_token_succeeds(self, mock_delete_session, auth_client, auth_app):
        auth_app.state._client_type = "mobile"

        response = auth_client.post("/auth/logout", json={"refresh_token": "not-a-jwt"})

        assert response.status_code == 200
        assert response.json() == {"idp_logout_url": None}
        mock_delete_session.assert_not_called()

    @patch("modules.auth.authentication.service.sessions_integration.delete_session")
    def test_web_logout_does_not_use_a_body_token(
        self, mock_delete_session, auth_client, token_manager, sample_user_read
    ):
        token = self._refresh_token(token_manager, sample_user_read)

        response = auth_client.post("/auth/logout", json={"refresh_token": token})

        assert response.status_code == 200
        assert response.json() == {"idp_logout_url": None}
        assert self._cookie_is_cleared(response)
        mock_delete_session.assert_not_called()

    def test_logout_refuses_an_unknown_body_member(self, auth_client, auth_app):
        auth_app.state._client_type = "mobile"

        response = auth_client.post("/auth/logout", json={"refresh_token": "x", "extra": 1})

        assert response.status_code == 422

    @staticmethod
    def _mobile_refresh_token(token_manager, sample_user_read):
        return token_manager.create_token(
            _SID_SID_1,
            sample_user_read,
            auth_constants.ClientType.MOBILE,
            auth_token_manager.TokenType.REFRESH,
            timedelta(days=1),
        )[1]


# ------------------------------------------------------------------
# POST /auth/refresh: where each client type sends its refresh token
# ------------------------------------------------------------------


class TestRefreshTokenSource:
    """A mobile client sends its refresh token in the body; a web client only ever uses its cookie."""

    @staticmethod
    def _token(token_manager, sample_user_read, client_type):
        return token_manager.create_token(
            _SID_SID_1, sample_user_read, client_type, auth_token_manager.TokenType.REFRESH, timedelta(days=1)
        )[1]

    def test_mobile_refresh_without_a_body_token_is_refused_as_a_missing_token(self, auth_client, auth_app):
        auth_app.state._client_type = "mobile"

        response = auth_client.post("/auth/refresh")

        assert response.status_code == 401
        assert response.json()["type"] == "urn:endurain:error:invalid-token"
        assert response.json()["detail"] == "Refresh token missing from request body"

    def test_mobile_refresh_ignores_a_refresh_token_in_the_authorization_header(
        self, auth_client, auth_app, token_manager, sample_user_read
    ):
        auth_app.state._client_type = "mobile"
        token = self._token(token_manager, sample_user_read, auth_constants.ClientType.MOBILE)

        response = auth_client.post("/auth/refresh", headers={"Authorization": f"Bearer {token}"})

        assert response.status_code == 401
        assert response.json()["detail"] == "Refresh token missing from request body"

    def test_mobile_refresh_reads_the_token_from_the_body(self, auth_client, auth_app, token_manager, sample_user_read):
        auth_app.state._client_type = "mobile"
        auth_app.dependency_overrides[access_tokens_integration.get_token_manager] = lambda: token_manager
        token = self._token(token_manager, sample_user_read, auth_constants.ClientType.MOBILE)

        with patch(
            "modules.auth.authentication.public_router.auth_refresh_service.refresh_token",
            side_effect=core_exceptions.InvalidTokenError("stop here"),
        ) as refresh:
            auth_client.post("/auth/refresh", json={"refresh_token": token})

        assert refresh.call_args.args[4] == token

    def test_web_refresh_does_not_use_a_body_token(self, auth_client, token_manager, sample_user_read):
        token = self._token(token_manager, sample_user_read, auth_constants.ClientType.MOBILE)

        response = auth_client.post("/auth/refresh", json={"refresh_token": token})

        assert response.status_code == 401
        assert response.json()["detail"] == "Refresh token missing from cookie"
