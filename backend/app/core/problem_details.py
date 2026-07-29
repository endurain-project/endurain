"""RFC 9457 *Problem Details for HTTP APIs* — the API's one error response shape.

Every error the API emits is a problem document, whatever raised it: a
:class:`~core.exceptions.DomainError`, a bare ``HTTPException`` from a module not
yet converted, a request-validation failure, or a rate-limit rejection. One shape
means a client writes one error path.

Why the members are what they are
---------------------------------
``type`` is the machine-readable discriminator, and it is a **URN**
(``urn:endurain:error:not-found``) rather than a documentation URL. That is a
deliberate trade: RFC 9457 §3.1.1 permits a non-dereferenceable URI, and a URN
does not promise a page that does not exist yet. It is also a one-way door —
clients will match on this string, so switching to ``https://docs.endurain.com/…``
later would break them. Stability beats dereferenceability here.

``detail`` is kept, and kept first-class, because the existing clients already
read it — RFC 9457 happens to name its human-readable member exactly what
FastAPI's default body used. That is what makes this change additive rather than
breaking for a consumer that only reads ``detail``.

``instance`` carries the request path, and ``request_id`` is an extension member
carrying the ``X-Request-ID`` the logging middleware already assigns. That pairing
is the point: a user can quote the id from a failed response and it resolves to
the exact log line, without the response ever exposing an internal message.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# Media type mandated by RFC 9457 for a problem document.
PROBLEM_CONTENT_TYPE = "application/problem+json"

# Namespace for the ``type`` member. Values under it must stay stable: clients
# match on them.
_TYPE_PREFIX = "urn:endurain:error"

# Used when nothing more specific applies. RFC 9457 §4.2.1 defines "about:blank"
# as "the status code is the whole story".
DEFAULT_TYPE = "about:blank"


def problem_type(code: str) -> str:
    """Return the ``type`` URN for a machine-readable error code.

    Args:
        code: Stable slug, e.g. ``"not-found"``.

    Returns:
        The URN, e.g. ``"urn:endurain:error:not-found"``.
    """
    return f"{_TYPE_PREFIX}:{code}"


class ProblemDetail(BaseModel):
    """An RFC 9457 problem document, as returned for every API error.

    Declared as a model so it appears in the generated OpenAPI schema and the
    frontend's typed client, rather than being an undocumented dict shape.

    Attributes:
        type: Stable URN identifying the error kind; the member a client should
            branch on. ``about:blank`` when the status code says everything.
        title: Short, human-readable summary of the error kind. Does not vary
            between occurrences of the same ``type``.
        status: The HTTP status code, repeated in the body so a document that has
            been logged or forwarded is still self-describing.
        detail: Human-readable explanation specific to this occurrence. Safe to
            show a user; never carries internal diagnostics.
        instance: The request path the error occurred on.
        request_id: The ``X-Request-ID`` for this request, when one was assigned.
            Quoting it in a bug report resolves to the exact server log line.
        errors: Field-level validation failures, present only for a request
            validation error.
    """

    model_config = ConfigDict(extra="allow")

    type: str = DEFAULT_TYPE
    title: str
    status: int
    detail: str
    instance: str | None = None
    request_id: str | None = None
    errors: list[dict[str, Any]] | None = Field(default=None)
