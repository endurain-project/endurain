"""
Centralized rate limiting for the Endurain API.

Provides a single :data:`limiter` instance used by every
router, named tier constants for different endpoint
classes, and a JSON-aware 429 error handler.

The limiter key function hashes the Bearer token when
present (each session gets its own bucket) and falls
back to the proxy-aware client IP for unauthenticated
callers.

Architecture
------------
1. ``SlowAPIMiddleware`` applies :data:`DEFAULT` limits
   to every route automatically (no endpoint code
   changes needed).
2. Routers import a tier constant (e.g. :data:`WRITE`)
   and decorate individual endpoints with
   ``@limiter.limit(...)`` for tighter caps.
3. To add a new tier, define a module-level constant
   and document it in this module.
"""

import hashlib

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from starlette.responses import Response

import core.config as core_config
import core.logger as core_logger
import core.network as core_network

logger = core_logger.get_logger(__name__)

#: Baseline applied globally via ``SlowAPIMiddleware``.
DEFAULT: str = "120/minute"

#: Write operations — creating or mutating resources.
WRITE: str = "30/minute"

#: Sensitive operations — login, MFA, password reset,
#: signup, OAuth flows.
SENSITIVE: str = "10/minute"

#: Activity file uploads / imports — CPU/IO-heavy parsing
#: of user-supplied files; tighter than WRITE to bound
#: resource consumption on the ingestion endpoints.
UPLOAD: str = "20/minute"


def _get_rate_limit_key(request: Request) -> str:
    """
    Derive a per-caller rate-limit bucket key.

    Authenticated callers are identified by a truncated
    SHA-256 of their Bearer token so users behind the
    same NAT are rate-limited independently.  Falls back
    to the proxy-aware client IP for unauthenticated
    callers.

    Args:
        request: Incoming Starlette/FastAPI request.

    Returns:
        String key used as the rate-limit bucket.
    """
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer ") and len(auth) > 7:
        token_hash = hashlib.sha256(auth[7:].encode()).hexdigest()[:16]
        return f"user:{token_hash}"
    return core_network.get_ip_address(request)


limiter: Limiter = Limiter(
    key_func=_get_rate_limit_key,
    default_limits=[DEFAULT],
    enabled=core_config.settings.RATE_LIMIT_ENABLED,
    storage_uri=core_config.settings.resolved_state_uri,
)


def rate_limit_exceeded_handler(
    request: Request,
    exc: RateLimitExceeded,
) -> Response:
    """
    Return a JSON 429 response when a limit is breached.

    Injects standard ``X-RateLimit-*`` and
    ``Retry-After`` headers so clients can back off
    gracefully.

    Args:
        request: The request that exceeded the limit.
        exc: The RateLimitExceeded exception raised by
            slowapi.

    Returns:
        JSON response with 429 status and rate-limit
        headers attached when available.
    """
    logger.warning(f"Rate limit exceeded: {_get_rate_limit_key(request)} on {request.method} {request.url.path}")
    response = JSONResponse(
        status_code=429,
        content={
            "detail": ("Too many requests. Please try again later."),
        },
    )
    # Inject X-RateLimit-* and Retry-After headers.
    # request.state.view_rate_limit is populated by
    # SlowAPIMiddleware before this handler is called.
    try:
        response = request.app.state.limiter._inject_headers(
            response,
            request.state.view_rate_limit,
        )
    except Exception as header_err:
        # Headers are informational — never let injection
        # errors break the 429 response itself.
        logger.debug(f"Failed to inject rate-limit headers: {header_err}")
    return response
