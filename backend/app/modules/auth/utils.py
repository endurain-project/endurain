"""Authentication utilities for the auth router.

Provides credential verification, JWT/CSRF token creation, and the
``complete_login`` / ``create_mobile_pkce_session_response`` helpers used by
both password and PKCE login flows.
"""

from datetime import datetime

from fastapi import (
    Request,
    Response,
)
from fastapi.responses import JSONResponse

import core.config as core_config
import core.exceptions as core_exceptions
import core.network as core_network
import modules.auth.access_tokens.integration_service as auth_token_manager
import modules.auth.authentication.dependencies as authentication_dependencies
import modules.auth.credentials.integration_service as auth_credentials_crud
import modules.auth.credentials.integration_service as auth_password_hasher
import modules.auth.identity_providers.utils as idp_utils
import modules.auth.oauth_state.integration_service as oauth_state_crud
import modules.auth.sessions.integration_service as auth_sessions_utils
import modules.server_settings.integration_service as server_settings_integration
import modules.users.users.integration_service as users_integration

REFRESH_TOKEN_COOKIE_NAME = "endurain" + "_refresh_token"
REFRESH_TOKEN_COOKIE_PATH = "/api/v1/" + "auth"
LEGACY_REFRESH_TOKEN_COOKIE_PATHS = ("/",)
REFRESH_TOKEN_COOKIE_CLEAR_PATHS = (*LEGACY_REFRESH_TOKEN_COOKIE_PATHS, REFRESH_TOKEN_COOKIE_PATH)

__all__ = [
    "REFRESH_TOKEN_COOKIE_CLEAR_PATHS",
    "REFRESH_TOKEN_COOKIE_NAME",
    "REFRESH_TOKEN_COOKIE_PATH",
    "ClearRefreshTokenCookieHTTPException",
    "auth_credentials_crud",
    "auth_password_hasher",
    "auth_sessions_utils",
    "auth_token_manager",
    "clear_refresh_token_cookie_exception_handler",
    "clear_refresh_token_cookies",
    "core_config",
    "core_exceptions",
    "core_network",
    "idp_utils",
    "oauth_state_crud",
    "server_settings_integration",
    "set_refresh_token_cookie",
    "users_integration",
]


ClearRefreshTokenCookieHTTPException = authentication_dependencies.ClearRefreshTokenCookieHTTPException


def _is_secure_cookie_environment() -> bool:
    """Return ``True`` when refresh cookies must be served with ``Secure``.

    Single source of truth for the cookie ``Secure`` flag used by the
    password login, refresh, and SSO token-exchange flows. Basing the
    decision on ``ENVIRONMENT`` (``production``/``demo``) keeps the
    behaviour identical across all three flows and avoids the prior
    bug where the SSO path used ``FRONTEND_PROTOCOL`` and could issue
    a non-Secure refresh cookie when that env var was missing or
    mis-set in production.
    """
    return core_config.settings.ENVIRONMENT in {"production", "demo"}


def set_refresh_token_cookie(
    response: Response,
    refresh_token: str,
    expires_at: datetime,
) -> None:
    """Set the canonical refresh-token cookie with consistent attributes.

    All web-client refresh-cookie writes (initial login, ``/refresh``,
    SSO token exchange) must go through this helper so that
    ``HttpOnly``, ``SameSite=Strict``, ``Path``, expiry, and the
    ``Secure`` flag stay in lockstep.

    Args:
        response: Response object to receive the cookie.
        refresh_token: The refresh token to store.
        expires_at: When the refresh token expires; the cookie expires with it.
    """
    authentication_dependencies.set_refresh_token_cookie(
        response,
        refresh_token,
        expires_at,
        environment=core_config.settings.ENVIRONMENT,
    )


def clear_refresh_token_cookies(response: Response) -> None:
    """Clear refresh-token cookies on all known paths.

    Args:
        response: Response object to receive cookie-deletion headers.

    Returns:
        None.

    Raises:
        None.
    """
    authentication_dependencies.clear_refresh_token_cookies(
        response,
        environment=core_config.settings.ENVIRONMENT,
    )


async def clear_refresh_token_cookie_exception_handler(
    _request: Request,
    exc: ClearRefreshTokenCookieHTTPException,
) -> JSONResponse:
    """Delegate error rendering and cookie clearing to authentication dependencies."""
    return await authentication_dependencies.clear_refresh_token_cookie_exception_handler(_request, exc)


# Login and token workflows live in authentication.service.


def __getattr__(name: str):
    """Resolve login-workflow compatibility names from their authentication service."""
    if name in {
        "authenticate_user",
        "build_token_response",
        "complete_login",
        "create_mobile_pkce_session_response",
        "create_tokens",
        "mint_access_token",
    }:
        from modules.auth.authentication import service

        return getattr(service, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
