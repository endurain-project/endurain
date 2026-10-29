"""Public authentication dependencies for routers and application modules."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Annotated

from fastapi import Depends, Path, Query, Request
from fastapi.security import APIKeyHeader, SecurityScopes
from sqlalchemy.orm import Session

import core.config as core_config
import core.dependencies as core_dependencies
import core.exceptions as core_exceptions
import core.logger as core_logger
import modules.auth.account_security.integration_service as account_security_integration
import modules.auth.authentication.dependencies as authentication_dependencies
import modules.auth.authentication.integration_service as authentication_integration
import modules.auth.contracts as auth_contracts
import modules.auth.identity_providers.dependencies as identity_providers_dependencies
import modules.auth.mfa.dependencies as auth_mfa_dependencies

logger = core_logger.get_logger(__name__)

oauth2_scheme = authentication_dependencies.oauth2_scheme
header_api_key_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)
AuthContext = auth_contracts.AuthContext
ApiKeyId = Annotated[str, Path(min_length=1)]
IdentityProviderSlug = Annotated[str, Path(min_length=1)]
AuthSessionId = Annotated[str, Path(min_length=1)]
set_idp_link_binding_cookie = identity_providers_dependencies.set_link_binding_cookie


def get_access_token(
    access_token: Annotated[str | None, Depends(oauth2_scheme)],
    _client_type: str = Depends(authentication_dependencies.header_client_type_scheme),
) -> str:
    """Require an access token from the Authorization header."""
    if access_token is None:
        raise core_exceptions.UnauthenticatedError("Access token missing from Authorization header")
    return access_token


def _require_scopes(granted: Iterable[str], required: SecurityScopes) -> None:
    """Refuse a caller that lacks any scope the route declares.

    Args:
        granted: Scopes the caller holds.
        required: Scopes the route requires.

    Raises:
        PermissionDeniedError: When a required scope is missing.
    """
    missing = set(required.scopes) - set(granted)
    if missing:
        logger.warning("Request refused: missing scopes <scopes>", extra=core_logger.context(scopes=sorted(missing)))
        error = core_exceptions.PermissionDeniedError(f"Unauthorized Access - Missing permissions: {missing}")
        error.headers = {"WWW-Authenticate": f'Bearer scope="{required.scopes}"'}
        raise error


def _resolve_and_cache_principal(access_token: str, request: Request, db: Session) -> auth_contracts.Principal:
    """Resolve the request principal once and cache it on request state."""
    principal = getattr(request.state, "principal", None)
    if principal is None:
        principal = authentication_integration.resolve_from_access_token(access_token, db)
        request.state.principal = principal
    return principal


def validate_access_token(
    request: Request,
    access_token: Annotated[str, Depends(get_access_token)],
    db: core_dependencies.DbSession,
) -> None:
    """Resolve an access token and require an active user."""
    _resolve_and_cache_principal(access_token, request, db)


def check_scopes(
    request: Request,
    access_token: Annotated[str, Depends(get_access_token)],
    db: core_dependencies.DbSession,
    security_scopes: SecurityScopes,
) -> None:
    """Resolve an access token and require all declared scopes."""
    principal = _resolve_and_cache_principal(access_token, request, db)
    _require_scopes(principal.scopes, security_scopes)


def get_sub_from_access_token(
    request: Request,
    access_token: Annotated[str, Depends(get_access_token)],
    db: core_dependencies.DbSession,
) -> int:
    """Return the authenticated user's id after resolving the access token."""
    return _resolve_and_cache_principal(access_token, request, db).user_id


def get_sid_from_access_token(
    request: Request,
    access_token: Annotated[str, Depends(get_access_token)],
    db: core_dependencies.DbSession,
) -> str:
    """Return the session id carried by a validated access token."""
    principal = _resolve_and_cache_principal(access_token, request, db)
    if not isinstance(principal.credential, auth_contracts.AccessTokenCred):
        raise core_exceptions.UnauthenticatedError("Invalid credential type for session ID")
    return principal.credential.session_id


def validate_access_token_or_api_key(
    request: Request,
    db: core_dependencies.DbSession,
    access_token: str | None = Depends(oauth2_scheme),
    api_key_header: str | None = Depends(header_api_key_scheme),
    api_key_query: str | None = Query(None, alias="api_key"),
) -> AuthContext:
    """Resolve a JWT or API key, preserving request-level principal caching."""
    cached = getattr(request.state, "principal", None)
    if cached is not None:
        return AuthContext(cached.user_id, list(cached.scopes), "api_key" if cached.is_api_key() else "jwt")
    if access_token is not None:
        principal = authentication_integration.resolve_from_access_token(access_token, db)
        auth_type = "jwt"
    else:
        raw_key = api_key_header
        if raw_key is None and api_key_query is not None and core_config.settings.ALLOW_API_KEY_QUERY_PARAM:
            logger.warning(
                "API key supplied via query string (?api_key=). "
                "This is a security risk: credentials appear in access logs and browser history. "
                "Set X-API-Key header instead."
            )
            raw_key = api_key_query
        if raw_key is None:
            raise core_exceptions.UnauthenticatedError("Not authenticated. Provide a Bearer token or an API key.")
        principal = authentication_integration.resolve_from_api_key(raw_key, request, db)
        auth_type = "api_key"
    request.state.principal = principal
    return AuthContext(principal.user_id, list(principal.scopes), auth_type)


def get_user_id_from_auth(
    auth: Annotated[AuthContext, Depends(validate_access_token_or_api_key)],
) -> int:
    """Return the user id from resolved JWT or API-key authentication."""
    return auth.user_id


def check_auth_scopes(
    auth: Annotated[AuthContext, Depends(validate_access_token_or_api_key)],
    security_scopes: SecurityScopes,
) -> None:
    """Require all declared scopes from a JWT or API-key context."""
    _require_scopes(auth.scopes, security_scopes)


#: Authenticated user id extracted from a resolved access token.
CurrentUserId = Annotated[int, Depends(get_sub_from_access_token)]
StepUpStore = account_security_integration.StepUpStore
get_step_up_attempts = account_security_integration.get_step_up_attempts
MFASecretStoreBackend = auth_mfa_dependencies.MFASecretStoreBackend
get_mfa_secret_store = auth_mfa_dependencies.get_mfa_secret_store

__all__ = [
    "AuthContext",
    "CurrentUserId",
    "MFASecretStoreBackend",
    "StepUpStore",
    "check_auth_scopes",
    "check_scopes",
    "get_access_token",
    "get_mfa_secret_store",
    "get_sid_from_access_token",
    "get_step_up_attempts",
    "get_sub_from_access_token",
    "get_user_id_from_auth",
    "validate_access_token",
    "validate_access_token_or_api_key",
]
