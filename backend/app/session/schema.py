from pydantic import BaseModel, Field, field_validator, ConfigDict
from datetime import datetime
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware


class UsersSessions(BaseModel):
    """
    Represents a user session with metadata about the device, browser, and session timing.
    Attributes:
        id (str): Unique session identifier.
        user_id (int): User ID that owns this session.
        refresh_token (str): Session refresh token.
        ip_address (str): Client IP address (max length: 45).
        device_type (str): Device type (max length: 45).
        operating_system (str): Operating system (max length: 45).
        operating_system_version (str): OS version (max length: 45).
        browser (str): Browser name (max length: 45).
        browser_version (str): Browser version (max length: 45).
        created_at (datetime): Session creation timestamp.
        expires_at (datetime): Session expiration timestamp.
    Config:
        from_attributes (bool): Allows model initialization from attributes.
        extra (str): Forbids extra fields not defined in the model.
        validate_assignment (bool): Enables validation on assignment.
    Validators:
        expires_at: Ensures that the expiration timestamp is after the creation timestamp.
    """

    id: str = Field(..., description="Unique session identifier")
    user_id: int = Field(..., description="User ID that owns this session")
    refresh_token: str = Field(..., description="Session refresh token")
    ip_address: str = Field(..., max_length=45, description="Client IP address")
    device_type: str = Field(..., max_length=45, description="Device type")
    operating_system: str = Field(..., max_length=45, description="Operating system")
    operating_system_version: str = Field(..., max_length=45, description="OS version")
    browser: str = Field(..., max_length=45, description="Browser name")
    browser_version: str = Field(..., max_length=45, description="Browser version")
    created_at: datetime = Field(..., description="Session creation timestamp")
    expires_at: datetime = Field(..., description="Session expiration timestamp")

    model_config = ConfigDict(
        from_attributes=True, extra="forbid", validate_assignment=True
    )


class LoginRequest(BaseModel):
    """
    Schema for login requests containing username and password.

    Attributes:
        username (str): The username of the user. Must be between 1 and 250 characters.
        password (str): The user's password. Must be at least 8 characters long.
    """
    username: str = Field(..., min_length=1, max_length=250)
    password: str = Field(..., min_length=8)


class MFALoginRequest(BaseModel):
    """
    Schema for Multi-Factor Authentication (MFA) login request.

    Attributes:
        username (str): The username of the user attempting to log in. Must be between 1 and 250 characters.
        mfa_code (str): The 6-digit MFA code provided by the user. Must match the pattern: six consecutive digits.
    """
    username: str = Field(..., min_length=1, max_length=250)
    mfa_code: str = Field(..., pattern=r'^\d{6}$')


class MFARequiredResponse(BaseModel):
    """
    Represents a response indicating that Multi-Factor Authentication (MFA) is required.

    Attributes:
        mfa_required (bool): Indicates whether MFA is required. Defaults to True.
        username (str): The username for which MFA is required.
        message (str): A message describing the requirement. Defaults to "MFA verification required".
    """
    mfa_required: bool = True
    username: str
    message: str = "MFA verification required"


class PendingMFALogin:
    """
    A class to manage pending Multi-Factor Authentication (MFA) login sessions.

    This class provides methods to add, retrieve, delete, and check pending login entries
    for users who are in the process of MFA authentication. It uses an internal dictionary
    to store the mapping between usernames and their associated user IDs.

    Attributes:
        _store (dict): Internal storage mapping usernames to user IDs for pending logins.

    Methods:
        add_pending_login(username: str, user_id: int):
            Adds a pending login entry for the specified username and user ID.

        get_pending_login(username: str):
            Retrieves the user ID associated with the given username's pending login entry.

        delete_pending_login(username: str):
            Removes the pending login entry for the specified username.

        has_pending_login(username: str):
            Checks if the specified username has a pending login entry.

        clear_all():
            Clears all pending login entries from the internal store.
    """

    def __init__(self):
        self._store = {}

    def add_pending_login(self, username: str, user_id: int):
        """
        Adds a pending login entry for a user.

        Stores the provided username and associated user ID in the internal store,
        marking the user as pending login.

        Args:
            username (str): The username of the user to add.
            user_id (int): The unique identifier of the user.

        """
        self._store[username] = user_id

    def get_pending_login(self, username: str):
        """
        Retrieve the pending login information for a given username.

        Args:
            username (str): The username to look up.

        Returns:
            Any: The pending login information associated with the username, or None if not found.
        """
        return self._store.get(username)

    def delete_pending_login(self, username: str):
        """
        Removes the pending login entry for the specified username from the internal store.

        Args:
            username (str): The username whose pending login entry should be deleted.

        Returns:
            None
        """
        if username in self._store:
            del self._store[username]

    def has_pending_login(self, username: str):
        """
        Checks if the given username has a pending login session.

        Args:
            username (str): The username to check for a pending login.

        Returns:
            bool: True if the username has a pending login session, False otherwise.
        """
        return username in self._store

    def clear_all(self):
        """
        Removes all items from the internal store, effectively resetting it to an empty state.
        """
        self._store.clear()


def get_pending_mfa_store():
    """
    Retrieve the current pending MFA (Multi-Factor Authentication) store.

    Returns:
        dict: The pending MFA store containing MFA-related data.
    """
    return pending_mfa_store


pending_mfa_store = PendingMFALogin()


class CSRFMiddleware(BaseHTTPMiddleware):
    """
    Middleware for CSRF protection in FastAPI applications.

    This middleware checks for a valid CSRF token in requests from web clients to prevent cross-site request forgery attacks.
    It exempts specific API paths from CSRF checks and only enforces validation for POST, PUT, DELETE, and PATCH requests.

    Attributes:
        exempt_paths (list): List of URL paths that are exempt from CSRF protection.

    Methods:
        dispatch(request, call_next):
            Processes incoming requests, enforcing CSRF checks for web clients on non-exempt paths and applicable HTTP methods.
            Raises HTTPException with status code 403 if CSRF token is missing or invalid.
    """
    def __init__(self, app):
        super().__init__(app)
        # Define paths that don't need CSRF protection
        self.exempt_paths = [
            "/api/v1/token",
            "/api/v1/refresh",
            "/api/v1/mfa/verify",
            "/api/v1/password-reset/request",
            "/api/v1/password-reset/confirm",
            "/api/v1/sign-up/request",
            "/api/v1/sign-up/confirm"
        ]

    async def dispatch(self, request: Request, call_next):
        """
        Middleware method to enforce CSRF protection for web clients.

        Args:
            request (Request): The incoming HTTP request.
            call_next (Callable): The next middleware or endpoint handler.

        Returns:
            Response: The HTTP response after CSRF validation.

        Behavior:
            - Skips CSRF checks for non-web clients (determined by "X-Client-Type" header).
            - Skips CSRF checks for exempt paths.
            - For web clients and non-exempt paths, validates CSRF token for POST, PUT, DELETE, and PATCH requests:
                - Requires both "endurain_csrf_token" cookie and "X-CSRF-Token" header.
                - Raises HTTPException 403 if tokens are missing or do not match.
        """
        # Get client type from header
        client_type = request.headers.get("X-Client-Type")

        # Skip CSRF checks for not web clients
        if client_type != "web":
            return await call_next(request)

        # Skip CSRF check for exempt paths
        if request.url.path in self.exempt_paths:
            return await call_next(request)

        # Check for CSRF token in POST, PUT, DELETE, and PATCH requests
        if request.method in ["POST", "PUT", "DELETE", "PATCH"]:
            csrf_cookie = request.cookies.get("endurain_csrf_token")
            csrf_header = request.headers.get("X-CSRF-Token")

            if not csrf_cookie or not csrf_header:
                raise HTTPException(status_code=403, detail="CSRF token missing")

            if csrf_cookie != csrf_header:
                raise HTTPException(status_code=403, detail="CSRF token invalid")

        response = await call_next(request)
        return response
