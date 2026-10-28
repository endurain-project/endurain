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
    APIKeyHeader,
    OAuth2PasswordBearer,
)

import core.config as core_config
import core.exceptions as core_exceptions
import core.logger as core_logger
import modules.auth.access_tokens.integration_service as auth_token_manager
import modules.auth.constants as auth_constants
import modules.auth.identity_service as auth_identity_service
from modules.auth.authentication.dependencies import (
    ClientTypeHeader,
    cookie_refresh_token_scheme,
    get_and_return_refresh_token,
    get_refresh_token,
    get_sid_from_refresh_token,
    get_sub_from_refresh_token,
    header_client_type_scheme,
    header_csrf_token_scheme,
    validate_refresh_token,
)
from modules.auth.principal import AccessTokenCred, Principal

__all__ = [
    "ClientTypeHeader",
    "cookie_refresh_token_scheme",
    "get_and_return_refresh_token",
    "get_refresh_token",
    "get_sid_from_refresh_token",
    "get_sub_from_refresh_token",
    "header_client_type_scheme",
    "header_csrf_token_scheme",
    "validate_refresh_token",
]

logger = core_logger.get_logger(__name__)

# Define the OAuth2 scheme for handling bearer tokens
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/login",
    scopes=auth_constants.SCOPE_DICT,
    auto_error=False,
)


# Define the API key header for the client type

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

# Define the API key cookie for the refresh token


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
    except core_exceptions.DomainError as err:
        raise HTTPException(status_code=err.status_code, detail=err.detail) from err
    except Exception as err:
        logger.error(
            f"Unexpected error during access token validation: {type(err).__name__}",
            exc_info=err,
            extra=core_logger.context(credential="access_token"),
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
        logger.warning(
            "API key supplied via query string (?api_key=). "
            "This is a security risk: credentials appear in access logs "
            "and browser history. Set X-API-Key header instead."
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
