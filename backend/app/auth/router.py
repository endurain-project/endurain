import os
from datetime import datetime, timedelta, timezone
from typing import Annotated, Callable

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    Response,
    Request,
)
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

import session.utils as session_utils
import auth.security as auth_security
import auth.utils as auth_utils
import auth.constants as auth_constants
import session.crud as session_crud
import auth.password_hasher as auth_password_hasher
import auth.token_manager as auth_token_manager
import auth.schema as auth_schema

import auth.identity_providers.utils as idp_utils

import users.user.crud as users_crud
import users.user.utils as users_utils
import profile.utils as profile_utils

import core.database as core_database
import core.rate_limit as core_rate_limit

import session.rotated_refresh_tokens.utils as rotated_tokens_utils

# Define the API router
router = APIRouter()


@router.post("/login")
@core_rate_limit.limiter.limit(core_rate_limit.SESSION_LOGIN_LIMIT)
async def login_for_access_token(
    response: Response,
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    client_type: Annotated[str, Depends(auth_security.header_client_type_scheme)],
    failed_attempts: Annotated[
        auth_schema.FailedLoginAttempts,
        Depends(auth_schema.get_failed_login_attempts),
    ],
    pending_mfa_store: Annotated[
        auth_schema.PendingMFALogin, Depends(auth_schema.get_pending_mfa_store)
    ],
    password_hasher: Annotated[
        auth_password_hasher.PasswordHasher,
        Depends(auth_password_hasher.get_password_hasher),
    ],
    token_manager: Annotated[
        auth_token_manager.TokenManager,
        Depends(auth_token_manager.get_token_manager),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    """
    Handles user login and access token generation, including Multi-Factor Authentication (MFA) flow.

    Protection Mechanisms:
    - Rate limiting: 3 requests per minute per IP (prevents DoS attacks)
    - Progressive lockout: Per-username tracking prevents targeted brute-force:
      * 5 failures: 5 minute lockout
      * 10 failures: 30 minute lockout
      * 20 failures: 24 hour lockout

    This endpoint authenticates a user using provided credentials, checks if the user is active,
    and determines if MFA is required. If MFA is enabled for the user, it stores the pending login
    and returns an MFA-required response. Otherwise, it completes the login process and returns
    the required information.

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

    Returns:
        Union[auth_schema.MFARequiredResponse, dict, str]:
            - If MFA is required, returns an MFA-required response (schema or dict depending on client type)
            - If MFA is not required, proceeds with normal login via auth_utils.complete_login()

    Raises:
        HTTPException: If authentication fails, user is inactive, or account is locked
    """
    # Check if username is locked out from too many failed login attempts
    if failed_attempts.is_locked_out(form_data.username):
        lockout_until = failed_attempts.get_lockout_time(form_data.username)
        if lockout_until:
            seconds_remaining = int(
                (lockout_until - datetime.now(timezone.utc)).total_seconds()
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Account locked due to too many failed login attempts. Try again in {seconds_remaining} seconds.",
            )

    # Authenticate user
    try:
        user = auth_utils.authenticate_user(
            form_data.username, form_data.password, password_hasher, db
        )
    except HTTPException as err:
        # Record failed attempt on authentication errors (401 Unauthorized)
        if err.status_code == 401:
            failed_attempts.record_failed_attempt(form_data.username)
        raise err

    # Check if the user is active
    users_utils.check_user_is_active(user)

    # Check if MFA is enabled for this user
    if profile_utils.is_mfa_enabled_for_user(user.id, db):
        # Store the user for pending MFA verification
        pending_mfa_store.add_pending_login(form_data.username, user.id)

        # Don't reset failed login attempts yet - wait for MFA verification
        # This prevents bypassing lockout by triggering MFA flow

        # Return MFA required response
        if client_type == "web":
            response.status_code = status.HTTP_202_ACCEPTED
            return auth_schema.MFARequiredResponse(
                mfa_required=True,
                username=form_data.username,
                message="MFA verification required",
            )
        if client_type == "mobile":
            return {
                "mfa_required": True,
                "username": form_data.username,
                "message": "MFA verification required",
            }

    # Password authentication successful and no MFA required
    # Reset failed login attempts counter
    failed_attempts.reset_attempts(form_data.username)

    # If no MFA required, proceed with normal login
    return auth_utils.complete_login(
        response, request, user, client_type, password_hasher, token_manager, db
    )


@router.post("/mfa/verify")
@core_rate_limit.limiter.limit(core_rate_limit.MFA_VERIFY_LIMIT)
async def verify_mfa_and_login(
    response: Response,
    request: Request,
    mfa_request: auth_schema.MFALoginRequest,
    client_type: Annotated[str, Depends(auth_security.header_client_type_scheme)],
    failed_attempts: Annotated[
        auth_schema.FailedLoginAttempts,
        Depends(auth_schema.get_failed_login_attempts),
    ],
    pending_mfa_store: Annotated[
        auth_schema.PendingMFALogin, Depends(auth_schema.get_pending_mfa_store)
    ],
    password_hasher: Annotated[
        auth_password_hasher.PasswordHasher,
        Depends(auth_password_hasher.get_password_hasher),
    ],
    token_manager: Annotated[
        auth_token_manager.TokenManager,
        Depends(auth_token_manager.get_token_manager),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    """
    Verify MFA code and complete login process.

    This endpoint verifies the MFA code for a pending login and completes
    the authentication process if the code is valid.

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

    Returns:
        Result from auth_utils.complete_login()

    Raises:
        HTTPException: If no pending login found, MFA code is invalid, or user not found
    """
    # Check if user is locked out from too many failed attempts
    if pending_mfa_store.is_locked_out(mfa_request.username):
        lockout_until = pending_mfa_store.get_lockout_time(mfa_request.username)
        if lockout_until:
            seconds_remaining = int(
                (lockout_until - datetime.now(timezone.utc)).total_seconds()
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many failed MFA attempts. Account locked for {seconds_remaining} seconds.",
            )

    # Check if there's a pending MFA login for this username
    user_id = pending_mfa_store.get_pending_login(mfa_request.username)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No pending MFA login found for this username",
        )

    # Verify the MFA code (TOTP or backup code)
    if not profile_utils.verify_user_mfa(
        user_id, mfa_request.mfa_code, password_hasher, db
    ):
        # Record failed attempt and apply lockout if threshold exceeded
        failed_count = pending_mfa_store.record_failed_attempt(mfa_request.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid MFA code. Failed attempts: {failed_count}",
        )

    # Get the user and complete login
    user = users_crud.get_user_by_id(user_id, db)
    if not user:
        pending_mfa_store.delete_pending_login(mfa_request.username)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    # Check if the user is still active
    users_utils.check_user_is_active(user)

    # MFA verification successful - reset both MFA and login failed attempts counters
    pending_mfa_store.reset_failed_attempts(mfa_request.username)
    failed_attempts.reset_attempts(mfa_request.username)

    # Clean up pending login
    pending_mfa_store.delete_pending_login(mfa_request.username)

    # Complete the login
    return auth_utils.complete_login(
        response, request, user, client_type, password_hasher, token_manager, db
    )


@router.post("/refresh")
async def refresh_token(
    response: Response,
    request: Request,
    _validate_refresh_token: Annotated[
        Callable, Depends(auth_security.validate_refresh_token)
    ],
    token_user_id: Annotated[
        int,
        Depends(auth_security.get_sub_from_refresh_token),
    ],
    token_session_id: Annotated[
        str,
        Depends(auth_security.get_sid_from_refresh_token),
    ],
    refresh_token_value: Annotated[
        str,
        Depends(auth_security.get_and_return_refresh_token),
    ],
    password_hasher: Annotated[
        auth_password_hasher.PasswordHasher,
        Depends(auth_password_hasher.get_password_hasher),
    ],
    token_manager: Annotated[
        auth_token_manager.TokenManager,
        Depends(auth_token_manager.get_token_manager),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
    client_type: Annotated[str, Depends(auth_security.header_client_type_scheme)],
    x_csrf_token: Annotated[
        str | None, Depends(auth_security.header_csrf_token_scheme)
    ] = None,
):
    """
    Handles the refresh token process for user sessions.

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
        password_hasher: Utility for verifying token hashes.
        token_manager: Utility for creating tokens.
        db: Database session.
        client_type: Client type (\"web\" or \"mobile\").
        x_csrf_token: CSRF token header (web clients only, optional on page reload).

    Returns:
        dict: Contains session_id, access_token, csrf_token, token_type, expires_in.

    Raises:
        HTTPException: If session not found, refresh token invalid,
                       user is inactive, or CSRF token is invalid (when provided).
    """
    # Get the session from the database
    session = session_crud.get_session_by_id(token_session_id, db)

    # Check if the session was found
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Validate session hasn't exceeded idle or absolute timeout
    session_utils.validate_session_timeout(session)

    # Verify CSRF token for web clients only
    # Mobile clients don't use CSRF tokens
    # OAuth 2.1 Bootstrap Pattern for page reload:
    # - On page reload, in-memory tokens are lost but httpOnly cookie persists
    # - If x_csrf_token is None (missing from request), allow refresh anyway
    # - Security: httpOnly cookie + SameSite=Strict prevents CSRF at browser level
    # - If x_csrf_token is provided, it MUST be valid (prevent partial CSRF)
    # - CSRF token is defense-in-depth; SameSite=Strict is primary protection
    if client_type == "web" and x_csrf_token and session.csrf_token_hash is not None:
        # CSRF token was provided: validate it
        if not password_hasher.verify(x_csrf_token, session.csrf_token_hash):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid CSRF token",
                headers={"WWW-Authenticate": "Bearer"},
            )

    # Check for token reuse BEFORE validating token
    # Hash the incoming token to compare with rotated tokens
    hashed_refresh_token = password_hasher.hash_password(refresh_token_value)
    is_reused, in_grace = rotated_tokens_utils.check_token_reuse(
        hashed_refresh_token, db
    )

    if is_reused and not in_grace:
        # Token theft detected - invalidate entire family
        rotated_tokens_utils.invalidate_token_family(session.token_family_id, db)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token reuse detected. All sessions invalidated.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    is_valid = password_hasher.verify(refresh_token_value, session.refresh_token)

    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # get user
    user = users_crud.get_user_by_id(token_user_id, db)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check if the user is active
    users_utils.check_user_is_active(user)

    # Store old refresh token BEFORE rotating
    # This enables detection if the old token is reused later
    rotated_tokens_utils.store_rotated_token(
        session.refresh_token,
        session.token_family_id,
        session.rotation_count,
        db,
    )

    # Create the tokens
    (
        session_id,
        new_access_token_exp,
        new_access_token,
        _,
        new_refresh_token,
        new_csrf_token,
    ) = auth_utils.create_tokens(user, token_manager, session.id)

    # Edit session and store in database
    # Note: edit_session automatically increments rotation_count
    # and updates last_rotation_at
    session_utils.edit_session(
        session,
        request,
        new_refresh_token,
        password_hasher,
        db,
        new_csrf_token=new_csrf_token,
    )

    # Opportunistically refresh IdP tokens for all linked identity providers
    await idp_utils.refresh_idp_tokens_if_needed(user.id, db)

    secure = os.environ.get("FRONTEND_PROTOCOL") == "https"
    response.set_cookie(
        key="endurain_refresh_token",
        value=new_refresh_token,
        expires=datetime.now(timezone.utc)
        + timedelta(days=auth_constants.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
        httponly=True,
        path="/",
        secure=secure,
        samesite="strict",
    )

    # Return tokens in response body for in-memory storage
    return {
        "session_id": session_id,
        "access_token": new_access_token,
        "csrf_token": new_csrf_token,
        "token_type": "bearer",
        "expires_in": int(new_access_token_exp.timestamp()),
    }


@router.post("/logout")
async def logout(
    response: Response,
    _validate_access_token: Annotated[
        Callable, Depends(auth_security.validate_access_token)
    ],
    token_session_id: Annotated[
        str,
        Depends(auth_security.get_sid_from_access_token),
    ],
    refresh_token_value: Annotated[
        str,
        Depends(auth_security.get_and_return_refresh_token),
    ],
    client_type: Annotated[str, Depends(auth_security.header_client_type_scheme)],
    token_user_id: Annotated[
        int,
        Depends(auth_security.get_sub_from_refresh_token),
    ],
    password_hasher: Annotated[
        auth_password_hasher.PasswordHasher,
        Depends(auth_password_hasher.get_password_hasher),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    """
    Logs out a user by validating and deleting their session, and clearing the refresh token cookie.
    Parameters:
        response (Response): The response object to modify cookies.
        _validate_access_token (Callable): Dependency to validate the access token.
        token_session_id (str): The session ID extracted from the access token.
        refresh_token_value (str): The refresh token value from the request.
        client_type (str): The type of client ("web" or "mobile").
        token_user_id (int): The user ID extracted from the refresh token.
        password_hasher (PasswordHasher): Utility for verifying the refresh token.
        db (Session): Database session for CRUD operations.
    Returns:
        dict: A message indicating successful logout.
    Raises:
        HTTPException: If the refresh token is invalid (401 Unauthorized).
        HTTPException: If the client type is invalid (403 Forbidden).
    """
    # Get the session from the database
    session = session_crud.get_session_by_id(token_session_id, db)

    # Check if the session was found
    if session is not None:
        # Verify the refresh token
        is_valid = password_hasher.verify(refresh_token_value, session.refresh_token)

        # If the refresh token is not valid, raise an exception
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Delete the session from the database
        session_crud.delete_session(session.id, token_user_id, db)

        # Clear all IdP refresh tokens for security
        await idp_utils.clear_all_idp_tokens(token_user_id, db)

    if client_type == "web":
        response.delete_cookie(key="endurain_refresh_token", path="/")
        return {"message": "Logout successful"}
    if client_type == "mobile":
        return {"message": "Logout successful"}
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Invalid client type",
        headers={"WWW-Authenticate": "Bearer"},
    )
