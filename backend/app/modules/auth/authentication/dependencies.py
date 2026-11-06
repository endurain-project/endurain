"""Authentication transport dependencies and refresh-cookie helpers."""

from datetime import UTC, datetime
from typing import Annotated, Self

from fastapi import Depends, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyCookie, APIKeyHeader, OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel

import core.cache_control as core_cache_control
import core.config as core_config
import core.exceptions as core_exceptions
import core.logger as core_logger
import modules.auth.access_tokens.integration_service as access_tokens_integration
import modules.auth.authentication.schema as auth_schema
import modules.auth.computation as auth_computation
import modules.auth.constants as auth_constants
import modules.auth.known_devices.dependencies as known_devices_dependencies

REFRESH_TOKEN_COOKIE_NAME = "endurain" + "_refresh_token"
REFRESH_TOKEN_COOKIE_PATH = "/api/v1/" + "auth"
LEGACY_REFRESH_TOKEN_COOKIE_PATHS = ("/",)
REFRESH_TOKEN_COOKIE_CLEAR_PATHS = (*LEGACY_REFRESH_TOKEN_COOKIE_PATHS, REFRESH_TOKEN_COOKIE_PATH)


def reject_nul_in_login_form(form_data: Annotated[OAuth2PasswordRequestForm, Depends()]) -> OAuth2PasswordRequestForm:
    """Refuse a NUL character in any field of the login form and trim the username.

    PostgreSQL text cannot hold NUL. The NUL middleware reads urlencoded and JSON bodies but leaves multipart
    ones streaming, and FastAPI parses this form from multipart too, so the fields are checked here.

    The username loses surrounding whitespace, as the web form does; the password is kept exactly as sent.

    Args:
        form_data: The parsed login form.

    Returns:
        The form, with the username trimmed.

    Raises:
        RequestValidationError: When a field holds a NUL (422).
    """
    errors = [
        {"type": "value_error", "loc": ("body", name), "msg": "NUL characters are not allowed"}
        for name, value in vars(form_data).items()
        if isinstance(value, str) and "\x00" in value
    ]
    if isinstance(form_data.scopes, list) and any("\x00" in scope for scope in form_data.scopes):
        errors.append({"type": "value_error", "loc": ("body", "scope"), "msg": "NUL characters are not allowed"})
    if errors:
        raise RequestValidationError(errors)
    form_data.username = form_data.username.strip()
    return form_data


#: The login form, with NUL characters refused and the username trimmed.
LoginForm = Annotated[OAuth2PasswordRequestForm, Depends(reject_nul_in_login_form)]


class ClearRefreshTokenCookieError(core_exceptions.InvalidTokenError):
    """An invalid refresh token whose problem response also clears the refresh-token cookies."""

    @classmethod
    def refusing(cls, err: core_exceptions.UnauthenticatedError) -> Self:
        """Wrap an authentication refusal so the browser drops its refresh cookie.

        Args:
            err: The refusal.

        Returns:
            The invalid-token error carrying the refusal's message.
        """
        return cls(err.detail)


def set_refresh_token_cookie(
    response: Response,
    refresh_token: str,
    expires_at: datetime,
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


def deliver_auth_outcome[BodyT: BaseModel](response: Response, outcome: auth_schema.AuthOutcome[BodyT]) -> BodyT:
    """Set the outcome's refresh and device cookies on the response and return its body.

    The response carries ``Cache-Control: no-store`` and ``Pragma: no-cache`` so no cache keeps the tokens
    (RFC 6749 section 5.1).

    Args:
        response: Response that receives the cookies.
        outcome: Result of an authentication workflow.

    Returns:
        The outcome's response body.
    """
    core_cache_control.set_no_store(response)
    if outcome.refresh_cookie is not None:
        set_refresh_token_cookie(
            response,
            outcome.refresh_cookie.value,
            outcome.refresh_cookie.expires_at,
            environment=core_config.settings.ENVIRONMENT,
        )
    if outcome.device_id is not None:
        known_devices_dependencies.set_device_cookie(response, outcome.device_id)
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
    """Render an invalid-token problem and clear refresh-token cookies."""
    response = core_exceptions.build_problem_response(
        request=request,
        status_code=exc.status_code,
        code=exc.code,
        title=exc.title,
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

    async def __call__(self, request: Request) -> auth_constants.ClientType:
        """Return the request's client type.

        Args:
            request: The incoming request.

        Returns:
            The ``X-Client-Type`` header's client type.

        Raises:
            InvalidInputError: When the header is missing, empty or neither ``web`` nor ``mobile``.
        """
        value = request.headers.get(self.model.name)
        try:
            return auth_constants.ClientType(value or "")
        except ValueError:
            raise core_exceptions.InvalidInputError("Missing or invalid X-Client-Type header (web or mobile)") from None


header_client_type_scheme = ClientTypeHeader(name="X-Client-Type")
header_csrf_token_scheme = APIKeyHeader(name="X-CSRF-Token", auto_error=False)
cookie_refresh_token_scheme = APIKeyCookie(name=REFRESH_TOKEN_COOKIE_NAME, auto_error=False)


def get_token(
    non_cookie_token: str | None,
    cookie_token: str | None,
    client_type: auth_constants.ClientType,
    token_type: access_tokens_integration.TokenType,
) -> str | None:
    """Select a credential source according to client and token type."""
    if token_type == access_tokens_integration.TokenType.ACCESS:
        if non_cookie_token is None:
            raise core_exceptions.InvalidTokenError("Access token missing from Authorization header", scheme="Bearer")
        return non_cookie_token
    if token_type == access_tokens_integration.TokenType.REFRESH:
        if client_type == auth_constants.ClientType.WEB:
            if cookie_token is None:
                raise core_exceptions.InvalidTokenError("Refresh token missing from cookie", scheme="Bearer")
            return cookie_token
        if client_type == auth_constants.ClientType.MOBILE:
            if non_cookie_token is None:
                raise core_exceptions.InvalidTokenError(
                    "Refresh token missing from Authorization header", scheme="Bearer"
                )
            return non_cookie_token
    logger.warning("Token lookup refused: unsupported client type or token type")
    raise core_exceptions.PermissionDeniedError("Invalid client type or token type")


def get_refresh_token(
    non_cookie_refresh_token: Annotated[str | None, Depends(oauth2_scheme)],
    cookie_refresh_token: str | None = Depends(cookie_refresh_token_scheme),
    client_type: auth_constants.ClientType = Depends(header_client_type_scheme),
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
    """Validate refresh-token expiry; a refused token also clears the refresh cookies."""
    try:
        token_manager.validate_token_expiration(refresh_token, access_tokens_integration.TokenType.REFRESH)
    except core_exceptions.DomainError as http_err:
        logger.debug(
            "Refresh token validation failed: <detail>",
            extra=core_logger.context(credential="refresh_token", detail=http_err.detail),
        )
        if isinstance(http_err, core_exceptions.UnauthenticatedError):
            raise ClearRefreshTokenCookieError.refusing(http_err) from http_err
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
        raise core_exceptions.InvalidTokenError("Invalid token: 'sub' claim must be a decimal string")
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
        raise core_exceptions.InvalidTokenError("Invalid token: 'sid' claim must be a string")
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
        raise core_exceptions.InvalidTokenError("Invalid token: 'exp' claim must be an integer")
    return datetime.fromtimestamp(exp, UTC)


def get_and_return_refresh_token(
    refresh_token: Annotated[str, Depends(get_refresh_token)],
) -> str:
    """Return the resolved refresh token for downstream dependencies."""
    return refresh_token
