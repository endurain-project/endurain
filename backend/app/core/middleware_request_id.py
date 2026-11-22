"""Request ID middleware for the Endurain API.

Assigns a unique identifier to every request so that all
log entries produced during a single request can be
correlated. If the client sends an ``X-Request-ID``
header, its value is reused (after validation). Otherwise
the trace id of a valid W3C ``traceparent`` header is used,
so a log line can be found from the caller's trace, and
failing that a new UUID4 is generated. ``traceparent`` and
``tracestate`` are echoed back unchanged; the API starts no
spans of its own.

The request ID is stored in a :class:`~contextvars.ContextVar`
so any code in the call chain (CRUD, utilities, etc.)
can read it without an explicit parameter.
"""

import re
import uuid
from collections.abc import Awaitable, Callable
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_REQUEST_ID_HEADER = "X-Request-ID"
# Only allow alphanumeric characters and hyphens to
# prevent log injection and header injection (OWASP A03).
_VALID_REQUEST_ID = re.compile(r"^[a-zA-Z0-9\-]{1,64}$")

_TRACEPARENT_HEADER = "traceparent"
_TRACESTATE_HEADER = "tracestate"
# W3C Trace Context level 1: version-trace_id-parent_id-flags in lowercase hex. Version ff is invalid, and a trace
# or parent id of all zeros is invalid.
_VALID_TRACEPARENT = re.compile(r"^(?!ff)[0-9a-f]{2}-(?!0{32}-)([0-9a-f]{32})-(?!0{16}-)[0-9a-f]{16}-[0-9a-f]{2}$")
# A list of at most 32 ``key=value`` members in printable ASCII, 512 characters at most.
_VALID_TRACESTATE = re.compile(r"^[\x20-\x7e]{1,512}$")

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")


def get_request_id() -> str:
    """
    Return the current request ID from context.

    Returns:
        The request ID string, or empty string when
        called outside an active request context.
    """
    return request_id_ctx.get()


class RequestIdMiddleware(BaseHTTPMiddleware):
    """
    Starlette middleware that assigns a request ID.

    Reads ``X-Request-ID`` from the incoming request
    (if it matches the validation regex) or generates
    a UUID4. Stores the value in :data:`request_id_ctx`
    and echoes it back in the response headers so
    clients can correlate requests with server logs. A valid
    ``traceparent`` (and its ``tracestate``) is echoed too.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """
        Set the request ID and forward the request.

        Args:
            request: Incoming HTTP request.
            call_next: Next ASGI handler in the chain.

        Returns:
            Response with the ``X-Request-ID`` header set, and the trace headers when the request carried a valid
            ``traceparent``.
        """
        incoming = request.headers.get(_REQUEST_ID_HEADER)
        traceparent = request.headers.get(_TRACEPARENT_HEADER, "").strip()
        trace = _VALID_TRACEPARENT.match(traceparent)
        if incoming and _VALID_REQUEST_ID.match(incoming):
            rid = incoming
        elif trace:
            rid = trace.group(1)
        else:
            rid = str(uuid.uuid4())

        # Not reset afterwards: an unhandled error is answered by Starlette's outermost middleware after this
        # one has exited, and its response and log line still need the id. The server runs each request in its
        # own task, so the value does not outlive the request.
        request_id_ctx.set(rid)
        response = await call_next(request)
        response.headers[_REQUEST_ID_HEADER] = rid
        if trace:
            response.headers[_TRACEPARENT_HEADER] = traceparent
            tracestate = request.headers.get(_TRACESTATE_HEADER, "").strip()
            if _VALID_TRACESTATE.match(tracestate):
                response.headers[_TRACESTATE_HEADER] = tracestate
        return response
