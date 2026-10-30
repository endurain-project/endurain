"""
Centralized rate limiting for the Endurain API.

Provides a single :data:`limiter` instance used by every
router, named tier constants for different endpoint
classes, and a JSON-aware 429 error handler.

The limiter key function uses the user a Bearer token names
when it is a signed, unexpired access token, so a user keeps one
bucket across token refreshes and users behind one NAT stay apart,
and falls back to the proxy-aware client IP for unauthenticated
callers and any other token.

Architecture
------------
1. :class:`RateLimitMiddleware` applies :data:`DEFAULT` limits
   to every route automatically (no endpoint code
   changes needed). The counter store is synchronous, so the
   check runs in the threadpool, as the checks of decorated
   sync routes already do.
2. Routers import a tier constant (e.g. :data:`WRITE`)
   and decorate individual endpoints with
   ``@limiter.limit(...)`` for tighter caps.
3. To add a new tier, define a module-level constant
   and document it in this module.
"""

from fastapi import Request
from joserfc import jwt
from joserfc.errors import JoseError
from joserfc.jwk import OctKey
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware, _find_route_handler, _should_exempt, sync_check_limits
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

import core.config as core_config
import core.exceptions as core_exceptions
import core.jwt_keys as core_jwt_keys
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

#: Reads that aggregate or return a whole activity's worth of data (summaries, streams, the health
#: dashboard, goal progress). Each costs far more than a row lookup, so they take a tighter cap than
#: DEFAULT; a page makes one such call, so a person using the app never meets it.
EXPENSIVE_READ: str = "30/minute"

#: Unauthenticated reads that are cheap, such as a shared activity, its laps, a thumbnail or the public
#: server settings. Keyed by client IP, so visitors behind one NAT share a bucket. It starts at the
#: global default and exists so public reads can be tuned apart from authenticated ones.
PUBLIC_READ: str = DEFAULT

#: Unauthenticated reads that are expensive, such as a shared activity's streams. Keyed by client IP,
#: so visitors behind one NAT share a bucket; kept apart from EXPENSIVE_READ so the two can be tuned
#: separately.
EXPENSIVE_PUBLIC_READ: str = "30/minute"

#: Endpoints that trigger OUTBOUND calls to a third-party
#: provider (Strava, Garmin Connect). Tighter than WRITE
#: because each request amplifies into several external
#: HTTP calls: without a cap a caller can burn the
#: server's shared provider quota (or have the server
#: throttled/banned) with almost no local cost.
PROVIDER_SYNC: str = "6/minute"

#: Seconds a connect or a read on the shared counter store may take before the limiter treats the
#: store as down and counts in memory instead.
STORE_TIMEOUT_SECONDS: float = 2.0


#: Expiry and type a token must carry to name a bucket; a refresh or expired token would let one
#: client mint buckets from tokens it can no longer use.
_ACCESS_TOKEN_CLAIMS = jwt.JWTClaimsRegistry(exp={"essential": True}, typ={"essential": True, "value": "access"})


def _jwt_verification_key() -> OctKey | None:
    """Return the key used to check Bearer token signatures, or None if unset."""
    return core_jwt_keys.verification_key()


def _verified_subject(token: str) -> str | None:
    """Return the ``sub`` claim of a signed, unexpired access token, or None otherwise."""
    key = _jwt_verification_key()
    if key is None:
        return None
    try:
        claims = core_jwt_keys.decode(token, key).claims
        _ACCESS_TOKEN_CLAIMS.validate(claims)
    except (JoseError, ValueError):
        return None
    subject = claims.get("sub")
    return subject if isinstance(subject, str) else None


def _get_rate_limit_key(request: Request) -> str:
    """
    Derive a per-caller rate-limit bucket key.

    Authenticated callers are identified by the user their
    Bearer token names, so users behind the same NAT are
    rate-limited independently and a token refresh does not
    reset the bucket.  The token must be a signed, unexpired
    access token, otherwise a client could mint a fresh bucket
    per request with a random or refresh token.  Falls back to
    the proxy-aware client IP for unauthenticated callers and
    any other token.

    Args:
        request: Incoming Starlette/FastAPI request.

    Returns:
        String key used as the rate-limit bucket.
    """
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer ") and len(auth) > 7 and (subject := _verified_subject(auth[7:])):
        return f"user:{subject}"
    return core_network.get_ip_address(request)


def build_limiter(*, storage_uri: str, enabled: bool) -> Limiter:
    """
    Build the application limiter.

    When the shared state backend cannot be reached, each process keeps enforcing every limit
    from its own memory and goes back to the shared backend once it answers again. The limits
    are then per replica, so a caller can do up to as many times the limit as there are
    replicas, but a state outage neither answers every request with a 500 nor lifts the limits
    that protect login and other sensitive routes.

    Args:
        storage_uri: Where the shared counters live.
        enabled: Whether limits are enforced at all.

    Returns:
        The configured limiter.
    """
    return Limiter(
        key_func=_get_rate_limit_key,
        default_limits=[DEFAULT],
        enabled=enabled,
        storage_uri=storage_uri,
        in_memory_fallback_enabled=True,
        storage_options={"socket_connect_timeout": STORE_TIMEOUT_SECONDS, "socket_timeout": STORE_TIMEOUT_SECONDS},
    )


class RateLimitMiddleware(SlowAPIMiddleware):
    """
    Apply the default limits without blocking the event loop.

    slowapi's own middleware calls its synchronous limit check straight from ``dispatch``, so a
    slow shared store would stall every request. This runs that same check in the threadpool.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """
        Check the default limits off the event loop, then pass the request on.

        Args:
            request: Incoming request.
            call_next: The rest of the application.

        Returns:
            The 429 response when a limit is breached, otherwise the application's response.
        """
        app = request.app
        limiter: Limiter = app.state.limiter
        if not limiter.enabled:
            return await call_next(request)

        handler = _find_route_handler(app.routes, request.scope)
        if _should_exempt(limiter, handler):
            return await call_next(request)

        error_response, should_inject_headers = await run_in_threadpool(
            sync_check_limits, limiter, request, handler, app
        )
        if error_response is not None:
            return error_response

        response = await call_next(request)
        if should_inject_headers:
            response = limiter._inject_headers(response, request.state.view_rate_limit)
        return response


limiter: Limiter = build_limiter(
    storage_uri=core_config.settings.resolved_state_uri, enabled=core_config.settings.RATE_LIMIT_ENABLED
)

# slowapi's ``headers_enabled`` is deliberately left off. It injects the
# ``X-RateLimit-*`` headers on *successful* responses too, and to do that the
# decorator requires every rate-limited endpoint to either return a ``Response``
# or declare a ``response: Response`` parameter — it raises on any handler that
# returns a plain model, which is most of them. The refusal is where a client
# actually needs the numbers, and :func:`rate_limit_exceeded_handler` sets them
# there without that constraint.


def rate_limit_exceeded_handler(
    request: Request,
    exc: RateLimitExceeded,
) -> Response:
    """
    Return a JSON 429 response when a limit is breached.

    Sets ``Retry-After`` and the ``X-RateLimit-*`` headers so clients can back
    off gracefully rather than guessing an interval.

    Args:
        request: The request that exceeded the limit.
        exc: The RateLimitExceeded exception raised by
            slowapi.

    Returns:
        JSON response with 429 status and rate-limit
        headers attached when available.
    """
    logger.warning(
        "Rate limit exceeded",
        extra=core_logger.context(caller=_get_rate_limit_key(request), method=request.method, path=request.url.path),
    )
    response = core_exceptions.build_problem_response(
        request=request,
        status_code=429,
        code="rate-limited",
        title="Too Many Requests",
        detail="Too many requests. Please try again later.",
    )
    # Read off the breached limit rather than slowapi's ``_inject_headers``,
    # which is inert unless ``headers_enabled`` is set on the limiter — see the
    # note there for why it cannot be.
    try:
        breached = exc.limit.limit
        response.headers["Retry-After"] = str(breached.get_expiry())
        response.headers["X-RateLimit-Limit"] = str(breached.amount)
        response.headers["X-RateLimit-Remaining"] = "0"
    except Exception as header_err:
        # Headers are informational — never let a missing attribute break the
        # 429 response itself.
        logger.debug("Failed to set rate-limit headers", exc_info=header_err)
    return response
