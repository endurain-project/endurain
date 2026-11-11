"""Public login, refresh, MFA-login and logout routes."""

from datetime import datetime
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Request,
    Response,
)

import core.cache_control as core_cache_control
import core.config as core_config
import core.dependencies as core_dependencies
import core.exceptions as core_exceptions
import core.logger as core_logger
import core.network as core_network
import core.openapi_contract as core_openapi_contract
import core.rate_limit as core_rate_limit
import modules.auth.access_tokens.integration_service as access_tokens_integration
import modules.auth.authentication.dependencies as authentication_dependencies
import modules.auth.authentication.failed_login_store as failed_login_store
import modules.auth.authentication.pending_password_change_store as pending_password_change_store
import modules.auth.authentication.refresh_service as auth_refresh_service
import modules.auth.authentication.schema as auth_schema
import modules.auth.authentication.service as auth_service
import modules.auth.constants as auth_constants
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.known_devices.dependencies as known_devices_dependencies
import modules.auth.mfa.dependencies as mfa_dependencies

logger = core_logger.get_logger(__name__)

# Define the API router
router = APIRouter()


@router.post(
    "/login",
    response_model=auth_schema.LoginRead,
    responses={
        200: {"headers": core_openapi_contract.NO_STORE_RESPONSE_HEADERS},
        401: {"description": "The username or password is wrong, or the account may not sign in."},
    },
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def login_for_access_token(
    response: Response,
    request: Request,
    form_data: authentication_dependencies.LoginForm,
    client_type: Annotated[auth_constants.ClientType, Depends(authentication_dependencies.get_client_type)],
    failed_attempts: Annotated[
        failed_login_store.FailedLoginStore,
        Depends(failed_login_store.get_failed_login_attempts),
    ],
    pending_mfa_store: Annotated[
        mfa_dependencies.PendingMFAStore,
        Depends(mfa_dependencies.get_pending_mfa_store),
    ],
    password_change_store: Annotated[
        pending_password_change_store.PendingPasswordChangeStore,
        Depends(pending_password_change_store.get_pending_password_change_store),
    ],
    password_hasher: Annotated[
        credentials_integration.PasswordHasher,
        Depends(credentials_integration.get_password_hasher),
    ],
    token_manager: Annotated[
        access_tokens_integration.TokenManager,
        Depends(access_tokens_integration.get_token_manager),
    ],
    db: core_dependencies.DbSession,
    device_id: known_devices_dependencies.DeviceId,
) -> auth_schema.LoginRead:
    """Handles user login and access token generation, including Multi-Factor Authentication (MFA) flow.

    Protection Mechanisms:
    - Rate limiting: 10 requests per minute per IP (SENSITIVE tier, prevents DoS attacks)
    - Progressive lockout: Per-username and client-network tracking (an IPv6 address counts by its /64) prevents
      targeted brute-force without letting one client lock the account for everyone:
      * 5 failures: 5 minute lockout
      * 10 failures: 30 minute lockout
      * 20 failures: 24 hour lockout
    - Account lock: 100 failed password sign-ins in a row for one account, from any addresses, lock the account for
      30 days. A device the account has signed in from since its last security change is not held by it. A successful
      sign-in, a completed password reset, a password change or an administrator setting the password lifts it.

    This endpoint authenticates a user using provided credentials, checks if the user is active,
    and determines if MFA is required. If MFA is enabled for the user, it stores the pending login
    and returns an MFA-required response. Otherwise, it completes the login process and returns
    the required information.

    PKCE (mobile):
    - A mobile client sends the form fields code_challenge and code_challenge_method (S256), and a web client sends
      neither (422)
    - A mobile sign-in never returns tokens: it returns a session_id to exchange for tokens at
      /auth/sessions/{session_id}/tokens with the PKCE verifier

    Args:
        response: The HTTP response object
        request: The HTTP request object
        form_data: Form data containing username, password and, for a mobile client, the PKCE challenge
        client_type: The type of client making the request ("web" or "mobile")
        failed_attempts: Failed login attempts tracker for progressive lockout
        pending_mfa_store: Store for pending MFA logins
        password_change_store: Store for pending password changes
        password_hasher: The password hasher instance used for verifying passwords
        token_manager: The token manager instance used for token operations
        db: Database session
        device_id: Device id from the browser's device cookie or the mobile app's X-Device-Id header, or None when
            the client sent no valid one

    Returns:
        The next step of the sign-in:
            - If MFA is required, an MFA-required response
            - If an administrator set the password, a password-change response and no session
            - Otherwise, for a mobile client the session_id to exchange for tokens, for a web client the tokens

    Raises:
        HTTPException: If authentication fails, user is inactive, or account is locked
    """
    outcome = auth_service.login_for_access_token(
        core_network.get_ip_address(request),
        core_network.get_user_agent(request),
        form_data.username,
        form_data.password,
        client_type,
        failed_attempts,
        pending_mfa_store,
        password_hasher,
        token_manager,
        db,
        code_challenge=form_data.code_challenge,
        code_challenge_method=form_data.code_challenge_method,
        password_change_store=password_change_store,
        device_id=device_id,
    )
    return authentication_dependencies.deliver_auth_outcome(response, outcome)


@router.post(
    "/mfa/verify",
    response_model=auth_schema.MFAVerifyRead,
    responses={
        200: {"headers": core_openapi_contract.NO_STORE_RESPONSE_HEADERS},
        400: {"description": "The MFA code is wrong and the sign-in challenge is still live."},
        401: {
            "description": "The sign-in challenge is unknown, expired, ended after three wrong codes, or presented "
            "from another client network or client type, so the client signs in again at `POST /auth/login`; "
            "or its account can no longer sign in."
        },
        403: {"description": "The account is no longer active."},
    },
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def verify_mfa_and_login(
    response: Response,
    request: Request,
    mfa_request: auth_schema.MFALoginRequest,
    client_type: Annotated[auth_constants.ClientType, Depends(authentication_dependencies.get_client_type)],
    failed_attempts: Annotated[
        failed_login_store.FailedLoginStore,
        Depends(failed_login_store.get_failed_login_attempts),
    ],
    pending_mfa_store: Annotated[
        mfa_dependencies.PendingMFAStore,
        Depends(mfa_dependencies.get_pending_mfa_store),
    ],
    password_change_store: Annotated[
        pending_password_change_store.PendingPasswordChangeStore,
        Depends(pending_password_change_store.get_pending_password_change_store),
    ],
    password_hasher: Annotated[
        credentials_integration.PasswordHasher,
        Depends(credentials_integration.get_password_hasher),
    ],
    token_manager: Annotated[
        access_tokens_integration.TokenManager,
        Depends(access_tokens_integration.get_token_manager),
    ],
    db: core_dependencies.DbSession,
    device_id: known_devices_dependencies.DeviceId,
) -> auth_schema.MFAVerifyRead:
    """Verify MFA code and complete login process.

    This endpoint verifies the MFA code for a pending login and completes
    the authentication process if the code is valid. When an administrator set the
    account's password, the answer is the password-change step instead of a session.

    The step carries no PKCE values: the password step recorded them with the login. The challenge lives five
    minutes, is accepted only from the client network (an IPv4 address or an IPv6 /64) and client type of the
    password step, and ends after three wrong codes. A wrong code is answered 400; a challenge that is unknown,
    expired, ended or presented from another network or client type is answered 401 and the client signs in again.
    A mobile client gets a session_id to exchange for tokens at /auth/sessions/{session_id}/tokens, never tokens.

    Args:
        response: The HTTP response object
        request: The HTTP request object
        failed_attempts: Failed login attempts tracker for progressive lockout
        mfa_request: MFA login request containing username and MFA code
        client_type: The type of client making the request ("web" or "mobile")
        pending_mfa_store: Store for pending MFA logins
        password_change_store: Store for pending password changes
        password_hasher: The password hasher instance used for verifying passwords
        token_manager: The token manager instance used for token operations
        db: Database session
        device_id: Device id from the browser's device cookie or the mobile app's X-Device-Id header, or None when
            the client sent no valid one

    Returns:
        The tokens of a web client, the session to exchange for a mobile client, or the password-change response

    Raises:
        HTTPException: If the challenge is dead, MFA code is invalid, or user not found
    """
    outcome = auth_service.verify_mfa_and_login(
        core_network.get_ip_address(request),
        core_network.get_user_agent(request),
        mfa_request,
        client_type,
        failed_attempts,
        pending_mfa_store,
        password_hasher,
        token_manager,
        db,
        password_change_store=password_change_store,
        device_id=device_id,
    )
    return authentication_dependencies.deliver_auth_outcome(response, outcome)


@router.post(
    "/refresh",
    response_model=(auth_schema.TokenWebRead | auth_schema.TokenMobileRead),
    responses={200: {"headers": core_openapi_contract.NO_STORE_RESPONSE_HEADERS}},
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def refresh_token(
    response: Response,
    request: Request,
    _validate_refresh_token: Annotated[None, Depends(authentication_dependencies.validate_refresh_token)],
    token_user_id: Annotated[
        int,
        Depends(authentication_dependencies.get_sub_from_refresh_token),
    ],
    token_session_id: Annotated[
        str,
        Depends(authentication_dependencies.get_sid_from_refresh_token),
    ],
    refresh_token_value: Annotated[
        str,
        Depends(authentication_dependencies.get_and_return_refresh_token),
    ],
    refresh_token_exp: Annotated[
        datetime,
        Depends(authentication_dependencies.get_exp_from_refresh_token),
    ],
    password_hasher: Annotated[
        credentials_integration.PasswordHasher,
        Depends(credentials_integration.get_password_hasher),
    ],
    token_manager: Annotated[
        access_tokens_integration.TokenManager,
        Depends(access_tokens_integration.get_token_manager),
    ],
    db: core_dependencies.DbSession,
    client_type: Annotated[auth_constants.ClientType, Depends(authentication_dependencies.get_client_type)],
    x_csrf_token: Annotated[str | None, Depends(authentication_dependencies.get_csrf_token)] = None,
) -> auth_schema.TokenRead:
    r"""Handles the refresh token process for user sessions.

    This endpoint validates the provided refresh token, checks session status,
    validates the CSRF token (web clients only), and issues new tokens. A web client sends its refresh cookie and no
    body. A mobile client sends its refresh token in the JSON body as refresh_token (RFC 6749 section 6), never in
    the Authorization header; a body token sent by a web client is not read.

    OAuth 2.1 Bootstrap Pattern for Page Reload:
        On page reload, in-memory tokens are lost but httpOnly cookie persists.
        - If no CSRF header: Allow refresh (page reload scenario)
        - If CSRF header provided: Validate it (legitimate request with cached token)
        - Security: httpOnly cookie + SameSite=Strict prevents CSRF at browser level
        - CSRF validation adds defense-in-depth but is not the primary protection

    Args:
        response: The HTTP response object.
        request: The HTTP request object.
        _validate_refresh_token: Dependency to validate the refresh token.
        token_user_id: User ID extracted from the refresh token.
        token_session_id: Session ID extracted from the refresh token.
        refresh_token_value: The raw refresh token value.
        refresh_token_exp: Expiry of the presented refresh token.
        password_hasher: Utility for verifying token hashes.
        token_manager: Utility for creating tokens.
        db: Database session.
        client_type: Client type (\"web\" or \"mobile\").
        x_csrf_token: CSRF token header (web clients only, optional on page reload).

    Returns:
        dict: Contains session_id, access_token, csrf_token, token_type, expires_in, refresh_token_expires_in.

    Raises:
        HTTPException: If session not found, refresh token invalid,
                       user is inactive, or CSRF token is invalid (when provided).
    """
    try:
        outcome = auth_refresh_service.refresh_token(
            core_network.get_ip_address(request),
            core_network.get_user_agent(request),
            token_user_id,
            token_session_id,
            refresh_token_value,
            refresh_token_exp,
            password_hasher,
            token_manager,
            client_type,
            db,
            x_csrf_token,
        )
    except core_exceptions.UnauthenticatedError as err:
        raise authentication_dependencies.ClearRefreshTokenCookieError.refusing(err) from err
    return authentication_dependencies.deliver_auth_outcome(response, outcome)


@router.post(
    "/logout",
    response_model=auth_schema.LogoutRead,
    responses={200: {"headers": core_openapi_contract.NO_STORE_RESPONSE_HEADERS}},
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def logout(
    response: Response,
    request: Request,
    target: Annotated[
        authentication_dependencies.LogoutTarget | None, Depends(authentication_dependencies.get_logout_target)
    ],
    client_type: Annotated[auth_constants.ClientType, Depends(authentication_dependencies.get_client_type)],
    password_hasher: Annotated[
        credentials_integration.PasswordHasher,
        Depends(credentials_integration.get_password_hasher),
    ],
    db: core_dependencies.DbSession,
) -> auth_schema.LogoutRead:
    """Log out a user by deleting their session, and answer where to end it at the identity provider.

    A session that signed in through an identity provider whose discovery document names an end-session endpoint
    (OpenID Connect RP-Initiated Logout 1.0) gets idp_logout_url, the provider's URL carrying the ID token as a hint
    and client_id. A web client also gets the login page as post_logout_redirect_uri, which the provider must have
    registered; a mobile client gets none. Any other session gets null. When the provider cannot be reached for
    its endpoint, the session still ends and idp_logout_url is null: the provider session stays. The answer is never
    cached, because the URL carries the ID token. A web client sends the `X-CSRF-Token` header, and without it the
    answer is 403.

    Logout is idempotent. A refresh token that is missing, malformed, expired, revoked or whose session is gone ends
    nothing and gets the same 200 answer with a null idp_logout_url, and a web client's refresh cookie is cleared
    all the same.

    A mobile client sends its refresh token in the JSON body as refresh_token (RFC 7009), never in the Authorization
    header. A web client sends its refresh cookie and no body; a body token sent by a web client is not read.

    Args:
        response: The HTTP response object to modify cookies.
        request: The HTTP request object, read by the rate limiter.
        target: The session the refresh token names, or None when the token is not usable.
        client_type: The type of client ("web" or "mobile").
        password_hasher: Utility for verifying the refresh token.
        db: Database session for CRUD operations.

    Returns:
        The identity provider's end-session URL, or None when there is none.
    """
    idp_logout_url = None
    if target is not None:
        idp_logout_url = auth_service.logout(
            target.session_id,
            target.refresh_token,
            target.user_id,
            password_hasher,
            client_type,
            db,
        )
    core_cache_control.set_no_store(response)
    if client_type == auth_constants.ClientType.WEB:
        authentication_dependencies.clear_refresh_token_cookies(response, environment=core_config.settings.ENVIRONMENT)
    return auth_schema.LogoutRead(idp_logout_url=idp_logout_url)
