from pydantic import BaseModel
from datetime import datetime
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware


class UsersSessions(BaseModel):
    id: str
    user_id: int
    refresh_token: str
    ip_address: str
    device_type: str
    operating_system: str
    operating_system_version: str
    browser: str
    browser_version: str
    created_at: datetime
    expires_at: datetime

    model_config = {"from_attributes": True}


class LoginRequest(BaseModel):
    username: str
    password: str


class MFALoginRequest(BaseModel):
    username: str
    mfa_code: str


class MFARequiredResponse(BaseModel):
    mfa_required: bool = True
    username: str
    message: str = "MFA verification required"


class PendingMFALogin:
    """Store for pending MFA logins"""

    def __init__(self):
        self._store = {}

    def add_pending_login(self, username: str, user_id: int):
        self._store[username] = user_id

    def get_pending_login(self, username: str):
        return self._store.get(username)

    def delete_pending_login(self, username: str):
        if username in self._store:
            del self._store[username]

    def has_pending_login(self, username: str):
        return username in self._store

    def clear_all(self):
        self._store.clear()


def get_pending_mfa_store():
    return pending_mfa_store


pending_mfa_store = PendingMFALogin()


class CSRFMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        # Define paths that don't need CSRF protection
        self.exempt_paths = [
            "/api/v1/token",
            "/api/v1/refresh",
            "/api/v1/mfa/verify",
            "/api/v1/password-reset/request",
            "/api/v1/password-reset/confirm",
        ]

    async def dispatch(self, request: Request, call_next):
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
