"""HTTP middleware for security headers, the cookie-route origin check and response compression."""

import asyncio
import time
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, status
from fastapi.concurrency import run_in_threadpool
from starlette.datastructures import MutableHeaders, State
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

import core.config as core_config
import core.exceptions as core_exceptions
import core.logger as core_logger
import core.security_headers as core_security_headers

logger = core_logger.get_logger(__name__)

#: gzip level. The moderate level: the library default, 9, spends several times the CPU for a few percent
#: more. The library compresses chunks of 128 KiB or more in a worker thread and smaller ones inline.
COMPRESSION_LEVEL = 5

#: How long a process trusts its cached CSP tile domains before re-reading them. An
#: admin edit lands in one process; every other worker or replica picks it up here.
TILE_DOMAINS_REFRESH_SECONDS = 30.0

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
    "X-Request-ID",
    "traceparent",
    "tracestate",
)

#: Response headers a browser client may read. Anything not listed is invisible
#: to JavaScript even though it is on the wire — which is why ``ETag`` belongs
#: here: it is the tag the client echoes back in ``If-Match``. ``Retry-After`` says when to try again,
#: ``X-RateLimit-Limit`` and ``X-RateLimit-Remaining`` give the limit a 429 refused, and
#: ``Content-Location`` names the job of accepted background work.
CORS_EXPOSE_HEADERS: tuple[str, ...] = (
    "ETag",
    "X-Request-ID",
    "Retry-After",
    "X-RateLimit-Limit",
    "X-RateLimit-Remaining",
    "Content-Location",
)


async def _reload_allowed_tile_domains(state: State, loader: Callable[[], list[str]]) -> None:
    """Run the loader on a worker thread and keep its result as the cached domains.

    A failure keeps the previous value, so a database hiccup never breaks a response.

    Args:
        state: The app state holding ``allowed_tile_domains``.
        loader: Reads the current domains from their source.
    """
    try:
        state.allowed_tile_domains = await run_in_threadpool(loader)
    except Exception as err:
        logger.warning(
            "Could not refresh the allowed tile domains; keeping the previous ones",
            exc_info=err,
        )


def _refresh_allowed_tile_domains(request: Request) -> None:
    """Start a background re-read of ``app.state.allowed_tile_domains`` once it is stale.

    Only an app that records ``allowed_tile_domains_read_at`` and
    ``allowed_tile_domains_loader`` (the composition root does, at startup) is
    refreshed; core does not know where the domains come from. The read never sits
    on the response path: the request that notices staleness is served the cached
    value and the next one sees the new value.

    Args:
        request: Incoming HTTP request, used to reach the app state.
    """
    state = request.app.state
    read_at = getattr(state, "allowed_tile_domains_read_at", None)
    loader = getattr(state, "allowed_tile_domains_loader", None)
    if read_at is None or loader is None or time.monotonic() - read_at < TILE_DOMAINS_REFRESH_SECONDS:
        return
    # Stamped before the read, so concurrent requests do not each start one.
    state.allowed_tile_domains_read_at = time.monotonic()
    # The state keeps the task so it is not garbage-collected before it finishes.
    state.allowed_tile_domains_refresh_task = asyncio.create_task(_reload_allowed_tile_domains(state, loader))


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

        core_security_headers.apply(response)

        # An HTML page gets the policy of the app shell unless its route set its own (the API docs pages); a JSON
        # response got its policy from ``apply``.
        if core_security_headers.is_html(response.headers.get("content-type")) and (
            "Content-Security-Policy" not in response.headers
        ):
            _refresh_allowed_tile_domains(request)
            allowed_tile_domains = getattr(request.app.state, "allowed_tile_domains", ())
            tile_domains_str = " ".join(allowed_tile_domains)

            # Object storage serves blobs (thumbnails, photos, media) from its
            # own origin through presigned URLs; local storage is same-origin.
            storage_origin = getattr(request.app.state, "storage_origin", None)
            blob_src = f" {storage_origin}" if storage_origin else ""

            # Extra connect-src origins for deployments behind a
            # forward-auth reverse proxy that redirects API calls
            # to its own domain (see CSP_ADDITIONAL_CONNECT_SRC).
            connect_src = "'self' https://api.github.com"
            extra_connect_src = core_config.settings.CSP_ADDITIONAL_CONNECT_SRC
            if extra_connect_src:
                connect_src = f"{connect_src} {' '.join(extra_connect_src)}"

            # No inline script or style is allowed; the SPA writes styles through the CSSOM, which style-src does not
            # block.
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                f"img-src 'self' data: {tile_domains_str}{blob_src} "
                "https://fastapi.tiangolo.com; "
                "style-src 'self'; "
                "script-src 'self'; "
                f"connect-src {connect_src}; "
                f"media-src 'self' data:{blob_src}; "
                "base-uri 'self'; "
                "object-src 'none'; "
                "frame-ancestors 'none'"
            )

        if "Server" in response.headers:
            del response.headers["Server"]

        return response


#: The caching rule of a JSON response that sets none: a browser may keep it but must revalidate before reuse. Personal
#: data must never be served from a heuristic freshness lifetime.
DEFAULT_CACHE_CONTROL = "private, no-cache"


class GetSemanticsMiddleware:
    """
    Give every ``GET`` route the HTTP semantics the routes do not repeat.

    An ``ETag`` here is the version a write echoes in ``If-Match``, not a validator of the whole body, so a matching
    ``If-None-Match`` is not answered ``304``.

    * ``HEAD`` runs the ``GET`` route and sends its headers without the body (RFC 9110 section 9.3.2).
    * A JSON response that sets no ``Cache-Control`` gets :data:`DEFAULT_CACHE_CONTROL`.

    Install it first, so it is the innermost middleware.

    Attributes:
        app: The wrapped ASGI application.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """
        Run the wrapped application with the response rules applied.

        Args:
            scope: ASGI connection scope.
            receive: ASGI receive callable.
            send: ASGI send callable.
        """
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        is_head = scope["method"] == "HEAD"
        if is_head:
            scope = {**scope, "method": "GET"}
        drop_body = is_head

        async def send_with_rules(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                if "cache-control" not in headers and core_security_headers.is_json(headers.get("content-type")):
                    headers["Cache-Control"] = DEFAULT_CACHE_CONTROL
            elif message["type"] == "http.response.body" and drop_body:
                if message.get("more_body", False):
                    return
                message = {"type": "http.response.body", "body": b""}
            await send(message)

        await self.app(scope, receive, send_with_rules)


class CookieRouteOriginMiddleware(BaseHTTPMiddleware):
    """
    Refuse a web request to a cookie route that does not come from an allowed origin.

    The refresh cookie is the one credential a browser attaches by itself, and only ``POST /auth/refresh`` and
    ``POST /auth/logout`` read it. A request that declares ``X-Client-Type: web`` to either route must carry an
    ``Origin`` header equal to one of ``app.state.cors_allow_origins``: a missing, ``null`` or foreign origin is
    refused with 403, since a browser always sends ``Origin`` on a cross-site ``POST``. A ``Sec-Fetch-Site`` of
    ``cross-site`` is refused too; ``same-origin`` is not required, because the development SPA is same-site but not
    same-origin. A mobile client uses no cookie and is not checked, and every other route reads its credential from
    the ``Authorization`` header, which a browser never attaches by itself.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """
        Refuse a web request to a cookie route whose origin is not allowed.

        Args:
            request: Incoming HTTP request.
            call_next: Next ASGI handler in the chain.

        Returns:
            The downstream response, or a 403 problem response when the origin is not allowed.

        Raises:
            Exception: Propagates downstream request errors.
        """
        if (
            request.method == "POST"
            and request.url.path in (f"{core_config.ROOT_PATH}/auth/refresh", f"{core_config.ROOT_PATH}/auth/logout")
            and request.headers.get("X-Client-Type") == "web"
            and (
                request.headers.get("Origin") not in request.app.state.cors_allow_origins
                or request.headers.get("Sec-Fetch-Site") == "cross-site"
            )
        ):
            return core_exceptions.build_problem_response(
                request=request,
                status_code=status.HTTP_403_FORBIDDEN,
                code="permission-denied",
                title="Forbidden",
                detail="Origin not allowed",
            )

        return await call_next(request)


def install_compression(app: FastAPI) -> None:
    """Gzip-compress the app's responses for clients that accept it.

    Install it last: a middleware added later wraps the earlier ones, so every header they add is on
    the compressed response. A response that already carries a ``Content-Encoding`` (a proxy's or a
    pre-compressed file) is not compressed again.

    Args:
        app: The application to wrap.
    """
    app.add_middleware(GZipMiddleware, compresslevel=COMPRESSION_LEVEL)
