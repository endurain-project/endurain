"""Public authentication dependencies for non-auth modules.

This module is the supported boundary for routers outside ``auth`` that
need identity, scope checks, or mixed JWT/API-key authentication. The
implementations delegate credential resolution to ``IdentityService`` so
callers do not import ``auth._internal.internal_dependencies`` directly.

``AuthContext``, the shared OAuth2/API-key schemes
(``oauth2_scheme``, ``header_client_type_scheme``, ``header_api_key_scheme``),
the principal caching helper ``_resolve_and_cache_principal``, and functions
whose implementations are identical in ``auth._internal.internal_dependencies`` are
re-exported from that module.  Only functions with a different FastAPI
dependency signature (using ``IdentityService`` instead of ``TokenManager``),
plus the unified ``check_auth_scopes``, are defined here.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import SecurityScopes

import auth._internal.security_stores as auth_security_stores
import auth.identity_service as auth_identity_service
from auth._internal.internal_dependencies import (
    AuthContext,
    _resolve_and_cache_principal,
    get_access_token,
    get_sid_from_access_token,
    get_sub_from_access_token,
    get_user_id_from_auth,
    validate_access_token_or_api_key,
)


def validate_access_token(
    request: Request,
    access_token: Annotated[str, Depends(get_access_token)],
    identity_service: Annotated[
        auth_identity_service.IdentityService,
        Depends(auth_identity_service.get_identity_service),
    ],
) -> None:
    """Validate an access token through IdentityService.

    Args:
        request: Current HTTP request.
        access_token: Raw JWT access token.
        identity_service: Per-request IdentityService.

    Raises:
        HTTPException: 401 if the token is invalid.
    """
    _resolve_and_cache_principal(access_token, request, identity_service)


def check_scopes(
    request: Request,
    access_token: Annotated[str, Depends(get_access_token)],
    identity_service: Annotated[
        auth_identity_service.IdentityService,
        Depends(auth_identity_service.get_identity_service),
    ],
    security_scopes: SecurityScopes,
) -> None:
    """Validate required scopes through IdentityService.

    Args:
        request: Current HTTP request.
        access_token: Raw JWT access token.
        identity_service: Per-request IdentityService.
        security_scopes: Required scopes for the endpoint.

    Raises:
        HTTPException: 403 if required scopes are missing.
    """
    principal = _resolve_and_cache_principal(access_token, request, identity_service)
    identity_service.check_scope(principal, frozenset(security_scopes.scopes))


def check_auth_scopes(
    auth: Annotated[
        AuthContext,
        Depends(validate_access_token_or_api_key),
    ],
    security_scopes: SecurityScopes,
) -> None:
    """Validate scopes from a unified AuthContext.

    Use this in place of :func:`check_scopes` on endpoints that accept both
    JWT and API key auth. The underlying ``AuthContext`` is resolved by
    :func:`validate_access_token_or_api_key`, which goes through
    ``IdentityService`` (asserting the user exists and is active).

    Args:
        auth: Resolved AuthContext from validate_access_token_or_api_key.
        security_scopes: Required scopes for the endpoint.

    Raises:
        HTTPException: 403 if any required scope is missing from the
            AuthContext.
    """
    missing = set(security_scopes.scopes) - set(auth.scopes)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(f"Unauthorized Access - Missing permissions: {missing}"),
            headers={"WWW-Authenticate": (f'Bearer scope="{security_scopes.scopes}"')},
        )


__all__ = [
    "AuthContext",
    "StepUpStore",
    "check_auth_scopes",
    "check_scopes",
    "get_access_token",
    "get_sid_from_access_token",
    "get_step_up_attempts",
    "get_sub_from_access_token",
    "get_user_id_from_auth",
    "validate_access_token",
    "validate_access_token_or_api_key",
]

# Re-export step-up store type and dep getter for non-auth modules
StepUpStore = auth_security_stores.StepUpStore
get_step_up_attempts = auth_security_stores.get_step_up_attempts
