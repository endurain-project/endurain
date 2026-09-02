"""Tests for auth.identity_service module.

Covers:
- Structural conformance: DefaultIdentityService satisfies
  the IdentityService Protocol.
- One happy-path delegation per Protocol method (using mocks).
- Request-scoped dependency returns a new instance per call.
- Round-trip per Credential variant proving the discriminated
  union encodes/decodes correctly through DefaultIdentityService.
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, Request
from sqlalchemy.exc import SQLAlchemyError

from modules.auth.identity_service import (
    DefaultIdentityService,
    IdentityService,
    get_identity_service,
)
from modules.auth.principal import (
    AccessTokenCred,
    ApiKeyCred,
    PasswordCred,
    Principal,
    SessionCookieCred,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db() -> MagicMock:
    """Return a mock SQLAlchemy session.

    Returns:
        MagicMock: Mock database session.
    """
    return MagicMock()


@pytest.fixture
def mock_token_manager() -> MagicMock:
    """Return a mock TokenManager.

    Returns:
        MagicMock: Mock token manager.
    """
    return MagicMock()


@pytest.fixture
def mock_password_hasher() -> MagicMock:
    """Return a mock PasswordHasher.

    Returns:
        MagicMock: Mock password hasher.
    """
    return MagicMock()


@pytest.fixture
def service(
    mock_db: MagicMock,
    mock_token_manager: MagicMock,
    mock_password_hasher: MagicMock,
) -> DefaultIdentityService:
    """Return a DefaultIdentityService with mocked dependencies.

    Args:
        mock_db: Mock database session.
        mock_token_manager: Mock token manager.
        mock_password_hasher: Mock password hasher.

    Returns:
        DefaultIdentityService: Service under test.
    """
    return DefaultIdentityService(
        db=mock_db,
        token_manager=mock_token_manager,
        password_hasher=mock_password_hasher,
    )


def _mock_user(
    user_id: int = 1,
    username: str = "alice",
    email: str = "alice@example.com",
    active: bool = True,
    access_type: str = "regular",
) -> MagicMock:
    """Build a minimal mock ORM user.

    Args:
        user_id: User primary key.
        username: Username string.
        email: Email address.
        active: Whether the account is active.
        access_type: ``"regular"`` or ``"admin"``.

    Returns:
        MagicMock: Mock user ORM object.
    """
    user = MagicMock()
    user.id = user_id
    user.username = username
    user.email = email
    user.active = active
    user.access_type = access_type
    return user


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    """DefaultIdentityService structurally satisfies IdentityService."""

    def test_default_service_satisfies_protocol(
        self,
        service: DefaultIdentityService,
    ):
        """isinstance check passes for the runtime_checkable Protocol."""
        assert isinstance(service, IdentityService)

    def test_protocol_has_required_methods(self):
        """IdentityService Protocol exposes all expected method names."""
        expected = {
            "authenticate_password",
            "resolve_from_access_token",
            "resolve_from_api_key",
            "resolve_from_session_cookie",
            "issue_token_pair",
            "revoke_session",
            "check_scope",
        }
        for method in expected:
            assert hasattr(IdentityService, method), f"Protocol missing method: {method}"


# ---------------------------------------------------------------------------
# authenticate_password
# ---------------------------------------------------------------------------


class TestAuthenticatePassword:
    """Tests for DefaultIdentityService.authenticate_password."""

    def test_happy_path_returns_principal_with_password_cred(
        self,
        service: DefaultIdentityService,
    ):
        """Returns a Principal with PasswordCred on success."""
        mock_user = _mock_user()

        with patch(
            "modules.auth.identity_service.auth_utils.authenticate_user",
            return_value=mock_user,
        ) as mock_auth:
            result = service.authenticate_password("alice", "secret")

        mock_auth.assert_called_once_with("alice", "secret", service._password_hasher, service._db)
        assert isinstance(result, Principal)
        assert isinstance(result.credential, PasswordCred)
        assert result.credential.username == "alice"
        assert result.user_id == 1
        assert result.username == "alice"

    def test_invalid_credentials_raises_401(
        self,
        service: DefaultIdentityService,
    ):
        """Propagates HTTPException from authenticate_user."""
        with (
            patch(
                "modules.auth.identity_service.auth_utils.authenticate_user",
                side_effect=HTTPException(status_code=401, detail="bad"),
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            service.authenticate_password("bad", "wrong")

        assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# resolve_from_access_token
# ---------------------------------------------------------------------------


class TestResolveFromAccessToken:
    """Tests for DefaultIdentityService.resolve_from_access_token."""

    def test_happy_path_returns_principal_with_access_token_cred(
        self,
        service: DefaultIdentityService,
        mock_token_manager: MagicMock,
        mock_db: MagicMock,
    ):
        """Returns a Principal with AccessTokenCred on valid token."""
        mock_user = _mock_user()

        mock_token_manager.get_token_claim.side_effect = lambda token, claim: {
            "sub": 1,
            "scope": ["profile", "users:read"],
            "sid": "sid-abc",
        }[claim]

        with (
            patch(
                "modules.auth.identity_service.users_utils.get_user_by_id_or_404",
                return_value=mock_user,
            ),
            patch("modules.auth.identity_service.users_utils.check_user_is_active"),
        ):
            result = service.resolve_from_access_token("token123")

        assert isinstance(result, Principal)
        assert isinstance(result.credential, AccessTokenCred)
        assert result.credential.session_id == "sid-abc"
        assert "profile" in result.scopes
        assert result.user_id == 1

    def test_expired_token_raises_401(
        self,
        service: DefaultIdentityService,
        mock_token_manager: MagicMock,
    ):
        """Propagates HTTPException from validate_access_expiration_logged."""
        mock_token_manager.validate_access_expiration_logged.side_effect = HTTPException(
            status_code=401, detail="expired"
        )
        with pytest.raises(HTTPException) as exc_info:
            service.resolve_from_access_token("expired_token")

        assert exc_info.value.status_code == 401

    def test_non_integer_sub_raises_401(
        self,
        service: DefaultIdentityService,
        mock_token_manager: MagicMock,
    ):
        """Raises 401 when 'sub' claim is not an integer."""
        mock_token_manager.get_token_claim.return_value = "not-an-int"
        with pytest.raises(HTTPException) as exc_info:
            service.resolve_from_access_token("bad_token")

        assert exc_info.value.status_code == 401

    def test_non_list_scope_claim_raises_401(
        self,
        service: DefaultIdentityService,
        mock_token_manager: MagicMock,
    ):
        """Raises 401 when 'scope' claim is not a list."""
        mock_token_manager.get_token_claim.side_effect = lambda token, claim: {
            "sub": "1",
            "scope": "not-a-list",
        }[claim]
        with pytest.raises(HTTPException) as exc_info:
            service.resolve_from_access_token("bad_token")

        assert exc_info.value.status_code == 401

    def test_non_string_sid_claim_raises_401(
        self,
        service: DefaultIdentityService,
        mock_token_manager: MagicMock,
    ):
        """Raises 401 when 'sid' claim is not a string."""
        mock_token_manager.get_token_claim.side_effect = lambda token, claim: {
            "sub": "1",
            "scope": ["profile"],
            "sid": 99,
        }[claim]
        with pytest.raises(HTTPException) as exc_info:
            service.resolve_from_access_token("bad_token")

        assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# resolve_from_api_key
# ---------------------------------------------------------------------------


class TestResolveFromApiKey:
    """Tests for DefaultIdentityService.resolve_from_api_key."""

    def test_happy_path_returns_principal_with_api_key_cred(
        self,
        service: DefaultIdentityService,
    ):
        """Returns a Principal with ApiKeyCred on a valid key."""
        mock_db_key = MagicMock()
        mock_db_key.key_hash = "a" * 64
        mock_db_key.user_id = 1
        mock_db_key.is_active = True
        mock_db_key.expires_at = None
        mock_db_key.id = "key-uuid-1"
        mock_db_key.key_prefix = "endurain"
        mock_db_key.scopes = '["profile"]'

        mock_user = _mock_user()
        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/api/v1/activities"
        mock_request.client.host = "127.0.0.1"

        with (
            patch(
                "modules.auth.identity_service.auth_api_keys_utils.hash_api_key",
                return_value="a" * 64,
            ),
            patch(
                "modules.auth.identity_service.auth_api_keys_crud.get_api_key_by_hash",
                return_value=mock_db_key,
            ),
            patch(
                "modules.auth.identity_service.users_utils.get_user_by_id_or_404",
                return_value=mock_user,
            ),
            patch("modules.auth.identity_service.users_utils.check_user_is_active"),
            patch("modules.auth.identity_service.auth_api_keys_crud.update_last_used"),
            patch(
                "modules.auth.identity_service.auth_api_keys_utils.json_to_scopes",
                return_value=["profile"],
            ),
        ):
            result = service.resolve_from_api_key("endurain_raw_key", mock_request)

        assert isinstance(result, Principal)
        assert isinstance(result.credential, ApiKeyCred)
        assert result.credential.api_key_id == "key-uuid-1"
        assert result.credential.key_prefix == "endurain"
        assert result.is_api_key() is True

    def test_invalid_key_raises_401(
        self,
        service: DefaultIdentityService,
    ):
        """Raises 401 when the key is not found in the database."""
        mock_request = MagicMock(spec=Request)

        with (
            patch(
                "modules.auth.identity_service.auth_api_keys_utils.hash_api_key",
                return_value="b" * 64,
            ),
            patch(
                "modules.auth.identity_service.auth_api_keys_crud.get_api_key_by_hash",
                return_value=None,
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            service.resolve_from_api_key("invalid_key", mock_request)

        assert exc_info.value.status_code == 401

    def test_revoked_key_raises_401(
        self,
        service: DefaultIdentityService,
    ):
        """Raises 401 when the key is revoked (is_active=False)."""
        mock_db_key = MagicMock()
        mock_db_key.key_hash = "c" * 64
        mock_db_key.user_id = 1
        mock_db_key.is_active = False
        mock_db_key.expires_at = None

        mock_request = MagicMock(spec=Request)

        with (
            patch(
                "modules.auth.identity_service.auth_api_keys_utils.hash_api_key",
                return_value="c" * 64,
            ),
            patch(
                "modules.auth.identity_service.auth_api_keys_crud.get_api_key_by_hash",
                return_value=mock_db_key,
            ),
            patch(
                "modules.auth.identity_service.users_utils.get_user_by_id_or_404",
                return_value=_mock_user(),
            ),
            patch("modules.auth.identity_service.users_utils.check_user_is_active"),
            pytest.raises(HTTPException) as exc_info,
        ):
            service.resolve_from_api_key("revoked", mock_request)

        assert exc_info.value.status_code == 401

    def test_expired_key_raises_401(
        self,
        service: DefaultIdentityService,
    ):
        """Raises 401 when the API key has expired."""
        mock_db_key = MagicMock()
        mock_db_key.key_hash = "d" * 64
        mock_db_key.user_id = 1
        mock_db_key.is_active = True
        mock_db_key.expires_at = datetime(2020, 1, 1, tzinfo=UTC)

        mock_request = MagicMock(spec=Request)

        with (
            patch(
                "modules.auth.identity_service.auth_api_keys_utils.hash_api_key",
                return_value="d" * 64,
            ),
            patch(
                "modules.auth.identity_service.auth_api_keys_crud.get_api_key_by_hash",
                return_value=mock_db_key,
            ),
            patch(
                "modules.auth.identity_service.users_utils.get_user_by_id_or_404",
                return_value=_mock_user(),
            ),
            patch("modules.auth.identity_service.users_utils.check_user_is_active"),
            pytest.raises(HTTPException) as exc_info,
        ):
            service.resolve_from_api_key("expired_key", mock_request)

        assert exc_info.value.status_code == 401

    def test_update_last_used_error_does_not_fail_request(
        self,
        service: DefaultIdentityService,
    ):
        """SQLAlchemyError in update_last_used is swallowed; succeeds."""
        mock_db_key = MagicMock()
        mock_db_key.key_hash = "e" * 64
        mock_db_key.user_id = 1
        mock_db_key.is_active = True
        mock_db_key.expires_at = None
        mock_db_key.id = "key-uuid-2"
        mock_db_key.key_prefix = "endurain"
        mock_db_key.scopes = '["profile"]'

        mock_user = _mock_user()
        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/api/v1/health"
        mock_request.client.host = "10.0.0.1"

        with (
            patch(
                "modules.auth.identity_service.auth_api_keys_utils.hash_api_key",
                return_value="e" * 64,
            ),
            patch(
                "modules.auth.identity_service.auth_api_keys_crud.get_api_key_by_hash",
                return_value=mock_db_key,
            ),
            patch(
                "modules.auth.identity_service.users_utils.get_user_by_id_or_404",
                return_value=mock_user,
            ),
            patch("modules.auth.identity_service.users_utils.check_user_is_active"),
            patch(
                "modules.auth.identity_service.auth_api_keys_crud.update_last_used",
                side_effect=SQLAlchemyError("db down"),
            ),
            patch(
                "modules.auth.identity_service.auth_api_keys_utils.json_to_scopes",
                return_value=["profile"],
            ),
        ):
            result = service.resolve_from_api_key("endurain_raw_key2", mock_request)

        assert isinstance(result, Principal)
        assert result.is_api_key() is True


# ---------------------------------------------------------------------------
# resolve_from_session_cookie
# ---------------------------------------------------------------------------


class TestResolveFromSessionCookie:
    """Tests for DefaultIdentityService.resolve_from_session_cookie."""

    def test_happy_path_returns_principal_with_session_cookie_cred(
        self,
        service: DefaultIdentityService,
    ):
        """Returns a Principal with SessionCookieCred on valid session."""
        mock_session = MagicMock()
        mock_session.user_id = 1
        mock_user = _mock_user()

        with (
            patch(
                "modules.auth.identity_service.auth_sessions_crud.get_session_by_id_not_expired",
                return_value=mock_session,
            ),
            patch(
                "modules.auth.identity_service.users_utils.get_user_by_id_or_404",
                return_value=mock_user,
            ),
            patch("modules.auth.identity_service.users_utils.check_user_is_active"),
        ):
            result = service.resolve_from_session_cookie("sess-abc")

        assert isinstance(result, Principal)
        assert isinstance(result.credential, SessionCookieCred)
        assert result.credential.session_id == "sess-abc"

    def test_expired_session_raises_401(
        self,
        service: DefaultIdentityService,
    ):
        """Raises 401 when the session is not found or expired."""
        with (
            patch(
                "modules.auth.identity_service.auth_sessions_crud.get_session_by_id_not_expired",
                return_value=None,
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            service.resolve_from_session_cookie("old-sess")

        assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# issue_token_pair
# ---------------------------------------------------------------------------


class TestIssueTokenPair:
    """Tests for DefaultIdentityService.issue_token_pair."""

    def test_delegates_to_create_tokens(
        self,
        service: DefaultIdentityService,
    ):
        """Delegates to auth_utils.create_tokens with correct args."""
        mock_user = MagicMock()
        expected = (
            "sid-1",
            datetime.now(UTC),
            "access_token",
            datetime.now(UTC),
            "refresh_token",
            "csrf",
        )

        with patch(
            "modules.auth.identity_service.auth_utils.create_tokens",
            return_value=expected,
        ) as mock_create:
            result = service.issue_token_pair(mock_user, session_id="sid-1")

        mock_create.assert_called_once_with(mock_user, service._token_manager, "sid-1")
        assert result == expected

    def test_delegates_without_session_id_passes_none(
        self,
        service: DefaultIdentityService,
    ):
        """Passes None as session_id when the argument is omitted."""
        mock_user = MagicMock()
        expected = (
            "new-sid",
            datetime.now(UTC),
            "access_token",
            datetime.now(UTC),
            "refresh_token",
            "csrf",
        )

        with patch(
            "modules.auth.identity_service.auth_utils.create_tokens",
            return_value=expected,
        ) as mock_create:
            result = service.issue_token_pair(mock_user)

        mock_create.assert_called_once_with(mock_user, service._token_manager, None)
        assert result == expected


# ---------------------------------------------------------------------------
# revoke_session
# ---------------------------------------------------------------------------


class TestRevokeSession:
    """Tests for DefaultIdentityService.revoke_session."""

    def test_delegates_to_delete_session(
        self,
        service: DefaultIdentityService,
    ):
        """Delegates to auth_sessions_crud.delete_session."""
        with patch("modules.auth.identity_service.auth_sessions_crud.delete_session") as mock_delete:
            service.revoke_session("sess-1", user_id=42)

        mock_delete.assert_called_once_with("sess-1", 42, service._db)

    def test_propagates_404_from_crud(
        self,
        service: DefaultIdentityService,
    ):
        """Propagates HTTPException(404) raised by delete_session."""
        with (
            patch(
                "modules.auth.identity_service.auth_sessions_crud.delete_session",
                side_effect=HTTPException(status_code=404, detail="not found"),
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            service.revoke_session("missing-sess", user_id=1)

        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# check_scope
# ---------------------------------------------------------------------------


class TestCheckScope:
    """Tests for DefaultIdentityService.check_scope."""

    def _principal(self, scopes: frozenset[str]) -> Principal:
        """Build a principal with given scopes.

        Args:
            scopes: frozenset of scope strings.

        Returns:
            Principal: Principal with the given scopes.
        """
        return Principal(
            user_id=1,
            username="u",
            email="u@e.com",
            is_active=True,
            is_superuser=False,
            scopes=scopes,
            credential=PasswordCred(username="u"),
        )

    def test_passes_when_scopes_satisfied(
        self,
        service: DefaultIdentityService,
    ):
        """No exception when principal has all required scopes."""
        p = self._principal(frozenset({"profile", "users:read"}))
        service.check_scope(p, frozenset({"profile"}))

    def test_raises_403_when_scope_missing(
        self,
        service: DefaultIdentityService,
    ):
        """Raises 403 when a required scope is absent."""
        p = self._principal(frozenset({"profile"}))
        with pytest.raises(HTTPException) as exc_info:
            service.check_scope(p, frozenset({"users:write"}))

        assert exc_info.value.status_code == 403

    def test_passes_with_empty_required_scopes(
        self,
        service: DefaultIdentityService,
    ):
        """No exception when required_scopes is empty."""
        p = self._principal(frozenset())
        service.check_scope(p, frozenset())

    def test_multiple_required_scopes_partial_miss_raises_403(
        self,
        service: DefaultIdentityService,
    ):
        """Raises 403 when principal satisfies some but not all scopes."""
        p = self._principal(frozenset({"profile", "users:read"}))
        with pytest.raises(HTTPException) as exc_info:
            service.check_scope(
                p,
                frozenset({"profile", "users:read", "users:write"}),
            )

        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# get_identity_service FastAPI dependency
# ---------------------------------------------------------------------------


class TestGetIdentityServiceDependency:
    """Tests for the get_identity_service FastAPI dependency."""

    def test_returns_new_instance_per_call(self):
        """Each call returns a distinct DefaultIdentityService."""
        db1 = MagicMock()
        db2 = MagicMock()
        tm = MagicMock()
        ph = MagicMock()

        svc1 = get_identity_service(db=db1, token_manager=tm, password_hasher=ph)
        svc2 = get_identity_service(db=db2, token_manager=tm, password_hasher=ph)

        assert svc1 is not svc2

    def test_returns_default_identity_service_instance(self):
        """Returns a DefaultIdentityService (satisfies Protocol)."""
        svc = get_identity_service(
            db=MagicMock(),
            token_manager=MagicMock(),
            password_hasher=MagicMock(),
        )
        assert isinstance(svc, DefaultIdentityService)
        assert isinstance(svc, IdentityService)


# ---------------------------------------------------------------------------
# validate_and_hash_password
# ---------------------------------------------------------------------------


class TestValidateAndHashPassword:
    """Tests for DefaultIdentityService.validate_and_hash_password."""

    def test_happy_path_validates_and_hashes(self, service, mock_password_hasher):
        mock_password_hasher.validate_password.return_value = None
        mock_password_hasher.hash_password.return_value = "$argon2id$hash"
        result = service.validate_and_hash_password("validPass1!", 8, "standard")
        mock_password_hasher.validate_password.assert_called_once_with("validPass1!", 8, "standard")
        mock_password_hasher.hash_password.assert_called_once_with("validPass1!")
        assert result == "$argon2id$hash"

    def test_password_policy_error_raises_400(self, service, mock_password_hasher):
        from modules.auth._internal.password_hasher import PasswordPolicyError

        mock_password_hasher.validate_password.side_effect = PasswordPolicyError("Too short")
        with pytest.raises(HTTPException) as exc_info:
            service.validate_and_hash_password("short", 12, "standard")
        assert exc_info.value.status_code == 400
        assert "Too short" in str(exc_info.value.detail)


# ---------------------------------------------------------------------------
# hash_password
# ---------------------------------------------------------------------------


class TestHashPassword:
    """Tests for DefaultIdentityService.hash_password."""

    def test_delegates_to_password_hasher(self, service, mock_password_hasher):
        mock_password_hasher.hash_password.return_value = "$argon2id$abc"
        result = service.hash_password("secret123")
        mock_password_hasher.hash_password.assert_called_once_with("secret123")
        assert result == "$argon2id$abc"


# ---------------------------------------------------------------------------
# verify_password
# ---------------------------------------------------------------------------


class TestVerifyPassword:
    """Tests for DefaultIdentityService.verify_password."""

    def test_delegates_to_password_hasher(self, service, mock_password_hasher):
        mock_password_hasher.verify_password.return_value = True
        result = service.verify_password("pass", "$argon2id$hash")
        mock_password_hasher.verify_password.assert_called_once_with("pass", "$argon2id$hash")
        assert result is True


# ---------------------------------------------------------------------------
# local credential accessors
# ---------------------------------------------------------------------------


class TestGetPasswordHash:
    """Tests for DefaultIdentityService.get_password_hash."""

    def test_returns_hash_when_credential_exists(self, service, mock_db):
        credential = MagicMock()
        credential.password_hash = "$argon2id$abc"
        with patch(
            "modules.auth.identity_service.auth_credentials_crud.get_credential",
            return_value=credential,
        ) as get_credential:
            result = service.get_password_hash(42)
        get_credential.assert_called_once_with(42, mock_db)
        assert result == "$argon2id$abc"

    def test_returns_none_when_no_credential(self, service, mock_db):
        with patch(
            "modules.auth.identity_service.auth_credentials_crud.get_credential",
            return_value=None,
        ) as get_credential:
            result = service.get_password_hash(42)
        get_credential.assert_called_once_with(42, mock_db)
        assert result is None


class TestSetLocalPasswordHash:
    """Tests for DefaultIdentityService.set_local_password_hash."""

    def test_delegates_to_crud(self, service, mock_db):
        with patch(
            "modules.auth.identity_service.auth_credentials_crud.upsert_password_hash",
        ) as upsert:
            service.set_local_password_hash(42, "$argon2id$abc")
        upsert.assert_called_once_with(42, "$argon2id$abc", mock_db)


class TestClearLocalPassword:
    """Tests for DefaultIdentityService.clear_local_password."""

    def test_delegates_to_crud(self, service, mock_db):
        with patch(
            "modules.auth.identity_service.auth_credentials_crud.delete_credential",
        ) as delete_credential:
            service.clear_local_password(42)
        delete_credential.assert_called_once_with(42, mock_db)
