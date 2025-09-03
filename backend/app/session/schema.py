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


class CSRFMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        # Define paths that don't need CSRF protection
        self.exempt_paths = [
            "/api/v1/token",
            "/api/v1/refresh",
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
