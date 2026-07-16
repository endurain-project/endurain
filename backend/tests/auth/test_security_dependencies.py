"""Regression tests for security dependencies via IdentityService.

Covers:
- JWT happy path via get_sub_from_access_token.
- API key happy path via validate_access_token_or_api_key.
- Session cookie (AccessTokenCred.session_id) via get_sid_from_access_token.
- request.state.principal cache hit: second dependency call within
  the same request does not trigger a second IdentityService call.
- No-credential 401 from validate_access_token_or_api_key.
- check_auth_scopes happy path and missing-scope 403.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, Request, status
from fastapi.security import SecurityScopes

import modules.auth._internal.internal_dependencies as auth_security
import modules.auth.dependencies as auth_dependencies
from modules.auth.identity_service import IdentityService
from modules.auth.principal import AccessTokenCred, ApiKeyCred, Principal

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_principal(
    user_id: int = 1,
    username: str = "alice",
    email: str = "alice@example.com",
    scopes: frozenset[str] | None = None,
    credential=None,
) -> Principal:
    """Build a minimal test Principal.

    Args:
        user_id: User primary key.
        username: Username string.
        email: Email address.
        scopes: Granted scopes.
        credential: Credential variant.

    Returns:
        Principal: Frozen principal for tests.
    """
    return Principal(
        user_id=user_id,
        username=username,
        email=email,
        is_active=True,
        is_superuser=False,
        scopes=(scopes if scopes is not None else frozenset(["profile"])),
        credential=(credential if credential is not None else AccessTokenCred(session_id="sid-abc")),
    )


def _fresh_request() -> MagicMock:
    """Return a mock Request with an empty state namespace.

    Returns:
        MagicMock: Mock HTTP request.
    """
    req = MagicMock(spec=Request)
    req.state = SimpleNamespace()
    req.client = MagicMock()
    req.client.host = "127.0.0.1"
    req.url = MagicMock()
    req.url.path = "/test"
    return req


# ---------------------------------------------------------------------------
# _resolve_and_cache_principal
# ---------------------------------------------------------------------------


class TestResolvePrincipalCaching:
    """Test the internal caching helper directly."""

    def test_cache_miss_calls_identity_service(self):
        """Cache miss: IdentityService is called once."""
        request = _fresh_request()
        principal = _make_principal()
        mock_svc = MagicMock(spec=IdentityService)
        mock_svc.resolve_from_access_token.return_value = principal

        result = auth_security._resolve_and_cache_principal("tok", request, mock_svc)

        assert result is principal
        assert request.state.principal is principal
        mock_svc.resolve_from_access_token.assert_called_once_with("tok")

    def test_cache_hit_skips_identity_service(self):
        """Cache hit: IdentityService is NOT called a second time."""
        request = _fresh_request()
        principal = _make_principal()
        request.state.principal = principal  # pre-populate cache
        mock_svc = MagicMock(spec=IdentityService)

        result = auth_security._resolve_and_cache_principal("tok", request, mock_svc)

        assert result is principal
        mock_svc.resolve_from_access_token.assert_not_called()

    def test_service_failure_propagates(self):
        """IdentityService 401 is not swallowed."""
        request = _fresh_request()
        mock_svc = MagicMock(spec=IdentityService)
        mock_svc.resolve_from_access_token.side_effect = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="expired",
        )

        with pytest.raises(HTTPException) as exc:
            auth_security._resolve_and_cache_principal("bad", request, mock_svc)
        assert exc.value.status_code == 401
        assert not hasattr(request.state, "principal")


# ---------------------------------------------------------------------------
# get_sub_from_access_token — JWT happy and failure paths
# ---------------------------------------------------------------------------


class TestGetSubFromAccessTokenDependency:
    """JWT user-ID extraction via IdentityService."""

    def test_jwt_happy_path(self):
        """Valid JWT returns user_id and caches Principal."""
        request = _fresh_request()
        principal = _make_principal(user_id=42)
        mock_svc = MagicMock(spec=IdentityService)
        mock_svc.resolve_from_access_token.return_value = principal

        result = auth_security.get_sub_from_access_token(request, "valid_jwt", mock_svc)

        assert result == 42
        assert request.state.principal is principal

    def test_jwt_invalid_raises_401(self):
        """Invalid token propagates 401."""
        request = _fresh_request()
        mock_svc = MagicMock(spec=IdentityService)
        mock_svc.resolve_from_access_token.side_effect = HTTPException(status_code=401, detail="Token expired")

        with pytest.raises(HTTPException) as exc:
            auth_security.get_sub_from_access_token(request, "bad.token", mock_svc)
        assert exc.value.status_code == 401

    def test_cache_hit_no_extra_db_roundtrip(self):
        """Second call within the same request hits cache."""
        request = _fresh_request()
        principal = _make_principal(user_id=7)
        mock_svc = MagicMock(spec=IdentityService)
        mock_svc.resolve_from_access_token.return_value = principal

        first = auth_security.get_sub_from_access_token(request, "tok", mock_svc)
        second = auth_security.get_sub_from_access_token(request, "tok", mock_svc)

        assert first == second == 7
        mock_svc.resolve_from_access_token.assert_called_once()


# ---------------------------------------------------------------------------
# get_sid_from_access_token — session-cookie (sid) extraction
# ---------------------------------------------------------------------------


class TestGetSidFromAccessTokenDependency:
    """Session ID extraction via IdentityService."""

    def test_session_cookie_happy_path(self):
        """Valid JWT with AccessTokenCred returns session_id."""
        request = _fresh_request()
        principal = _make_principal(credential=AccessTokenCred(session_id="sess-xyz"))
        mock_svc = MagicMock(spec=IdentityService)
        mock_svc.resolve_from_access_token.return_value = principal

        sid = auth_security.get_sid_from_access_token(request, "tok", mock_svc)

        assert sid == "sess-xyz"

    def test_wrong_credential_type_raises_401(self):
        """Principal with non-AccessTokenCred raises 401."""
        request = _fresh_request()
        principal = _make_principal(credential=ApiKeyCred(api_key_id=1, key_prefix="key_"))
        mock_svc = MagicMock(spec=IdentityService)
        mock_svc.resolve_from_access_token.return_value = principal

        with pytest.raises(HTTPException) as exc:
            auth_security.get_sid_from_access_token(request, "tok", mock_svc)
        assert exc.value.status_code == 401
        assert "credential type" in exc.value.detail

    def test_cache_shared_between_sub_and_sid_calls(self):
        """Sub and SID deps share the same cached Principal."""
        request = _fresh_request()
        principal = _make_principal(
            user_id=3,
            credential=AccessTokenCred(session_id="shared-sid"),
        )
        mock_svc = MagicMock(spec=IdentityService)
        mock_svc.resolve_from_access_token.return_value = principal

        sub = auth_security.get_sub_from_access_token(request, "tok", mock_svc)
        sid = auth_security.get_sid_from_access_token(request, "tok", mock_svc)

        assert sub == 3
        assert sid == "shared-sid"
        # Only one DB call across both deps
        mock_svc.resolve_from_access_token.assert_called_once()


# ---------------------------------------------------------------------------
# validate_access_token_or_api_key — unified auth
# ---------------------------------------------------------------------------


class TestValidateAccessTokenOrApiKey:
    """Unified JWT / API-key auth dependency."""

    @pytest.mark.asyncio
    async def test_jwt_path_happy(self):
        """JWT bearer token resolves to AuthContext."""
        request = _fresh_request()
        principal = _make_principal(user_id=5, scopes=frozenset(["profile", "activities"]))
        mock_svc = MagicMock(spec=IdentityService)
        mock_svc.resolve_from_access_token.return_value = principal

        ctx = await auth_security.validate_access_token_or_api_key(
            request,
            mock_svc,
            access_token="valid_jwt",
            api_key_header=None,
        )

        assert ctx.user_id == 5
        assert ctx.auth_type == "jwt"
        assert "profile" in ctx.scopes
        assert request.state.principal is principal

    @pytest.mark.asyncio
    async def test_api_key_path_happy(self):
        """API key resolves to AuthContext with auth_type='api_key'."""
        request = _fresh_request()
        principal = _make_principal(
            user_id=9,
            scopes=frozenset(["activities"]),
            credential=ApiKeyCred(api_key_id=2, key_prefix="pfx_"),
        )
        mock_svc = MagicMock(spec=IdentityService)
        mock_svc.resolve_from_api_key.return_value = principal

        ctx = await auth_security.validate_access_token_or_api_key(
            request,
            mock_svc,
            access_token=None,
            api_key_header="raw-api-key",
        )

        assert ctx.user_id == 9
        assert ctx.auth_type == "api_key"
        assert request.state.principal is principal

    @pytest.mark.asyncio
    async def test_api_key_query_string_ignored_when_disabled(self):
        """Query-string API key is silently ignored when ALLOW_API_KEY_QUERY_PARAM is False."""
        request = _fresh_request()
        mock_svc = MagicMock(spec=IdentityService)
        mock_settings = MagicMock()
        mock_settings.ALLOW_API_KEY_QUERY_PARAM = False

        with (
            patch("modules.auth._internal.internal_dependencies.core_config.settings", mock_settings),
            pytest.raises(HTTPException) as exc,
        ):
            await auth_security.validate_access_token_or_api_key(
                request,
                mock_svc,
                access_token=None,
                api_key_header=None,
                api_key_query="qk-456",
            )
        assert exc.value.status_code == 401
        mock_svc.resolve_from_api_key.assert_not_called()

    @pytest.mark.asyncio
    async def test_api_key_query_string_accepted_when_enabled(self):
        """Query-string API key resolves when ALLOW_API_KEY_QUERY_PARAM is True."""
        request = _fresh_request()
        principal = _make_principal(
            user_id=9,
            credential=ApiKeyCred(api_key_id=3, key_prefix="pfx_"),
        )
        mock_svc = MagicMock(spec=IdentityService)
        mock_svc.resolve_from_api_key.return_value = principal
        mock_settings = MagicMock()
        mock_settings.ALLOW_API_KEY_QUERY_PARAM = True

        with patch("modules.auth._internal.internal_dependencies.core_config.settings", mock_settings):
            ctx = await auth_security.validate_access_token_or_api_key(
                request,
                mock_svc,
                access_token=None,
                api_key_header=None,
                api_key_query="qk-456",
            )
        assert ctx.auth_type == "api_key"
        assert ctx.user_id == 9
        mock_svc.resolve_from_api_key.assert_called_once_with("qk-456", request)

    @pytest.mark.asyncio
    async def test_no_credential_raises_401(self):
        """Neither JWT nor API key → 401."""
        request = _fresh_request()
        mock_svc = MagicMock(spec=IdentityService)
        mock_settings = MagicMock()
        mock_settings.ALLOW_API_KEY_QUERY_PARAM = False

        with (
            patch("modules.auth._internal.internal_dependencies.core_config.settings", mock_settings),
            pytest.raises(HTTPException) as exc,
        ):
            await auth_security.validate_access_token_or_api_key(
                request,
                mock_svc,
                access_token=None,
                api_key_header=None,
                api_key_query=None,
            )
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_cache_hit_returns_early(self):
        """Pre-cached Principal skips IdentityService calls."""
        request = _fresh_request()
        principal = _make_principal(user_id=11)
        request.state.principal = principal  # pre-populate
        mock_svc = MagicMock(spec=IdentityService)

        ctx = await auth_security.validate_access_token_or_api_key(
            request,
            mock_svc,
            access_token="any_token",
            api_key_header=None,
        )

        assert ctx.user_id == 11
        mock_svc.resolve_from_access_token.assert_not_called()
        mock_svc.resolve_from_api_key.assert_not_called()

    @pytest.mark.asyncio
    async def test_jwt_failure_raises_401(self):
        """IdentityService JWT failure propagates 401."""
        request = _fresh_request()
        mock_svc = MagicMock(spec=IdentityService)
        mock_svc.resolve_from_access_token.side_effect = HTTPException(status_code=401, detail="Token expired")

        with pytest.raises(HTTPException) as exc:
            await auth_security.validate_access_token_or_api_key(
                request,
                mock_svc,
                access_token="bad_token",
                api_key_header=None,
            )
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_jwt_takes_precedence_over_api_key(self):
        """JWT wins when both Bearer token and X-API-Key are present.

        The JWT path must run and the API key resolver
        must not be called.
        """
        request = _fresh_request()
        principal = _make_principal(user_id=20)
        mock_svc = MagicMock(spec=IdentityService)
        mock_svc.resolve_from_access_token.return_value = principal

        ctx = await auth_security.validate_access_token_or_api_key(
            request,
            mock_svc,
            access_token="valid_jwt",
            api_key_header="some-api-key",
        )

        assert ctx.auth_type == "jwt"
        assert ctx.user_id == 20
        mock_svc.resolve_from_api_key.assert_not_called()

    @pytest.mark.asyncio
    async def test_api_key_failure_raises_401(self):
        """IdentityService API key failure propagates 401."""
        request = _fresh_request()
        mock_svc = MagicMock(spec=IdentityService)
        mock_svc.resolve_from_api_key.side_effect = HTTPException(status_code=401, detail="Invalid API key")

        with pytest.raises(HTTPException) as exc:
            await auth_security.validate_access_token_or_api_key(
                request,
                mock_svc,
                access_token=None,
                api_key_header="bad-key",
            )
        assert exc.value.status_code == 401


# ---------------------------------------------------------------------------
# check_auth_scopes
# ---------------------------------------------------------------------------


class TestCheckAuthScopes:
    """Scope validation on unified AuthContext."""

    def _make_auth_ctx(
        self,
        scopes: list[str],
        auth_type: str = "jwt",
        user_id: int = 1,
    ) -> auth_security.AuthContext:
        """Return an AuthContext directly.

        Args:
            scopes: List of granted scope strings.
            auth_type: Authentication method string.
            user_id: User primary key.

        Returns:
            AuthContext: Populated context for tests.
        """
        return auth_security.AuthContext(user_id=user_id, scopes=scopes, auth_type=auth_type)

    def test_all_required_scopes_present(self):
        """No exception when all required scopes are present."""
        ctx = self._make_auth_ctx(["profile", "activities"])
        security_scopes = SecurityScopes(scopes=["profile"])

        # Should not raise
        auth_dependencies.check_auth_scopes(ctx, security_scopes)

    def test_missing_scope_raises_403(self):
        """Missing required scope raises 403."""
        ctx = self._make_auth_ctx(["profile"])
        security_scopes = SecurityScopes(scopes=["admin:write"])

        with pytest.raises(HTTPException) as exc:
            auth_dependencies.check_auth_scopes(ctx, security_scopes)
        assert exc.value.status_code == 403
        assert "Missing permissions" in exc.value.detail

    def test_empty_required_scopes_passes(self):
        """No required scopes → always passes."""
        ctx = self._make_auth_ctx([])
        security_scopes = SecurityScopes(scopes=[])

        auth_dependencies.check_auth_scopes(ctx, security_scopes)

    def test_api_key_auth_type_scope_check(self):
        """Scope check also works for API key auth."""
        ctx = self._make_auth_ctx(["activities"], auth_type="api_key")
        security_scopes = SecurityScopes(scopes=["profile"])

        with pytest.raises(HTTPException) as exc:
            auth_dependencies.check_auth_scopes(ctx, security_scopes)
        assert exc.value.status_code == 403


# ---------------------------------------------------------------------------
# AuthContext identity
# ---------------------------------------------------------------------------


class TestAuthContextIdentity:
    """Assert that dependencies.AuthContext is the canonical security.AuthContext."""

    def test_auth_context_is_same_type_as_dependencies(self):
        import modules.auth.dependencies as auth_dependencies

        assert auth_security.AuthContext is auth_dependencies.AuthContext
