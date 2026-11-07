"""Regression tests for principal resolution and caching in public dependencies."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.security import SecurityScopes

import core.exceptions as core_exceptions
import modules.auth.dependencies as auth_dependencies
from modules.auth.contracts import AccessTokenCred, Principal


def _principal(scopes: frozenset[str] = frozenset({"profile"})) -> Principal:
    return Principal(
        user_id=12,
        username="alice",
        email="alice@example.com",
        is_active=True,
        is_superuser=False,
        scopes=scopes,
        credential=AccessTokenCred(session_id="sid-12"),
    )


def test_resolver_caches_principal_for_request():
    request = MagicMock()
    request.state = SimpleNamespace()
    db = MagicMock()
    principal = _principal()
    with patch.object(
        auth_dependencies.authentication_integration, "resolve_from_access_token", return_value=principal
    ) as resolve:
        assert auth_dependencies._resolve_and_cache_principal("token", request, db) is principal
        assert auth_dependencies._resolve_and_cache_principal("token", request, db) is principal
    resolve.assert_called_once_with("token", db)


def test_sid_dependency_requires_an_access_token_credential():
    request = MagicMock()
    request.state = SimpleNamespace(principal=_principal())
    assert auth_dependencies.get_sid_from_access_token(request, "token", MagicMock()) == "sid-12"


def test_scope_dependency_rejects_missing_scope():
    request = MagicMock()
    request.state = SimpleNamespace(principal=_principal())
    with pytest.raises(core_exceptions.PermissionDeniedError) as exc_info:
        auth_dependencies.check_scopes(request, "token", MagicMock(), SecurityScopes(scopes=["users:write"]))
    assert exc_info.value.status_code == 403


def test_unified_scope_dependency_accepts_declared_scope():
    context = auth_dependencies.AuthContext(user_id=12, scopes=["profile"], auth_type="jwt")
    auth_dependencies.check_auth_scopes(context, SecurityScopes(scopes=["profile"]))
