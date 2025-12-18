"""
Rate limiting middleware for Endurain API.

This module provides rate limiting functionality to protect API endpoints from abuse,
particularly focusing on OAuth2/OIDC authentication flows. It uses slowapi (built on
python-limits) to implement per-IP rate limiting with in-memory storage.

Protects endpoints from:
- Brute-force attacks on authorization endpoints
- Callback flooding and replay attempts
- Account enumeration attacks
- Denial of Service (DoS) attacks

Usage:
    from core.rate_limit import limiter, rate_limit_exceeded_handler

    # In main.py, add the limiter to the FastAPI app
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

    # In routers, apply rate limits to endpoints
    @router.get("/authorize")
    @limiter.limit("10/minute")
    async def authorize(request: Request, ...):
        ...
"""

from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from fastapi import Request, Response
from fastapi.responses import JSONResponse
import core.logger as core_logger
import session.utils as session_utils


# Predefined rate limit decorators for common use cases
# These can be imported and used directly on routes

# OAuth endpoints - moderate protection (authentication flows are user-initiated)
OAUTH_AUTHORIZE_LIMIT = "10/minute"  # Authorization initiation
OAUTH_CALLBACK_LIMIT = "10/minute"  # Callback handling after IdP redirect
OAUTH_DISCONNECT_LIMIT = "5/minute"  # Account disconnection (less frequent)
PKCE_TOKEN_EXCHANGE_LIMIT = "10/minute"  # Mobile PKCE token exchange

# Session endpoints - stricter protection (potential brute-force target)
SESSION_LOGIN_LIMIT = (
    "3/minute"  # Login attempts (reduced from 5 to prevent brute-force)
)
SESSION_REFRESH_LIMIT = "20/minute"  # Token refresh (more frequent but still limited)
SESSION_LOGOUT_LIMIT = "10/minute"  # Logout requests

# MFA endpoints - very strict protection (high-value target for brute-force)
MFA_VERIFY_LIMIT = (
    "3/minute"  # MFA code verification (AuthQuake-style attack prevention)
)

# API endpoints - generous limits for normal usage
API_READ_LIMIT = "60/minute"  # GET requests (read operations)
API_WRITE_LIMIT = "30/minute"  # POST/PUT/DELETE (write operations)

# Admin endpoints - restrictive limits
ADMIN_LIMIT = "10/minute"  # Administrative operations


# Initialize the rate limiter with in-memory storage
# For production with multiple backend instances, consider using Redis storage:
# from slowapi.middleware import SlowAPIMiddleware
# from slowapi import _rate_limit_exceeded_handler
# limiter = Limiter(key_func=session_utils.get_ip_address, storage_uri="redis://localhost:6379")
limiter = Limiter(
    key_func=session_utils.get_ip_address,
    default_limits=["100/minute"],  # Global default: 100 requests per minute per IP
    storage_uri="memory://",  # In-memory storage (single instance only)
    headers_enabled=True,  # Include rate limit headers in responses
)


async def rate_limit_exceeded_handler(
    request: Request, exc: RateLimitExceeded
) -> Response:
    """
    Handle rate limit exceeded exceptions with standardized responses.
    This handler is triggered when a client exceeds the configured rate limit for an endpoint.
    It logs the violation with client details and returns a standardized JSON response with
    appropriate HTTP 429 status code and retry timing information.
    Args:
        request (Request): The incoming FastAPI/Starlette request object containing client information.
        exc (RateLimitExceeded): The rate limit exception raised by slowapi, containing violation details.
    Returns:
        Response: A JSONResponse with status code 429 containing:
            - error: A brief error message
            - detail: User-friendly message with retry timing
            - retry_after: Number of seconds until the client can retry
            Also includes a 'Retry-After' HTTP header with the same timing information.
    Note:
        The function logs rate limit violations with client IP, requested path, and limit details
        for monitoring and security purposes. The default retry period is set to 60 seconds.
    """
    # Extract client identifier for logging
    client_ip = session_utils.get_ip_address(request)
    path = request.url.path

    # Log the rate limit violation
    core_logger.print_to_log(
        f"Rate limit exceeded for {client_ip} on {path}: {exc.detail}",
        "warning",
        context={"client_ip": client_ip, "path": path, "limit": str(exc.detail)},
    )

    # Parse retry_after from the exception if available
    # slowapi provides this in the format "X per Y" (e.g., "10 per 1 minute")
    retry_after_seconds = 60  # Default to 1 minute

    # Create standardized error response
    response_data = {
        "error": "Rate limit exceeded",
        "detail": f"Too many requests. Please try again in {retry_after_seconds} seconds.",
        "retry_after": retry_after_seconds,
    }

    # Create response with proper headers
    response = JSONResponse(
        status_code=429,
        content=response_data,
    )

    # Add Retry-After header (standard HTTP header for rate limiting)
    response.headers["Retry-After"] = str(retry_after_seconds)

    return response
