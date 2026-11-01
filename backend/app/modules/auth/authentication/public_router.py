"""Public login, refresh, MFA-login and logout routes."""

from collections.abc import Callable
from datetime import datetime
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Query,
    Request,
    Response,
)
from fastapi.security import OAuth2PasswordRequestForm

import core.config as core_config
import core.dependencies as core_dependencies
import core.logger as core_logger
import core.network as core_network
import core.rate_limit as core_rate_limit
import modules.auth.access_tokens.integration_service as access_tokens_integration
import modules.auth.authentication.dependencies as authentication_dependencies
import modules.auth.authentication.failed_login_store as failed_login_store
import modules.auth.authentication.schema as auth_schema
import modules.auth.authentication.service as auth_service
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.mfa.dependencies as mfa_dependencies

logger = core_logger.get_logger(__name__)

# Define the API router
router = APIRouter()


@router.post(
    "/login",
    response_model=(
        auth_schema.MFARequiredRead
        | auth_schema.MobileSessionRead
        | auth_schema.TokenWebRead
        | auth_schema.TokenMobileRead
    ),
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def login_for_access_token(
    response: Response,
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    client_type: Annotated[str, Depends(authentication_dependencies.header_client_type_scheme)],
    failed_attempts: Annotated[
        failed_login_store.FailedLoginStore,
        Depends(failed_login_store.get_failed_login_attempts),
    ],
    pending_mfa_store: Annotated[
        mfa_dependencies.PendingMFAStore,
        Depends(mfa_dependencies.get_pending_mfa_store),
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
    code_challenge: Annotated[str | None, Query()] = None,
    code_challenge_method: Annotated[str | None, Query()] = None,
):
    """Handles user login and access token generation, including Multi-Factor Authentication (MFA) flow.

    Protection Mechanisms:
    - Rate limiting: 10 requests per minute per IP (SENSITIVE tier, prevents DoS attacks)
    - Progressive lockout: Per-username and client-address tracking prevents targeted brute-force without
      letting one client lock the account for everyone:
      * 5 failures: 5 minute lockout
      * 10 failures: 30 minute lockout
      * 20 failures: 24 hour lockout
      * A much higher account-wide threshold across all addresses stops a distributed brute force

    This endpoint authenticates a user using provided credentials, checks if the user is active,
    and determines if MFA is required. If MFA is enabled for the user, it stores the pending login
    and returns an MFA-required response. Otherwise, it completes the login process and returns
    the required information.

    PKCE Support (Mobile):
    - Mobile clients can optionally provide code_challenge and code_challenge_method
    - For mobile clients with PKCE parameters, tokens are not returned directly
        - Instead, a session_id is returned for secure token exchange via
            /public/idp/session/{session_id}/tokens

    Args:
        response: The HTTP response object
        request: The HTTP request object
        form_data: Form data containing username and password
        client_type: The type of client making the request ("web" or "mobile")
        failed_attempts: Failed login attempts tracker for progressive lockout
        pending_mfa_store: Store for pending MFA logins
        password_hasher: The password hasher instance used for verifying passwords
        token_manager: The token manager instance used for token operations
        db: Database session
        code_challenge: PKCE code challenge (base64url-encoded SHA256, optional for mobile)
        code_challenge_method: PKCE method (must be S256 if provided, optional for mobile)

    Returns:
        Union[auth_schema.MFARequiredResponse, dict, str]:
            - If MFA is required, returns an MFA-required response (schema or dict depending on client type)
            - If MFA is not required and mobile client with PKCE, returns session_id for token exchange
            - If MFA is not required and no PKCE, proceeds with normal login via auth_utils.complete_login()

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
        code_challenge,
        code_challenge_method,
    )
    return authentication_dependencies.deliver_auth_outcome(response, outcome)


@router.post(
    "/mfa/verify",
    response_model=(auth_schema.MobileSessionRead | auth_schema.TokenWebRead | auth_schema.TokenMobileRead),
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def verify_mfa_and_login(
    response: Response,
    request: Request,
    mfa_request: auth_schema.MFALoginRequest,
    client_type: Annotated[str, Depends(authentication_dependencies.header_client_type_scheme)],
    failed_attempts: Annotated[
        failed_login_store.FailedLoginStore,
        Depends(failed_login_store.get_failed_login_attempts),
    ],
    pending_mfa_store: Annotated[
        mfa_dependencies.PendingMFAStore,
        Depends(mfa_dependencies.get_pending_mfa_store),
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
    code_challenge: Annotated[str | None, Query()] = None,
    code_challenge_method: Annotated[str | None, Query()] = None,
):
    """Verify MFA code and complete login process.

    This endpoint verifies the MFA code for a pending login and completes
    the authentication process if the code is valid.

    PKCE Support (Mobile):
    - Mobile clients can optionally provide code_challenge and code_challenge_method
    - For mobile clients with PKCE parameters, tokens are not returned directly
        - Instead, a session_id is returned for secure token exchange via
            /public/idp/session/{session_id}/tokens

    Args:
        response: The HTTP response object
        request: The HTTP request object
        failed_attempts: Failed login attempts tracker for progressive lockout
        mfa_request: MFA login request containing username and MFA code
        client_type: The type of client making the request ("web" or "mobile")
        pending_mfa_store: Store for pending MFA logins
        password_hasher: The password hasher instance used for verifying passwords
        token_manager: The token manager instance used for token operations
        db: Database session
        code_challenge: PKCE code challenge (base64url-encoded SHA256, optional for mobile)
        code_challenge_method: PKCE method (must be S256 if provided, optional for mobile)

    Returns:
        Result from auth_utils.complete_login() or PKCE session response

    Raises:
        HTTPException: If no pending login found, MFA code is invalid, or user not found
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
        code_challenge,
        code_challenge_method,
    )
    return authentication_dependencies.deliver_auth_outcome(response, outcome)


@router.post(
    "/refresh",
    response_model=(auth_schema.TokenWebRead | auth_schema.TokenMobileRead),
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def refresh_token(
    response: Response,
    request: Request,
    _validate_refresh_token: Annotated[Callable, Depends(authentication_dependencies.validate_refresh_token)],
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
    client_type: Annotated[str, Depends(authentication_dependencies.header_client_type_scheme)],
    x_csrf_token: Annotated[str | None, Depends(authentication_dependencies.header_csrf_token_scheme)] = None,
):
    r"""Handles the refresh token process for user sessions.

    This endpoint validates the provided refresh token, checks session status,
    validates the CSRF token (web clients only), and issues new tokens.

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
    outcome = auth_service.refresh_token(
        core_network.get_ip_address(request),
        core_network.get_user_agent(request),
        _validate_refresh_token,
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
    return authentication_dependencies.deliver_auth_outcome(response, outcome)


@router.post("/logout", response_model=auth_schema.LogoutRead)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def logout(
    response: Response,
    request: Request,
    _validate_refresh_token: Annotated[Callable, Depends(authentication_dependencies.validate_refresh_token)],
    token_session_id: Annotated[
        str,
        Depends(authentication_dependencies.get_sid_from_refresh_token),
    ],
    refresh_token_value: Annotated[
        str,
        Depends(authentication_dependencies.get_and_return_refresh_token),
    ],
    client_type: Annotated[str, Depends(authentication_dependencies.header_client_type_scheme)],
    token_user_id: Annotated[
        int,
        Depends(authentication_dependencies.get_sub_from_refresh_token),
    ],
    password_hasher: Annotated[
        credentials_integration.PasswordHasher,
        Depends(credentials_integration.get_password_hasher),
    ],
    db: core_dependencies.DbSession,
):
    """Log out a user by validating and deleting their session.

    Args:
        response: The HTTP response object to modify cookies.
        request: The HTTP request object, read by the rate limiter.
        _validate_refresh_token: Dependency to validate the refresh token.
        token_session_id: The session ID extracted from the refresh token.
        refresh_token_value: The refresh token value from the request.
        client_type: The type of client ("web" or "mobile").
        token_user_id: The user ID extracted from the refresh token.
        password_hasher: Utility for verifying the refresh token.
        db: Database session for CRUD operations.

    Returns:
        dict: A message indicating successful logout.

    Raises:
        HTTPException: If refresh token is invalid (401 Unauthorized).
        HTTPException: If client type is invalid (403 Forbidden).
    """
    message = auth_service.logout(
        _validate_refresh_token,
        token_session_id,
        refresh_token_value,
        client_type,
        token_user_id,
        password_hasher,
        db,
    )
    if client_type == "web":
        authentication_dependencies.clear_refresh_token_cookies(response, environment=core_config.settings.ENVIRONMENT)
    return message
