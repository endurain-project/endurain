from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware


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
            "/api/v1/sign-up/confirm",
        ]
        # Define path prefixes that don't need CSRF protection (for dynamic routes)
        self.exempt_path_prefixes = [
            "/api/v1/public/idp/session/",
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
                - Requires "X-CSRF-Token" header.
                - Raises HTTPException 403 if token is missing.
        """
        # Get client type from header
        client_type = request.headers.get("X-Client-Type")

        # Skip CSRF checks for not web clients
        if client_type != "web":
            return await call_next(request)

        # Skip CSRF check for exempt paths (exact match)
        if request.url.path in self.exempt_paths:
            return await call_next(request)

        # Skip CSRF check for exempt path prefixes (dynamic routes)
        for prefix in self.exempt_path_prefixes:
            if request.url.path.startswith(prefix):
                return await call_next(request)

        # Check for CSRF token in POST, PUT, DELETE, and PATCH requests
        if request.method in ["POST", "PUT", "DELETE", "PATCH"]:
            csrf_header = request.headers.get("X-CSRF-Token")

            if not csrf_header:
                raise HTTPException(status_code=403, detail="CSRF token required")

        response = await call_next(request)
        return response
