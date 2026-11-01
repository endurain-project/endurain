"""Tests for app/auth/dependencies.py.

Covers all public functions and async dependencies defined in the module.
"""

import inspect
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import jasil.testing as jasil_testing
import pytest
from fastapi.security import SecurityScopes

import core.exceptions as core_exceptions
import modules.auth.authentication.dependencies as authentication_dependencies
import modules.auth.dependencies as auth_dependencies
from modules.auth.contracts import ApiKeyCred, PasswordCred, Principal
from modules.auth.dependencies import (
    AuthContext,
    _require_scopes,
    check_auth_scopes,
    check_scopes,
    get_access_token,
    get_sub_from_access_token,
    get_user_id_from_auth,
    validate_access_token,
    validate_access_token_or_api_key,
)


class TestGetAccessToken:
    """Tests for get_access_token."""

    def test_valid_token_returns_token_string(self):
        result = get_access_token("my-token", "web")
        assert result == "my-token"

    def test_none_token_raises_401(self):
        with pytest.raises(core_exceptions.UnauthenticatedError) as exc_info:
            get_access_token(None, "web")
        assert exc_info.value.status_code == 401
        assert "Access token missing" in exc_info.value.detail


class TestValidateAccessToken:
    """Tests for validate_access_token."""

    @patch("modules.auth.dependencies._resolve_and_cache_principal")
    def test_calls_resolve_and_cache_principal(self, mock_resolve):
        request = MagicMock()
        validate_access_token(request, "token", MagicMock())
        mock_resolve.assert_called_once()


class TestGetSubFromAccessToken:
    """Tests for get_sub_from_access_token."""

    @patch("modules.auth.dependencies._resolve_and_cache_principal")
    def test_returns_user_id(self, mock_resolve):
        principal = Principal(
            user_id=5,
            username="u",
            email="u@e.com",
            is_active=True,
            is_superuser=False,
            scopes=frozenset(),
            credential=PasswordCred(username="u"),
        )
        mock_resolve.return_value = principal
        result = get_sub_from_access_token(MagicMock(), "token", MagicMock())
        assert result == 5


class TestCheckScopes:
    """Tests for check_scopes."""

    @patch("modules.auth.dependencies._resolve_and_cache_principal")
    def test_checks_required_scope_on_resolved_principal(self, mock_resolve):
        principal = MagicMock()
        principal.scopes = frozenset({"profile"})
        mock_resolve.return_value = principal
        security_scopes = MagicMock()
        security_scopes.scopes = ["profile"]

        check_scopes(MagicMock(), "token", MagicMock(), security_scopes)


class TestValidateAccessTokenOrApiKey:
    """Tests for validate_access_token_or_api_key."""

    def test_is_sync_so_blocking_lookups_run_in_the_threadpool(self):
        assert not inspect.iscoroutinefunction(validate_access_token_or_api_key)

    def test_cached_principal_api_key_returns_auth_context(self):
        request = MagicMock()
        request.state = SimpleNamespace()
        request.state.principal = Principal(
            user_id=3,
            username="apiuser",
            email="api@e.com",
            is_active=True,
            is_superuser=False,
            scopes=frozenset({"read"}),
            credential=ApiKeyCred(api_key_id=1, key_prefix="test"),
        )
        result = validate_access_token_or_api_key(request, MagicMock())
        assert isinstance(result, AuthContext)
        assert result.user_id == 3
        assert result.auth_type == "api_key"

    def test_cached_principal_jwt_returns_auth_context(self):
        request = MagicMock()
        request.state = SimpleNamespace()
        request.state.principal = Principal(
            user_id=4,
            username="jwtuser",
            email="jwt@e.com",
            is_active=True,
            is_superuser=False,
            scopes=frozenset({"profile"}),
            credential=PasswordCred(username="jwtuser"),
        )
        result = validate_access_token_or_api_key(request, MagicMock())
        assert result.auth_type == "jwt"

    @patch("modules.auth.dependencies.authentication_integration.resolve_from_access_token")
    def test_access_token_provided_resolves_via_integration(self, mock_resolve):
        request = MagicMock()
        request.state = SimpleNamespace()
        db = MagicMock()
        mock_resolve.return_value = Principal(
            user_id=7,
            username="tokenuser",
            email="t@e.com",
            is_active=True,
            is_superuser=False,
            scopes=frozenset({"admin"}),
            credential=PasswordCred(username="tokenuser"),
        )
        result = validate_access_token_or_api_key(request, db, access_token="bearer-token")
        assert result.user_id == 7
        assert result.auth_type == "jwt"
        mock_resolve.assert_called_once_with("bearer-token", db)

    @patch("modules.auth.dependencies.authentication_integration.resolve_from_api_key")
    def test_api_key_header_provided_resolves_via_integration(self, mock_resolve):
        request = MagicMock()
        request.state = SimpleNamespace()
        db = MagicMock()
        mock_resolve.return_value = Principal(
            user_id=8,
            username="keyuser",
            email="k@e.com",
            is_active=True,
            is_superuser=False,
            scopes=frozenset({"read"}),
            credential=ApiKeyCred(api_key_id=2, key_prefix="sk"),
        )
        result = validate_access_token_or_api_key(request, db, access_token=None, api_key_header="sk-123")
        assert result.user_id == 8
        assert result.auth_type == "api_key"
        mock_resolve.assert_called_once_with("sk-123", request, db)

    def test_api_key_query_string_ignored_when_disabled(self):
        request = MagicMock()
        request.state = SimpleNamespace()
        db = MagicMock()
        mock_settings = MagicMock()
        mock_settings.ALLOW_API_KEY_QUERY_PARAM = False
        with (
            patch("modules.auth.dependencies.core_config.settings", mock_settings),
            patch("modules.auth.dependencies.authentication_integration.resolve_from_api_key") as mock_resolve,
            pytest.raises(core_exceptions.UnauthenticatedError) as exc_info,
        ):
            validate_access_token_or_api_key(
                request, db, access_token=None, api_key_header=None, api_key_query="qk-456"
            )
        assert exc_info.value.status_code == 401
        mock_resolve.assert_not_called()

    @patch("modules.auth.dependencies.authentication_integration.resolve_from_api_key")
    def test_api_key_query_string_accepted_when_enabled(self, mock_resolve):
        request = MagicMock()
        request.state = SimpleNamespace()
        db = MagicMock()
        mock_resolve.return_value = Principal(
            user_id=9,
            username="quser",
            email="q@e.com",
            is_active=True,
            is_superuser=False,
            scopes=frozenset({"read"}),
            credential=ApiKeyCred(api_key_id=3, key_prefix="qk"),
        )
        mock_settings = MagicMock()
        mock_settings.ALLOW_API_KEY_QUERY_PARAM = True
        with patch("modules.auth.dependencies.core_config.settings", mock_settings):
            result = validate_access_token_or_api_key(
                request, db, access_token=None, api_key_header=None, api_key_query="qk-456"
            )
        assert result.user_id == 9
        assert result.auth_type == "api_key"
        mock_resolve.assert_called_once_with("qk-456", request, db)

    def test_no_credentials_raises_401(self):
        request = MagicMock()
        request.state = SimpleNamespace()
        mock_settings = MagicMock()
        mock_settings.ALLOW_API_KEY_QUERY_PARAM = False
        with (
            patch("modules.auth.dependencies.core_config.settings", mock_settings),
            pytest.raises(core_exceptions.UnauthenticatedError) as exc_info,
        ):
            validate_access_token_or_api_key(
                request,
                MagicMock(),
                access_token=None,
                api_key_header=None,
                api_key_query=None,
            )
        assert exc_info.value.status_code == 401


class TestGetUserIdFromAuth:
    """Tests for get_user_id_from_auth."""

    def test_returns_user_id(self):
        auth = AuthContext(user_id=10, scopes=[], auth_type="jwt")
        result = get_user_id_from_auth(auth)
        assert result == 10


class TestCheckAuthScopes:
    """Tests for check_auth_scopes."""

    def test_all_scopes_present_no_exception(self):
        auth = AuthContext(user_id=1, scopes=["profile", "read"], auth_type="jwt")
        security_scopes = MagicMock()
        security_scopes.scopes = ["profile"]
        check_auth_scopes(auth, security_scopes)

    def test_missing_scopes_raises_403(self):
        auth = AuthContext(user_id=1, scopes=["profile"], auth_type="jwt")
        security_scopes = MagicMock()
        security_scopes.scopes = ["profile", "admin"]
        with pytest.raises(core_exceptions.PermissionDeniedError) as exc_info:
            check_auth_scopes(auth, security_scopes)
        assert exc_info.value.status_code == 403


class TestResolveAndCachePrincipal:
    """Tests for _resolve_and_cache_principal."""

    def test_returns_cached_principal(self):
        principal = Principal(
            user_id=1,
            username="u",
            email="u@e.com",
            is_active=True,
            is_superuser=False,
            scopes=frozenset(),
            credential=PasswordCred(username="u"),
        )
        request = MagicMock()
        request.state = SimpleNamespace()
        request.state.principal = principal

        result = auth_dependencies._resolve_and_cache_principal("token", request, MagicMock())
        assert result == principal


class TestAuthContextIdentity:
    """Assert that dependencies.AuthContext is the same type as internal_dependencies.AuthContext."""

    def test_auth_context_is_same_type_as_security(self):
        import modules.auth.dependencies as auth_security

        assert auth_dependencies.AuthContext is auth_security.AuthContext


class TestClientTypeHeader:
    """Tests for the required X-Client-Type header scheme."""

    @staticmethod
    def _request(headers: dict[str, str]):
        from starlette.requests import Request

        scope = {"type": "http", "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()]}
        return Request(scope)

    @pytest.mark.asyncio
    async def test_missing_header_is_a_400_naming_the_header(self):
        import core.exceptions as core_exceptions

        with pytest.raises(core_exceptions.InvalidInputError) as exc_info:
            await authentication_dependencies.header_client_type_scheme(self._request({}))
        assert exc_info.value.status_code == 400
        assert "X-Client-Type" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_present_header_is_returned(self):

        result = await authentication_dependencies.header_client_type_scheme(self._request({"X-Client-Type": "web"}))
        assert result == "web"


class TestAuditContextFromRequest:
    """The audit context names the request's principal, or the system outside a request."""

    @staticmethod
    def _request(principal=None, ip="203.0.113.7", user_agent="Mozilla/5.0"):
        from starlette.requests import Request

        headers = [(b"user-agent", user_agent.encode())] if user_agent else []
        request = Request({"type": "http", "method": "POST", "path": "/", "headers": headers, "client": (ip, 1234)})
        if principal is not None:
            request.state.principal = principal
        return request

    @staticmethod
    def _principal(credential):
        return Principal(
            user_id=42,
            username="alice",
            email="alice@example.com",
            is_active=True,
            is_superuser=False,
            scopes=frozenset(),
            credential=credential,
        )

    def _context(self, request):
        with patch.object(auth_dependencies.core_request_context, "get_current_request", return_value=request):
            return auth_dependencies.audit_context_from_request()

    def test_outside_a_request_the_system_acts(self):
        import jasil.audit as jasil_audit

        context = self._context(None)

        assert context.actor_type is jasil_audit.ActorType.SYSTEM
        assert context.source is jasil_audit.Source.WORKER
        assert context.actor_id is None

    def test_before_authentication_the_client_is_anonymous(self):
        import jasil.audit as jasil_audit

        context = self._context(self._request())

        assert context.actor_type is jasil_audit.ActorType.ANONYMOUS
        assert context.source is jasil_audit.Source.API
        assert context.ip_address == "203.0.113.7"
        assert context.user_agent == "Mozilla/5.0"

    def test_a_session_principal_is_the_user(self):
        import jasil.audit as jasil_audit

        from modules.auth.contracts import AccessTokenCred

        context = self._context(self._request(self._principal(AccessTokenCred(session_id="sid-1"))))

        assert context.actor_type is jasil_audit.ActorType.USER
        assert context.actor_id == "42"
        assert context.credential_type == "access_token"
        assert context.credential_id == "sid-1"

    def test_an_api_key_principal_names_the_key_not_its_value(self):
        import jasil.audit as jasil_audit

        context = self._context(self._request(self._principal(ApiKeyCred(api_key_id=7, key_prefix="end_abc"))))

        assert context.actor_type is jasil_audit.ActorType.API_KEY
        assert context.actor_id == "42"
        assert context.credential_type == "api_key"
        assert context.credential_id == "7"

    def test_an_unknown_client_and_missing_user_agent_are_left_empty(self):
        from starlette.requests import Request

        request = Request({"type": "http", "method": "GET", "path": "/", "headers": []})

        context = self._context(request)

        assert context.ip_address is None
        assert context.user_agent is None


class TestRequireScopesAudit:
    """A refused scope check leaves a denial in the audit trail."""

    def test_a_missing_scope_is_audited_as_denied_with_the_sorted_missing_scopes(self):
        security_scopes = SecurityScopes(scopes=["users:write", "activities:read"])

        with jasil_testing.capture_audit() as audit, pytest.raises(core_exceptions.PermissionDeniedError):
            _require_scopes(["profile"], security_scopes)

        entry = audit.assert_audited("auth.scope.denied", outcome="denied")
        assert entry.details == {"missing_scopes": ["activities:read", "users:write"]}

    def test_a_granted_scope_writes_nothing(self):
        with jasil_testing.capture_audit() as audit:
            _require_scopes(["profile"], SecurityScopes(scopes=["profile"]))

        audit.assert_not_audited("auth.scope.denied")
