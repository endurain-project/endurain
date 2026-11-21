"""Transport-agnostic domain errors raised by application layers.

The application layers — services, the ingestion pipeline, the file parsers —
describe *what went wrong in the domain*, not *which HTTP status to send*. They
raise the exceptions defined here; :func:`domain_error_handler`, registered once
on the FastAPI app, is the single place that turns a domain error into a
response.

Why this exists
---------------
Raising ``fastapi.HTTPException`` directly would couple those layers to HTTP in three unhelpful ways:

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
import math
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from enum import StrEnum

import jasil.orm as jasil_orm
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

import core.job_status as core_job_status
import core.logger as core_logger
import core.middleware_request_id as core_middleware_request_id
import core.problem_details as core_problem_details
import core.security_headers as core_security_headers

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
        extensions: RFC 9457 extension members the error adds to its problem document (the scopes a credential is
            missing); ``None`` when it adds none.
    """

    headers: dict[str, str] | None = None
    extensions: dict[str, object] | None = None
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


class StepUpFailedError(PermissionDeniedError):
    """A sensitive operation's re-authentication did not verify.

    The answer is the same whichever factor failed (password, ticket or MFA code), so it never confirms a correct
    password. It is a ``403``, not a ``401``: the access token is fine, so the client must not refresh it or take
    the user to the sign-in page.
    """

    code = "step-up-failed"
    default_detail = "Step-up verification failed"


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


class InvalidTokenError(UnauthenticatedError):
    """The access token of a resource route is missing, expired, malformed or its session ended.

    Only a resource route answers it. Clients branch on the ``invalid-token`` problem type to refresh their tokens
    once and send the request again; a refusal of the sign-in or the refresh is :class:`SessionEndedError`. The
    challenge follows RFC 6750: ``error="invalid_token"``, and no error code when the request carried no token.
    """

    code = "invalid-token"
    default_detail = "Invalid or expired token"

    def __init__(self, detail: str | None = None, *, scheme: str = 'Bearer error="invalid_token"') -> None:
        """Initialise the error with the authentication challenge to return.

        Args:
            detail: Message returned to the client.
            scheme: Authentication challenge for ``WWW-Authenticate``; pass ``"Bearer"`` when the request carried
                no token.
        """
        super().__init__(detail, scheme=scheme)


class SessionEndedError(UnauthenticatedError):
    """The sign-in or the refresh credential is final: the client must sign in again, not retry.

    ``/auth/refresh`` answers it for every refusal, and ``/auth/mfa/verify`` and ``/auth/password-change`` answer it
    for a pending sign-in that is dead. The routes have no bearer scheme, so the challenge is ``Session``, a
    scheme without parameters.
    """

    code = "session-ended"
    default_detail = "The session has ended. Sign in again."

    def __init__(self, detail: str | None = None, *, scheme: str = "Session") -> None:
        """Initialise the error with the authentication challenge to return.

        Args:
            detail: Message returned to the client.
            scheme: Authentication challenge for ``WWW-Authenticate``.
        """
        super().__init__(detail, scheme=scheme)


class InvalidInputError(DomainError):
    """The request is well-formed but semantically unusable."""

    status_code = status.HTTP_400_BAD_REQUEST
    code = "invalid-input"
    title = "Bad Request"
    default_detail = "Bad Request"


class InvalidMfaCodeError(InvalidInputError):
    """A submitted MFA code did not verify.

    Renders as a ``400`` with the ``invalid-mfa-code`` problem type, so a client can tell a wrong code from other
    input failures; code that catches :class:`InvalidInputError` still catches it.
    """

    code = "invalid-mfa-code"
    default_detail = "Invalid MFA code"


class ProviderScopeInsufficientError(InvalidInputError):
    """The user granted an external provider fewer permissions than the integration needs.

    Clients branch on the ``provider-scope-insufficient`` problem type to tell the user to authorize again and
    grant every requested permission.
    """

    code = "provider-scope-insufficient"
    default_detail = "The provider authorization is missing a required permission"


class MfaEnrolmentRequiredError(PermissionDeniedError):
    """The server requires MFA of this account, which has not enrolled a second factor.

    Renders as ``403``. Clients branch on the ``mfa-enrolment-required`` problem type to send the user to enrol; the
    account may still make the requests enrolment needs, and sign out.
    """

    code = "mfa-enrolment-required"
    default_detail = "Set up two-step verification to continue"


class EmailVerificationDisabledError(PermissionDeniedError):
    """A sign-up confirmation arrived while email verification is turned off on this server.

    Renders as ``403``. Clients branch on the ``email-verification-disabled`` problem type to tell the user the
    link cannot be used here; retrying never succeeds.
    """

    code = "email-verification-disabled"
    default_detail = "Email verification is not enabled on this server"


class PasswordRequiredError(InvalidInputError):
    """A request arrived without the password the server needs.

    That happens on a sign-up while email verification is off, or on an account an administrator creates while mail
    is not configured to invite its owner.

    Clients branch on the ``password-required`` problem type to ask for a password and send the same request again.
    """

    code = "password-required"
    default_detail = "A password is required"


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


class LastSignInMethodError(ConflictError):
    """Unlinking an identity provider would leave the account with no way to sign in.

    Renders as ``409``. Clients branch on the ``last-sign-in-method`` problem type to tell the user to set a
    password or link another provider first.
    """

    code = "last-sign-in-method"
    default_detail = "This is the account's only sign-in method"


class LastAdministratorError(ConflictError):
    """A change would leave the server without an active administrator.

    Renders as ``409``. Clients branch on the ``last-administrator`` problem type to tell the user to make
    another user an administrator first.
    """

    code = "last-administrator"
    default_detail = "The only administrator cannot be changed"


class ApprovalPendingError(ConflictError):
    """An edit would activate a user who is awaiting administrator approval.

    Renders as ``409``. Clients branch on the ``approval-pending`` problem type to tell the administrator to use the
    approve action instead.
    """

    code = "approval-pending"
    default_detail = "User is awaiting approval"


class IssuerInUseError(ConflictError):
    """Another identity provider already uses the issuer URL being set.

    Renders as ``409``. Clients branch on the ``issuer-in-use`` problem type to tell the administrator to pick a
    different issuer URL.
    """

    code = "issuer-in-use"
    default_detail = "Another identity provider already uses this issuer"


class IdentityProviderLockedError(ConflictError):
    """An edit changes fields that identify an identity provider while users are linked to it.

    Renders as ``409``. Clients branch on the ``identity-provider-locked`` problem type to tell the administrator to
    unlink the users or add a new provider instead. The detail names the locked fields the edit changes.
    """

    code = "identity-provider-locked"
    default_detail = "These fields cannot change while users are linked to this provider"


class ApiKeyLimitError(ConflictError):
    """The user already holds the most active API keys one account may have.

    Renders as ``409``. Clients branch on the ``api-key-limit`` problem type to tell the user to revoke or delete a
    key first.
    """

    code = "api-key-limit"
    default_detail = "The account already has the maximum number of active API keys"


class ComponentsOutsideGearTypeError(ConflictError):
    """A gear's type cannot change while it has components the new type does not allow.

    Renders as ``409``. Clients branch on the ``components-outside-gear-type`` problem type to tell the user to remove
    the components that do not fit the new type first.
    """

    code = "components-outside-gear-type"
    default_detail = "Remove the components that do not fit the new gear type first"


class JobAlreadyRunningError(ConflictError):
    """A start route refused a second run of work that is still running.

    Renders as the same ``409`` and ``conflict`` problem as :class:`ConflictError`, plus, when the running job
    can be named, a ``Content-Location`` header pointing at ``GET /jobs/{job_id}`` and a ``job_id`` member, so a
    client that lost the ``202`` of the first request can pick the run up again.

    Attributes:
        job_id: The id of the running job, or None when it cannot be named.
    """

    def __init__(self, detail: str | None = None, *, job_id: uuid.UUID | None) -> None:
        """Initialise the error with the job in progress.

        Args:
            detail: Message returned to the client.
            job_id: The id of the running job, or None when it cannot be named (it finished or expired meanwhile).
        """
        super().__init__(detail)
        self.job_id = job_id
        if job_id is not None:
            self.extensions = {"job_id": str(job_id)}


#: The page of the client documentation that describes ``Idempotency-Key``.
IDEMPOTENCY_DOCS_URL = "https://docs.endurain.com/integrate/idempotency/"
_IDEMPOTENCY_LINK = f'<{IDEMPOTENCY_DOCS_URL}>; rel="describedby"'


class IdempotencyKeyInvalidError(InvalidInputError):
    """The ``Idempotency-Key`` header is not one quoted printable-ASCII string of 1 to 255 characters.

    Renders as ``400`` with the ``idempotency-key-invalid`` problem type and a ``Link`` to the page that states the
    grammar.
    """

    code = "idempotency-key-invalid"
    default_detail = "Idempotency-Key must be one quoted string of 1 to 255 printable ASCII characters"

    def __init__(self, detail: str | None = None) -> None:
        """Initialise the error with the ``Link`` to the page that describes the header.

        Args:
            detail: Message returned to the client.
        """
        super().__init__(detail)
        self.headers = {"Link": _IDEMPOTENCY_LINK}


class IdempotencyKeyReusedError(DomainError):
    """An ``Idempotency-Key`` that was used for one request came back with another.

    Renders as ``422`` with the ``idempotency-key-reused`` problem type: the request is well formed but cannot be
    answered, because answering it with the first request's outcome would tell the client something false.
    """

    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "idempotency-key-reused"
    title = "Idempotency Key Reused"
    default_detail = "This Idempotency-Key was already used for a different request"

    def __init__(self, detail: str | None = None) -> None:
        """Initialise the error with the ``Link`` to the page that describes the header.

        Args:
            detail: Message returned to the client.
        """
        super().__init__(detail)
        self.headers = {"Link": _IDEMPOTENCY_LINK}


class IdempotencyInFlightError(ConflictError):
    """A request with this ``Idempotency-Key`` is still being served.

    Renders as ``409`` with the ``idempotency-key-in-flight`` problem type and ``Retry-After``: the client repeats the
    request once the first one has finished and gets its outcome.
    """

    code = "idempotency-key-in-flight"
    title = "Idempotency Key In Flight"
    default_detail = "A request with this Idempotency-Key is still being processed"

    def __init__(self, detail: str | None = None, *, retry_after_seconds: int) -> None:
        """Initialise the error with how long the client waits before it repeats the request.

        Args:
            detail: Message returned to the client.
            retry_after_seconds: The ``Retry-After`` value.
        """
        super().__init__(detail)
        self.headers = {"Link": _IDEMPOTENCY_LINK, "Retry-After": str(retry_after_seconds)}


class IdempotentReplayError(Exception):
    """The request repeats one already answered; the handler sends that answer again instead of running the route.

    Attributes:
        status_code: The stored status.
        headers: The stored headers, as ``(name, value)`` pairs.
        body: The stored body, byte for byte.
    """

    def __init__(self, status_code: int, headers: list[tuple[str, str]], body: bytes) -> None:
        """Hold the stored response.

        Args:
            status_code: The stored status.
            headers: The stored headers.
            body: The stored body.
        """
        super().__init__(status_code)
        self.status_code = status_code
        self.headers = headers
        self.body = body


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


class SyncExpiredError(DomainError):
    """A sync cursor is older than the deletions the server remembers.

    Renders as ``410``. A deletion that happened before the cursor's position may already be forgotten, so the
    client's copy cannot be brought up to date from it; clients branch on the ``sync-expired`` problem type to
    discard their copy and sync again from the start.
    """

    status_code = status.HTTP_410_GONE
    code = "sync-expired"
    title = "Sync Expired"
    default_detail = "The sync cursor has expired; sync again from the start"


class PreconditionRequiredError(DomainError):
    """The request must be conditional and carries no ``If-Match`` header.

    A write to a versioned resource without a precondition is last-writer-wins,
    so the caller is told to read the resource and send the tag it got.
    """

    status_code = status.HTTP_428_PRECONDITION_REQUIRED
    code = "precondition-required"
    title = "Precondition Required"
    default_detail = "This request must be conditional; send the ETag you read in an If-Match header"


class TooManyRequestsScope(StrEnum):
    """What a 429 says was exhausted, the ``scope`` member of its problem document.

    The set is open: a client treats a value it does not know like any other 429 and waits for ``Retry-After``.
    """

    REQUESTS = "requests"
    SIGN_IN = "sign-in"
    MFA = "mfa"
    STEP_UP = "step-up"
    PROVIDER = "provider"
    FOLLOW_REQUEST = "follow-request"


class TooManyRequestsError(DomainError):
    """A per-resource limit is reached, as opposed to the caller's request rate.

    Renders as ``429`` with the ``too-many-requests`` problem type, a ``scope`` member and, when the end of the limit
    is known, ``Retry-After``.

    Attributes:
        scope: What was exhausted.
        retry_at: When the limit clears, when the raiser knows it; a job that hit a provider's
            limit waits until then instead of retrying into it.
    """

    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "too-many-requests"
    title = "Too Many Requests"
    default_detail = "Too Many Requests"

    def __init__(
        self, detail: str | None = None, *, scope: TooManyRequestsScope, retry_at: datetime | None = None
    ) -> None:
        """Initialise the error with an optional message, what was exhausted and the time the limit clears.

        Args:
            detail: Message returned to the client.
            scope: What was exhausted.
            retry_at: When the limit clears, if known.
        """
        super().__init__(detail)
        self.scope = scope
        self.retry_at = retry_at
        self.extensions = {"scope": scope.value}


class UnsupportedFormatError(DomainError):
    """The supplied payload is in a format this endpoint cannot process."""

    status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    code = "unsupported-format"
    title = "Unsupported Media Type"
    default_detail = "Unsupported Media Type"


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
    domain errors, framework ``HTTPException``s, validation failures, rate
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

    A server-side error the code did not plan for (500) is logged at ``error``
    with a traceback because it indicates a defect. A dependency the request
    could not use (502 and 503: a store, a provider or a mail server that is
    down or not configured) is a degraded path, logged at ``warning`` without a
    traceback; where it was detected logs the cause. Client-side (4xx) errors
    are logged at ``debug`` because they are the API behaving as designed and
    would otherwise flood the logs with routine 404s.

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
    if isinstance(exc, ServiceUnavailableError | UpstreamError):
        logger.warning("Dependency unavailable", extra=log_context)
    elif exc.status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
        logger.error("Unhandled domain error", exc_info=exc, extra=log_context)
    else:
        logger.debug("Domain error", extra=log_context)

    headers = exc.headers
    if isinstance(exc, TooManyRequestsError) and exc.retry_at is not None:
        # Rendered when the response is built, so the seconds count from the moment the client is told.
        seconds = max(0, math.ceil((exc.retry_at - datetime.now(UTC)).total_seconds()))
        headers = {**(headers or {}), "Retry-After": str(seconds)}
    if isinstance(exc, JobAlreadyRunningError) and exc.job_id is not None:
        location = request.url_for(core_job_status.JOB_ROUTE, job_id=str(exc.job_id)).path
        headers = {**(headers or {}), "Content-Location": location}

    return build_problem_response(
        request=request,
        status_code=exc.status_code,
        code=exc.code,
        title=exc.title,
        detail=exc.detail,
        headers=headers,
        **(exc.extensions or {}),
    )


async def idempotent_replay_handler(request: Request, exc: IdempotentReplayError) -> Response:
    """Send the stored response of a request that repeats an answered one.

    The route never ran, so nothing was created, audited or published a second time. The replay adds no header of
    its own: the client sees the response it would have seen the first time.

    Args:
        request: The incoming request.
        exc: The replay, carrying the stored response.

    Returns:
        The stored status, headers and body.
    """
    logger.info(
        "Replayed the stored response of an idempotent request",
        extra=core_logger.context(path=request.url.path, method=request.method, status_code=exc.status_code),
    )
    response = Response(content=exc.body, status_code=exc.status_code)
    for name, value in exc.headers:
        response.headers.append(name, value)
    return response


#: PostgreSQL SQLSTATEs of a database too busy to take the request now: a lock wait (``lock_timeout``) and a cancelled
#: statement (``statement_timeout``).
_BUSY_DB_SQLSTATES = frozenset({"55P03", "57014"})
#: Seconds a client is told to wait before retrying a request the database could not serve.
_DB_RETRY_AFTER_SECONDS = 5


def _is_database_busy(exc: SQLAlchemyError) -> bool:
    """Tell whether a database error is a lock or statement timeout, which a retry may get past.

    Args:
        exc: The database error.

    Returns:
        True for a statement that timed out waiting for a lock or ran past ``statement_timeout``.
    """
    return isinstance(exc, OperationalError) and getattr(exc.orig, "sqlstate", None) in _BUSY_DB_SQLSTATES


async def database_error_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    """Render a database error that reached the boundary as a problem document.

    The one place a database failure raised outside ``crud`` is translated. A
    ``service`` owns the commit, so a failed commit reaches this boundary;
    wrapping every ``db.commit()`` in its own ``try`` would repeat this in each
    service.
    The session has already been rolled back by ``core.database.get_db``.

    A database out of reach (``jasil.orm.is_database_unavailable``) or too busy (a lock or statement timeout) is
    transient, so it answers 503 with ``Retry-After``; an ``IntegrityError`` is a unique or foreign-key conflict that
    only surfaced at commit, so it answers 409. Both are logged as warnings. Anything else is an opaque 500 logged as an
    error.

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
    if jasil_orm.is_database_unavailable(exc) or _is_database_busy(exc):
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
    # Starlette's outermost layer calls this handler, outside every middleware, so the response header and the
    # security headers are set here.
    request_id = core_middleware_request_id.get_request_id()
    response = build_problem_response(
        request=request,
        status_code=ProcessingError.status_code,
        code=ProcessingError.code,
        title=ProcessingError.title,
        detail=ProcessingError.default_detail,
        headers={"X-Request-ID": request_id} if request_id else None,
    )
    core_security_headers.apply(response)
    return response


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
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


def register_handler[E: Exception](
    app: FastAPI, exc_class: type[E], handler: Callable[[Request, E], Awaitable[Response]]
) -> None:
    """Register an exception handler typed by the exception class it renders.

    Starlette types every handler as taking any ``Exception``, though it only calls one with an instance
    of the class it was registered for. The registered function checks that instance once, so each
    handler can name the exception it actually receives.

    Args:
        app: The FastAPI application to register the handler on.
        exc_class: The exception class, subclasses included, the handler renders.
        handler: The coroutine that renders the exception as a response.
    """

    async def handle(request: Request, exc: Exception) -> Response:
        if not isinstance(exc, exc_class):
            raise exc
        return await handler(request, exc)

    app.add_exception_handler(exc_class, handle)


def register_sync_handler[E: Exception](
    app: FastAPI, exc_class: type[E], handler: Callable[[Request, E], Response]
) -> None:
    """Register a synchronous exception handler typed by the exception class it renders.

    The registered function stays synchronous, so Starlette runs it in the threadpool and the rate-limit
    middleware, which only calls a synchronous handler, can still call it.

    Args:
        app: The FastAPI application to register the handler on.
        exc_class: The exception class, subclasses included, the handler renders.
        handler: The function that renders the exception as a response.
    """

    def handle(request: Request, exc: Exception) -> Response:
        if not isinstance(exc, exc_class):
            raise exc
        return handler(request, exc)

    app.add_exception_handler(exc_class, handle)


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
    register_handler(app, DomainError, domain_error_handler)
    register_handler(app, IdempotentReplayError, idempotent_replay_handler)
    register_handler(app, SQLAlchemyError, database_error_handler)
    register_handler(app, HTTPException, http_exception_handler)
    register_handler(app, StarletteHTTPException, http_exception_handler)
    register_handler(app, RequestValidationError, validation_error_handler)
    register_handler(app, Exception, unhandled_error_handler)
