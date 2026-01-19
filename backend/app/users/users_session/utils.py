"""Session utility functions and classes"""

from enum import Enum
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from fastapi import (
    Request,
    HTTPException,
    status,
)
from user_agents import parse

from sqlalchemy.orm import Session

import auth.constants as auth_constants
import auth.password_hasher as auth_password_hasher

import users.users_session.schema as users_session_schema
import users.users_session.crud as users_session_crud

import users.users.schema as users_schema

import core.logger as core_logger
from core.database import SessionLocal


class DeviceType(Enum):
    """
    An enumeration representing different types of devices.

    Attributes:
        MOBILE: Represents a mobile device.
        TABLET: Represents a tablet device.
        PC: Represents a personal computer/desktop device.
    """

    MOBILE = "Mobile"
    TABLET = "Tablet"
    PC = "PC"


@dataclass
class DeviceInfo:
    """
    Represents information about a user's device.

    Attributes:
        device_type (DeviceType): The type of device (e.g., mobile, desktop).
        operating_system (str): The name of the operating system (e.g., 'Windows', 'macOS').
        operating_system_version (str): The version of the operating system.
        browser (str): The name of the browser (e.g., 'Chrome', 'Firefox').
        browser_version (str): The version of the browser.
    """

    device_type: DeviceType
    operating_system: str
    operating_system_version: str
    browser: str
    browser_version: str


def validate_session_timeout(session: users_session_schema.UsersSessions) -> None:
    """
    Validate session hasn't exceeded idle or absolute timeout.
    Only enforces timeout when SESSION_IDLE_TIMEOUT_ENABLED=true.

    Checks:
    1. Idle timeout: last_activity_at must be within SESSION_IDLE_TIMEOUT_HOURS
    2. Absolute timeout: created_at must be within SESSION_ABSOLUTE_TIMEOUT_HOURS

    Args:
        session: The session to validate

    Raises:
        HTTPException: 401 if session has timed out
    """
    # Skip validation if timeouts are disabled
    if not auth_constants.SESSION_IDLE_TIMEOUT_ENABLED:
        return

    now = datetime.now(timezone.utc)

    # Check idle timeout
    idle_limit = session.last_activity_at + timedelta(
        hours=auth_constants.SESSION_IDLE_TIMEOUT_HOURS
    )
    if now > idle_limit:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired due to inactivity",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check absolute timeout
    absolute_limit = session.created_at + timedelta(
        hours=auth_constants.SESSION_ABSOLUTE_TIMEOUT_HOURS
    )
    if now > absolute_limit:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired. Please login again for security.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def create_session_object(
    session_id: str,
    user: users_schema.UsersRead,
    request: Request,
    hashed_refresh_token: str,
    refresh_token_exp: datetime,
    oauth_state_id: str | None = None,
    csrf_token_hash: str | None = None,
) -> users_session_schema.UsersSessions:
    """
    Creates a UsersSessions object with device and request metadata.

    Args:
        session_id: Unique identifier for the session.
        user: The user associated with the session.
        request: The HTTP request object containing client information.
        hashed_refresh_token: The hashed refresh token for the session.
        refresh_token_exp: The expiration datetime for the refresh token.
        oauth_state_id: Optional OAuth state ID for PKCE mobile flows.
        csrf_token_hash: Hashed CSRF token for refresh validation.

    Returns:
        The session object populated with user, device, and request details.
    """
    user_agent = get_user_agent(request)
    device_info = parse_user_agent(user_agent)

    now = datetime.now(timezone.utc)

    return users_session_schema.UsersSessions(
        id=session_id,
        user_id=user.id,
        refresh_token=hashed_refresh_token,
        ip_address=get_ip_address(request),
        device_type=device_info.device_type.value,
        operating_system=device_info.operating_system,
        operating_system_version=device_info.operating_system_version,
        browser=device_info.browser,
        browser_version=device_info.browser_version,
        created_at=now,
        last_activity_at=now,
        expires_at=refresh_token_exp,
        oauth_state_id=oauth_state_id,
        tokens_exchanged=False,
        token_family_id=session_id,
        rotation_count=0,
        last_rotation_at=None,
        csrf_token_hash=csrf_token_hash,
    )


def edit_session_object(
    request: Request,
    hashed_refresh_token: str,
    refresh_token_exp: datetime,
    session: Session,
    csrf_token_hash: str | None = None,
) -> users_session_schema.UsersSessions:
    """
    Edits and returns a UsersSessions object with updated session info.

    Args:
        request: The incoming HTTP request object.
        hashed_refresh_token: The hashed refresh token for the session.
        refresh_token_exp: The expiration datetime for the refresh token.
        session: The existing session object to update.
        csrf_token_hash: Hashed CSRF token for refresh validation.

    Returns:
        The updated UsersSessions object with device and token details.
    """
    user_agent = get_user_agent(request)
    device_info = parse_user_agent(user_agent)

    now = datetime.now(timezone.utc)
    new_rotation_count = session.rotation_count + 1

    return users_session_schema.UsersSessions(
        id=session.id,
        user_id=session.user_id,
        refresh_token=hashed_refresh_token,
        ip_address=get_ip_address(request),
        device_type=device_info.device_type.value,
        operating_system=device_info.operating_system,
        operating_system_version=device_info.operating_system_version,
        browser=device_info.browser,
        browser_version=device_info.browser_version,
        created_at=session.created_at,
        last_activity_at=now,
        expires_at=refresh_token_exp,
        oauth_state_id=session.oauth_state_id,
        tokens_exchanged=session.tokens_exchanged,
        token_family_id=session.token_family_id,
        rotation_count=new_rotation_count,
        last_rotation_at=now,
        csrf_token_hash=csrf_token_hash,
    )


def create_session(
    session_id: str,
    user: users_schema.UsersRead,
    request: Request,
    refresh_token: str,
    password_hasher: auth_password_hasher.PasswordHasher,
    db: Session,
    oauth_state_id: str | None = None,
    csrf_token: str | None = None,
) -> None:
    """
    Creates a new user session and stores it in the database.

    Args:
        session_id: Unique identifier for the session.
        user: The user for whom the session is being created.
        request: The incoming HTTP request object.
        refresh_token: The refresh token to be associated with the session.
        password_hasher: Utility to hash tokens.
        db: Database session for storing the session.
        oauth_state_id: Optional OAuth state ID for PKCE mobile flows.
        csrf_token: Plain CSRF token to hash and store for validation.

    Returns:
        None
    """
    # Calculate the refresh token expiration date
    exp = datetime.now(timezone.utc) + timedelta(
        days=auth_constants.JWT_REFRESH_TOKEN_EXPIRE_DAYS
    )

    # Hash the CSRF token if provided
    csrf_hash = None
    if csrf_token:
        csrf_hash = password_hasher.hash_password(csrf_token)

    # Create a new session
    new_session = create_session_object(
        session_id,
        user,
        request,
        password_hasher.hash_password(refresh_token),
        exp,
        oauth_state_id,
        csrf_hash,
    )

    # Add the session to the database
    users_session_crud.create_session(new_session, db)


def edit_session(
    session: users_session_schema.UsersSessions,
    request: Request,
    new_refresh_token: str,
    password_hasher: auth_password_hasher.PasswordHasher,
    db: Session,
    new_csrf_token: str | None = None,
) -> None:
    """
    Edits an existing user session by updating its refresh token.

    Args:
        session: The current user session object to be edited.
        request: The incoming request object containing session context.
        new_refresh_token: The new refresh token to be set for the session.
        password_hasher: Utility for hashing tokens.
        db: Database session for committing changes.
        new_csrf_token: Plain CSRF token to hash and store for validation.

    Returns:
        None
    """
    # Calculate the refresh token expiration date
    exp = datetime.now(timezone.utc) + timedelta(
        days=auth_constants.JWT_REFRESH_TOKEN_EXPIRE_DAYS
    )

    # Hash the new CSRF token if provided
    csrf_hash = None
    if new_csrf_token:
        csrf_hash = password_hasher.hash_password(new_csrf_token)

    # Update the session
    updated_session = edit_session_object(
        request,
        password_hasher.hash_password(new_refresh_token),
        exp,
        session,
        csrf_hash,
    )

    # Update the session in the database
    users_session_crud.edit_session(updated_session, db)


def get_user_agent(request: Request) -> str:
    """
    Extracts the 'User-Agent' string from the request headers.

    Args:
        request (Request): The incoming HTTP request object.

    Returns:
        str: The value of the 'User-Agent' header if present, otherwise an empty string.
    """
    return request.headers.get("user-agent", "")


def get_ip_address(request: Request) -> str:
    """
    Extracts the client's IP address from a FastAPI Request object.

    This function checks for common proxy headers ("X-Forwarded-For" and "X-Real-IP") to determine the original client IP address.
    If these headers are not present, it falls back to the direct client host information.

    Args:
        request (Request): The FastAPI Request object containing headers and client info.

    Returns:
        str: The determined IP address of the client, or "unknown" if it cannot be determined.
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
    Parse a user agent string and extract device information.

    This function analyzes a user agent string to determine device characteristics
    including device type, operating system, and browser information.

    Args:
        user_agent (str): The user agent string to parse.

    Returns:
        DeviceInfo: An object containing parsed device information with the following attributes:
            - device_type: The type of device (MOBILE, TABLET, or PC)
            - operating_system: The name of the operating system family
            - operating_system_version: The version string of the operating system
            - browser: The name of the browser family
            - browser_version: The version string of the browser

    Note:
        - Device type is determined based on whether the user agent indicates a mobile
          or tablet device, defaulting to PC if neither.
        - If any information cannot be determined, it defaults to "Unknown".
    """
    ua = parse(user_agent)
    device_type = (
        DeviceType.MOBILE
        if ua.is_mobile
        else DeviceType.TABLET if ua.is_tablet else DeviceType.PC
    )

    return DeviceInfo(
        device_type=device_type,
        operating_system=ua.os.family or "Unknown",
        operating_system_version=ua.os.version_string or "Unknown",
        browser=ua.browser.family or "Unknown",
        browser_version=ua.browser.version_string or "Unknown",
    )


def cleanup_idle_sessions():
    """
    Clean up idle user sessions that have exceeded the timeout threshold.
    This function removes sessions from the database that have been inactive for longer
    than the configured idle timeout period. It only runs if session idle timeout is enabled.
    The function:
    1. Checks if session idle timeout is enabled via auth_constants
    2. Calculates the cutoff time based on SESSION_IDLE_TIMEOUT_HOURS
    3. Deletes sessions with last_activity_at older than the cutoff time
    4. Logs the number of sessions cleaned up if any were removed
    Returns:
        None
    Raises:
        Any database-related exceptions from users_session_crud.delete_idle_sessions
        are propagated to the caller.
    Note:
        The database session is always properly closed in the finally block.
    """
    if not auth_constants.SESSION_IDLE_TIMEOUT_ENABLED:
        return

    db = SessionLocal()
    try:
        cutoff_time = datetime.now(timezone.utc) - timedelta(
            hours=auth_constants.SESSION_IDLE_TIMEOUT_HOURS
        )

        # Delete sessions with last_activity_at older than cutoff
        deleted_count = users_session_crud.delete_idle_sessions(cutoff_time, db)

        if deleted_count > 0:
            core_logger.print_to_log(
                f"Cleaned up {deleted_count} idle sessions", "info"
            )
    finally:
        db.close()
