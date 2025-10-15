import os

from enum import Enum
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

import session.constants as session_constants
import session.schema as session_schema
import session.crud as session_crud
import session.password_hasher as session_password_hasher
import session.token_manager as session_token_manager

import users.user.crud as users_crud
import users.user.schema as users_schema
import users.user_identity_providers.crud as user_idp_crud

import identity_providers.service as idp_service
import core.logger as core_logger


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


def create_session_object(
    session_id: str,
    user: users_schema.UserRead,
    request: Request,
    hashed_refresh_token: str,
    refresh_token_exp: datetime,
) -> session_schema.UsersSessions:
    """
    Creates a UsersSessions object representing a user session with device and request metadata.

    Args:
        session_id (str): Unique identifier for the session.
        user (users_schema.UserRead): The user associated with the session.
        request (Request): The HTTP request object containing client information.
        hashed_refresh_token (str): The hashed refresh token for the session.
        refresh_token_exp (datetime): The expiration datetime for the refresh token.

    Returns:
        session_schema.UsersSessions: The session object populated with user, device, and request details.
    """
    user_agent = get_user_agent(request)
    device_info = parse_user_agent(user_agent)

    return session_schema.UsersSessions(
        id=session_id,
        user_id=user.id,
        refresh_token=hashed_refresh_token,
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
    hashed_refresh_token: str,
    refresh_token_exp: datetime,
    session: Session,
) -> session_schema.UsersSessions:
    """
    Edits and returns a UsersSessions object with updated session information.

    Args:
        request (Request): The incoming HTTP request object.
        hashed_refresh_token (str): The hashed refresh token to associate with the session.
        refresh_token_exp (datetime): The expiration datetime for the refresh token.
        session (Session): The existing session object to update.

    Returns:
        session_schema.UsersSessions: The updated UsersSessions object containing session details such as device info, IP address, and token expiration.
    """
    user_agent = get_user_agent(request)
    device_info = parse_user_agent(user_agent)

    return session_schema.UsersSessions(
        id=session.id,
        user_id=session.user_id,
        refresh_token=hashed_refresh_token,
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

    Args:
        username (str): The username of the user attempting to authenticate.
        password (str): The plaintext password provided by the user.
        password_hasher (session_password_hasher.PasswordHasher): An instance of the password hasher for verifying and updating password hashes.
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
    token_manager: session_token_manager.TokenManager,
    session_id: str | None = None,
) -> Tuple[str, datetime, str, datetime, str, str]:
    """
    Generates session tokens for a user, including access token, refresh token, and CSRF token.

    Args:
        user (users_schema.UserRead): The user object for whom the tokens are being created.
        token_manager (session_token_manager.TokenManager): The token manager responsible for token creation.
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
        session_id, user, session_token_manager.TokenType.ACCESS
    )

    refresh_token_exp, refresh_token = token_manager.create_token(
        session_id, user, session_token_manager.TokenType.REFRESH
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


def create_response_with_tokens(
    response: Response, access_token: str, refresh_token: str, csrf_token: str
) -> Response:
    """
    Sets access, refresh, and CSRF tokens as cookies on the given response object.

    Args:
        response (Response): The response object to set cookies on.
        access_token (str): The JWT access token to be set as a cookie.
        refresh_token (str): The JWT refresh token to be set as a cookie.
        csrf_token (str): The CSRF token to be set as a cookie.

    Returns:
        Response: The response object with the tokens set as cookies.
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
    session_id: str,
    user: users_schema.UserRead,
    request: Request,
    refresh_token: str,
    password_hasher: session_password_hasher.PasswordHasher,
    db: Session,
) -> None:
    """
    Creates a new user session and stores it in the database.

    Args:
        session_id (str): Unique identifier for the session.
        user (users_schema.UserRead): The user for whom the session is being created.
        request (Request): The incoming HTTP request object.
        refresh_token (str): The refresh token to be associated with the session.
        password_hasher (session_password_hasher.PasswordHasher): Utility to hash the refresh token.
        db (Session): Database session for storing the session.

    Returns:
        None
    """
    # Calculate the refresh token expiration date
    exp = datetime.now(timezone.utc) + timedelta(
        days=session_constants.JWT_REFRESH_TOKEN_EXPIRE_DAYS
    )

    # Create a new session
    new_session = create_session_object(
        session_id,
        user,
        request,
        password_hasher.hash_password(refresh_token),
        exp,
    )

    # Add the session to the database
    session_crud.create_session(new_session, db)


def edit_session(
    session: session_schema.UsersSessions,
    request: Request,
    new_refresh_token: str,
    password_hasher: session_password_hasher.PasswordHasher,
    db: Session,
) -> None:
    """
    Edits an existing user session by updating its refresh token and expiration date.

    Args:
        session (session_schema.UsersSessions): The current user session object to be edited.
        request (Request): The incoming request object containing session context.
        new_refresh_token (str): The new refresh token to be set for the session.
        password_hasher (session_password_hasher.PasswordHasher): Utility for hashing the refresh token.
        db (Session): Database session for committing changes.

    Returns:
        None
    """
    # Calculate the refresh token expiration date
    exp = datetime.now(timezone.utc) + timedelta(
        days=session_constants.JWT_REFRESH_TOKEN_EXPIRE_DAYS
    )

    # Update the session
    updated_session = edit_session_object(
        request,
        password_hasher.hash_password(new_refresh_token),
        exp,
        session,
    )

    # Update the session in the database
    session_crud.edit_session(updated_session, db)


def complete_login(
    response: Response,
    request: Request,
    user: users_schema.UserRead,
    client_type: str,
    password_hasher: session_password_hasher.PasswordHasher,
    token_manager: session_token_manager.TokenManager,
    db: Session,
) -> dict | str:
    """
    Handles the completion of the login process by generating session and authentication tokens,
    storing the session in the database, and returning appropriate responses based on client type.

    Args:
        response (Response): The HTTP response object to set cookies for web clients.
        request (Request): The HTTP request object containing client information.
        user (users_schema.UserRead): The authenticated user object.
        client_type (str): The type of client ("web" or "mobile").
        password_hasher (session_password_hasher.PasswordHasher): Utility for password hashing.
        token_manager (session_token_manager.TokenManager): Utility for token generation and management.
        db (Session): Database session for storing session information.

    Returns:
        dict | str: For web clients, returns the session ID as a string.
                    For mobile clients, returns a dictionary containing tokens and session info.

    Raises:
        HTTPException: If the client type is invalid, raises a 403 Forbidden error.
    """
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
    create_session(session_id, user, request, refresh_token, password_hasher, db)

    if client_type == "web":
        # Set response cookies with tokens
        create_response_with_tokens(response, access_token, refresh_token, csrf_token)

        # Return the session_id
        return {
            "session_id": session_id,
        }
    if client_type == "mobile":
        # Return the tokens directly (no cookies for mobile)
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "session_id": session_id,
            "token_type": "Bearer",
            "expires_in": int(access_token_exp.timestamp()),
        }

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Invalid client type",
        headers={"WWW-Authenticate": "Bearer"},
    )


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
    Parses a user agent string and extracts device information.

    Args:
        user_agent (str): The user agent string to be parsed.

    Returns:
        DeviceInfo: An object containing details about the device type, operating system,
                    operating system version, browser, and browser version.

    DeviceInfo fields:
        - device_type (DeviceType): The type of device ("Mobile", "Tablet", or "PC").
        - operating_system (str): The name of the operating system.
        - operating_system_version (str): The version of the operating system.
        - browser (str): The name of the browser.
        - browser_version (str): The version of the browser.
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


async def refresh_idp_tokens_if_needed(user_id: int, db: Session) -> None:
    """
    Opportunistically refresh IdP tokens for all linked identity providers.

    This helper function is called during Endurain session refresh to check if any
    linked identity providers have tokens that need refreshing. If tokens are close
    to expiry (within 5 minutes), it attempts to silently refresh them.

    This provides a better user experience by:
    - Reducing the need for re-authentication with IdPs
    - Maintaining seamless SSO sessions
    - Avoiding token expiry during active user sessions

    Args:
        user_id (int): The ID of the user whose IdP tokens should be checked.
        db (Session): The database session for querying user-IdP links.

    Returns:
        None

    Side Effects:
        - May update IdP tokens in database if refresh is successful
        - Logs refresh attempts at debug level
        - Logs refresh failures at debug level (non-blocking)

    Error Handling:
        - All errors are caught and logged, but do not block session refresh
        - IdP token refresh failures are non-fatal (user session continues)
        - Network errors to IdP are logged but don't affect Endurain session

    Performance:
        - Only refreshes tokens that are close to expiry (policy-based)
        - Rate-limited to prevent excessive IdP API calls (1-minute minimum)
        - Runs asynchronously to avoid blocking session refresh response

    Security:
        - Uses existing IdP service methods (inherits all security controls)
        - Token refresh follows OAuth2 refresh_token grant type
        - Failed refreshes clear invalid tokens from database
    """
    try:
        # Get all IdP links for this user
        idp_links = user_idp_crud.get_user_idp_links(user_id, db)

        if not idp_links:
            # User has no IdP links - nothing to refresh
            return

        # Check each IdP link and refresh if needed
        for link in idp_links:
            try:
                # Check if this IdP token needs refreshing (policy-based)
                if idp_service.idp_service._should_refresh_idp_token(link):
                    core_logger.print_to_log(
                        f"Attempting to refresh IdP token for user {user_id}, idp {link.idp_id}",
                        "debug",
                    )

                    # Attempt to refresh the IdP session
                    result = await idp_service.idp_service.refresh_idp_session(
                        user_id, link.idp_id, db
                    )

                    if result:
                        core_logger.print_to_log(
                            f"Successfully refreshed IdP token for user {user_id}, idp {link.idp_id}",
                            "debug",
                        )
                    else:
                        core_logger.print_to_log(
                            f"IdP token refresh failed for user {user_id}, idp {link.idp_id}. "
                            "User may need to re-authenticate with IdP later.",
                            "debug",
                        )
                else:
                    # Token doesn't need refreshing yet (still valid or recently refreshed)
                    pass

            except Exception as err:
                # Log individual IdP refresh failure but continue with other IdPs
                core_logger.print_to_log(
                    f"Error checking/refreshing IdP token for user {user_id}, idp {link.idp_id}: {err}",
                    "warning",
                    exc=err,
                )
                # Continue to next IdP link

    except Exception as err:
        # Catch-all for unexpected errors (e.g., database query failure)
        core_logger.print_to_log(
            f"Error retrieving IdP links for user {user_id}: {err}",
            "warning",
            exc=err,
        )
        # Don't raise - IdP token refresh is opportunistic and non-blocking


async def clear_all_idp_tokens(user_id: int, db: Session) -> None:
    """
    Clear all IdP refresh tokens for a user upon logout.

    This helper function is called during logout to clear all stored IdP refresh tokens
    for the user. This implements the security best practice of invalidating tokens
    when a user explicitly logs out.

    According to OAuth2 best practices (RFC 6819), refresh tokens should be revoked
    when the user logs out to minimize the window of token exposure.

    Args:
        user_id (int): The ID of the user who is logging out.
        db (Session): The database session for querying and updating user-IdP links.

    Returns:
        None

    Side Effects:
        - Clears all IdP refresh tokens from database for this user
        - Sets idp_refresh_token, idp_access_token_expires_at, and
          idp_refresh_token_updated_at to NULL
        - Logs clearing actions at debug level

    Error Handling:
        - All errors are caught and logged but do not block logout
        - Logout succeeds even if IdP token clearing fails
        - Individual IdP failures don't prevent clearing other IdPs

    Security Note:
        - This follows the principle of least privilege
        - Reduces the window of token validity after logout
        - User must re-authenticate with IdP on next SSO login
        - Does NOT revoke tokens at the IdP (optional future enhancement)
    """
    try:
        # Get all IdP links for this user
        idp_links = user_idp_crud.get_user_idp_links(user_id, db)

        if not idp_links:
            # User has no IdP links - nothing to clear
            return

        # Clear tokens for each IdP link
        for link in idp_links:
            try:
                success = user_idp_crud.clear_idp_refresh_token(
                    user_id, link.idp_id, db
                )

                if success:
                    core_logger.print_to_log(
                        f"Cleared IdP refresh token for user {user_id}, idp {link.idp_id} on logout",
                        "debug",
                    )
                else:
                    core_logger.print_to_log(
                        f"No IdP refresh token to clear for user {user_id}, idp {link.idp_id}",
                        "debug",
                    )

            except Exception as err:
                # Log individual IdP token clearing failure but continue with other IdPs
                core_logger.print_to_log(
                    f"Error clearing IdP token for user {user_id}, idp {link.idp_id}: {err}",
                    "warning",
                    exc=err,
                )
                # Continue to next IdP link

    except Exception as err:
        # Catch-all for unexpected errors (e.g., database query failure)
        core_logger.print_to_log(
            f"Error retrieving IdP links for user {user_id} during logout: {err}",
            "warning",
            exc=err,
        )
        # Don't raise - IdP token clearing is a best-effort security measure
