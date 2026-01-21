"""Session utility functions and classes."""

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

import users.users_sessions.models as users_session_models
import users.users_sessions.schema as users_session_schema
import users.users_sessions.crud as users_session_crud

import users.users.schema as users_schema

import core.logger as core_logger
from core.database import SessionLocal


class DeviceType(Enum):
    """
    Device type enumeration.

    Attributes:
        MOBILE: Mobile device.
        TABLET: Tablet device.
        PC: Desktop/laptop device.
    """

    MOBILE = "Mobile"
    TABLET = "Tablet"
    PC = "PC"


@dataclass
class DeviceInfo:
    """
    Device information container.

    Attributes:
        device_type: Device type (mobile, tablet, PC).
        operating_system: OS name.
        operating_system_version: OS version string.
        browser: Browser name.
        browser_version: Browser version string.
    """

    device_type: DeviceType
    operating_system: str
    operating_system_version: str
    browser: str
    browser_version: str


def validate_session_timeout(
    session: users_session_models.UsersSessions,
) -> None:
    """
    Validate session hasn't exceeded idle or absolute timeout.

    Only enforces when SESSION_IDLE_TIMEOUT_ENABLED=true.
    Checks idle timeout (last_activity_at) and absolute
    timeout (created_at).

    Args:
        session: The session to validate.

    Raises:
        HTTPException: 401 if session has timed out.
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
    hashed_refresh_token: str | None,
    refresh_token_exp: datetime,
    oauth_state_id: str | None = None,
    csrf_token_hash: str | None = None,
) -> users_session_schema.UsersSessionsInternal:
    """
    Create session object with device and request metadata.

    Args:
        session_id: Unique identifier for the session.
        user: The user associated with the session.
        request: HTTP request containing client information.
        hashed_refresh_token: Hashed refresh token.
        refresh_token_exp: Refresh token expiration datetime.
        oauth_state_id: Optional OAuth state ID for PKCE.
        csrf_token_hash: Hashed CSRF token for validation.

    Returns:
        Session object with user, device, and request details.
    """
    user_agent = get_user_agent(request)
    device_info = parse_user_agent(user_agent)

    now = datetime.now(timezone.utc)

    return users_session_schema.UsersSessionsInternal(
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
    session: users_session_schema.UsersSessionsInternal,
    csrf_token_hash: str | None = None,
) -> users_session_schema.UsersSessionsInternal:
    """
    Create updated session object with new token and metadata.

    Args:
        request: The incoming HTTP request object.
        hashed_refresh_token: Hashed refresh token.
        refresh_token_exp: Refresh token expiration datetime.
        session: The existing session object to update.
        csrf_token_hash: Hashed CSRF token for validation.

    Returns:
        Updated session object with device and token details.
    """
    user_agent = get_user_agent(request)
    device_info = parse_user_agent(user_agent)

    now = datetime.now(timezone.utc)
    new_rotation_count = session.rotation_count + 1

    return users_session_schema.UsersSessionsInternal(
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
    refresh_token: str | None,
    password_hasher: auth_password_hasher.PasswordHasher,
    db: Session,
    oauth_state_id: str | None = None,
    csrf_token: str | None = None,
) -> None:
    """
    Create new user session and store in database.

    Args:
        session_id: Unique identifier for the session.
        user: User for whom session is being created.
        request: The incoming HTTP request object.
        refresh_token: Refresh token to associate or None.
        password_hasher: Utility to hash tokens.
        db: Database session for storing.
        oauth_state_id: Optional OAuth state ID for PKCE.
        csrf_token: Plain CSRF token to hash and store.

    Raises:
        HTTPException: If database error occurs.
    """
    # Calculate the refresh token expiration date
    exp = datetime.now(timezone.utc) + timedelta(
        days=auth_constants.JWT_REFRESH_TOKEN_EXPIRE_DAYS
    )

    # Hash the CSRF token if provided
    csrf_hash = password_hasher.hash_password(csrf_token) if csrf_token else None

    # Create a new session
    new_session = create_session_object(
        session_id,
        user,
        request,
        password_hasher.hash_password(refresh_token) if refresh_token else None,
        exp,
        oauth_state_id,
        csrf_hash,
    )

    # Add the session to the database
    users_session_crud.create_session(new_session, db)


def edit_session(
    session: users_session_schema.UsersSessionsInternal,
    request: Request,
    new_refresh_token: str,
    password_hasher: auth_password_hasher.PasswordHasher,
    db: Session,
    new_csrf_token: str | None = None,
) -> None:
    """
    Update existing user session with new refresh token.

    Args:
        session: Current user session object to edit.
        request: Incoming request containing session context.
        new_refresh_token: New refresh token to set.
        password_hasher: Utility for hashing tokens.
        db: Database session for committing changes.
        new_csrf_token: Plain CSRF token to hash and store.

    Raises:
        HTTPException: If database error occurs.
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
    Extract User-Agent string from request headers.

    Args:
        request: The incoming HTTP request object.

    Returns:
        User-Agent header value or empty string.
    """
    return request.headers.get("user-agent", "")


def get_ip_address(request: Request) -> str:
    """
    Extract client IP address from request.

    Checks proxy headers (X-Forwarded-For, X-Real-IP) first,
    then falls back to direct client host.

    Args:
        request: Request object with headers and client info.

    Returns:
        Client IP address or "unknown" if indeterminate.
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
    Parse user agent string and extract device information.

    Args:
        user_agent: The user agent string to parse.

    Returns:
        Device information including type, OS, and browser
        details. Unknown fields default to "Unknown".
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


def cleanup_idle_sessions() -> None:
    """
    Clean up idle sessions exceeding timeout threshold.

    Removes sessions inactive longer than the configured idle
    timeout period. Only runs if SESSION_IDLE_TIMEOUT_ENABLED.
    Logs count of cleaned sessions.

    Raises:
        HTTPException: If database error occurs.
    """
    if not auth_constants.SESSION_IDLE_TIMEOUT_ENABLED:
        return

    with SessionLocal() as db:
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
        except Exception as err:
            core_logger.print_to_log(
                f"Error in cleanup_idle_sessions: {err}",
                "error",
                exc=err,
            )
