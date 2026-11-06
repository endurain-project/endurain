"""What the OpenAPI document states about errors, headers and server-owned fields, declared once.

FastAPI documents only what a route lists in ``responses=``, so left alone the document names 200 and 422 and a
client learns the rest by trying. The facts below follow from what an operation already declares, so they are
derived for every operation instead of repeated on each route:

- the default rate limit and an unavailable database answer 429 and 503 on every operation (``Retry-After``);
- a security requirement can answer 401 (``WWW-Authenticate``) and 403;
- a path parameter can answer 404, a request body 413, an upload (``x-max-body-bytes``) 415, and a write 409;
- ``If-Match`` is required, because its absence is refused with 428, and a stale or wildcard tag is 412 or 400;
- a success response carrying a ``version`` sends an ``ETag``, and a create that can be read by id a ``Location``;
- ``id``, ``version``, ``created_at`` and ``updated_at`` are ``readOnly`` in every schema a client does not send;
- an operation's description is its docstring up to the first Google section, so ``Args:``, ``Returns:`` and
  ``Raises:`` (which name the handler's own parameters) never reach a client.

A route lists in ``responses=`` only what the document cannot derive: ``core.location.ACCEPTED_RESPONSE`` and
``POLLED_STATUS_HEADERS``, :data:`ETAG_HEADERS` where the version is not a field of the body, and
:func:`binary_response`.
"""

import re
from typing import Any

import core.etag as core_etag

_METHODS = ("get", "post", "put", "patch", "delete")
_SCHEMA_REF = "#/components/schemas/"
_SERVER_OWNED_FIELDS = frozenset({"id", "version", "created_at", "updated_at"})
_UPLOAD_EXTENSION = "x-max-body-bytes"
#: A Google docstring section header. Matches what the architecture test refuses in a new route docstring.
_SECTION = re.compile(r"^\s*(Args|Arguments|Returns|Raises|Yields|Attributes|Notes?|Examples?):\s*$", re.M)

_ETAG_HEADER: dict[str, Any] = {
    "description": "The version of the resource, to send back as `If-Match` on the next write.",
    "schema": {"type": "string"},
}
#: The ``headers`` of a success response whose ``ETag`` the document cannot derive, for a route's ``responses``.
ETAG_HEADERS: dict[str, Any] = {"ETag": _ETAG_HEADER}
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
    "428": ("The `If-Match` header is missing.", {}),
    "429": ("The rate limit was reached.", {"Retry-After": _RETRY_AFTER_HEADER}),
    "503": ("A dependency is unavailable for a moment.", {"Retry-After": _RETRY_AFTER_HEADER}),
}


def binary_response(*media_types: str, description: str = "The file.") -> dict[int | str, dict[str, Any]]:
    """Build the ``responses`` entry of a route that sends bytes.

    Pair it with ``response_class=Response``: a route without a body class of its own would also declare an
    empty JSON body next to the media types.

    Args:
        *media_types: The media types the route sends.
        description: What the file is.

    Returns:
        The ``responses`` mapping to pass to the route.
    """
    schema = {"schema": {"type": "string", "format": "binary"}}
    return {200: {"description": description, "content": dict.fromkeys(media_types, schema)}}


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


def _declare_errors(operation: dict[str, Any], method: str) -> None:
    """Add the errors the operation can answer, keeping any a route declared itself."""
    parameters = operation.get("parameters", [])
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
    # A route that answers an error of its own (a sign-in's 401) gets that error's headers too.
    codes += [code for code in operation["responses"] if code in _ERRORS and code not in codes]
    for code in codes:
        description, headers = _ERRORS[code]
        response = operation["responses"].setdefault(code, {"description": description})
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


def _trim_description(operation: dict[str, Any]) -> None:
    """Cut an operation's description at the first docstring section, and drop it when nothing is left."""
    description = operation.get("description")
    if description is None:
        return
    section = _SECTION.search(description)
    trimmed = (description[: section.start()] if section else description).strip()
    if trimmed:
        operation["description"] = trimmed
    else:
        del operation["description"]


def declare_contract(document: dict[str, Any]) -> dict[str, Any]:
    """Declare in the OpenAPI document the errors, headers and read-only fields that follow from each operation.

    Args:
        document: The OpenAPI document, mutated in place.

    Returns:
        The same document.
    """
    for path, item in document["paths"].items():
        for method in _METHODS:
            if method in item:
                _trim_description(item[method])
                _declare_errors(item[method], method)
                _declare_headers(document, path, method, item[method])
    _mark_read_only(document)
    return document
