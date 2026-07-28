"""Transport-agnostic domain errors raised by application layers.

The application layers — services, the ingestion pipeline, the file parsers —
describe *what went wrong in the domain*, not *which HTTP status to send*. They
raise the exceptions defined here; :func:`domain_error_handler`, registered once
on the FastAPI app, is the single place that turns a domain error into a
response.

Why this exists
---------------
Those layers previously raised ``fastapi.HTTPException`` directly, which coupled
them to HTTP in three unhelpful ways:

* they could not be unit-tested (or reused from the durable-job worker, which
  serves no HTTP at all) without importing FastAPI;
* the status code — a transport decision — was scattered across dozens of call
  sites instead of being stated once per error kind;
* a "pure" file parser had to import a web framework to report a bad file.

Each subclass owns its ``status_code`` and a safe default ``detail``. Call sites
pass a caller-safe message or nothing at all; nothing internal (SQL, stack
detail, filesystem paths) belongs in ``detail``, because it is returned verbatim
to the client (OWASP A09 — avoid information disclosure in error responses).
"""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

import core.logger as core_logger

logger = core_logger.get_logger(__name__)


class DomainError(Exception):
    """Base class for every transport-agnostic application error.

    Attributes:
        status_code: HTTP status the API boundary maps this error to.
        detail: Caller-safe message returned in the response body.
    """

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail: str = "Internal Server Error"

    def __init__(self, detail: str | None = None) -> None:
        """Initialise the error with an optional caller-safe message.

        Args:
            detail: Message returned to the client. Falls back to the subclass's
                ``default_detail`` when omitted. Must never contain internal
                diagnostics — log those separately with ``exc_info``.
        """
        self.detail = detail or self.default_detail
        super().__init__(self.detail)


class NotFoundError(DomainError):
    """The requested resource does not exist, or is not visible to the caller.

    Deliberately also used for "exists but is not yours" where returning 403
    would confirm the id exists (the activity-media endpoints rely on this).
    """

    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "Not found"


class PermissionDeniedError(DomainError):
    """The caller is authenticated but not allowed to perform this action."""

    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "Forbidden"


class InvalidInputError(DomainError):
    """The request is well-formed but semantically unusable."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Bad Request"


class ConflictError(DomainError):
    """The action conflicts with the resource's current state."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = "Conflict"


class UnsupportedFormatError(DomainError):
    """The supplied payload is in a format this endpoint cannot process."""

    status_code = status.HTTP_406_NOT_ACCEPTABLE
    default_detail = "Not Acceptable"


class UnsupportedMediaTypeError(DomainError):
    """The supplied file's media type is not accepted."""

    status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    default_detail = "Unsupported Media Type"


class ProcessingError(DomainError):
    """An internal step failed; the caller can do nothing about it.

    The default detail is intentionally opaque — the cause belongs in the log
    line, not in the response.
    """

    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = "Internal Server Error"


async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    """Render a :class:`DomainError` as the API's standard error response.

    Emits the same ``{"detail": ...}`` body FastAPI produces for
    ``HTTPException``, so the shape the clients already parse is unchanged.

    Server-side (5xx) errors are logged at ``error`` with a traceback because
    they indicate a defect; client-side (4xx) errors are logged at ``debug``
    because they are the API behaving as designed and would otherwise flood the
    logs with routine 404s.

    Args:
        request: The incoming request (used for log context only).
        exc: The domain error raised by the application layer.

    Returns:
        The JSON error response.
    """
    log_context = core_logger.context(
        path=request.url.path,
        method=request.method,
        status_code=exc.status_code,
        error=type(exc).__name__,
    )
    if exc.status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
        logger.error(f"Unhandled domain error on {request.method} {request.url.path}", exc_info=exc, extra=log_context)
    else:
        logger.debug(f"Domain error on {request.method} {request.url.path}: {exc.detail}", extra=log_context)

    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


def register_exception_handlers(app: FastAPI) -> None:
    """Wire the domain-error boundary onto a FastAPI application.

    Kept as a helper rather than an inline ``add_exception_handler`` call so the
    production app and the router tests register the boundary the same way. A
    test app that skipped it would surface an unhandled ``DomainError`` as a
    raised exception instead of the response real clients receive — exactly the
    drift that makes route tests pass while the API misbehaves.

    Args:
        app: The FastAPI application to register the handler on.

    Returns:
        None.
    """
    app.add_exception_handler(DomainError, domain_error_handler)  # type: ignore[arg-type]
