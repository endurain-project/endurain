"""HTTP middleware for security headers and CSRF checks."""

from collections.abc import Awaitable, Callable

from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from starlette.types import ASGIApp

import core.config as core_config
import modules.server_settings.schema as server_settings_schema

_DEPLOYED_ENVIRONMENTS = {"production", "demo"}
_CSRF_METHODS = {"POST", "PUT", "DELETE", "PATCH"}

#: Request headers a browser client may send cross-origin. A header missing from
#: this list is not merely stripped — the browser's preflight fails outright, so
#: the request never happens. Declared here rather than inline in ``create_app``
#: so a test can check it against the headers the routes actually declare.
CORS_ALLOW_HEADERS: tuple[str, ...] = (
    "Authorization",
    "Content-Type",
    "Idempotency-Key",
    "If-Match",
    "X-Client-Type",
    "X-CSRF-Token",
)

#: Response headers a browser client may read. Anything not listed is invisible
#: to JavaScript even though it is on the wire — which is why ``ETag`` belongs
#: here: it is the tag the client echoes back in ``If-Match``.
CORS_EXPOSE_HEADERS: tuple[str, ...] = ("ETag", "X-Request-ID")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Add browser security headers to HTTP responses.

    Attributes:
        None.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """
        Add security headers to the downstream response.

        Args:
            request: Incoming HTTP request.
            call_next: Next ASGI handler in the chain.

        Returns:
            Response with security headers applied.

        Raises:
            Exception: Propagates downstream request errors.
        """
        response = await call_next(request)

        # Prevent MIME sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"

        # Disable legacy browser XSS auditors; CSP is the modern control.
        response.headers["X-XSS-Protection"] = "0"

        # Control referrer information leakage
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Disable unnecessary browser features
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

        if core_config.settings.ENVIRONMENT in _DEPLOYED_ENVIRONMENTS:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        # Only HTML receives CSP to avoid surprising JSON API clients.
        content_type = response.headers.get("content-type", "")
        if "text/html" in content_type:
            allowed_tile_domains = getattr(
                request.app.state,
                "allowed_tile_domains",
                server_settings_schema.DEFAULT_ALLOWED_TILE_DOMAINS,
            )
            tile_domains_str = " ".join(allowed_tile_domains)

            # Extra connect-src origins for deployments behind a
            # forward-auth reverse proxy that redirects API calls
            # to its own domain (see CSP_ADDITIONAL_CONNECT_SRC).
            connect_src = "'self' https://cdn.jsdelivr.net https://codeberg.org"
            extra_connect_src = core_config.settings.CSP_ADDITIONAL_CONNECT_SRC
            if extra_connect_src:
                connect_src = f"{connect_src} {' '.join(extra_connect_src)}"

            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                f"img-src 'self' data: {tile_domains_str} "
                "https://fastapi.tiangolo.com; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                f"connect-src {connect_src}; "
                "media-src 'self' data:"
            )

        if "Server" in response.headers:
            del response.headers["Server"]

        return response


class CSRFMiddleware(BaseHTTPMiddleware):
    """
    Require CSRF headers for browser state-changing requests.

    Attributes:
        exempt_paths: Exact paths skipped by CSRF checks.
        exempt_path_prefixes: Path prefixes skipped by CSRF checks.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        # Define paths that don't need CSRF protection
        self.exempt_paths = [
            "/api/v1/auth/login",
            "/api/v1/auth/mfa/verify",
            "/api/v1/auth/refresh",
            "/api/v1/password-reset/request",
            "/api/v1/password-reset/confirm",
            "/api/v1/sign-up/request",
            "/api/v1/sign-up/confirm",
        ]
        self.exempt_path_prefixes = [
            "/api/v1/public/idp/session/",
        ]

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """
        Enforce CSRF header presence for web clients.

        Args:
            request: Incoming HTTP request.
            call_next: Next ASGI handler in the chain.

        Returns:
            Response from the downstream handler, or a 403
            response when CSRF validation fails.

        Raises:
            Exception: Propagates downstream request errors.
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

        if request.method in _CSRF_METHODS:
            csrf_header = request.headers.get("X-CSRF-Token")

            if not csrf_header:
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={"detail": "CSRF token required"},
                )

        response = await call_next(request)
        return response
