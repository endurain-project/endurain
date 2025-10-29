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

# Define the API router
router = APIRouter()


@router.post("/token")
@core_rate_limit.limiter.limit(core_rate_limit.SESSION_LOGIN_LIMIT)
async def login_for_access_token(
    response: Response,
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    client_type: Annotated[str, Depends(auth_security.header_client_type_scheme)],
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

    Rate Limit: 5 requests per minute per IP

    This endpoint authenticates a user using provided credentials, checks if the user is active,
    and determines if MFA is required. If MFA is enabled for the user, it stores the pending login
    and returns an MFA-required response. Otherwise, it completes the login process and returns
    the required information.

    Args:
        response: The HTTP response object
        request: The HTTP request object
        form_data: Form data containing username and password
        client_type: The type of client making the request ("web" or "mobile")
        pending_mfa_store: Store for pending MFA logins
        password_hasher: The password hasher instance used for verifying passwords
        token_manager: The token manager instance used for token operations
        db: Database session

    Returns:
        Union[auth_schema.MFARequiredResponse, dict, str]:
            - If MFA is required, returns an MFA-required response (schema or dict depending on client type)
            - If MFA is not required, proceeds with normal login via auth_utils.complete_login()

    Raises:
        HTTPException: If authentication fails or the user is inactive
    """
    user = auth_utils.authenticate_user(
        form_data.username, form_data.password, password_hasher, db
    )

    # Check if the user is active
    users_utils.check_user_is_active(user)

    # Check if MFA is enabled for this user
    if profile_utils.is_mfa_enabled_for_user(user.id, db):
        # Store the user for pending MFA verification
        pending_mfa_store.add_pending_login(form_data.username, user.id)

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

    # If no MFA required, proceed with normal login
    return auth_utils.complete_login(
        response, request, user, client_type, password_hasher, token_manager, db
    )


@router.post("/mfa/verify")
async def verify_mfa_and_login(
    response: Response,
    request: Request,
    mfa_request: auth_schema.MFALoginRequest,
    client_type: Annotated[str, Depends(auth_security.header_client_type_scheme)],
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
    # Check if there's a pending MFA login for this username
    user_id = pending_mfa_store.get_pending_login(mfa_request.username)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No pending MFA login found for this username",
        )

    # Verify the MFA code
    if not profile_utils.verify_user_mfa(user_id, mfa_request.mfa_code, db):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid MFA code"
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
    client_type: Annotated[str, Depends(auth_security.header_client_type_scheme)],
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
    Handles the refresh token process for user sessions.

    This endpoint validates the provided refresh token, checks session and user status,
    and issues new access, refresh, and CSRF tokens. The response format depends on the client type.

    Args:
        response (Response): The HTTP response object.
        request (Request): The HTTP request object.
        _validate_refresh_token (Callable): Dependency to validate the refresh token.
        token_user_id (int): User ID extracted from the refresh token.
        token_session_id (str): Session ID extracted from the refresh token.
        refresh_token_value (str): The raw refresh token value.
        client_type (str): The type of client ("web" or "mobile").
        password_hasher (PasswordHasher): Utility for verifying token hashes.
        token_manager (TokenManager): Utility for creating tokens.
        db (Session): Database session.

    Returns:
        Union[str, dict]: For "web" clients, returns the session ID.
                          For "mobile" clients, returns a dictionary with new tokens and session ID.

    Raises:
        HTTPException: If the session is not found, the refresh token is invalid,
                       the user is inactive, or the client type is invalid.
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

    # Create the tokens
    (
        session_id,
        new_access_token_exp,
        new_access_token,
        _new_refresh_token_exp,
        new_refresh_token,
        new_csrf_token,
    ) = auth_utils.create_tokens(user, token_manager, session.id)

    # Edit the session and store it in the database
    session_utils.edit_session(session, request, new_refresh_token, password_hasher, db)

    # Opportunistically refresh IdP tokens for all linked identity providers
    await idp_utils.refresh_idp_tokens_if_needed(user.id, db)

    if client_type == "web":
        response = auth_utils.create_response_with_tokens(
            response, new_access_token, new_refresh_token, new_csrf_token
        )

        # Return session ID
        return {
            "session_id": session_id,
        }
    if client_type == "mobile":
        # Return the tokens
        return {
            "access_token": new_access_token,
            "refresh_token": new_refresh_token,
            "session_id": session_id,
            "token_type": "bearer",
            "expires_in": int(new_access_token_exp.timestamp()),
        }
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Invalid client type",
        headers={"WWW-Authenticate": "Bearer"},
    )


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
    Logs out a user by validating and deleting their session, and clearing authentication cookies for web clients.
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
        # Clear the cookies by setting their expiration to the past
        response.delete_cookie(key="endurain_access_token", path="/")
        response.delete_cookie(key="endurain_refresh_token", path="/")
        response.delete_cookie(key="endurain_csrf_token", path="/")
        return {"message": "Logout successful"}
    if client_type == "mobile":
        return {"message": "Logout successful"}
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Invalid client type",
        headers={"WWW-Authenticate": "Bearer"},
    )
