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
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError
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
        headers: Response headers the error adds (``WWW-Authenticate``, ``Retry-After``); ``None`` when it adds none.
    """

    headers: dict[str, str] | None = None
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


class AccessConcealedError(NotFoundError):
    """A caller was refused, and the refusal is answered exactly like a missing resource.

    Renders as the same ``404`` and ``not-found`` problem as :class:`NotFoundError`,
    so a client cannot tell the two apart. The difference is on the server: raising
    this says the code *decided* to refuse (an invalid capability token, a network
    the caller may not view), which is a security-relevant event the service must log
    as a WARNING, while a plain :class:`NotFoundError` reports a record that is
    missing or whose absence cannot be told from a refusal.
    """


class PermissionDeniedError(DomainError):
    """The caller is authenticated but not allowed to perform this action."""

    status_code = status.HTTP_403_FORBIDDEN
    code = "permission-denied"
    title = "Forbidden"
    default_detail = "Forbidden"


class UnauthenticatedError(DomainError):
    """The caller did not provide valid authentication credentials."""

    status_code = status.HTTP_401_UNAUTHORIZED
    code = "unauthorized"
    title = "Unauthorized"
    default_detail = "Not authenticated"

    def __init__(self, detail: str | None = None, *, scheme: str = "Bearer") -> None:
        """Initialise the error with the authentication challenge to return.

        Args:
            detail: Message returned to the client.
            scheme: Authentication scheme named by ``WWW-Authenticate``.
        """
        super().__init__(detail)
        self.headers = {"WWW-Authenticate": scheme}


class InvalidInputError(DomainError):
    """The request is well-formed but semantically unusable."""

    status_code = status.HTTP_400_BAD_REQUEST
    code = "invalid-input"
    title = "Bad Request"
    default_detail = "Bad Request"


class InvalidMfaCodeError(InvalidInputError):
    """A submitted MFA code did not verify.

    Renders as the same ``400`` and ``invalid-input`` problem as :class:`InvalidInputError`; callers branch on the
    type to tell a wrong code from other input failures.
    """

    default_detail = "Invalid MFA code"


class MfaRequiredError(PermissionDeniedError):
    """The account has MFA enabled and the request carried no MFA code.

    Clients branch on the ``mfa-required`` problem type to ask for a code and send the same request again.
    """

    code = "mfa-required"
    default_detail = "MFA verification required"


class IdpReauthRequiredError(UnauthenticatedError):
    """The account has no local password and the request carried no proof of a fresh identity-provider sign-in.

    Clients branch on the ``idp-reauth-required`` problem type to send the user through their identity provider
    and send the same request again with the proof. The challenge follows RFC 9470.
    """

    code = "idp-reauth-required"
    default_detail = "Sign in again with your identity provider to continue"

    def __init__(self, max_age: int, detail: str | None = None) -> None:
        """Initialise the error with the freshness the new sign-in must meet.

        Args:
            max_age: Seconds within which the identity-provider sign-in must have happened.
            detail: Message returned to the client.
        """
        super().__init__(
            detail,
            scheme=f'Bearer error="insufficient_user_authentication", max_age="{max_age}"',
        )


class ConflictError(DomainError):
    """The action conflicts with the resource's current state."""

    status_code = status.HTTP_409_CONFLICT
    code = "conflict"
    title = "Conflict"
    default_detail = "Conflict"


class PreconditionFailedError(DomainError):
    """The request's ``If-Match`` precondition does not hold.

    Distinct from :class:`ConflictError`: the resource state is fine, but the
    caller's copy is stale, so applying their write would silently discard
    somebody else's.
    """

    status_code = status.HTTP_412_PRECONDITION_FAILED
    code = "precondition-failed"
    title = "Precondition Failed"
    default_detail = "Precondition Failed"


class PreconditionRequiredError(DomainError):
    """The request must be conditional and carries no ``If-Match`` header.

    A write to a versioned resource without a precondition is last-writer-wins,
    so the caller is told to read the resource and send the tag it got.
    """

    status_code = status.HTTP_428_PRECONDITION_REQUIRED
    code = "precondition-required"
    title = "Precondition Required"
    default_detail = "This request must be conditional; send the ETag you read in an If-Match header"


class TooManyRequestsError(DomainError):
    """A per-resource limit is reached, as opposed to the caller's request rate.

    Attributes:
        retry_at: When the limit clears, when the raiser knows it; a job that hit a provider's
            limit waits until then instead of retrying into it.
    """

    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "too-many-requests"
    title = "Too Many Requests"
    default_detail = "Too Many Requests"

    def __init__(self, detail: str | None = None, *, retry_at: datetime | None = None) -> None:
        """Initialise the error with an optional message and the time the limit clears.

        Args:
            detail: Message returned to the client.
            retry_at: When the limit clears, if known.
        """
        super().__init__(detail)
        self.retry_at = retry_at


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


class PayloadTooLargeError(DomainError):
    """The supplied payload exceeds the size this endpoint accepts."""

    status_code = status.HTTP_413_CONTENT_TOO_LARGE
    code = "payload-too-large"
    title = "Content Too Large"
    default_detail = "Content Too Large"


class ServiceUnavailableError(DomainError):
    """A capability the request depends on is not configured or not reachable."""

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "service-unavailable"
    title = "Service Unavailable"
    default_detail = "Service Unavailable"


class UpstreamError(DomainError):
    """An external system the server called (mail relay, provider) failed."""

    status_code = status.HTTP_502_BAD_GATEWAY
    code = "upstream-error"
    title = "Bad Gateway"
    default_detail = "Bad Gateway"


class DependencyFailedError(DomainError):
    """A request depends on an external system that rejected it or is not linked."""

    status_code = status.HTTP_424_FAILED_DEPENDENCY
    code = "dependency-failed"
    title = "Failed Dependency"
    default_detail = "Failed Dependency"


class ProcessingError(DomainError):
    """An internal step failed; the caller can do nothing about it.

    The default detail is intentionally opaque — the cause belongs in the log
    line, not in the response.
    """

    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    code = "internal-error"
    title = "Internal Server Error"
    default_detail = "Internal Server Error"


class CryptographyError(ProcessingError):
    """Encrypting or decrypting a secret failed, or the configured key cannot be used.

    The response is as opaque as :class:`ProcessingError`: the cause belongs in the log.
    """


class UndecryptableError(CryptographyError):
    """A stored secret was not produced by the configured key, or is corrupt.

    Unlike a missing or malformed key, this concerns one value: the secret has to be entered
    again, and retrying the same operation meets the same answer.
    """


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
        detail=exc.detail,
    )
    if exc.status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
        logger.error("Unhandled domain error", exc_info=exc, extra=log_context)
    else:
        logger.debug("Domain error", extra=log_context)

    return build_problem_response(
        request=request,
        status_code=exc.status_code,
        code=exc.code,
        title=exc.title,
        detail=exc.detail,
        headers=exc.headers,
    )


#: PostgreSQL SQLSTATEs for a lock wait (``lock_timeout``) and a cancelled statement (``statement_timeout``).
_TRANSIENT_DB_SQLSTATES = frozenset({"55P03", "57014"})
#: Seconds a client is told to wait before retrying a request the database could not serve.
_DB_RETRY_AFTER_SECONDS = 5


def _is_database_unavailable(exc: SQLAlchemyError) -> bool:
    """Tell whether a database error means the database could not take the request right now.

    Args:
        exc: The database error.

    Returns:
        True for an exhausted connection pool, a lock timeout or a statement timeout.
    """
    if isinstance(exc, SQLAlchemyTimeoutError):
        return True
    if isinstance(exc, OperationalError):
        return getattr(exc.orig, "sqlstate", None) in _TRANSIENT_DB_SQLSTATES
    return False


async def database_error_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    """Render a database error that reached the boundary as a problem document.

    The one place a database failure raised outside ``crud`` is translated. A
    ``service`` owns the commit, so a failed commit reaches this boundary;
    wrapping every ``db.commit()`` in its own ``try`` would repeat this in each
    service.
    The session has already been rolled back by ``core.database.get_db``.

    An exhausted connection pool, a lock timeout and a statement timeout are transient, so they answer 503 with
    ``Retry-After``; an ``IntegrityError`` is a unique or foreign-key conflict that only surfaced at commit, so it
    answers 409. Both are logged as warnings. Anything else is an opaque 500 logged as an error.

    Only the exception class goes in the log message: SQLAlchemy error strings
    embed the SQL statement and its parameters (OWASP A09), so they are never
    interpolated and never returned to the client.

    Args:
        request: The incoming request (used for log context and ``instance``).
        exc: The database error raised by the application layer.

    Returns:
        The problem document for the failure.
    """
    log_context = core_logger.context(path=request.url.path, method=request.method, error=type(exc).__name__)
    message = f"Database error on {request.method} {request.url.path}: {type(exc).__name__}"
    headers: dict[str, str] | None = None
    if _is_database_unavailable(exc):
        logger.warning(message, extra=log_context)
        error: type[DomainError] = ServiceUnavailableError
        headers = {"Retry-After": str(_DB_RETRY_AFTER_SECONDS)}
    elif isinstance(exc, IntegrityError):
        logger.warning(message, extra=log_context)
        error = ConflictError
    else:
        logger.error(message, exc_info=exc, extra=log_context)
        error = ProcessingError
    return build_problem_response(
        request=request,
        status_code=error.status_code,
        code=error.code,
        title=error.title,
        detail=error.default_detail,
        headers=headers,
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Render an error nothing else handled as the same opaque problem document.

    Without it Starlette answers a plain-text 500, so clients would see a second error shape. Only the
    exception class is logged in the message; the traceback goes in ``exc_info``.

    Args:
        request: The incoming request (used for log context and ``instance``).
        exc: The unhandled exception.

    Returns:
        The same problem document a :class:`ProcessingError` produces.
    """
    logger.error(
        f"Unhandled error on {request.method} {request.url.path}: {type(exc).__name__}",
        exc_info=exc,
        extra=core_logger.context(path=request.url.path, method=request.method, error=type(exc).__name__),
    )
    # This handler runs outside the request-id middleware, so the response header is set here.
    request_id = core_middleware_request_id.get_request_id()
    return build_problem_response(
        request=request,
        status_code=ProcessingError.status_code,
        code=ProcessingError.code,
        title=ProcessingError.title,
        detail=ProcessingError.default_detail,
        headers={"X-Request-ID": request_id} if request_id else None,
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
    app.add_exception_handler(SQLAlchemyError, database_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(HTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_error_handler)
