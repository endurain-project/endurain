from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add security headers to all HTTP responses.

    This middleware adds essential security headers to protect against common web vulnerabilities:
    - XSS (Cross-Site Scripting)
    - Clickjacking
    - MIME sniffing attacks
    - Information leakage through referrer
    - Unauthorized feature access

    Headers added:
        X-Content-Type-Options: nosniff
            Prevents MIME sniffing attacks by forcing browsers to respect declared content types.

        X-Frame-Options: DENY
            Prevents clickjacking attacks by disallowing the page to be embedded in iframes.

        X-XSS-Protection: 1; mode=block
            Enables browser's XSS filter and blocks page rendering if XSS attack detected.
            (Legacy header but still supported by older browsers)

        Referrer-Policy: strict-origin-when-cross-origin
            Controls how much referrer information is sent with requests:
            - Same origin: full URL
            - Cross origin: only origin (no path/query)
            - HTTPS to HTTP: no referrer

        Permissions-Policy: geolocation=(), microphone=(), camera=()
            Disables unnecessary browser features to reduce attack surface.
            Prevents unauthorized access to sensitive device APIs.

        Content-Security-Policy: default-src 'self'
            Restricts resources to same origin by default (API responses).
            For frontend serving, this would need customization.

    Note:
        These headers are applied globally to all responses.
        Individual endpoints can override headers if needed via response objects.
    """

    async def dispatch(self, request: Request, call_next):
        """
        Process request and add security headers to response.

        Args:
            request: The incoming HTTP request
            call_next: The next middleware or endpoint handler

        Returns:
            Response with security headers added
        """
        response = await call_next(request)

        # Prevent MIME sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"

        # XSS protection (legacy but still useful for older browsers)
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Control referrer information leakage
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Disable unnecessary browser features
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=()"
        )

        # Content Security Policy for API responses
        # Note: Only add CSP for HTML responses to avoid affecting JSON API responses
        content_type = response.headers.get("content-type", "")
        if "text/html" in content_type:
            response.headers["Content-Security-Policy"] = "default-src 'self'"

        # Remove server version header for security through obscurity
        if "Server" in response.headers:
            del response.headers["Server"]

        return response


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
            "/api/v1/auth/login",
            "/api/v1/auth/refresh",
            "/api/v1/auth/mfa/verify",
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
