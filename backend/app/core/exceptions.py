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

Each subclass owns its ``status_code``, a stable machine-readable ``code``, a
``title``, and a safe default ``detail``. Call sites pass a caller-safe message
or nothing at all; nothing internal (SQL, stack detail, filesystem paths) belongs
in ``detail``, because it is returned verbatim to the client (OWASP A09 — avoid
information disclosure in error responses).

Every error leaves the API as an RFC 9457 problem document — see
:mod:`core.problem_details` for the shape and why its members were chosen.
"""

import http

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

import core.logger as core_logger
import core.middleware_request_id as core_middleware_request_id
import core.problem_details as core_problem_details

logger = core_logger.get_logger(__name__)


class DomainError(Exception):
    """Base class for every transport-agnostic application error.

    Attributes:
        status_code: HTTP status the API boundary maps this error to.
        code: Stable machine-readable slug, rendered as the RFC 9457 ``type``
            URN. Clients branch on it, so it must not change once released.
        title: Short human-readable summary of the error *kind*. Constant per
            subclass; the per-occurrence message is ``detail``.
        detail: Caller-safe message returned in the response body.
    """

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    code: str = "internal-error"
    title: str = "Internal Server Error"
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
    code = "not-found"
    title = "Not Found"
    default_detail = "Not found"


class PermissionDeniedError(DomainError):
    """The caller is authenticated but not allowed to perform this action."""

    status_code = status.HTTP_403_FORBIDDEN
    code = "permission-denied"
    title = "Forbidden"
    default_detail = "Forbidden"


class InvalidInputError(DomainError):
    """The request is well-formed but semantically unusable."""

    status_code = status.HTTP_400_BAD_REQUEST
    code = "invalid-input"
    title = "Bad Request"
    default_detail = "Bad Request"


class ConflictError(DomainError):
    """The action conflicts with the resource's current state."""

    status_code = status.HTTP_409_CONFLICT
    code = "conflict"
    title = "Conflict"
    default_detail = "Conflict"


class UnsupportedFormatError(DomainError):
    """The supplied payload is in a format this endpoint cannot process."""

    status_code = status.HTTP_406_NOT_ACCEPTABLE
    code = "unsupported-format"
    title = "Not Acceptable"
    default_detail = "Not Acceptable"


class UnsupportedMediaTypeError(DomainError):
    """The supplied file's media type is not accepted."""

    status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    code = "unsupported-media-type"
    title = "Unsupported Media Type"
    default_detail = "Unsupported Media Type"


class ProcessingError(DomainError):
    """An internal step failed; the caller can do nothing about it.

    The default detail is intentionally opaque — the cause belongs in the log
    line, not in the response.
    """

    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    code = "internal-error"
    title = "Internal Server Error"
    default_detail = "Internal Server Error"


def build_problem_response(
    *,
    request: Request,
    status_code: int,
    code: str,
    title: str,
    detail: str,
    headers: dict[str, str] | None = None,
    **extensions: object,
) -> JSONResponse:
    """Build an RFC 9457 problem document response.

    The single place a problem document is constructed, so every error path —
    domain errors, unconverted ``HTTPException``s, validation failures, rate
    limiting, the refresh-cookie clearing handler — produces an identical shape.
    Public because those last two live outside this module but must not build
    their own body.

    Args:
        request: The incoming request, for the ``instance`` member.
        status_code: HTTP status to return.
        code: Stable machine-readable slug, rendered as the ``type`` URN.
        title: Short summary of the error kind.
        detail: Caller-safe, occurrence-specific message.
        headers: Optional response headers (e.g. ``Retry-After``).
        **extensions: Additional RFC 9457 extension members.

    Returns:
        The problem document, served as ``application/problem+json``.
    """
    document: dict[str, object] = {
        "type": core_problem_details.problem_type(code),
        "title": title,
        "status": status_code,
        "detail": detail,
        "instance": request.url.path,
    }
    request_id = core_middleware_request_id.get_request_id()
    if request_id:
        document["request_id"] = request_id
    document.update({key: value for key, value in extensions.items() if value is not None})

    return JSONResponse(
        status_code=status_code,
        content=document,
        media_type=core_problem_details.PROBLEM_CONTENT_TYPE,
        headers=headers,
    )


async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    """Render a :class:`DomainError` as an RFC 9457 problem document.

    Server-side (5xx) errors are logged at ``error`` with a traceback because
    they indicate a defect; client-side (4xx) errors are logged at ``debug``
    because they are the API behaving as designed and would otherwise flood the
    logs with routine 404s.

    Args:
        request: The incoming request (used for log context and ``instance``).
        exc: The domain error raised by the application layer.

    Returns:
        The problem document.
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

    return build_problem_response(
        request=request,
        status_code=exc.status_code,
        code=exc.code,
        title=exc.title,
        detail=exc.detail,
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Render a bare ``HTTPException`` as a problem document.

    Registered so that a module which has not yet moved to domain errors still
    produces the same shape — otherwise the API would speak two error dialects
    depending on which module answered, which is precisely what a single error
    contract is for.

    ``detail`` may be a dict on some paths (the upload helpers attach a
    ``code``), so it is normalised to a string and any structured payload is
    preserved as extension members.

    Args:
        request: The incoming request.
        exc: The raised ``HTTPException``.

    Returns:
        The problem document.
    """
    detail = exc.detail
    extensions: dict[str, object] = {}
    if isinstance(detail, dict):
        message = str(detail.get("message", "")) or http.HTTPStatus(exc.status_code).phrase
        extensions = {key: value for key, value in detail.items() if key != "message"}
        detail = message

    phrase = http.HTTPStatus(exc.status_code).phrase
    return build_problem_response(
        request=request,
        status_code=exc.status_code,
        code=str(extensions.pop("code", None) or _slug(phrase)),
        title=phrase,
        detail=str(detail) if detail else phrase,
        headers=getattr(exc, "headers", None),
        **extensions,
    )


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Render a request-validation failure as a problem document.

    FastAPI's default 422 body is ``{"detail": [ …list of field errors… ]}``,
    which makes ``detail`` a list for this one status and a string everywhere
    else. The field errors move to an ``errors`` extension member so ``detail``
    keeps a single type across the whole API.

    Args:
        request: The incoming request.
        exc: The validation error raised by FastAPI.

    Returns:
        The problem document.
    """
    errors = [
        {
            "field": ".".join(str(part) for part in error.get("loc", ())),
            "message": error.get("msg", ""),
            "type": error.get("type", ""),
        }
        for error in exc.errors()
    ]
    return build_problem_response(
        request=request,
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        code="validation-failed",
        title="Unprocessable Content",
        detail="The request could not be validated.",
        errors=errors,
    )


def _slug(phrase: str) -> str:
    """Turn an HTTP reason phrase into a stable error slug."""
    return phrase.lower().replace(" ", "-")


def register_exception_handlers(app: FastAPI) -> None:
    """Wire the RFC 9457 error boundary onto a FastAPI application.

    Kept as a helper rather than inline ``add_exception_handler`` calls so the
    production app and the router tests register the boundary the same way. A
    test app that skipped it would surface an unhandled ``DomainError`` as a
    raised exception instead of the response real clients receive — exactly the
    drift that makes route tests pass while the API misbehaves.

    Args:
        app: The FastAPI application to register the handlers on.

    Returns:
        None.
    """
    app.add_exception_handler(DomainError, domain_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(HTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]
