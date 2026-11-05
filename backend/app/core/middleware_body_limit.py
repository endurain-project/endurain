"""Request body size cap for the Endurain API.

The upload validators check a file's size only after the framework has received the whole body and
spooled it to disk, and nothing bounds a JSON body at all, so a client could fill the temporary volume or
memory before any route ran. This middleware refuses an oversized body first: at once when the declared
``Content-Length`` is over the limit, and mid-stream for a body that declares none.

A route that takes a form or file body declares its own cap with :func:`upload_limit`, passed as its
``openapi_extra``: the largest file the route accepts plus :data:`MULTIPART_OVERHEAD_BYTES`. The cap is read from
the matched route and is published in the OpenAPI document as ``x-max-body-bytes``. Every other request, and a
multipart request to a route that declares no cap, gets the small :data:`MAX_BODY_BYTES`. The routes still validate
their files. A reverse proxy in front of the application should enforce a cap as well.
"""

from typing import Any

from fastapi import params, routing
from starlette.requests import Request
from starlette.routing import Match
from starlette.types import ASGIApp, Message, Receive, Scope, Send

import core.exceptions as core_exceptions

# Every body that is not an upload is JSON or form data.
MAX_BODY_BYTES = 10 * 1024 * 1024
# What a multipart body carries beyond the file: boundaries, part headers and form fields.
MULTIPART_OVERHEAD_BYTES = 1024 * 1024
# The OpenAPI extension an upload route's cap is published under.
BODY_LIMIT_EXTENSION = "x-max-body-bytes"


class _BodyTooLargeError(BaseException):
    """The body being read went over the limit.

    A ``BaseException`` so that FastAPI's form parsing, which turns any ``Exception`` into a 400, cannot swallow it.
    """


def upload_limit(max_file_bytes: int) -> dict[str, Any]:
    """Build the ``openapi_extra`` that gives an upload route its body cap.

    Args:
        max_file_bytes: The largest file the route accepts.

    Returns:
        The extra to pass as the route's ``openapi_extra``.
    """
    return {BODY_LIMIT_EXTENSION: max_file_bytes + MULTIPART_OVERHEAD_BYTES}


def route_limit(route: routing.RouteContext) -> int | None:
    """Read the body cap a route declares.

    Args:
        route: The route to inspect.

    Returns:
        The cap in bytes, or None when the route declares none.
    """
    return (route.openapi_extra or {}).get(BODY_LIMIT_EXTENSION)


def upload_routes(app: ASGIApp) -> list[routing.RouteContext]:
    """List the routes of an application that take a file.

    The routes are read through FastAPI's route contexts because a router included in the application is not
    flattened into ``app.routes``.

    Args:
        app: The application whose routes are inspected.

    Returns:
        The upload routes, in registration order.
    """
    return [
        route
        for route in routing.iter_route_contexts(getattr(app, "routes", []))
        if isinstance(route.original_route, routing.APIRoute)
        and any(isinstance(field.field_info, params.File) for field in route.dependant.body_params)
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

    A multipart request to a route that declares a form or file body gets that route's own cap. Every other request,
    including a multipart one to a route that takes no upload, to no route at all or to an upload route with no cap,
    gets the small one. The routes are read from the application on the first request, after every router has been
    included.

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
        routes = app.state.upload_routes = upload_routes(app)
    for route in routes:
        if route.matches(scope)[0] == Match.FULL:
            return route_limit(route) or MAX_BODY_BYTES
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
