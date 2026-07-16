"""Auth-internal FastAPI dependencies and credential-extraction helpers.

This is the low-level, auth-internal dependency layer. Non-auth modules must
**not** import it directly (enforced by the ``auth-boundary`` import-linter
contract); they consume identity through :mod:`modules.auth.dependencies` and
:class:`~auth.identity_service.IdentityService` instead.

Provides FastAPI dependencies that resolve and validate JWT access/refresh
tokens (cookie or Authorization header) and accept API keys as an alternative
credential. Defines :class:`AuthContext`, the unified credential representation
passed to endpoints that accept either auth method.

Scope enforcement is intentionally not provided here: the canonical,
principal-resolving ``check_scopes`` lives in :mod:`modules.auth.dependencies` (it goes
through :class:`~auth.identity_service.IdentityService`, which also asserts the
user exists and is active). Use that instead.
"""

from dataclasses import dataclass
from typing import Annotated

from fastapi import (
    Depends,
    HTTPException,
    Query,
    Request,
    status,
)
from fastapi.security import (
    APIKeyCookie,
    APIKeyHeader,
    OAuth2PasswordBearer,
)
from joserfc.errors import MissingClaimError

import core.config as core_config
import core.logger as core_logger
import modules.auth._internal.token_manager as auth_token_manager
import modules.auth.constants as auth_constants
import modules.auth.identity_service as auth_identity_service
import modules.auth.utils as auth_utils
from modules.auth.principal import AccessTokenCred, Principal

# Define the OAuth2 scheme for handling bearer tokens
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/login",
    scopes=auth_constants.SCOPE_DICT,
    auto_error=False,
)

# Define the API key header for the client type
header_client_type_scheme = APIKeyHeader(name="X-Client-Type")

# Define the API key header for third-party API key auth
header_api_key_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)


@dataclass
class AuthContext:
    """
    Unified authentication context.

    Carries the resolved user identity and scopes
    regardless of whether authentication was via JWT
    or API key.

    Attributes:
        user_id: Authenticated user's ID.
        scopes: List of granted scope strings.
        auth_type: Source of authentication
            (``"jwt"`` or ``"api_key"``).
    """

    user_id: int
    scopes: list[str]
    auth_type: str


# Define the API key header for CSRF token
header_csrf_token_scheme = APIKeyHeader(name="X-CSRF-Token", auto_error=False)

# Define the API key cookie for the refresh token
cookie_refresh_token_scheme = APIKeyCookie(
    name="endurain_refresh_token",
    auto_error=False,
)


def _resolve_and_cache_principal(
    access_token: str,
    request: Request,
    identity_service: auth_identity_service.IdentityService,
) -> Principal:
    """Resolve and cache a Principal from a JWT access token.

    Checks ``request.state.principal`` first so that multiple
    dependencies in the same request share a single DB lookup.
    On cache miss, delegates to
    :meth:`~auth.identity_service.IdentityService.resolve_from_access_token`
    and stores the result on ``request.state``.

    Args:
        access_token: Raw JWT access token string.
        request: Current HTTP request used for caching.
        identity_service: Per-request IdentityService.

    Returns:
        Principal: Cached or freshly-resolved principal.

    Raises:
        HTTPException: 401 if the token is invalid or
            the user is not found.
    """
    cached: Principal | None = getattr(request.state, "principal", None)
    if cached is not None:
        return cached
    principal = identity_service.resolve_from_access_token(access_token)
    request.state.principal = principal
    return principal


def get_token(
    non_cookie_token: Annotated[str | None, Depends(oauth2_scheme)],
    cookie_token: str | None,
    client_type: str,
    token_type: auth_token_manager.TokenType,
) -> str | None:
    """
    Retrieves the authentication token based on client type and token type.

    Args:
        non_cookie_token (str | None): Token provided via Authorization header.
        cookie_token (str | None): Token provided via cookie.
        client_type (str): Type of client requesting the token ("web" or "mobile").
        token_type (TokenType): Type of token being requested (ACCESS or REFRESH).

    Returns:
        str: The authentication token appropriate for the client type and token type.

    Raises:
        HTTPException: If the required token is missing, or if the client type is invalid.
    """
    # OAuth 2.1: Access tokens always come from Authorization header (all clients)
    if token_type == auth_token_manager.TokenType.ACCESS:
        if non_cookie_token is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Access token missing from Authorization header",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return non_cookie_token

    # Refresh tokens: cookie (web) or Authorization header (mobile)
    if token_type == auth_token_manager.TokenType.REFRESH:
        if client_type == "web":
            if cookie_token is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Refresh token missing from cookie",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            return cookie_token
        if client_type == "mobile":
            if non_cookie_token is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Refresh token missing from Authorization header",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            return non_cookie_token

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Invalid client type or token type",
        headers={"WWW-Authenticate": "Bearer"},
    )


## ACCESS TOKEN VALIDATION
def get_access_token(
    access_token: Annotated[str | None, Depends(oauth2_scheme)],
    _client_type: str = Depends(header_client_type_scheme),
) -> str:
    """
    Retrieves the access token from the Authorization header.

    Args:
        access_token (str | None): Access token provided via the Authorization header (OAuth2 scheme).
        _client_type (str): The type of client making the request, extracted from a custom header.

    Returns:
        str: The access token from the Authorization header.

    Raises:
        HTTPException: If the access token is missing from the Authorization header.
    """
    if access_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token missing from Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return access_token


def _validate_access_token_impl(
    access_token: str,
    token_manager: auth_token_manager.TokenManager,
) -> None:
    """Shared implementation for access-token validation.

    Args:
        access_token: The access token to validate.
        token_manager: The configured token manager.

    Raises:
        HTTPException: If the token is missing claims, expired, or otherwise
            invalid. Unexpected exceptions are wrapped as a 500 so the global
            error handler can record them.
    """
    try:
        token_manager.validate_access_expiration_logged(access_token)
    except HTTPException:
        raise
    except Exception as err:
        core_logger.print_to_log(
            f"Unexpected error during access token validation: {type(err).__name__}",
            "error",
            exc=err,
            context={"access_token": "[REDACTED]"},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during token validation",
        ) from err


def validate_access_token_expiration(
    access_token: Annotated[str, Depends(get_access_token)],
    token_manager: Annotated[
        auth_token_manager.TokenManager,
        Depends(auth_token_manager.get_token_manager),
    ],
) -> None:
    """FastAPI dependency that validates only the *expiration* (and signature)
    of the access token from the Authorization header.

    This is the lightweight, expiry-only gate. It does **not** resolve the
    user, load the account, or check active status. Non-auth routers that need
    full identity resolution must use
    :func:`modules.auth.dependencies.validate_access_token` (the principal-resolving
    validator) instead.

    Args:
        access_token (str): The access token to be validated.
        token_manager (auth_token_manager.TokenManager): The token manager instance used for validation.

    Raises:
        HTTPException: If the token is expired or invalid.
    """
    _validate_access_token_impl(access_token, token_manager)


def get_sub_from_access_token(
    request: Request,
    access_token: Annotated[str, Depends(get_access_token)],
    identity_service: Annotated[
        auth_identity_service.IdentityService,
        Depends(auth_identity_service.get_identity_service),
    ],
) -> int:
    """Retrieve the user ID from the access token.

    Resolves and caches the :class:`~auth.principal.Principal`
    on ``request.state`` then returns ``principal.user_id``.
    Subsequent calls within the same request hit the cache
    instead of issuing another DB lookup.

    Args:
        request: Current HTTP request for state caching.
        access_token: JWT from the Authorization header.
        identity_service: Per-request IdentityService.

    Returns:
        int: Authenticated user's primary key.

    Raises:
        HTTPException: 401 if the token is invalid,
            expired, or the user is not found.
    """
    principal = _resolve_and_cache_principal(access_token, request, identity_service)
    return principal.user_id


def get_sid_from_access_token(
    request: Request,
    access_token: Annotated[str, Depends(get_access_token)],
    identity_service: Annotated[
        auth_identity_service.IdentityService,
        Depends(auth_identity_service.get_identity_service),
    ],
) -> str:
    """Retrieve the session ID from the access token.

    Resolves and caches the :class:`~auth.principal.Principal`
    on ``request.state`` then extracts the session ID from the
    :class:`~auth.principal.AccessTokenCred`.

    Args:
        request: Current HTTP request for state caching.
        access_token: JWT from the Authorization header.
        identity_service: Per-request IdentityService.

    Returns:
        str: Session ID (``sid`` claim) from the token.

    Raises:
        HTTPException: 401 if the token is invalid,
            expired, or the credential type is unexpected.
    """
    principal = _resolve_and_cache_principal(access_token, request, identity_service)
    cred = principal.credential
    if not isinstance(cred, AccessTokenCred):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credential type for session ID",
        )
    return cred.session_id


## REFRESH TOKEN VALIDATION
def get_refresh_token(
    non_cookie_refresh_token: Annotated[str | None, Depends(oauth2_scheme)],
    cookie_refresh_token: str | None = Depends(cookie_refresh_token_scheme),
    client_type: str = Depends(header_client_type_scheme),
) -> str | None:
    """
    Retrieves the refresh token from either the Authorization header or a cookie, depending on the client type.

    Args:
        non_cookie_refresh_token (str | None): The refresh token provided via the Authorization header (if present).
        cookie_refresh_token (str | None): The refresh token provided via a cookie (if present).
        client_type (str): The type of client making the request, extracted from the request headers.

    Returns:
        str: The resolved refresh token based on the provided sources and client type.

    Raises:
        HTTPException: If no valid refresh token is found or the client type is invalid.
    """
    return get_token(non_cookie_refresh_token, cookie_refresh_token, client_type, auth_token_manager.TokenType.REFRESH)


def validate_refresh_token(
    refresh_token: Annotated[str, Depends(get_refresh_token)],
    token_manager: Annotated[
        auth_token_manager.TokenManager,
        Depends(auth_token_manager.get_token_manager),
    ],
) -> None:
    """
    Validates the expiration of a refresh token using the provided token manager.

    Args:
        refresh_token (str): The refresh token to be validated, extracted via dependency injection.
        token_manager (auth_token_manager.TokenManager): The token manager instance used to validate the token, injected via dependency.

    Raises:
        HTTPException: If the refresh token is expired or invalid, or if an unexpected error occurs during validation.

    Logs:
        Errors and unexpected exceptions are logged with context, including a redacted refresh token.
    """
    try:
        # Validate the token expiration and type
        token_manager.validate_token_expiration(
            refresh_token,
            auth_token_manager.TokenType.REFRESH,
        )
    except HTTPException as http_err:
        log_level = "debug" if "expired" in http_err.detail.lower() else "error"
        core_logger.print_to_log(
            f"Refresh token validation failed: {http_err.detail}",
            log_level,
            exc=http_err,
            context={"refresh_token": "[REDACTED]"},
        )
        # If a pre-upgrade token (e.g. missing the ``typ`` claim) reaches
        # this point the SPA would otherwise loop forever: every page load
        # would resend the same stale cookie, refresh would 401, and the
        # client would never recover. A custom exception handler clears
        # both the legacy root-scoped cookie and the current auth-scoped
        # cookie using separate Set-Cookie headers. We only do this for
        # ``MissingClaimError``-style failures to avoid logging users out
        # on transient issues.
        if isinstance(http_err.__cause__, MissingClaimError):
            raise auth_utils.ClearRefreshTokenCookieHTTPException(
                status_code=http_err.status_code,
                detail=http_err.detail,
                headers=http_err.headers,
            ) from http_err
        raise
    except Exception as err:
        core_logger.print_to_log(
            f"Unexpected error during refresh token validation: {type(err).__name__}",
            "error",
            exc=err,
            context={"refresh_token": "[REDACTED]"},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during token validation",
        ) from err


def get_sub_from_refresh_token(
    refresh_token: Annotated[str, Depends(get_refresh_token)],
    token_manager: Annotated[
        auth_token_manager.TokenManager,
        Depends(auth_token_manager.get_token_manager),
    ],
) -> int:
    """
    Retrieves the user ID ('sub' claim) from a given refresh token.

    Args:
        refresh_token (str): The refresh token from which to extract the user ID.
        token_manager (auth_token_manager.TokenManager): The token manager instance used to validate and parse the token.

    Returns:
        int: The user ID associated with the provided refresh token.

    Raises:
        Exception: If the token is invalid or the 'sub' claim is not found.
    """
    # Return the user ID associated with the token
    sub = token_manager.get_token_claim(refresh_token, "sub")
    if not isinstance(sub, int):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: 'sub' claim must be an integer",
        )
    return sub


def get_sid_from_refresh_token(
    refresh_token: Annotated[str, Depends(get_refresh_token)],
    token_manager: Annotated[
        auth_token_manager.TokenManager,
        Depends(auth_token_manager.get_token_manager),
    ],
) -> str:
    """
    Retrieves the session ID ('sid') from a given refresh token.

    Args:
        refresh_token (str): The refresh token from which to extract the session ID.
        token_manager (auth_token_manager.TokenManager): The token manager used to validate and extract claims from the token.

    Returns:
        str: The session ID associated with the provided refresh token.

    Raises:
        Exception: If the token is invalid or the 'sid' claim is not present.
    """
    # Return the session ID associated with the token
    sid = token_manager.get_token_claim(refresh_token, "sid")
    if not isinstance(sid, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: 'sid' claim must be a string",
        )
    return sid


def get_and_return_refresh_token(
    refresh_token: Annotated[str, Depends(get_refresh_token)],
) -> str:
    """
    Retrieves and returns the refresh token from the request dependencies.

    Args:
        refresh_token (str): The refresh token extracted via dependency injection.

    Returns:
        str: The provided refresh token.
    """
    # Return token
    return refresh_token


## API KEY + UNIFIED AUTH
async def validate_api_key(
    raw_key: str,
    request: Request,
    identity_service: auth_identity_service.IdentityService,
) -> "AuthContext":
    """Validate a raw API key and return an AuthContext.

    Delegates to
    :meth:`~auth.identity_service.IdentityService.resolve_from_api_key`
    and wraps the returned
    :class:`~auth.principal.Principal` in an
    :class:`AuthContext` for backward compatibility.

    Args:
        raw_key: The plain-text API key from the
            request header or query parameter.
        request: The current HTTP request (for audit
            logging and state caching).
        identity_service: Per-request IdentityService.

    Returns:
        AuthContext with user_id, scopes, and
        auth_type set to ``"api_key"``.

    Raises:
        HTTPException: 401 if the key is not found,
            revoked, or expired.
    """
    principal = identity_service.resolve_from_api_key(raw_key, request)
    return AuthContext(
        user_id=principal.user_id,
        scopes=list(principal.scopes),
        auth_type="api_key",
    )


async def validate_access_token_or_api_key(
    request: Request,
    identity_service: Annotated[
        auth_identity_service.IdentityService,
        Depends(auth_identity_service.get_identity_service),
    ],
    access_token: str | None = Depends(oauth2_scheme),
    api_key_header: str | None = Depends(header_api_key_scheme),
    api_key_query: str | None = Query(None, alias="api_key"),
) -> "AuthContext":
    """Accept either a JWT bearer token or an API key.

    API keys should be supplied via the ``X-API-Key`` request header.
    Query-string delivery (``?api_key=``) is disabled by default because
    credentials in query strings appear in access logs, proxy histories,
    and browser history. It can be enabled via the
    ``ALLOW_API_KEY_QUERY_PARAM`` environment variable for self-hosted
    deployments that require it (e.g. webhook integrations that cannot
    set custom headers).

    Tries JWT first (Authorization: Bearer header). If none is
    present, falls back to the ``X-API-Key`` header, then the
    ``?api_key=`` query parameter if allowed. Raises 401 if none
    is supplied.

    Delegates to :class:`~auth.identity_service.IdentityService`
    for credential resolution and caches the resolved
    :class:`~auth.principal.Principal` on
    ``request.state.principal`` so that other dependencies in
    the same request can share the result without a second DB
    lookup.

    Args:
        request: The current HTTP request.
        identity_service: Per-request IdentityService.
        access_token: Optional Bearer token from the
            Authorization header.
        api_key_header: Optional API key from the
            ``X-API-Key`` header.
        api_key_query: Optional API key from the
            ``?api_key=`` query parameter (only honoured
            when ``ALLOW_API_KEY_QUERY_PARAM`` is ``true``).

    Returns:
        AuthContext with resolved user_id, scopes, and
        auth_type (``"jwt"`` or ``"api_key"``).

    Raises:
        HTTPException: 401 if no valid credential is
            provided.
    """
    # --- Cache check: return early if Principal already resolved ---
    cached: Principal | None = getattr(request.state, "principal", None)
    if cached is not None:
        auth_type = "api_key" if cached.is_api_key() else "jwt"
        return AuthContext(
            user_id=cached.user_id,
            scopes=list(cached.scopes),
            auth_type=auth_type,
        )

    # --- JWT path ---
    if access_token is not None:
        principal = identity_service.resolve_from_access_token(access_token)
        request.state.principal = principal
        return AuthContext(
            user_id=principal.user_id,
            scopes=list(principal.scopes),
            auth_type="jwt",
        )

    # --- API key path ---
    settings = core_config.settings
    raw_key = api_key_header
    if raw_key is None and api_key_query is not None and settings.ALLOW_API_KEY_QUERY_PARAM:
        core_logger.print_to_log(
            "API key supplied via query string (?api_key=). "
            "This is a security risk: credentials appear in access logs "
            "and browser history. Set X-API-Key header instead.",
            "warning",
        )
        raw_key = api_key_query
    if raw_key is not None:
        principal = identity_service.resolve_from_api_key(raw_key, request)
        request.state.principal = principal
        return AuthContext(
            user_id=principal.user_id,
            scopes=list(principal.scopes),
            auth_type="api_key",
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=("Not authenticated. Provide a Bearer token or an API key."),
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_user_id_from_auth(
    auth: Annotated[
        "AuthContext",
        Depends(validate_access_token_or_api_key),
    ],
) -> int:
    """Extract the user ID from a unified AuthContext.

    Use this in place of ``get_sub_from_access_token``
    on endpoints that accept both JWT and API key auth.

    Args:
        auth: Resolved AuthContext from
            validate_access_token_or_api_key.

    Returns:
        The authenticated user's ID.
    """
    return auth.user_id
