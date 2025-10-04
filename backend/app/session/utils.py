"""Session utility functions and helpers."""

import os
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from typing import Tuple
from fastapi import (
    HTTPException,
    status,
    Response,
    Request,
)
from user_agents import parse
from uuid import uuid4

from sqlalchemy.orm import Session

import session.security as session_security
import session.constants as session_constants
import session.schema as session_schema
import session.crud as session_crud
import session.password_hasher as session_password_hasher

import users.user.crud as users_crud
import users.user.schema as users_schema


@dataclass
class DeviceInfo:
    """Device information extracted from user agent."""

    device_type: str
    operating_system: str
    operating_system_version: str
    browser: str
    browser_version: str


def create_session_object(
    user: users_schema.UserRead,
    request: Request,
    refresh_token: str,
    refresh_token_exp: datetime,
) -> session_schema.UsersSessions:
    """
    Create a new session object from user and request data.

    Args:
        user: User object
        request: FastAPI request object
        refresh_token: Refresh token string
        refresh_token_exp: Refresh token expiration datetime

    Returns:
        UsersSessions schema object
    """
    user_agent = get_user_agent(request)
    device_info = parse_user_agent(user_agent)

    return session_schema.UsersSessions(
        id=str(uuid4()),
        user_id=user.id,
        refresh_token=refresh_token,
        ip_address=get_ip_address(request),
        device_type=device_info.device_type,
        operating_system=device_info.operating_system,
        operating_system_version=device_info.operating_system_version,
        browser=device_info.browser,
        browser_version=device_info.browser_version,
        created_at=datetime.now(timezone.utc),
        expires_at=refresh_token_exp,
    )


def edit_session_object(
    request: Request,
    refresh_token: str,
    refresh_token_exp: datetime,
    session: Session,
) -> session_schema.UsersSessions:
    """
    Create an updated session object with new token and request data.

    Args:
        request: FastAPI request object
        refresh_token: New refresh token string
        refresh_token_exp: New refresh token expiration datetime
        session: Existing session object

    Returns:
        Updated UsersSessions schema object
    """
    user_agent = get_user_agent(request)
    device_info = parse_user_agent(user_agent)

    return session_schema.UsersSessions(
        id=session.id,
        user_id=session.user_id,
        refresh_token=refresh_token,
        ip_address=get_ip_address(request),
        device_type=device_info.device_type,
        operating_system=device_info.operating_system,
        operating_system_version=device_info.operating_system_version,
        browser=device_info.browser,
        browser_version=device_info.browser_version,
        created_at=session.created_at,
        expires_at=refresh_token_exp,
    )


def authenticate_user(
    username: str,
    password: str,
    password_hasher: session_password_hasher.PasswordHasher,
    db: Session,
) -> users_schema.UserRead:
    """
    Authenticates a user by verifying the provided username and password.
    Updates the user password hash in the DB if necessary.
    Args:
        username (str): The username of the user attempting to authenticate.
        password (str): The password provided by the user.
        password_hasher (PasswordHasher): The password hasher instance used for verification.
        db (Session): The database session used to query user data.
    Returns:
        users_schema.UserRead: The authenticated user object.
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


def create_tokens(user: users_schema.UserRead) -> Tuple[str, str, str]:
    """
    Create access, refresh, and CSRF tokens for a user.

    Args:
        user: User object

    Returns:
        Tuple of (access_token, refresh_token, csrf_token)
    """
    # Check user access level and set scopes accordingly
    if user.access_type == users_schema.UserAccessType.REGULAR:
        scopes = session_constants.REGULAR_ACCESS_SCOPES
    else:
        scopes = session_constants.ADMIN_ACCESS_SCOPES

    # Create the access and refresh tokens
    access_token = session_security.create_token(
        data={
            "sub": user.id,
            "scopes": scopes,
            "exp": datetime.now(timezone.utc)
            + timedelta(minutes=session_constants.JWT_ACCESS_TOKEN_EXPIRE_MINUTES),
        },
    )

    refresh_token = session_security.create_token(
        data={
            "sub": user.id,
            "scopes": scopes,
            "exp": datetime.now(timezone.utc)
            + timedelta(days=session_constants.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
        },
    )

    csrf_token = session_security.create_csrf_token()

    return access_token, refresh_token, csrf_token


def create_response_with_tokens(
    response: Response, access_token: str, refresh_token: str, csrf_token: str
) -> Response:
    """
    Set authentication cookies on the response object.

    Args:
        response: FastAPI response object
        access_token: Access token string
        refresh_token: Refresh token string
        csrf_token: CSRF token string

    Returns:
        Response object with cookies set
    """
    secure = os.environ.get("FRONTEND_PROTOCOL") == "https"

    # Set the cookies with the tokens
    response.set_cookie(
        key="endurain_access_token",
        value=access_token,
        expires=datetime.now(timezone.utc)
        + timedelta(minutes=session_constants.JWT_ACCESS_TOKEN_EXPIRE_MINUTES),
        httponly=True,
        path="/",
        secure=secure,
        samesite="Lax",
    )
    response.set_cookie(
        key="endurain_refresh_token",
        value=refresh_token,
        expires=datetime.now(timezone.utc)
        + timedelta(days=session_constants.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
        httponly=True,
        path="/",
        secure=secure,
        samesite="Lax",
    )
    response.set_cookie(
        key="endurain_csrf_token",
        value=csrf_token,
        httponly=False,
        path="/",
        secure=secure,
        samesite="Lax",
    )

    # Return the response
    return response


def create_session(
    user: users_schema.UserRead,
    request: Request,
    refresh_token: str,
    db: Session,
) -> str:
    """
    Create a new user session and store it in the database.

    Args:
        user: User object
        request: FastAPI request object
        refresh_token: Refresh token string
        db: Database session

    Returns:
        Session ID string
    """
    # Create a new session
    new_session = create_session_object(
        user,
        request,
        refresh_token,
        datetime.now(timezone.utc)
        + timedelta(days=session_constants.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
    )

    # Add the session to the database
    session_crud.create_session(new_session, db)

    # Return the session ID
    return new_session.id


def edit_session(
    session: session_schema.UsersSessions,
    request: Request,
    new_refresh_token: str,
    db: Session,
) -> None:
    """
    Update an existing session with new token and request data.

    Args:
        session: Existing session object
        request: FastAPI request object
        new_refresh_token: New refresh token string
        db: Database session
    """
    # Update the session
    updated_session = edit_session_object(
        request,
        new_refresh_token,
        datetime.now(timezone.utc)
        + timedelta(days=session_constants.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
        session,
    )

    # Update the session in the database
    session_crud.edit_session(updated_session, db)


def complete_login(
    response: Response,
    request: Request,
    user: users_schema.UserRead,
    client_type: str,
    db: Session,
) -> dict | str:
    """
    Complete the login process by creating tokens and session.

    This function handles the final steps of authentication after credentials
    have been verified (and MFA if required). It creates tokens, sets cookies
    for web clients, and creates a session record in the database.

    Args:
        response: FastAPI response object (for setting cookies)
        request: FastAPI request object (for session metadata)
        user: Authenticated user object
        client_type: Type of client ("web" or "mobile")
        db: Database session

    Returns:
        For web clients: session_id string
        For mobile clients: dict with access_token, refresh_token, and session_id

    Raises:
        HTTPException: If client_type is invalid
    """
    # Create the tokens
    access_token, refresh_token, csrf_token = create_tokens(user)

    if client_type == "web":
        # Set response cookies with tokens
        create_response_with_tokens(response, access_token, refresh_token, csrf_token)

        # Create the session and store it in the database
        session_id = create_session(user, request, refresh_token, db)

        # Return the session_id
        return session_id

    if client_type == "mobile":
        # Create the session and store it in the database
        session_id = create_session(user, request, refresh_token, db)

        # Return the tokens directly (no cookies for mobile)
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "session_id": session_id,
        }

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Invalid client type",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_user_agent(request: Request) -> str:
    """
    Extract user agent string from request.

    Args:
        request: FastAPI request object

    Returns:
        User agent string or empty string if not present
    """
    return request.headers.get("user-agent", "")


def get_ip_address(request: Request) -> str:
    """
    Extract client IP address from request.
    Checks proxy headers first before falling back to client.host.

    Args:
        request: FastAPI request object

    Returns:
        IP address string
    """
    # Check for proxy headers first
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # Take the first IP in the chain
        return forwarded_for.split(",")[0].strip()

    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip

    return request.client.host if request.client else "unknown"


def parse_user_agent(user_agent: str) -> DeviceInfo:
    """
    Parse user agent string to extract device information.

    Args:
        user_agent: User agent string

    Returns:
        DeviceInfo dataclass with parsed information
    """
    ua = parse(user_agent)
    device_type = "Mobile" if ua.is_mobile else "Tablet" if ua.is_tablet else "PC"

    return DeviceInfo(
        device_type=device_type,
        operating_system=ua.os.family or "Unknown",
        operating_system_version=ua.os.version_string or "Unknown",
        browser=ua.browser.family or "Unknown",
        browser_version=ua.browser.version_string or "Unknown",
    )
