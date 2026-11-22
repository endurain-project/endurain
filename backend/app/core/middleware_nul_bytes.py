"""Refusal of NUL characters in a request.

PostgreSQL text cannot hold ``U+0000``, so a NUL that reaches a text column fails the insert and the API answers
500. The character never has a legitimate use in a path, query string, JSON string or form field, so this middleware
answers the validation problem document (422) before any route runs, whatever field would have received it.

It inspects the path, the query string, a JSON body (decoded, so an escaped backslash followed by ``u0000`` text is
not mistaken for a NUL) and a urlencoded form body. A multipart body carries uploads, whose bytes are checked by the
upload validators, and is passed through untouched. The body is read through the size cap that wraps this
middleware, then replayed to the application intact.
"""

import json
from typing import Any

import anyio.to_thread
from fastapi import status
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

import core.exceptions as core_exceptions

_NUL = "\x00"
_ENCODED_NUL = b"%00"
_ESCAPED_NUL = "\\u0000"


def _content_type(scope: Scope) -> str:
    """Read the media type a request declares, without parameters.

    Args:
        scope: The ASGI connection scope.

    Returns:
        The lower-cased media type, or an empty string when none is declared.
    """
    for name, value in scope["headers"]:
        if name == b"content-type":
            return value.decode("latin-1").split(";", 1)[0].strip().lower()
    return ""


def _json_contains_nul(document: Any) -> bool:
    """Tell whether any string or object key of a decoded JSON document holds a NUL.

    Walks with an explicit stack, so a deeply nested document cannot exhaust the interpreter's recursion limit.

    Args:
        document: The decoded JSON value.

    Returns:
        True when a NUL is present.
    """
    pending = [document]
    while pending:
        item = pending.pop()
        if isinstance(item, str):
            if _NUL in item:
                return True
        elif isinstance(item, list):
            pending.extend(item)
        elif isinstance(item, dict):
            for key, value in item.items():
                if _NUL in key:
                    return True
                pending.append(value)
    return False


def _body_has_nul(content_type: str, body: bytes) -> bool:
    """Tell whether a buffered body carries a NUL in a place the application would read as text.

    A JSON body can only hold a NUL through the escape ``\\u0000``, since a raw control character is invalid
    JSON, so a body without that text is not parsed at all; the parse and walk are not free for a large body.

    Args:
        content_type: The request's media type.
        body: The whole request body.

    Returns:
        True when the body holds a NUL. A JSON body that does not parse is left for the application to refuse.
    """
    if content_type == "application/x-www-form-urlencoded":
        return _ENCODED_NUL in body or _NUL.encode() in body
    try:
        text = body.decode(json.detect_encoding(body))
    except UnicodeDecodeError:
        return False
    if _ESCAPED_NUL not in text:
        return False
    try:
        return _json_contains_nul(json.loads(text))
    except (ValueError, RecursionError):
        return False


class NulByteMiddleware:
    """Answer 422 when the path, query string or body of a request holds a NUL character."""

    def __init__(self, app: ASGIApp) -> None:
        """Wrap an ASGI application.

        Args:
            app: The application to protect.
        """
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Check the request, then pass it on with its body replayed.

        Args:
            scope: The ASGI connection scope.
            receive: Receives the request body.
            send: Sends the response.
        """
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if _NUL in scope["path"] or _ENCODED_NUL in scope.get("raw_path", b""):
            await self._refuse("path", scope, receive, send)
            return
        query = scope.get("query_string", b"")
        if _ENCODED_NUL in query or _NUL.encode() in query:
            await self._refuse("query", scope, receive, send)
            return

        content_type = _content_type(scope)
        if content_type != "application/x-www-form-urlencoded" and not (
            content_type == "application/json" or content_type.endswith("+json")
        ):
            await self.app(scope, receive, send)
            return

        chunks: list[bytes] = []
        while True:
            message = await receive()
            if message["type"] != "http.request":
                # The client went away before the body was complete; nothing is left to inspect or answer.
                await self.app(scope, _replay(message, receive), send)
                return
            chunks.append(message.get("body", b""))
            if not message.get("more_body", False):
                break
        body = b"".join(chunks)

        if await anyio.to_thread.run_sync(_body_has_nul, content_type, body):
            await self._refuse("body", scope, receive, send)
            return
        await self.app(scope, _replay({"type": "http.request", "body": body, "more_body": False}, receive), send)

    @staticmethod
    async def _refuse(field: str, scope: Scope, receive: Receive, send: Send) -> None:
        """Answer 422 as the validation problem document.

        Args:
            field: The part of the request that held the NUL.
            scope: The ASGI connection scope.
            receive: Receives the request body.
            send: Sends the response.
        """
        response = core_exceptions.build_problem_response(
            request=Request(scope, receive),
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code="validation-failed",
            title="Unprocessable Content",
            detail="The request could not be validated.",
            errors=[{"field": field, "message": "NUL characters are not allowed", "type": "nul_character"}],
        )
        await response(scope, receive, send)


def _replay(first: Message, receive: Receive) -> Receive:
    """Build a ``receive`` that yields an already-read message first, then defers to the original.

    Args:
        first: The message to deliver on the first call.
        receive: The original ``receive``, used for later messages such as a disconnect.

    Returns:
        The replacing ``receive`` callable.
    """
    pending: list[Message] = [first]

    async def replay() -> Message:
        if pending:
            return pending.pop()
        return await receive()

    return replay
