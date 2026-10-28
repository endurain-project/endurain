"""Request body size cap for the Endurain API.

The upload validators check a file's size only after the framework has received the whole body and
spooled it to disk, and nothing bounds a JSON body at all, so a client could fill the temporary volume or
memory before any route ran. This middleware refuses an oversized body first: at once when the declared
``Content-Length`` is over the limit, and mid-stream for a body that declares none.

The limits are the ceiling of what any route accepts, not a route's own limit; the routes still validate
their files. A reverse proxy in front of the application should enforce a cap as well.
"""

from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

import core.exceptions as core_exceptions

# The largest upload any route accepts is a 500 MiB archive; the rest is multipart framing and form fields.
MAX_UPLOAD_BODY_BYTES = 520 * 1024 * 1024
# Every other body is JSON or form data.
MAX_BODY_BYTES = 10 * 1024 * 1024


class _BodyTooLargeError(Exception):
    """The body being read went over the limit."""


def _limit_for(scope: Scope) -> int:
    """Pick the limit that applies to a request by its content type.

    Args:
        scope: The ASGI connection scope.

    Returns:
        The largest body, in bytes, the request may carry.
    """
    for name, value in scope["headers"]:
        if name == b"content-type" and value.lower().startswith(b"multipart/"):
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
