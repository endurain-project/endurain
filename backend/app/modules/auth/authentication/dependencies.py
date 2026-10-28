"""Authentication transport dependencies and refresh-cookie helpers."""

import logging
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyCookie, APIKeyHeader, OAuth2PasswordBearer
from joserfc.errors import MissingClaimError

import core.config as core_config
import core.exceptions as core_exceptions
import core.logger as core_logger
import modules.auth.access_tokens.integration_service as auth_token_manager
import modules.auth.constants as auth_constants

REFRESH_TOKEN_COOKIE_NAME = "endurain" + "_refresh_token"
REFRESH_TOKEN_COOKIE_PATH = "/api/v1/" + "auth"
LEGACY_REFRESH_TOKEN_COOKIE_PATHS = ("/",)
REFRESH_TOKEN_COOKIE_CLEAR_PATHS = (*LEGACY_REFRESH_TOKEN_COOKIE_PATHS, REFRESH_TOKEN_COOKIE_PATH)

header_client_type_scheme = APIKeyHeader(name="X-Client-Type", auto_error=False)
header_csrf_token_scheme = APIKeyHeader(name="X-CSRF-Token", auto_error=False)


class ClearRefreshTokenCookieHTTPException(HTTPException):
    """HTTP exception that clears refresh-token cookies."""


def _secure_cookie(environment: str) -> bool:
    """Return whether the configured environment requires Secure cookies."""
    return environment in {"production", "demo"}


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
        secure=_secure_cookie(environment),
        samesite="strict",
    )


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
            secure=_secure_cookie(environment),
            httponly=True,
            samesite="strict",
        )


async def clear_refresh_token_cookie_exception_handler(
    request: Request,
    exc: ClearRefreshTokenCookieHTTPException,
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

    def make_not_authenticated_error(self) -> HTTPException:
        """Return the client-facing error for a missing client type."""
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required X-Client-Type header (web or mobile)",
        )


header_client_type_scheme = ClientTypeHeader(name="X-Client-Type")
header_csrf_token_scheme = APIKeyHeader(name="X-CSRF-Token", auto_error=False)
cookie_refresh_token_scheme = APIKeyCookie(name=REFRESH_TOKEN_COOKIE_NAME, auto_error=False)


def get_token(
    non_cookie_token: str | None,
    cookie_token: str | None,
    client_type: str,
    token_type: auth_token_manager.TokenType,
) -> str | None:
    """Select a credential source according to client and token type."""
    if token_type == auth_token_manager.TokenType.ACCESS:
        if non_cookie_token is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Access token missing from Authorization header",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return non_cookie_token
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
        auth_token_manager.TokenType.REFRESH,
    )


def validate_refresh_token(
    refresh_token: Annotated[str, Depends(get_refresh_token)],
    token_manager: Annotated[
        auth_token_manager.TokenManager,
        Depends(auth_token_manager.get_token_manager),
    ],
) -> None:
    """Validate refresh-token expiry and clear stale pre-upgrade cookies."""
    try:
        token_manager.validate_token_expiration(refresh_token, auth_token_manager.TokenType.REFRESH)
    except HTTPException as http_err:
        log_level = logging.DEBUG if "expired" in http_err.detail.lower() else logging.ERROR
        logger.log(
            log_level,
            f"Refresh token validation failed: {http_err.detail}",
            exc_info=http_err,
            extra=core_logger.context(credential="refresh_token"),
        )
        if isinstance(http_err.__cause__, MissingClaimError):
            raise ClearRefreshTokenCookieHTTPException(
                status_code=http_err.status_code,
                detail=http_err.detail,
                headers=http_err.headers,
            ) from http_err
        raise
    except core_exceptions.DomainError as err:
        raise HTTPException(status_code=err.status_code, detail=err.detail) from err
    except Exception as err:
        logger.error(
            f"Unexpected error during refresh token validation: {type(err).__name__}",
            exc_info=err,
            extra=core_logger.context(credential="refresh_token"),
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
    """Return the decimal subject claim from a refresh token."""
    sub = token_manager.get_token_claim(refresh_token, "sub")
    if not isinstance(sub, str) or not sub.isascii() or not sub.isdecimal():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: 'sub' claim must be a decimal string",
        )
    return int(sub)


def get_sid_from_refresh_token(
    refresh_token: Annotated[str, Depends(get_refresh_token)],
    token_manager: Annotated[
        auth_token_manager.TokenManager,
        Depends(auth_token_manager.get_token_manager),
    ],
) -> str:
    """Return the session identifier claim from a refresh token."""
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
    """Return the resolved refresh token for downstream dependencies."""
    return refresh_token
