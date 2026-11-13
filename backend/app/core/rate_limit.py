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
   changes needed), except requests the frontend fallback
   serves as files or pages, which are not counted. The counter store is synchronous, so the
   check runs in the threadpool, as the checks of decorated
   sync routes already do.
   A route with its own ``@limiter.limit`` is checked by that decorator alone, which counts
   only once the request has passed authentication. So that a flood the authentication layer
   refuses cannot go uncounted, every response of such a route with status 401 or 403 is
   counted against :data:`DEFAULT` for that client (same key function as the default) in a
   budget kept per route, whatever the path parameters, and apart from the route's own counter, so
   nothing is counted twice. Once that
   budget is spent, every further request from the client to that route is answered 429, with
   ``Retry-After`` and ``X-RateLimit-*``, until its window resets. The route's own limit and
   the counting of undecorated routes are unchanged.
2. Routers import a tier constant (e.g. :data:`WRITE`)
   and decorate individual endpoints with
   ``@limiter.limit(...)`` for tighter caps.
3. To add a new tier, define a module-level constant
   and document it in this module.
"""

import math
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import FastAPI, Request, routing
from joserfc import jwt
from joserfc.errors import JoseError
from joserfc.jwk import KeySet, OctKey
from limits import RateLimitItem
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware, _get_route_name, sync_check_limits
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response
from starlette.routing import Match
from starlette.types import Scope

import core.config as core_config
import core.exceptions as core_exceptions
import core.jwt_keys as core_jwt_keys
import core.logger as core_logger
import core.network as core_network
import core.router as core_router

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

#: Polling a background job: the web app reads ``GET /jobs/{job_id}`` every 1 to 3 seconds, so one running job
#: costs 20 to 60 requests a minute and several at once would exhaust DEFAULT.
JOB_POLL: str = "300/minute"

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

#: State URI schemes the shared counters live in Redis for. The Redis client reads its socket timeouts
#: from the query of such a URI.
_REDIS_SCHEMES = frozenset({"redis", "rediss", "unix"})


#: Expiry a token must carry to name a bucket, next to the ``at+jwt`` header type; a refresh or expired token
#: would let one client mint buckets from tokens it can no longer use. The expiry is judged with the clock leeway
#: authentication uses, so a token keeps its user's bucket for exactly as long as it authenticates.
_ACCESS_TOKEN_CLAIMS = jwt.JWTClaimsRegistry(leeway=core_jwt_keys.CLOCK_LEEWAY_SECONDS, exp={"essential": True})


def _jwt_verification_key() -> OctKey | KeySet | None:
    """Return the keys used to check Bearer token signatures, or None if unset: access-token keys only."""
    return core_jwt_keys.verification_keys()


def _verified_subject(token: str) -> str | None:
    """Return the ``sub`` claim of a signed, unexpired access token, or None otherwise."""
    key = _jwt_verification_key()
    if key is None:
        return None
    try:
        decoded = core_jwt_keys.decode(token, key)
        _ACCESS_TOKEN_CLAIMS.validate(decoded.claims)
    except (JoseError, ValueError):
        return None
    if decoded.header.get("typ") != core_jwt_keys.ACCESS_JWT_TYP:
        return None
    claims = decoded.claims
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
    the proxy-aware client network (an IPv6 address by its /64,
    so rotating through a block does not give a fresh bucket) for
    unauthenticated callers and any other token.

    Args:
        request: Incoming Starlette/FastAPI request.

    Returns:
        String key used as the rate-limit bucket.
    """
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer ") and len(auth) > 7 and (subject := _verified_subject(auth[7:])):
        return f"user:{subject}"
    return core_network.client_network(core_network.get_ip_address(request))


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
        storage_uri=with_store_timeouts(storage_uri),
        in_memory_fallback_enabled=True,
    )


def with_store_timeouts(storage_uri: str) -> str:
    """Return a Redis state URI that carries the store timeouts, unless it already sets them.

    The timeouts go in the URI's query, which the Redis client parses into floats; a timeout the
    operator set in the URI is kept. Any other store is returned unchanged.

    Args:
        storage_uri: Where the shared counters live.

    Returns:
        The URI the limiter connects with.
    """
    parts = urlsplit(storage_uri)
    if parts.scheme not in _REDIS_SCHEMES:
        return storage_uri
    query = parse_qsl(parts.query, keep_blank_values=True)
    named = {name for name, _ in query}
    query += [
        (name, str(STORE_TIMEOUT_SECONDS)) for name in ("socket_connect_timeout", "socket_timeout") if name not in named
    ]
    return urlunsplit(parts._replace(query=urlencode(query)))


def _route_handler(app: FastAPI, scope: Scope) -> Callable[..., Any] | None:
    """
    Find the endpoint a request is routed to.

    The routes are read through FastAPI's route contexts because a router included in the application is not
    flattened into ``app.routes``, which is all slowapi's own lookup sees. The first full match is the one the
    application serves, so a catch-all route registered after the real ones does not take its place. The contexts
    are listed on the first request, after every router has been included, and kept on the application.

    Args:
        app: The application serving the request.
        scope: The ASGI connection scope.

    Returns:
        The endpoint of the matching route, or None when the request matches no route or the route has no endpoint.
    """
    routes = getattr(app.state, "rate_limit_routes", None)
    if routes is None:
        routes = app.state.rate_limit_routes = list(routing.iter_route_contexts(app.routes))
    for route in routes:
        if route.matches(scope)[0] == Match.FULL:
            return route.endpoint
    return None


def _refusal_budget_exhausted(limiter: Limiter, request: Request, handler: Callable[..., Any], *, count: bool) -> bool:
    """
    Check, and optionally count against, the refusal budget a client has on a decorated route.

    The budget is the default limits, keyed as the default is (the limiter's key function) and scoped to the route's
    endpoint rather than the URL, so a flood that varies the path parameters still spends one budget. It is a counter
    of its own, apart from the one the route's decorator keeps.

    Args:
        limiter: The application limiter.
        request: The incoming request.
        handler: The decorated endpoint.
        count: True to count this request against the budget, False to only look.

    Returns:
        True when the budget is spent: with ``count`` the request could not be counted, without it none is left.
        ``request.state.view_rate_limit`` then names the spent counter for the 429 headers.
    """
    scope = f"{_get_route_name(handler)}:refused"
    for group in limiter._default_limits:
        for default in group:
            args = [default.key_func(request), scope]
            if limiter._key_prefix:
                args.insert(0, limiter._key_prefix)
            try:
                strategy = (
                    limiter._fallback_limiter
                    if limiter._storage_dead and limiter._fallback_limiter
                    else limiter.limiter
                )
                allowed = strategy.hit(default.limit, *args) if count else strategy.test(default.limit, *args)
            except Exception as err:
                if limiter._storage_dead or not limiter._in_memory_fallback_enabled:
                    raise
                logger.warning("Rate limit storage unreachable - falling back to in-memory storage", exc_info=err)
                limiter._storage_dead = True
                return _refusal_budget_exhausted(limiter, request, handler, count=count)
            if not allowed:
                request.state.view_rate_limit = (default.limit, args)
                return True
    return False


def _refusal_limit_exceeded(limiter: Limiter) -> RateLimitExceeded:
    """Build the exception for a request refused while the refusal budget is spent."""
    default = next(iter(next(iter(limiter._default_limits))))
    return RateLimitExceeded(default)


#: Response statuses of a refused request: the authentication layer answers 401 or 403.
_REFUSED_STATUSES = frozenset({401, 403})


def _is_decorated(limiter: Limiter, handler: Callable[..., Any]) -> bool:
    """Tell whether an endpoint carries its own ``@limiter.limit``."""
    name = _get_route_name(handler)
    return name in limiter._route_limits or name in limiter._dynamic_route_limits


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

        handler = _route_handler(app, request.scope)
        if (
            handler is None
            or _get_route_name(handler) in limiter._exempt_routes
            or (handler is core_router.frontend_not_found and core_router.serves_frontend(request.url.path))
        ):
            return await call_next(request)

        if _is_decorated(limiter, handler):
            return await self._dispatch_decorated(request, call_next, handler)

        error_response, should_inject_headers = await run_in_threadpool(
            sync_check_limits, limiter, request, handler, app
        )
        if error_response is not None:
            return error_response

        response = await call_next(request)
        if should_inject_headers:
            response = limiter._inject_headers(response, request.state.view_rate_limit)
        return response

    async def _dispatch_decorated(
        self, request: Request, call_next: RequestResponseEndpoint, handler: Callable[..., Any]
    ) -> Response:
        """
        Pass a request for a route with its own limit on, counting what authentication refuses.

        The route's decorator counts a request only after authentication, so a request answered 401 or 403 is
        counted here against the default limits, in a budget of its own for the route. A client that has spent
        that budget is answered 429 before the route runs.

        Args:
            request: Incoming request.
            call_next: The rest of the application.
            handler: The route's decorated endpoint.

        Returns:
            The 429 response when the refusal budget is spent, otherwise the application's response.
        """
        app = request.app
        limiter: Limiter = app.state.limiter
        if await run_in_threadpool(_refusal_budget_exhausted, limiter, request, handler, count=False):
            return rate_limit_exceeded_handler(request, _refusal_limit_exceeded(limiter))

        response = await call_next(request)
        if response.status_code in _REFUSED_STATUSES and await run_in_threadpool(
            _refusal_budget_exhausted, limiter, request, handler, count=True
        ):
            return rate_limit_exceeded_handler(request, _refusal_limit_exceeded(limiter))
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


def _seconds_until_reset(request: Request, breached: RateLimitItem) -> int:
    """
    Find how long a caller must wait before the breached limit lets a request through.

    Args:
        request: The request that exceeded the limit.
        breached: The limit that was exceeded.

    Returns:
        The seconds left in the window the request was counted in, at least 1. The whole window when the
        request carries no record of the counter it hit.
    """
    counter = getattr(request.state, "view_rate_limit", None)
    if counter is None:
        return breached.get_expiry()
    item, identifiers = counter
    reset_time = request.app.state.limiter.limiter.get_window_stats(item, *identifiers).reset_time
    return max(1, math.ceil(reset_time - time.time()))


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
    if exc.limit is not None:
        breached = exc.limit.limit
        response.headers["Retry-After"] = str(_seconds_until_reset(request, breached))
        response.headers["X-RateLimit-Limit"] = str(breached.amount)
        response.headers["X-RateLimit-Remaining"] = "0"
    return response
