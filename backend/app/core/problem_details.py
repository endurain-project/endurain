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

import json
from typing import Any

from fastapi import FastAPI
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


# FastAPI generates these from its own default 422 handler, which no longer runs.
_SUPERSEDED_SCHEMAS = ("HTTPValidationError", "ValidationError")


def _is_error_status(status_code: str) -> bool:
    """Return whether an OpenAPI response key denotes an error response."""
    return status_code == "default" or (status_code.isdigit() and int(status_code) >= 400)


def _problem_content() -> dict[str, Any]:
    """Return the OpenAPI ``content`` block for a problem document."""
    return {PROBLEM_CONTENT_TYPE: {"schema": {"$ref": f"#/components/schemas/{ProblemDetail.__name__}"}}}


def _rewrite_error_responses(schema: dict[str, Any]) -> dict[str, Any]:
    """Point every error response in an OpenAPI document at :class:`ProblemDetail`.

    FastAPI documents its *default* error shapes, not the ones this app installs:
    every operation with a path/query parameter declares a 422 returning
    ``HTTPValidationError``, whose ``detail`` is an **array**. The validation
    handler now returns a problem document whose ``detail`` is a string, so the
    generated schema — and the frontend client generated from it — described a
    response the API cannot produce.

    A ``default`` response is added too, so the document states that *any*
    unlisted failure is also a problem document, without enumerating every status
    on every operation.

    Args:
        schema: The OpenAPI document, mutated in place.

    Returns:
        The same document.
    """
    components = schema.setdefault("components", {}).setdefault("schemas", {})
    components[ProblemDetail.__name__] = ProblemDetail.model_json_schema(ref_template="#/components/schemas/{model}")

    for path_item in schema.get("paths", {}).values():
        for operation in path_item.values():
            if not isinstance(operation, dict) or "responses" not in operation:
                continue
            responses = operation["responses"]
            for status_code in list(responses):
                if _is_error_status(status_code):
                    responses[status_code] = {
                        "description": responses[status_code].get("description", "Error"),
                        "content": _problem_content(),
                    }
            responses.setdefault(
                "default",
                {"description": "Unexpected error", "content": _problem_content()},
            )

    # Drop the superseded schemas once nothing references them. Iterated because
    # removing one can orphan another: HTTPValidationError is the only referent
    # of ValidationError.
    for _ in range(len(_SUPERSEDED_SCHEMAS)):
        remaining = json.dumps(schema)
        orphans = [
            name
            for name in _SUPERSEDED_SCHEMAS
            if name in components and f'"#/components/schemas/{name}"' not in remaining
        ]
        if not orphans:
            break
        for name in orphans:
            components.pop(name)

    return schema


def install_problem_schema(app: FastAPI) -> None:
    """Make ``app.openapi()`` describe the errors the app actually returns.

    Wraps the generator rather than annotating ~30 ``include_router`` calls with
    ``responses=``: the rule is global, so stating it once is both less noise and
    impossible to forget on a new router.

    Args:
        app: The FastAPI application whose schema generator to wrap.

    Returns:
        None.
    """
    generate = app.openapi

    def patched() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        # ``generate()`` populates and returns ``app.openapi_schema``; mutating it
        # in place means the cached document is the patched one.
        app.openapi_schema = _rewrite_error_responses(generate())
        return app.openapi_schema

    app.openapi = patched  # type: ignore[method-assign]
