"""Public authentication dependencies for routers and application modules."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Query, Request, Response, status
from fastapi.security import APIKeyHeader, OAuth2PasswordBearer, SecurityScopes
from sqlalchemy.orm import Session

import core.config as core_config
import core.dependencies as core_dependencies
import modules.auth.access_tokens.integration_service as access_tokens_integration
import modules.auth.account_security.step_up_store as account_security_step_up_store
import modules.auth.authentication.dependencies as authentication_dependencies
import modules.auth.authentication.integration_service as authentication_integration
import modules.auth.constants as auth_constants
import modules.auth.contracts as auth_contracts
import modules.auth.mfa.dependencies as auth_mfa_dependencies

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/login",
    scopes=auth_constants.SCOPE_DICT,
    auto_error=False,
)
header_api_key_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)
AuthContext = auth_contracts.AuthContext
ClientTypeHeader = authentication_dependencies.ClientTypeHeader


def get_access_token(
    access_token: Annotated[str | None, Depends(oauth2_scheme)],
    _client_type: str = Depends(authentication_dependencies.header_client_type_scheme),
) -> str:
    """Require an access token from the Authorization header."""
    if access_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token missing from Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return access_token


def validate_access_token_expiration(
    access_token: Annotated[str, Depends(get_access_token)],
    token_manager: Annotated[
        access_tokens_integration.TokenManager,
        Depends(access_tokens_integration.get_token_manager),
    ],
) -> None:
    """Validate access-token signature and expiration without loading its user."""
    token_manager.validate_access_expiration_logged(access_token)


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
    missing = set(security_scopes.scopes) - set(principal.scopes)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Unauthorized Access - Missing permissions: {missing}",
            headers={"WWW-Authenticate": f'Bearer scope="{security_scopes.scopes}"'},
        )


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
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credential type for session ID")
    return principal.credential.session_id


async def validate_api_key(raw_key: str, request: Request, db: Session) -> AuthContext:
    """Resolve an API key and return its user and granted scopes."""
    principal = authentication_integration.resolve_from_api_key(raw_key, request, db)
    request.state.principal = principal
    return AuthContext(user_id=principal.user_id, scopes=list(principal.scopes), auth_type="api_key")


async def validate_access_token_or_api_key(
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
            import core.logger as core_logger

            core_logger.get_logger(__name__).warning(
                "API key supplied via query string (?api_key=). "
                "This is a security risk: credentials appear in access logs and browser history. "
                "Set X-API-Key header instead."
            )
            raw_key = api_key_query
        if raw_key is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated. Provide a Bearer token or an API key.",
                headers={"WWW-Authenticate": "Bearer"},
            )
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
    missing = set(security_scopes.scopes) - set(auth.scopes)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Unauthorized Access - Missing permissions: {missing}",
            headers={"WWW-Authenticate": f'Bearer scope="{security_scopes.scopes}"'},
        )


def clear_refresh_token_cookies(response: Response) -> None:
    """Clear refresh-token cookies using the configured environment."""
    authentication_dependencies.clear_refresh_token_cookies(
        response,
        environment=core_config.settings.ENVIRONMENT,
    )


#: Authenticated user id extracted from a resolved access token.
CurrentUserId = Annotated[int, Depends(get_sub_from_access_token)]
StepUpStore = account_security_step_up_store.StepUpStore
get_step_up_attempts = account_security_step_up_store.get_step_up_attempts
MFASecretStoreBackend = auth_mfa_dependencies.MFASecretStoreBackend
get_mfa_secret_store = auth_mfa_dependencies.get_mfa_secret_store

# Keep refresh dependency symbols available on the established public surface.
get_token = authentication_dependencies.get_token
get_refresh_token = authentication_dependencies.get_refresh_token
get_sid_from_refresh_token = authentication_dependencies.get_sid_from_refresh_token
get_sub_from_refresh_token = authentication_dependencies.get_sub_from_refresh_token
get_and_return_refresh_token = authentication_dependencies.get_and_return_refresh_token
validate_refresh_token = authentication_dependencies.validate_refresh_token
header_client_type_scheme = authentication_dependencies.header_client_type_scheme
header_csrf_token_scheme = authentication_dependencies.header_csrf_token_scheme
cookie_refresh_token_scheme = authentication_dependencies.cookie_refresh_token_scheme

__all__ = [
    "AuthContext",
    "ClientTypeHeader",
    "CurrentUserId",
    "MFASecretStoreBackend",
    "StepUpStore",
    "check_auth_scopes",
    "check_scopes",
    "clear_refresh_token_cookies",
    "get_access_token",
    "get_and_return_refresh_token",
    "get_mfa_secret_store",
    "get_refresh_token",
    "get_sid_from_access_token",
    "get_sid_from_refresh_token",
    "get_step_up_attempts",
    "get_sub_from_access_token",
    "get_sub_from_refresh_token",
    "get_token",
    "get_user_id_from_auth",
    "header_client_type_scheme",
    "header_csrf_token_scheme",
    "validate_access_token",
    "validate_access_token_expiration",
    "validate_access_token_or_api_key",
    "validate_refresh_token",
]
