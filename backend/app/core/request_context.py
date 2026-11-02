"""The HTTP request being served, for code that has no ``request`` parameter.

The audit trail asks who is acting at the moment a row is written, deep in a service. FastAPI runs synchronous
dependencies in a thread pool, so a context variable set there is gone before the route runs; this middleware
sets one in the request's own task instead, which every dependency and route of that request inherits. The
principal the auth dependencies resolve is cached on ``request.state``, which every ``Request`` built for the
same scope shares, so a reader sees it once a dependency has run.
"""

from contextvars import ContextVar

from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

_current_request: ContextVar[Request | None] = ContextVar("current_request", default=None)


def get_current_request() -> Request | None:
    """Return the HTTP request being served.

    Returns:
        The request, or None outside an HTTP request (a scheduled job, a durable-job worker, startup).
    """
    return _current_request.get()


class RequestContextMiddleware:
    """ASGI middleware that publishes the current HTTP request in a context variable."""

    def __init__(self, app: ASGIApp) -> None:
        """Wrap the next ASGI application.

        Args:
            app: The application to call.
        """
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Serve the request with it published for the duration of the call.

        Args:
            scope: The ASGI connection scope.
            receive: The ASGI receive channel.
            send: The ASGI send channel.
        """
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        token = _current_request.set(Request(scope))
        try:
            await self.app(scope, receive, send)
        finally:
            _current_request.reset(token)
