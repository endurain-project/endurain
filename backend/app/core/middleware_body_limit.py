"""Request body size cap for the Endurain API.

The upload validators check a file's size only after the framework has received the whole body and
spooled it to disk, and nothing bounds a JSON body at all, so a client could fill the temporary volume or
memory before any route ran. This middleware refuses an oversized body first: at once when the declared
``Content-Length`` is over the limit, and mid-stream for a body that declares none.

The limits are the ceiling of what any route accepts, not a route's own limit; the routes still validate
their files. A reverse proxy in front of the application should enforce a cap as well.
"""

from fastapi import params
from fastapi.routing import APIRoute
from starlette.requests import Request
from starlette.routing import Match
from starlette.types import ASGIApp, Message, Receive, Scope, Send

import core.exceptions as core_exceptions

# The largest upload any route accepts is a 500 MiB archive; the rest is multipart framing and form fields.
MAX_UPLOAD_BODY_BYTES = 520 * 1024 * 1024
# Every other body is JSON or form data.
MAX_BODY_BYTES = 10 * 1024 * 1024


class _BodyTooLargeError(BaseException):
    """The body being read went over the limit.

    A ``BaseException`` so that FastAPI's form parsing, which turns any ``Exception`` into a 400, cannot swallow it.
    """


def _upload_routes(app: ASGIApp) -> list[APIRoute]:
    """List the routes of an application that declare a form or file body.

    Args:
        app: The application whose routes are inspected.

    Returns:
        The upload routes, in registration order.
    """
    return [
        route
        for route in getattr(app, "routes", [])
        if isinstance(route, APIRoute)
        and route.body_field is not None
        and isinstance(route.body_field.field_info, params.Form)
    ]


def _is_multipart(scope: Scope) -> bool:
    """Tell whether a request declares a multipart body.

    Args:
        scope: The ASGI connection scope.

    Returns:
        True when the ``Content-Type`` is ``multipart/*``.
    """
    return any(name == b"content-type" and value.lower().startswith(b"multipart/") for name, value in scope["headers"])


def _limit_for(scope: Scope) -> int:
    """Pick the limit that applies to a request.

    The large limit is for a multipart request to a route that declares a form or file body. Every other request,
    including a multipart one to a route that takes no upload or to no route at all, gets the small one. The routes
    are read from the application on the first request, after every router has been included.

    Args:
        scope: The ASGI connection scope.

    Returns:
        The largest body, in bytes, the request may carry.
    """
    if not _is_multipart(scope):
        return MAX_BODY_BYTES
    app = scope["app"]
    routes = getattr(app.state, "upload_routes", None)
    if routes is None:
        routes = app.state.upload_routes = _upload_routes(app)
    if any(route.matches(scope)[0] == Match.FULL for route in routes):
        return MAX_UPLOAD_BODY_BYTES
    return MAX_BODY_BYTES


def _declared_length(scope: Scope) -> int | None:
    """Read the ``Content-Length`` a request declares.

    Args:
        scope: The ASGI connection scope.

    Returns:
        The declared length, or None when it is absent or not a number.
    """
    for name, value in scope["headers"]:
        if name == b"content-length":
            try:
                return int(value)
            except ValueError:
                return None
    return None


class BodySizeLimitMiddleware:
    """Refuse a request whose body is larger than the limit, with a 413 problem document."""

    def __init__(self, app: ASGIApp) -> None:
        """Wrap an ASGI application.

        Args:
            app: The application to protect.
        """
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Pass the request on, counting the body as it is read.

        Args:
            scope: The ASGI connection scope.
            receive: Receives the request body.
            send: Sends the response.
        """
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        limit = _limit_for(scope)
        declared = _declared_length(scope)
        if declared is not None and declared > limit:
            await self._refuse(scope, receive, send)
            return

        received = 0
        response_started = False

        async def counting_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise _BodyTooLargeError
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, counting_receive, tracking_send)
        except _BodyTooLargeError:
            if response_started:
                raise
            await self._refuse(scope, receive, send)

    @staticmethod
    async def _refuse(scope: Scope, receive: Receive, send: Send) -> None:
        """Answer 413 as a problem document.

        Args:
            scope: The ASGI connection scope.
            receive: Receives the request body.
            send: Sends the response.
        """
        error = core_exceptions.PayloadTooLargeError
        response = core_exceptions.build_problem_response(
            request=Request(scope, receive),
            status_code=error.status_code,
            code=error.code,
            title=error.title,
            detail="The request body is too large",
        )
        await response(scope, receive, send)
