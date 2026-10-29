"""Authentication transport dependencies and refresh-cookie helpers."""

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import Depends, Request, Response
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyCookie, APIKeyHeader, OAuth2PasswordBearer
from joserfc.errors import MissingClaimError

import core.config as core_config
import core.exceptions as core_exceptions
import core.logger as core_logger
import modules.auth.access_tokens.integration_service as access_tokens_integration
import modules.auth.authentication.schema as auth_schema
import modules.auth.computation as auth_computation
import modules.auth.constants as auth_constants

REFRESH_TOKEN_COOKIE_NAME = "endurain" + "_refresh_token"
REFRESH_TOKEN_COOKIE_PATH = "/api/v1/" + "auth"
LEGACY_REFRESH_TOKEN_COOKIE_PATHS = ("/",)
REFRESH_TOKEN_COOKIE_CLEAR_PATHS = (*LEGACY_REFRESH_TOKEN_COOKIE_PATHS, REFRESH_TOKEN_COOKIE_PATH)


class ClearRefreshTokenCookieError(core_exceptions.UnauthenticatedError):
    """Authentication error that clears refresh-token cookies."""


def set_refresh_token_cookie(
    response: Response,
    refresh_token: str,
    expires_at,
    *,
    cookie_name: str = REFRESH_TOKEN_COOKIE_NAME,
    cookie_path: str = REFRESH_TOKEN_COOKIE_PATH,
    environment: str,
) -> None:
    """Set the refresh-token cookie with the configured attributes."""
    clear_refresh_token_cookies(response, cookie_name=cookie_name, environment=environment)
    response.set_cookie(
        key=cookie_name,
        value=refresh_token,
        expires=expires_at,
        httponly=True,
        path=cookie_path,
        secure=auth_computation.secure_cookie(environment),
        samesite="strict",
    )


def deliver_auth_outcome(response: Response, outcome: auth_schema.AuthOutcome) -> Any:
    """Set the outcome's refresh cookie on the response and return its body.

    Args:
        response: Response that receives the refresh cookie.
        outcome: Result of an authentication workflow.

    Returns:
        The outcome's response body.
    """
    if outcome.refresh_cookie is not None:
        set_refresh_token_cookie(
            response,
            outcome.refresh_cookie.value,
            outcome.refresh_cookie.expires_at,
            environment=core_config.settings.ENVIRONMENT,
        )
    return outcome.body


def clear_refresh_token_cookies(
    response: Response,
    *,
    cookie_name: str = REFRESH_TOKEN_COOKIE_NAME,
    cookie_paths: tuple[str, ...] = REFRESH_TOKEN_COOKIE_CLEAR_PATHS,
    environment: str,
) -> None:
    """Clear the refresh-token cookie on all supported paths."""
    for path in cookie_paths:
        response.delete_cookie(
            key=cookie_name,
            path=path,
            secure=auth_computation.secure_cookie(environment),
            httponly=True,
            samesite="strict",
        )


async def clear_refresh_token_cookie_exception_handler(
    request: Request,
    exc: ClearRefreshTokenCookieError,
) -> JSONResponse:
    """Render an authentication failure and clear refresh-token cookies."""
    response = core_exceptions.build_problem_response(
        request=request,
        status_code=exc.status_code,
        code="authentication-failed",
        title="Unauthorized",
        detail=str(exc.detail),
        headers=exc.headers,
    )
    clear_refresh_token_cookies(response, environment=core_config.settings.ENVIRONMENT)
    return response


logger = core_logger.get_logger(__name__)
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/login",
    scopes=auth_constants.SCOPE_DICT,
    auto_error=False,
)


class ClientTypeHeader(APIKeyHeader):
    """Required X-Client-Type header that reports missing input as a 400."""

    def make_not_authenticated_error(self) -> core_exceptions.InvalidInputError:
        """Return the client-facing error for a missing client type."""
        return core_exceptions.InvalidInputError("Missing required X-Client-Type header (web or mobile)")


header_client_type_scheme = ClientTypeHeader(name="X-Client-Type")
header_csrf_token_scheme = APIKeyHeader(name="X-CSRF-Token", auto_error=False)
cookie_refresh_token_scheme = APIKeyCookie(name=REFRESH_TOKEN_COOKIE_NAME, auto_error=False)


def get_token(
    non_cookie_token: str | None,
    cookie_token: str | None,
    client_type: str,
    token_type: access_tokens_integration.TokenType,
) -> str | None:
    """Select a credential source according to client and token type."""
    if token_type == access_tokens_integration.TokenType.ACCESS:
        if non_cookie_token is None:
            raise core_exceptions.UnauthenticatedError("Access token missing from Authorization header")
        return non_cookie_token
    if token_type == access_tokens_integration.TokenType.REFRESH:
        if client_type == "web":
            if cookie_token is None:
                raise core_exceptions.UnauthenticatedError("Refresh token missing from cookie")
            return cookie_token
        if client_type == "mobile":
            if non_cookie_token is None:
                raise core_exceptions.UnauthenticatedError("Refresh token missing from Authorization header")
            return non_cookie_token
    logger.warning("Token lookup refused: unsupported client type or token type")
    raise core_exceptions.PermissionDeniedError("Invalid client type or token type")


def get_refresh_token(
    non_cookie_refresh_token: Annotated[str | None, Depends(oauth2_scheme)],
    cookie_refresh_token: str | None = Depends(cookie_refresh_token_scheme),
    client_type: str = Depends(header_client_type_scheme),
) -> str | None:
    """Resolve the refresh token from the client-appropriate location."""
    return get_token(
        non_cookie_refresh_token,
        cookie_refresh_token,
        client_type,
        access_tokens_integration.TokenType.REFRESH,
    )


def validate_refresh_token(
    refresh_token: Annotated[str, Depends(get_refresh_token)],
    token_manager: Annotated[
        access_tokens_integration.TokenManager,
        Depends(access_tokens_integration.get_token_manager),
    ],
) -> None:
    """Validate refresh-token expiry and clear stale pre-upgrade cookies."""
    try:
        token_manager.validate_token_expiration(refresh_token, access_tokens_integration.TokenType.REFRESH)
    except core_exceptions.DomainError as http_err:
        logger.debug(
            "Refresh token validation failed: <detail>",
            extra=core_logger.context(credential="refresh_token", detail=http_err.detail),
        )
        if isinstance(http_err.__cause__, MissingClaimError):
            raise ClearRefreshTokenCookieError(http_err.detail) from http_err
        raise
    except Exception as err:
        logger.debug(
            "Unexpected error during refresh token validation: <__name__>",
            exc_info=err,
            extra=dict(
                {**core_logger.context(credential="refresh_token"), **core_logger.context(__name__=type(err).__name__)}
            ),
        )
        raise core_exceptions.ProcessingError("Internal server error during token validation") from err


def get_sub_from_refresh_token(
    refresh_token: Annotated[str, Depends(get_refresh_token)],
    token_manager: Annotated[
        access_tokens_integration.TokenManager,
        Depends(access_tokens_integration.get_token_manager),
    ],
) -> int:
    """Return the decimal subject claim from a refresh token."""
    sub = token_manager.get_token_claim(refresh_token, "sub")
    if not isinstance(sub, str) or not sub.isascii() or not sub.isdecimal():
        raise core_exceptions.UnauthenticatedError("Invalid token: 'sub' claim must be a decimal string")
    return int(sub)


def get_sid_from_refresh_token(
    refresh_token: Annotated[str, Depends(get_refresh_token)],
    token_manager: Annotated[
        access_tokens_integration.TokenManager,
        Depends(access_tokens_integration.get_token_manager),
    ],
) -> str:
    """Return the session identifier claim from a refresh token."""
    sid = token_manager.get_token_claim(refresh_token, "sid")
    if not isinstance(sid, str):
        raise core_exceptions.UnauthenticatedError("Invalid token: 'sid' claim must be a string")
    return sid


def get_exp_from_refresh_token(
    refresh_token: Annotated[str, Depends(get_refresh_token)],
    token_manager: Annotated[
        access_tokens_integration.TokenManager,
        Depends(access_tokens_integration.get_token_manager),
    ],
) -> datetime:
    """Return the expiry claim of a refresh token as a timezone-aware UTC instant."""
    exp = token_manager.get_token_claim(refresh_token, "exp")
    if not isinstance(exp, int):
        raise core_exceptions.UnauthenticatedError("Invalid token: 'exp' claim must be an integer")
    return datetime.fromtimestamp(exp, UTC)


def get_and_return_refresh_token(
    refresh_token: Annotated[str, Depends(get_refresh_token)],
) -> str:
    """Return the resolved refresh token for downstream dependencies."""
    return refresh_token
