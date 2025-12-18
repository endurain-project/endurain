import os

from datetime import datetime, timedelta, timezone
from typing import Tuple
from fastapi import (
    HTTPException,
    status,
    Response,
    Request,
)
from uuid import uuid4

from sqlalchemy.orm import Session

import auth.constants as auth_constants
import session.utils as session_utils
import auth.password_hasher as auth_password_hasher
import auth.token_manager as auth_token_manager

import users.user.crud as users_crud
import users.user.schema as users_schema


def authenticate_user(
    username: str,
    password: str,
    password_hasher: auth_password_hasher.PasswordHasher,
    db: Session,
) -> users_schema.UserRead:
    """
    Authenticates a user by verifying the provided username and password.

    Args:
        username (str): The username of the user attempting to authenticate.
        password (str): The plaintext password provided by the user.
        password_hasher (auth_password_hasher.PasswordHasher): An instance of the password hasher for verifying and updating password hashes.
        db (Session): The database session used for querying and updating user data.

    Returns:
        users_schema.UserRead: The authenticated user object if authentication is successful.

    Raises:
        HTTPException: If the username does not exist or the password is invalid.
    """
    # Get the user from the database
    user = users_crud.authenticate_user(username, db)

    # Check if the user exists and if the password is correct
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verify password and get updated hash if applicable
    is_password_valid, updated_hash = password_hasher.verify_and_update(
        password, user.password
    )
    if not is_password_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Update user hash if applicable
    if updated_hash:
        users_crud.edit_user_password(
            user.id, updated_hash, password_hasher, db, is_hashed=True
        )

    # Return the user if the password is correct
    return user


def create_tokens(
    user: users_schema.UserRead,
    token_manager: auth_token_manager.TokenManager,
    session_id: str | None = None,
) -> Tuple[str, datetime, str, datetime, str, str]:
    """
    Generates session tokens for a user, including access token, refresh token, and CSRF token.

    Args:
        user (users_schema.UserRead): The user object for whom the tokens are being created.
        token_manager (auth_token_manager.TokenManager): The token manager responsible for token creation.
        session_id (str | None, optional): An optional session ID. If not provided, a new unique session ID is generated.

    Returns:
        Tuple[str, datetime, str, datetime, str, str]:
            A tuple containing:
                - session_id (str): The session identifier.
                - access_token_exp (datetime): Expiration datetime of the access token.
                - access_token (str): The access token string.
                - refresh_token_exp (datetime): Expiration datetime of the refresh token.
                - refresh_token (str): The refresh token string.
                - csrf_token (str): The CSRF token string.
    """
    if session_id is None:
        # Generate a unique session ID
        session_id = str(uuid4())

    # Create the access, refresh tokens and csrf token
    access_token_exp, access_token = token_manager.create_token(
        session_id, user, auth_token_manager.TokenType.ACCESS
    )

    refresh_token_exp, refresh_token = token_manager.create_token(
        session_id, user, auth_token_manager.TokenType.REFRESH
    )

    csrf_token = token_manager.create_csrf_token()

    return (
        session_id,
        access_token_exp,
        access_token,
        refresh_token_exp,
        refresh_token,
        csrf_token,
    )


def complete_login(
    response: Response,
    request: Request,
    user: users_schema.UserRead,
    client_type: str,
    password_hasher: auth_password_hasher.PasswordHasher,
    token_manager: auth_token_manager.TokenManager,
    db: Session,
) -> dict:
    """
    Handles the completion of the login process by generating session and authentication tokens,
    storing the session in the database, and returning tokens in response body.

    OAuth 2.1 compliant: Returns tokens in response body for all clients.
    - Access token and CSRF token: Returned in body (for in-memory storage)
    - Refresh token: Set as httpOnly cookie with SameSite=Strict

    This unified model works for both username/password and SSO login flows.

    Args:
        response (Response): The HTTP response object to set refresh cookie.
        request (Request): The HTTP request object containing client information.
        user (users_schema.UserRead): The authenticated user object.
        client_type (str): The type of client ("web" or "mobile").
        password_hasher (auth_password_hasher.PasswordHasher): Utility for password hashing.
        token_manager (auth_token_manager.TokenManager): Utility for token generation and management.
        db (Session): Database session for storing session information.

    Returns:
        dict: Contains session_id, access_token, csrf_token, token_type, and expires_in.

    Raises:
        HTTPException: If the client type is invalid, raises a 403 Forbidden error.
    """
    if client_type not in ["web", "mobile"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid client type",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create the tokens
    (
        session_id,
        access_token_exp,
        access_token,
        _refresh_token_exp,
        refresh_token,
        csrf_token,
    ) = create_tokens(user, token_manager)

    # Create the session and store it in the database
    session_utils.create_session(
        session_id, user, request, refresh_token, password_hasher, db
    )

    # Access token and CSRF token returned in body for in-memory storage
    secure = os.environ.get("FRONTEND_PROTOCOL") == "https"
    response.set_cookie(
        key="endurain_refresh_token",
        value=refresh_token,
        expires=datetime.now(timezone.utc)
        + timedelta(days=auth_constants.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
        httponly=True,
        path="/",
        secure=secure,
        samesite="strict",  # OAuth 2.1: Strict for defense-in-depth
    )

    # Return tokens in response body for all clients (unified OAuth 2.1 model)
    return {
        "session_id": session_id,
        "access_token": access_token,
        "csrf_token": csrf_token,
        "token_type": "bearer",
        "expires_in": int(access_token_exp.timestamp()),
    }
