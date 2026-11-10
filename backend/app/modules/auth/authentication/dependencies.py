"""Authentication transport dependencies and refresh-cookie helpers."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Any, Self

from fastapi import Depends, Form, Header, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyCookie, HTTPAuthorizationCredentials, HTTPBearer
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

_REFRESH_TOKEN_COOKIE_BASE_NAME = "endurain_refresh_token"
#: The name the browser sends the refresh cookie back under, fixed when the server starts.
REFRESH_TOKEN_COOKIE_NAME = auth_computation.host_cookie_name(
    _REFRESH_TOKEN_COOKIE_BASE_NAME, core_config.settings.ENVIRONMENT
)
#: The ``__Host-`` prefix requires ``Path=/``; the cookie is set without a ``Domain`` attribute.
REFRESH_TOKEN_COOKIE_PATH = "/"


def get_client_type(
    client_type: Annotated[
        auth_constants.ClientType,
        Header(alias="X-Client-Type", description="The kind of client: `web` or `mobile`."),
    ],
) -> auth_constants.ClientType:
    """Return the request's client type.

    An ordinary header parameter: a missing or unknown value is a ``422``.

    Args:
        client_type: The ``X-Client-Type`` header.

    Returns:
        The client type.
    """
    return client_type


@dataclass(frozen=True)
class LogoutTarget:
    """The session a logout names, read from a refresh token that is still valid.

    Attributes:
        user_id: The token's subject.
        session_id: The session the token belongs to.
        refresh_token: The raw refresh token.
    """

    user_id: int
    session_id: str
    refresh_token: str


@dataclass(frozen=True)
class LoginFormData:
    """The checked fields of the password sign-in form.

    Attributes:
        username: The username, without surrounding whitespace.
        password: The password exactly as sent.
        code_challenge: The PKCE challenge of a mobile sign-in; ``None`` for a web sign-in.
        code_challenge_method: The PKCE method of a mobile sign-in (``S256``); ``None`` for a web sign-in.
    """

    username: str
    password: str
    code_challenge: str | None
    code_challenge_method: str | None


def _pkce_errors(
    client_type: auth_constants.ClientType, code_challenge: str | None, code_challenge_method: str | None
) -> list[dict[str, Any]]:
    """Return the validation errors of the PKCE fields of a sign-in: required for mobile, refused for web.

    Args:
        client_type: The client type of the sign-in.
        code_challenge: The ``code_challenge`` form field, if sent.
        code_challenge_method: The ``code_challenge_method`` form field, if sent.

    Returns:
        One entry per field that is missing, refused or malformed.
    """
    sent = {"code_challenge": code_challenge, "code_challenge_method": code_challenge_method}
    if client_type == auth_constants.ClientType.WEB:
        # A browser gets its refresh token as an HttpOnly cookie and has nothing to exchange.
        return [
            {"type": "extra_forbidden", "loc": ("body", name), "msg": "Not accepted from a web client"}
            for name, value in sent.items()
            if value is not None
        ]
    errors: list[dict[str, Any]] = [
        {"type": "missing", "loc": ("body", name), "msg": "Required from a mobile client"}
        for name, value in sent.items()
        if value is None
    ]
    if code_challenge is None or code_challenge_method is None:
        return errors
    try:
        auth_computation.validate_pkce_challenge(code_challenge, code_challenge_method)
    except core_exceptions.InvalidInputError as err:
        name = "code_challenge_method" if code_challenge_method != "S256" else "code_challenge"
        errors.append({"type": "value_error", "loc": ("body", name), "msg": str(err.detail)})
    return errors


#: Longest username or password the login form accepts. The longest password any form lets a user set is 256
#: characters (change and reset), so every valid credential fits; anything longer never reaches Argon2.
LOGIN_FIELD_MAX_LENGTH = 256


def reject_nul_in_login_form(
    username: Annotated[str, Form(description="The account username.")],
    password: Annotated[str, Form(description="The account password.", json_schema_extra={"format": "password"})],
    client_type: Annotated[auth_constants.ClientType, Depends(get_client_type)],
    grant_type: Annotated[
        str | None,
        Form(
            pattern="^password$",
            description="Accepted so OAuth 2 password-grant clients keep working; the only value is `password` and "
            "it is ignored.",
        ),
    ] = None,
    code_challenge: Annotated[
        str | None,
        Form(
            description="PKCE code challenge (base64url SHA-256 of the verifier). Required from a mobile client; "
            "not accepted from a web client."
        ),
    ] = None,
    code_challenge_method: Annotated[
        str | None,
        Form(description="PKCE method, always `S256`. Required from a mobile client; not accepted from a web client."),
    ] = None,
) -> LoginFormData:
    """Check the login form: no NUL character in any field, a short enough username and password, the PKCE fields.

    The username and the password are at most ``LOGIN_FIELD_MAX_LENGTH`` characters, so no oversized password
    reaches the hash.

    PostgreSQL text cannot hold NUL. The NUL middleware reads urlencoded and JSON bodies but leaves multipart
    ones streaming, and FastAPI parses this form from multipart too, so the fields are checked here.

    A mobile client must send ``code_challenge`` and ``code_challenge_method`` (``S256``) and a web client must
    send neither, so a sign-in is valid or refused before the password is looked at.

    The username loses surrounding whitespace, as the web form does; the password is kept exactly as sent.

    Args:
        username: The username form field.
        password: The password form field.
        client_type: The ``X-Client-Type`` header.
        grant_type: The ``grant_type`` form field, which is checked and then ignored.
        code_challenge: The PKCE code challenge form field.
        code_challenge_method: The PKCE method form field.

    Returns:
        The username, the password and the PKCE values.

    Raises:
        RequestValidationError: When a field holds a NUL, the username or password is too long, or the PKCE fields do
            not fit the client type (422).
    """
    errors = [
        {"type": "value_error", "loc": ("body", name), "msg": "NUL characters are not allowed"}
        for name, value in {
            "username": username,
            "password": password,
            "grant_type": grant_type,
            "code_challenge": code_challenge,
            "code_challenge_method": code_challenge_method,
        }.items()
        if isinstance(value, str) and "\x00" in value
    ]
    errors += [
        {"type": "value_error", "loc": ("body", name), "msg": f"At most {LOGIN_FIELD_MAX_LENGTH} characters"}
        for name, value in (("username", username), ("password", password))
        if len(value) > LOGIN_FIELD_MAX_LENGTH
    ]
    errors += _pkce_errors(client_type, code_challenge, code_challenge_method)
    if errors:
        raise RequestValidationError(errors)
    return LoginFormData(username.strip(), password, code_challenge, code_challenge_method)


#: The login form, with NUL characters refused, the username trimmed and the PKCE fields checked.
LoginForm = Annotated[LoginFormData, Depends(reject_nul_in_login_form)]


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
    environment: str,
) -> None:
    """Set the refresh-token cookie.

    In a deployed environment the cookie meets the ``__Host-`` rules: ``Secure``, ``Path=/`` and no ``Domain``.
    """
    clear_refresh_token_cookies(response, environment=environment)
    response.set_cookie(
        key=auth_computation.host_cookie_name(_REFRESH_TOKEN_COOKIE_BASE_NAME, environment),
        value=refresh_token,
        expires=expires_at,
        httponly=True,
        path=REFRESH_TOKEN_COOKIE_PATH,
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
    environment: str,
) -> None:
    """Clear the refresh-token cookie."""
    response.delete_cookie(
        key=auth_computation.host_cookie_name(_REFRESH_TOKEN_COOKIE_BASE_NAME, environment),
        path=REFRESH_TOKEN_COOKIE_PATH,
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
bearer_scheme = HTTPBearer(
    bearerFormat="JWT",
    description="A JWT in the `Authorization: Bearer` header: the access token, or a mobile client's refresh token on "
    "`/auth/refresh` and `/auth/logout`. The scopes an access token can carry:\n\n"
    + "\n".join(f"- `{scope}`: {description}" for scope, description in auth_constants.SCOPE_DICT.items()),
    auto_error=False,
)


def get_bearer_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> str | None:
    """Return the token of an ``Authorization: Bearer`` header.

    Args:
        credentials: The parsed header.

    Returns:
        The token, or ``None`` when the header is missing, is not a bearer one or has no token.
    """
    return credentials.credentials if credentials is not None else None


def get_csrf_token(
    csrf_token: Annotated[
        str | None, Header(alias="X-CSRF-Token", description="The CSRF token of a web session.")
    ] = None,
) -> str | None:
    """Return the ``X-CSRF-Token`` header, if the request carries one.

    Args:
        csrf_token: The header value.

    Returns:
        The CSRF token, or ``None``.
    """
    return csrf_token


cookie_refresh_token_scheme = APIKeyCookie(
    name=REFRESH_TOKEN_COOKIE_NAME, scheme_name="RefreshTokenCookie", auto_error=False
)


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
    non_cookie_refresh_token: Annotated[str | None, Depends(get_bearer_token)],
    cookie_refresh_token: Annotated[str | None, Depends(cookie_refresh_token_scheme)],
    client_type: Annotated[auth_constants.ClientType, Depends(get_client_type)],
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


# The ``get_*_from_refresh_token`` readers below check only the token's signature and read a claim. A route that
# uses one declares ``validate_refresh_token`` before it, so the token's expiry and type are already checked when a
# reader runs; ``test_refresh_token_claim_readers_follow_validation`` pins that order.
def get_sub_from_refresh_token(
    refresh_token: Annotated[str, Depends(get_refresh_token)],
    token_manager: Annotated[
        access_tokens_integration.TokenManager,
        Depends(access_tokens_integration.get_token_manager),
    ],
) -> int:
    """Return the decimal subject claim from a refresh token.

    Precondition: ``validate_refresh_token`` ran first; this reader checks only the signature.
    """
    sub = token_manager.get_token_claim(refresh_token, "sub", access_tokens_integration.TokenType.REFRESH)
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
    """Return the session identifier claim from a refresh token.

    Precondition: ``validate_refresh_token`` ran first; this reader checks only the signature.
    """
    sid = token_manager.get_token_claim(refresh_token, "sid", access_tokens_integration.TokenType.REFRESH)
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
    """Return the expiry claim of a refresh token as a timezone-aware UTC instant.

    Precondition: ``validate_refresh_token`` ran first; this reader checks only the signature.
    """
    exp = token_manager.get_token_claim(refresh_token, "exp", access_tokens_integration.TokenType.REFRESH)
    if not isinstance(exp, int):
        raise core_exceptions.InvalidTokenError("Invalid token: 'exp' claim must be an integer")
    return datetime.fromtimestamp(exp, UTC)


def get_and_return_refresh_token(
    refresh_token: Annotated[str, Depends(get_refresh_token)],
) -> str:
    """Return the resolved refresh token for downstream dependencies."""
    return refresh_token


def get_logout_target(
    non_cookie_refresh_token: Annotated[str | None, Depends(get_bearer_token)],
    cookie_refresh_token: Annotated[str | None, Depends(cookie_refresh_token_scheme)],
    client_type: Annotated[auth_constants.ClientType, Depends(get_client_type)],
    token_manager: Annotated[
        access_tokens_integration.TokenManager,
        Depends(access_tokens_integration.get_token_manager),
    ],
) -> LogoutTarget | None:
    """Read the session a logout names from the client's refresh token.

    Logout is idempotent, so a refresh token that is missing, malformed, expired or of the wrong kind is not a
    refusal: there is no session to end.

    Args:
        non_cookie_refresh_token: The refresh token of a mobile client, from the ``Authorization`` header.
        cookie_refresh_token: The refresh token of a web client, from its cookie.
        client_type: The client type.
        token_manager: Utility for validating and reading tokens.

    Returns:
        The user, session and token the refresh token names, or ``None`` when it is not a usable refresh token.
    """
    try:
        refresh_token = get_token(
            non_cookie_refresh_token, cookie_refresh_token, client_type, access_tokens_integration.TokenType.REFRESH
        )
        if refresh_token is None:
            return None
        token_manager.validate_token_expiration(refresh_token, access_tokens_integration.TokenType.REFRESH)
        return LogoutTarget(
            get_sub_from_refresh_token(refresh_token, token_manager),
            get_sid_from_refresh_token(refresh_token, token_manager),
            refresh_token,
        )
    except core_exceptions.UnauthenticatedError as err:
        logger.debug(
            "Logout token not usable: <detail>",
            extra=core_logger.context(credential="refresh_token", detail=err.detail),
        )
        return None
