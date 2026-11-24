"""What the OpenAPI document states about errors, headers and server-owned fields, declared once.

FastAPI documents only what a route lists in ``responses=``, so left alone the document names 200 and 422 and a
client learns the rest by trying. The facts below follow from what an operation already declares, so they are
derived for every operation instead of repeated on each route:

- the default rate limit and an unavailable database answer 429 and 503 on every operation (``Retry-After``, and
    ``X-RateLimit-*`` on the 429);
- a security requirement can answer 401 (``WWW-Authenticate``) and 403;
- a path parameter can answer 404, a request body 413, an upload (``x-max-body-bytes``) 415, and a write 409;
- ``If-Match`` is required, because its absence is refused with 428, and a stale or wildcard tag is 412 or 400;
- an operation that declares ``Idempotency-Key`` can answer 400 for a malformed key and 422 for a key used for another
  request, and one that replays a stored response (:func:`replays_responses`) 409 for a request with that key still
  running;
- a success response carrying a ``version`` sends an ``ETag``, and a create that can be read by id a ``Location``;
- ``id``, ``version``, ``created_at`` and ``updated_at`` are ``readOnly`` in every schema a client does not send.

A route lists in ``responses=`` only what the document cannot derive: ``core.location.ACCEPTED_RESPONSE`` and
``POLLED_STATUS_HEADERS``, :data:`ETAG_HEADERS` where the version is not a field of the body,
:data:`NO_STORE_RESPONSE_HEADERS` on a response that carries a token or a secret, the errors a handler raises that no
operation fact implies (a refusal of its own, a status the dependencies and middleware do not give), and
:func:`binary_response`.
"""

import re
from collections.abc import Callable, Iterable
from typing import Any

from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute
from pydantic import BaseModel
from starlette.routing import BaseRoute

import core.etag as core_etag

_METHODS = ("get", "post", "put", "patch", "delete")
_SCHEMA_REF = "#/components/schemas/"
_SERVER_OWNED_FIELDS = frozenset({"id", "version", "created_at", "updated_at"})
_UPLOAD_EXTENSION = "x-max-body-bytes"
_IDEMPOTENCY_HEADER = "Idempotency-Key"

_ETAG_HEADER: dict[str, Any] = {
    "description": "The version of the resource, to send back as `If-Match` on the next write.",
    "schema": {"type": "string"},
}


def replaced_response(model: type[BaseModel]) -> dict[int | str, dict[str, Any]]:
    """Declare the ``200`` of a ``PUT`` that answers ``201`` for what it created.

    Args:
        model: The body both statuses carry.

    Returns:
        The ``responses`` entry.
    """
    return {200: {"model": model, "description": "The attachment replaced one that was there."}}


#: The ``headers`` of a success response whose ``ETag`` the document cannot derive, for a route's ``responses``.
ETAG_HEADERS: dict[str, Any] = {"ETag": _ETAG_HEADER}
#: The ``headers`` of a response that carries a token or a secret and so is never cached, for a route's ``responses``.
#: The handler sends them with ``core.cache_control.set_no_store`` or ``core.cache_control.NO_STORE_HEADERS``.
NO_STORE_RESPONSE_HEADERS: dict[str, Any] = {
    "Cache-Control": {
        "description": "`no-store`: no cache may keep the response, which carries a token or a secret.",
        "schema": {"type": "string"},
    },
    "Pragma": {"description": "`no-cache`, for HTTP/1.0 caches.", "schema": {"type": "string"}},
}
_LOCATION_HEADER: dict[str, Any] = {
    "description": "Path of the new resource.",
    "schema": {"type": "string"},
}
_AUTHENTICATE_HEADER: dict[str, Any] = {
    "description": "The authentication challenge.",
    "schema": {"type": "string"},
}
_RETRY_AFTER_HEADER: dict[str, Any] = {
    "description": "Seconds to wait before the request can succeed.",
    "schema": {"type": "integer"},
}

_RATE_LIMIT_LIMIT_HEADER: dict[str, Any] = {
    "description": "The number of requests the limit that was reached allows in its window.",
    "schema": {"type": "integer"},
}

_RATE_LIMIT_REMAINING_HEADER: dict[str, Any] = {
    "description": "The requests left in the window: always 0 on a 429.",
    "schema": {"type": "integer"},
}

#: Each derived error: the description and the headers it carries.
_ERRORS: dict[str, tuple[str, dict[str, Any]]] = {
    "400": ("The request is refused, for example `If-Match: *`.", {}),
    "401": ("The credential is missing, invalid or no longer valid.", {"WWW-Authenticate": _AUTHENTICATE_HEADER}),
    "403": ("The caller is signed in but not allowed, for example a scope is missing.", {}),
    "404": ("The resource does not exist, or is concealed from the caller.", {}),
    "409": ("The request conflicts with the current state.", {}),
    "412": ("The `If-Match` tag is stale: the resource changed since it was read.", {}),
    "413": ("The body is larger than the route accepts.", {}),
    "415": ("The uploaded file is a type the route does not accept.", {}),
    "422": ("The request does not match the schema.", {}),
    "428": ("The `If-Match` header is missing.", {}),
    "429": (
        "The rate limit was reached.",
        {
            "Retry-After": _RETRY_AFTER_HEADER,
            "X-RateLimit-Limit": _RATE_LIMIT_LIMIT_HEADER,
            "X-RateLimit-Remaining": _RATE_LIMIT_REMAINING_HEADER,
        },
    ),
    "503": ("A dependency is unavailable for a moment.", {"Retry-After": _RETRY_AFTER_HEADER}),
}

#: What an ``Idempotency-Key`` adds to the description of an error the operation can answer.
_IDEMPOTENCY_NOTES: dict[str, str] = {
    "400": "A malformed `Idempotency-Key` is refused with this status.",
    "409": "A request whose `Idempotency-Key` is still being served is answered with this status and `Retry-After`.",
    "422": "An `Idempotency-Key` already used for a different request is refused with this status.",
}
_FRAMEWORK_VALIDATION_DESCRIPTION = "Validation Error"


def binary_response(
    *media_types: str, description: str = "The file.", headers: dict[str, Any] | None = None
) -> dict[int | str, dict[str, Any]]:
    """Build the ``responses`` entry of a route that sends bytes.

    Pair it with ``response_class=Response``: a route without a body class of its own would also declare an
    empty JSON body next to the media types.

    Args:
        *media_types: The media types the route sends.
        description: What the file is.
        headers: The ``headers`` the response declares, such as :data:`NO_STORE_RESPONSE_HEADERS`.

    Returns:
        The ``responses`` mapping to pass to the route.
    """
    schema = {"schema": {"type": "string", "format": "binary"}}
    response: dict[str, Any] = {"description": description, "content": dict.fromkeys(media_types, schema)}
    if headers:
        response["headers"] = headers
    return {200: response}


def _resolve(document: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    """Follow ``$ref`` links to the schema with its own content."""
    while "$ref" in schema:
        schema = document["components"]["schemas"][schema["$ref"].removeprefix(_SCHEMA_REF)]
    return schema


def _carries_version(document: dict[str, Any], response: dict[str, Any]) -> bool:
    """Return whether a response's JSON body is a versioned resource."""
    schema = response.get("content", {}).get("application/json", {}).get("schema", {})
    return any(
        "version" in _resolve(document, option).get("properties", {}) for option in (schema, *schema.get("anyOf", []))
    )


def _is_readable_by_id(document: dict[str, Any], path: str) -> bool:
    """Return whether a ``GET`` reads a resource one segment below ``path``."""
    return any(
        re.fullmatch(re.escape(path) + r"/\{\w+\}", other) and "get" in item
        for other, item in document["paths"].items()
    )


def _declare_headers(document: dict[str, Any], path: str, method: str, operation: dict[str, Any]) -> None:
    """Declare the ``ETag`` and ``Location`` the operation's success responses send.

    Only a signed-in read or write of a versioned resource sends an ``ETag``: a public read has no ``If-Match``
    to feed, and an upload reports its parent's version without being the versioned resource.
    """
    if not operation.get("security") or _UPLOAD_EXTENSION in operation:
        return
    for code, response in operation["responses"].items():
        if code not in ("200", "201") or not _carries_version(document, response):
            continue
        response.setdefault("headers", {})["ETag"] = _ETAG_HEADER
        if code == "201" and method == "post" and _is_readable_by_id(document, path):
            response["headers"]["Location"] = _LOCATION_HEADER


def _declare_errors(operation: dict[str, Any], method: str, replays: bool) -> None:
    """Add the errors the operation can answer, keeping any a route declared itself.

    Args:
        operation: The operation, mutated in place.
        method: Its HTTP method.
        replays: Whether the route replays a stored response (:func:`replays_responses`), which only it can answer
            ``409`` in flight for.
    """
    parameters = operation.get("parameters", [])
    idempotent = any(
        parameter["in"] == "header" and parameter["name"] == _IDEMPOTENCY_HEADER for parameter in parameters
    )
    has_if_match = False
    codes = ["429", "503"]
    if operation.get("security"):
        codes += ["401", "403"]
    if any(parameter["in"] == "path" for parameter in parameters):
        codes.append("404")
    if "requestBody" in operation:
        codes.append("413")
    if _UPLOAD_EXTENSION in operation:
        codes.append("415")
    if method != "get":
        codes.append("409")
    for parameter in parameters:
        if parameter["in"] == "header" and parameter["name"] == core_etag.IF_MATCH_HEADER:
            parameter["required"] = True
            parameter["schema"] = {"type": "string"}
            codes += ["400", "412", "428"]
            has_if_match = True
    if idempotent:
        codes += [code for code in ("400", "422") if code not in codes]
    # A route that answers an error of its own (a sign-in's 401) gets that error's headers too.
    codes += [code for code in operation["responses"] if code in _ERRORS and code not in codes]
    for code in codes:
        description, headers = _ERRORS[code]
        if idempotent and code == "400" and not has_if_match:
            description = "The request is refused."
        response = operation["responses"].setdefault(code, {"description": description})
        if idempotent and code in _IDEMPOTENCY_NOTES and (replays or code != "409"):
            if response["description"] == _FRAMEWORK_VALIDATION_DESCRIPTION:
                response["description"] = _ERRORS[code][0]
            response["description"] = f"{response['description']} {_IDEMPOTENCY_NOTES[code]}"
            if code == "409":
                headers = {"Retry-After": _RETRY_AFTER_HEADER}
        if headers:
            response.setdefault("headers", headers)


def _mark_read_only(document: dict[str, Any]) -> None:
    """Mark the server-owned fields ``readOnly`` in every schema that no request body reaches."""
    schemas = document["components"]["schemas"]
    sent = {
        content["schema"]["$ref"].removeprefix(_SCHEMA_REF)
        for item in document["paths"].values()
        for operation in item.values()
        for content in operation.get("requestBody", {}).get("content", {}).values()
        if "$ref" in content.get("schema", {})
    }
    pending = list(sent)
    while pending:
        for name in re.findall(re.escape(_SCHEMA_REF) + r"(\w+)", str(schemas.get(pending.pop(), {}))):
            if name not in sent:
                sent.add(name)
                pending.append(name)
    for name, schema in schemas.items():
        if name in sent:
            continue
        for field, prop in schema.get("properties", {}).items():
            if field in _SERVER_OWNED_FIELDS:
                prop["readOnly"] = True


_REPLAYS_MARKER = "openapi_replays_response"


def replays_responses[F: Callable[..., Any]](dependency: F) -> F:
    """Mark a route dependency as one that answers a repeat of a request with a stored response.

    Only such a route can answer ``409`` for a request whose key is still being served, so the document derives that
    status (and its ``Retry-After``) for the routes that list the dependency, not for every route that reads the key.

    Args:
        dependency: The dependency function.

    Returns:
        The same function, marked.
    """
    setattr(dependency, _REPLAYS_MARKER, True)
    return dependency


def replaying_operations(routes: Iterable[BaseRoute]) -> frozenset[str]:
    """Return the operation ids of the routes that list a dependency marked with :func:`replays_responses`.

    Args:
        routes: The application's routes.

    Returns:
        The ids, as the OpenAPI document names the operations.
    """

    def marked(dependant: Dependant) -> bool:
        return any(getattr(dep.call, _REPLAYS_MARKER, False) or marked(dep) for dep in dependant.dependencies)

    return frozenset(
        route.operation_id or route.unique_id
        for route in routes
        if isinstance(route, APIRoute) and marked(route.dependant)
    )


def declare_contract(document: dict[str, Any], replaying: frozenset[str] = frozenset()) -> dict[str, Any]:
    """Declare in the OpenAPI document the errors, headers and read-only fields that follow from each operation.

    Args:
        document: The OpenAPI document, mutated in place.
        replaying: The operation ids of the routes that replay a stored response.

    Returns:
        The same document.
    """
    for path, item in document["paths"].items():
        for method in _METHODS:
            if method in item:
                _declare_errors(item[method], method, item[method].get("operationId") in replaying)
                _declare_headers(document, path, method, item[method])
    _mark_read_only(document)
    return document
