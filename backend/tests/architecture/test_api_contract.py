"""The HTTP API contract the generated OpenAPI document publishes, enforced.

``test_route_conventions.py`` reads the route source; these rules read what a client sees: the OpenAPI
document built the way ``scripts/export_openapi.py`` builds it, plus the handlers and request models behind it.
They keep the drift found by the 2026-11 API audit from coming back: an item that can be
edited but not read, a create that does not say where or at what version the record now is, a ``PUT`` that is a
patch, a response that is only a message, a request that sets server-owned fields, a naive timestamp, an
integer where a string enum belongs, endpoint docstrings that leak section headers into the public
description, errors that are not problem documents, and documentation that names a path that does not exist.

Every rule passes on today's code. Existing violations are recorded in the ``_...`` registers below. A debt
entry's value is the audit item that will clear it (``A1``, ``DOM-2``: the maintainers track those items); a
permanent entry's value is the reason. A register is shrink-only: a new violation fails the test, and so does
an entry that no longer violates, so the fix removes its own line. The rules themselves are stated in
``docs/developer-guide/http-api.md``.
"""

import ast
import datetime
import functools
import importlib.util
import pathlib
import re
import typing
from collections.abc import Iterator
from typing import Annotated, Any

from fastapi.routing import APIRoute
from pydantic import BaseModel, TypeAdapter, ValidationError
from tests._helpers.routes import route_decorators, router_functions

_APP = pathlib.Path("app")
_DOCS = pathlib.Path("..") / "docs"
_API_PREFIX = "/api/v1"
# Paths under the API root kept free for planned features, as docs/integrate/compatibility.md promises: no route may
# use them, and the docs may name them.
_RESERVED_PATHS: tuple[tuple[str, ...], ...] = (
    ("oauth",),
    ("auth", "webauthn"),
    ("profile", "passkeys"),
    ("profile", "grants"),
    ("oauth-clients",),
)
_METHODS = ("get", "post", "put", "patch", "delete")

# --- Registers (shrink-only) -------------------------------------------------------------------------------

#: Items with writes but no ``GET``, by design: revocations, relationships and file-served items. Permanent;
#: the value is the reason. Remove an entry when the item gains a ``GET``.
_NOT_READABLE_ITEMS: dict[str, str] = {
    "/activities/{activity_id}/media/{media_id}": "media is served as a file by the signed media route",
    "/profile/api-keys/{api_key_id}": "an API key is revoked, never read back after creation",
    "/profile/blocked-users/{user_id}": "a block is a relationship, read through the list",
    "/profile/follow-requests/{follower_id}": "a follow request is a relationship, read through the list",
    "/profile/sessions/{session_id}": "a session is revoked, read through the session list",
    "/users/{user_id}/followers/{follower_id}": "a follower link is a relationship, read through the lists",
}

#: A ``202`` that names no status resource, by design. Permanent; the value is the reason.
_NO_STATUS_RESOURCE: dict[str, str] = {
    "POST /profile/delete-account": "the account is closed before the answer, so its owner can no longer poll",
}

#: Optional properties of a ``PUT`` body whose omission is part of a full replacement, as
#: ``"PUT <route>: <field>"``. Permanent; the value says what omitting the field means: a write-only secret the
#: server never returns is kept, any other optional field is cleared.
_PUT_OPTIONAL_FIELDS: dict[str, str] = {
    "PUT /profile/goals/{goal_id}: goal_activities_number": "cleared when omitted; a goal type uses one target",
    "PUT /profile/goals/{goal_id}: goal_calories": "cleared when omitted; a goal type uses one target",
    "PUT /profile/goals/{goal_id}: goal_distance": "cleared when omitted; a goal type uses one target",
    "PUT /profile/goals/{goal_id}: goal_duration": "cleared when omitted; a goal type uses one target",
    "PUT /profile/goals/{goal_id}: goal_elevation": "cleared when omitted; a goal type uses one target",
    "PUT /server-settings: geocoding_api_key": "write-only secret, kept when omitted",
    "PUT /server-settings: tileserver_api_key": "write-only secret, kept when omitted",
    "PUT /server-settings/email/settings: password": "write-only secret, kept when omitted",
}

#: Routes callable without signing in that live outside ``/auth`` and ``/public``, as ``"<METHOD> <route>"``.
#: Permanent; the value is the reason. Remove an entry when the route moves under ``/public``.
_UNAUTHENTICATED_OUTSIDE_PUBLIC: dict[str, str] = {
    "GET /about": "the version probe of a reverse proxy or client, kept at the API root",
    "GET /activities/{activity_id}/media/{media_id}/file": "a signed URL that an image tag follows, no header",
    "GET /activities/{activity_id}/thumbnail": "a signed URL that an image tag follows, no header",
    "GET /health": "the liveness probe of the container and the orchestrator, kept at the API root",
    "GET /users/{user_id}/photo": "a signed URL that an image tag follows, no header",
}


#: Route handlers whose docstring carries a Google section, as ``{path relative to app/: handlers}``. Move the
#: section's content into ``Field``/``Query`` descriptions or ``responses`` and lower the count (HTTP-10).
_DOCSTRING_SECTIONS: dict[str, int] = {
    "modules/activities/activity/router.py": 2,
    "modules/activities/activity_exercise_titles/public_router.py": 1,
    "modules/activities/activity_exercise_titles/router.py": 1,
    "modules/auth/account_security/api_keys_router.py": 1,
    "modules/auth/account_security/identity_links_router.py": 4,
    "modules/auth/account_security/mfa_router.py": 6,
    "modules/auth/account_security/sessions_router.py": 3,
    "modules/auth/authentication/public_router.py": 4,
    "modules/auth/authentication/sso_public_router.py": 1,
    "modules/auth/identity_providers/public_router.py": 4,
    "modules/auth/identity_providers/router.py": 7,
    "modules/auth/sessions/router.py": 3,
    "modules/health/health_dashboard/router.py": 1,
    "modules/health/health_fasting/router.py": 8,
    "modules/health/health_poop/router.py": 6,
    "modules/health/health_sleep/router.py": 6,
    "modules/health/health_steps/router.py": 5,
    "modules/health/health_targets/router.py": 2,
    "modules/health/health_water/router.py": 5,
    "modules/health/health_weight/router.py": 5,
    "modules/notifications/router.py": 2,
    "modules/server_settings/logs_router.py": 4,
    "modules/server_settings/public_router.py": 3,
    "modules/server_settings/router.py": 8,
    "modules/strava/router.py": 1,
    "modules/users/users/photo_router.py": 1,
    "modules/users/users/router.py": 11,
    "modules/users/users_default_gear/router.py": 2,
    "modules/users/users_goals/router.py": 5,
    "modules/users/users_profile/router.py": 15,
    "modules/websocket/router.py": 1,
}


# --- The OpenAPI document and its handlers -----------------------------------------------------------------


@functools.cache
def _openapi() -> dict[str, Any]:
    """Return the OpenAPI document ``scripts/export_openapi.py`` builds, built once per run."""
    spec = importlib.util.spec_from_file_location("export_openapi", pathlib.Path("scripts") / "export_openapi.py")
    assert spec is not None and spec.loader is not None
    export_openapi = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(export_openapi)
    return export_openapi.build_openapi()


def _short(path: str) -> str:
    """Return an OpenAPI path without the ``/api/v1`` prefix."""
    return path.removeprefix(_API_PREFIX)


def _paths() -> dict[str, dict[str, Any]]:
    """Return the OpenAPI paths keyed without the ``/api/v1`` prefix."""
    return {_short(path): item for path, item in _openapi()["paths"].items()}


def _schemas() -> dict[str, Any]:
    """Return ``components.schemas``."""
    return _openapi()["components"]["schemas"]


def _resolve(schema: dict[str, Any]) -> dict[str, Any]:
    """Follow ``$ref`` links until a schema with its own content."""
    while "$ref" in schema:
        schema = _schemas()[schema["$ref"].rsplit("/", 1)[-1]]
    return schema


def _ref_name(schema: dict[str, Any]) -> str:
    """Return the component name a schema refers to, or ``"<inline>"``."""
    return schema["$ref"].rsplit("/", 1)[-1] if "$ref" in schema else "<inline>"


def _operations() -> Iterator[tuple[str, str, dict[str, Any]]]:
    """Yield ``(method, path without prefix, operation)`` for every operation."""
    for path, item in _paths().items():
        for method in _METHODS:
            if method in item:
                yield method, path, item[method]


def _request_schemas() -> Iterator[tuple[str, str, str, dict[str, Any]]]:
    """Yield ``(method, path, schema name, resolved schema)`` for each request body (JSON and form)."""
    for method, path, operation in _operations():
        for content in operation.get("requestBody", {}).get("content", {}).values():
            yield method, path, _ref_name(content["schema"]), _resolve(content["schema"])


@functools.cache
def _handlers() -> dict[tuple[str, str], tuple[pathlib.Path, ast.FunctionDef]]:
    """Map ``(method, path without prefix)`` to the route handler source, as the operation id names it.

    An operation id is its handler's function name, so a handler is matched to the operation that carries its
    name and method.
    """
    operation_ids = {operation["operationId"]: (method, path) for method, path, operation in _operations()}
    found: dict[tuple[str, str], tuple[pathlib.Path, ast.FunctionDef]] = {}
    for file, function in router_functions():
        for method, _call in route_decorators(function):
            operation = operation_ids.get(function.name)
            if operation is not None and operation[0] == method:
                found[operation] = (file, function)
    return found


def _calls(function: ast.FunctionDef) -> set[str]:
    """Return the names a function calls (``set_etag`` for both ``set_etag(...)`` and ``mod.set_etag(...)``)."""
    names: set[str] = set()
    for node in ast.walk(function):
        if isinstance(node, ast.Call):
            func = node.func
            names.add(func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else "")
    return names


def _described(parameter: dict[str, Any] | None) -> bool:
    """Return whether a header parameter is declared with a description."""
    return parameter is not None and bool(parameter.get("description"))


def _compare(kind: str, actual: set[str], register: dict[str, Any], fix: str) -> None:
    """Fail with every violation not in ``register`` and every ``register`` entry that no longer violates."""
    new = sorted(actual - register.keys())
    stale = sorted(register.keys() - actual)
    problems = []
    if new:
        problems.append(f"{kind}. {fix}:\n  " + "\n  ".join(new))
    if stale:
        problems.append("Remove from the register, they no longer violate:\n  " + "\n  ".join(stale))
    assert not problems, "\n".join(problems)


# --- The rules ----------------------------------------------------------------------------------------------


class TestApiContract:
    def test_an_item_with_writes_has_a_get(self):
        """A path ending in an ``{..._id}`` parameter that accepts ``PUT``, ``PATCH`` or ``DELETE`` also has ``GET``.

        A client that can edit or delete a record but cannot read it by id has to fetch a whole list to
        learn its current state and version. Revocations and relationships are the listed exceptions.
        """
        writable = {
            path
            for path, item in _paths().items()
            if re.fullmatch(r"\{\w+_id\}", path.rsplit("/", 1)[-1]) and {"put", "patch", "delete"} & item.keys()
        }
        unreadable = {path for path in writable if "get" not in _paths()[path]}

        _compare(
            "An item with PUT/PATCH/DELETE has no GET",
            unreadable,
            _NOT_READABLE_ITEMS,
            "Add a GET by id",
        )

    def test_a_route_without_authentication_lives_under_auth_or_public(self):
        """A route that needs no credential is under ``/auth`` (sessions) or ``/public``.

        ``/auth`` holds the routes that obtain, renew or end a session; every other route a client may call
        without signing in is under ``/public``, so a client and a proxy tell the two apart by the path.
        """
        unauthenticated = {
            f"{method.upper()} {path}"
            for method, path, operation in _operations()
            if not operation.get("security") and not path.startswith(("/auth/", "/public/"))
        }

        _compare(
            "A route callable without signing in is outside /auth and /public",
            unauthenticated,
            _UNAUTHENTICATED_OUTSIDE_PUBLIC,
            "Mount it under /public",
        )

    def test_a_write_without_a_session_is_csrf_exempt(self):
        """A state-changing route a client calls before it has a session needs no ``X-CSRF-Token``.

        A web client holds a CSRF token only once it has a session, so the CSRF middleware must not refuse a route
        that needs no credential.
        """
        import core.middleware as core_middleware

        refused = {
            f"{method.upper()} {path}"
            for method, path, operation in _operations()
            if method != "get"
            and not operation.get("security")
            and not core_middleware.CSRFMiddleware.is_exempt(_API_PREFIX + path)
        }

        _compare(
            "A write that needs no credential is refused without a CSRF token",
            refused,
            {},
            "Exempt it in CSRFMiddleware",
        )

    def test_the_session_routes_live_under_auth(self):
        """The routes that obtain, renew or end a session are under ``/auth``, and the old paths are gone."""
        routes = {f"{method.upper()} {path}" for method, path, _ in _operations()}

        assert {
            "POST /auth/login",
            "POST /auth/mfa/verify",
            "POST /auth/password-change",
            "POST /auth/sessions/{session_id}/tokens",
            "POST /auth/refresh",
            "POST /auth/logout",
        } <= routes
        assert not {route for route in routes if "/public/idp/session/" in route}

    def test_sign_up_and_password_reset_live_under_public(self):
        """Sign-up and password reset are public routes, so they sit under ``/public``."""
        routes = {f"{method.upper()} {path}" for method, path, _ in _operations()}

        assert {
            f"POST /public/{area}/{action}"
            for area, actions in (
                ("sign-up", ("request", "confirm", "resend")),
                ("password-reset", ("request", "confirm", "validate")),
            )
            for action in actions
        } <= routes
        assert not {route for route in routes if route.split(" ")[1].startswith(("/sign-up/", "/password-reset/"))}

    def test_a_create_sends_location_and_etag(self):
        """A ``POST`` answering 201 sets ``Location`` where the item has a ``GET``, and ``ETag`` when versioned.

        ``Location`` names where the new record is read and ``ETag`` is the version the client sends back as
        ``If-Match`` on its first edit, so the client needs no second request to learn either. OpenAPI does not
        declare ``Location``, so the handler's calls are read: it must call ``set_location`` or ``set_etag``.
        A resource is readable when ``GET <path>/{x_id}`` exists and versioned when its response schema has an
        ``id`` and a ``version`` (an upload that only reports its parent's version is not a created resource).
        """
        paths = _paths()
        missing: set[str] = set()
        for method, path, operation in _operations():
            if method != "post" or "201" not in operation["responses"]:
                continue
            readable = any(
                other.startswith(path + "/{") and other.count("/") == path.count("/") + 1 and "get" in item
                for other, item in paths.items()
            )
            body = operation["responses"]["201"].get("content", {}).get("application/json", {}).get("schema", {})
            versioned = {"id", "version"} <= _resolve(body).get("properties", {}).keys()
            _, function = _handlers()[(method, path)]
            calls = _calls(function)
            missing |= {
                f"{function.name}: {header}"
                for header, call, needed in (
                    ("Location", "set_location", readable),
                    ("ETag", "set_etag", versioned),
                )
                if needed and call not in calls
            }

        _compare("A create does not send its headers", missing, {}, "Call set_location and set_etag")

    def test_a_202_declares_where_to_poll_and_when(self):
        """Every ``202`` declares ``Content-Location`` and ``Retry-After`` in OpenAPI, and sets them.

        The ``202`` answers only "queued"; the headers say which resource reports the outcome and when to look.
        The handler must call ``set_status_location``, or ``set_job_location`` / ``_set_sync_location``, which
        wrap it.
        """
        undeclared: set[str] = set()
        unset: set[str] = set()
        accepted: set[str] = set()
        for method, path, operation in _operations():
            if "202" not in operation["responses"]:
                continue
            route = f"{method.upper()} {path}"
            accepted.add(route)
            headers = operation["responses"]["202"].get("headers", {})
            if not {"Content-Location", "Retry-After"} <= headers.keys():
                undeclared.add(route)
            _, function = _handlers()[(method, path)]
            if not {"set_status_location", "set_job_location", "_set_sync_location"} & _calls(function):
                unset.add(route)

        _compare("A 202 does not declare where to poll", undeclared, _NO_STATUS_RESOURCE, "Add ACCEPTED_RESPONSE")
        _compare("A 202 does not set where to poll", unset, _NO_STATUS_RESOURCE, "Call set_status_location")
        stale = sorted(_NO_STATUS_RESOURCE.keys() - accepted)
        assert not stale, "Remove from _NO_STATUS_RESOURCE, the route no longer answers 202:\n  " + "\n  ".join(stale)

    def test_a_job_status_is_the_job_envelope(self):
        """Every ``202`` body and every polled status read has the shared job fields, and a poll can answer ``null``.

        A client reads one ``status`` vocabulary, one ``error_code`` and the same ids and timestamps whatever the
        job is (``core.job_status.JobStatus``). A status read that finds nothing recorded answers ``200`` with
        ``null``, so its schema is nullable; a job that has an id of its own is read by it and is ``404`` when unknown.
        """
        envelope = {"id", "status", "error_code", "created_at", "finished_at"}
        states = {"queued", "running", "succeeded", "failed"}
        broken: set[str] = set()
        for method, path, operation in _operations():
            for code in ("200", "202"):
                response = operation["responses"].get(code, {})
                polled = code == "200" and "Retry-After" in response.get("headers", {})
                if code == "202" and "Content-Location" not in response.get("headers", {}):
                    continue
                if code == "200" and not polled:
                    continue
                schema = response["content"]["application/json"]["schema"]
                options = [option for option in schema.get("anyOf", [schema]) if option.get("type") != "null"]
                if polled and "{job_id}" not in path and len(options) == len(schema.get("anyOf", [schema])):
                    broken.add(f"{method.upper()} {path}: a polled status read must be nullable")
                for option in options:
                    properties = _resolve(option).get("properties", {})
                    status = _resolve(properties["status"]) if "status" in properties else {}
                    if not envelope <= properties.keys() or set(status.get("enum", [])) != states:
                        broken.add(f"{method.upper()} {path}: {code} is not a JobStatus")

        assert not broken, "Extend core.job_status.JobStatus:\n  " + "\n  ".join(sorted(broken))

    def test_a_put_replaces_the_whole_resource(self):
        """Every optional property of a ``PUT`` body is listed with what omitting it means.

        ``PUT`` means "this is what the resource looks like now", so an omitted field is cleared; only a
        write-only secret may be kept when omitted. The schema cannot show which a service does, so each
        optional field is reviewed into ``_PUT_OPTIONAL_FIELDS``.
        """
        partial: set[str] = set()
        secrets: set[str] = set()
        for method, path, operation in _operations():
            content = operation.get("requestBody", {}).get("content", {}).get("application/json")
            if method != "put" or content is None:
                continue
            schema = _resolve(content["schema"])
            optional = set(schema.get("properties", {})) - set(schema.get("required", []))
            allowed = {field for field in optional if f"PUT {path}: {field}" in _PUT_OPTIONAL_FIELDS}
            secrets |= {f"PUT {path}: {field}" for field in allowed}
            if optional - allowed:
                partial.add(f"PUT {path}")

        assert not partial, (
            "A PUT body has optional properties nobody reviewed. Clear the field when omitted and list it in "
            "_PUT_OPTIONAL_FIELDS, or make the route a PATCH:\n  " + "\n  ".join(sorted(partial))
        )
        stale = sorted(_PUT_OPTIONAL_FIELDS.keys() - secrets)
        assert not stale, "Remove from _PUT_OPTIONAL_FIELDS, the field is no longer optional:\n  " + "\n  ".join(stale)

    def test_no_success_body_only_carries_a_message(self):
        """No 2xx JSON response is an object whose properties are only ``message`` and ``detail``.

        A bare message cannot be told apart from an error and states no state of the resource; the response
        is the resource, or a 204 when nothing changed shape.
        """
        message_only: set[str] = set()
        for _, _, operation in _operations():
            for code, response in operation["responses"].items():
                schema = response.get("content", {}).get("application/json", {}).get("schema")
                if not code.startswith("2") or schema is None:
                    continue
                properties = set(_resolve(schema).get("properties", {}))
                if properties and properties <= {"message", "detail"}:
                    message_only.add(_ref_name(schema))

        assert not message_only, (
            "A success body only carries a message. Return the resource or a 204:\n  "
            + "\n  ".join(sorted(message_only))
        )

    def test_request_bodies_accept_no_server_owned_fields(self):
        """No request body property is ``id``, ``user_id``, ``version``, a timestamp, ``source`` or a provider id.

        The server assigns identity, ownership, versions, timestamps, the origin of a record and provider ids;
        a client-settable one lets a caller forge them or sends a value the server then ignores.
        """
        owned = re.compile(r"id|user_id|version|created_at|updated_at|source|(strava|garminconnect)_\w*_id")
        found = {
            f"{name}.{field}"
            for _, _, name, schema in _request_schemas()
            for field in schema.get("properties", {})
            if owned.fullmatch(field)
        }

        _compare("A request body accepts a server-owned field", found, {}, "Drop the field")

    def test_step_up_credentials_travel_in_one_object(self):
        """No schema but ``StepUpVerification`` has a ``current_password`` or ``idp_reauth`` property.

        A request that needs a step-up nests it in a ``step_up`` object, so a client builds it one way.
        """
        found = {
            f"{name}: {field}"
            for name, schema in _schemas().items()
            if name != "StepUpVerification"
            for field in ("current_password", "idp_reauth")
            if field in schema.get("properties", {})
        }
        _compare(
            "A schema carries step-up credentials outside StepUpVerification",
            found,
            {},
            "Nest them in a step_up object",
        )

    def test_request_datetimes_require_an_offset(self):
        """A datetime field of a request body model is ``pydantic.AwareDatetime`` or otherwise rejects a naive value.

        OpenAPI cannot tell ``datetime`` from ``AwareDatetime``, so the models are read: each field is
        validated with a naive timestamp. A naive one is read in a guessed zone and stored as another instant.
        A deliberate wall clock is named ``*_local`` and its description says it is a wall-clock time.
        """
        models: dict[str, type[BaseModel]] = {}
        for route in _api_routes():
            for body in route.dependant.body_params:
                for candidate in (body.field_info.annotation, *typing.get_args(body.field_info.annotation)):
                    if isinstance(candidate, type) and issubclass(candidate, BaseModel):
                        models[candidate.__name__] = candidate

        naive: set[str] = set()
        undocumented: set[str] = set()
        for name, model in models.items():
            for field, info in model.model_fields.items():
                kinds = [kind for kind in _unwrap(info.annotation) if kind is datetime.datetime]
                if kinds and field.endswith("_local"):
                    if "wall-clock" not in (info.description or "").lower():
                        undocumented.add(f"{name}.{field}")
                    continue
                if not kinds:
                    continue
                annotation = Annotated[info.annotation, *info.metadata] if info.metadata else info.annotation
                adapter = TypeAdapter(annotation)
                try:
                    adapter.validate_python("2024-01-01T10:00:00")
                except ValidationError:
                    continue
                naive.add(f"{name}.{field}")

        assert not naive, (
            f"A request datetime accepts a naive value (use AwareDatetime, or name a wall clock *_local): {sorted(naive)}"
        )
        assert not undocumented, f"A *_local datetime does not say it is a wall-clock time: {sorted(undocumented)}"

    def test_list_filters_follow_one_vocabulary(self):
        """A text filter is ``<field>_contains`` and a state filter is ``active=<bool>``.

        ``name``, ``search`` and ``term`` do not say what they match, and a ``show_*`` flag reads the opposite
        way from ``active``.
        """
        found: set[str] = set()
        for method, path, operation in _operations():
            if method != "get":
                continue
            for parameter in operation.get("parameters", []):
                name = parameter["name"]
                if parameter["in"] == "query" and (name.startswith("show_") or name in {"name", "search", "term", "q"}):
                    found.add(f"GET {path}: {name}")

        assert not found, f"A list filter breaks the vocabulary. Use <field>_contains or active: {sorted(found)}"

    def test_enums_are_strings(self):
        """Enumerated values are strings and ``is_*``/``has_*`` properties are booleans.

        An integer code (``type: 3``) says nothing to a reader of the response or the generated client and
        cannot gain a value without renumbering; a flag that is an integer invites ``0``/``1``/``2`` states.
        """
        integer_names = {"type", "visibility", "status", "kind"}
        found: set[str] = set()
        for name, schema in _schemas().items():
            if name == "ProblemDetail":
                # RFC 9457 defines ``status`` as the HTTP status code, an integer.
                continue
            if "enum" in schema and schema.get("type") == "integer":
                found.add(f"{name}.<enum>")
            for field, prop in schema.get("properties", {}).items():
                types = {prop.get("type"), *(option.get("type") for option in prop.get("anyOf", []))} - {None}
                if "integer" in types and (field in integer_names or field.endswith("_type")):
                    found.add(f"{name}.{field}")
                if re.match(r"(is|has)_", field) and "boolean" not in types:
                    found.add(f"{name}.{field}")

        _compare("A schema types a value as an integer", found, {}, "Use a string enum or a boolean")

    def test_endpoint_docstrings_carry_no_sections(self):
        """A route handler's docstring has no ``Args:``, ``Returns:``, ``Raises:`` or similar section.

        FastAPI publishes the docstring as the operation's description, so a section header lands verbatim in
        the API reference and the generated client; parameters are described with ``Field``/``Query``.
        """
        section = re.compile(r"^\s*(Args|Arguments|Returns|Raises|Yields|Attributes|Notes?|Examples?):\s*$", re.M)
        counts: dict[str, int] = {}
        for file, function in router_functions():
            if section.search(ast.get_docstring(function) or ""):
                key = file.relative_to(_APP).as_posix()
                counts[key] = counts.get(key, 0) + 1

        mismatches = [
            f"{name}: {counts.get(name, 0)} handler(s), registered {_DOCSTRING_SECTIONS.get(name, 0)}"
            for name in sorted(counts.keys() | _DOCSTRING_SECTIONS.keys())
            if counts.get(name, 0) != _DOCSTRING_SECTIONS.get(name, 0)
        ]
        assert not mismatches, (
            "A route docstring is the public description: drop its Google sections, and lower the count in "
            "_DOCSTRING_SECTIONS:\n  " + "\n  ".join(mismatches)
        )

    def test_if_match_is_required_and_its_failures_documented(self):
        """An operation that takes ``If-Match`` declares it required and documents 400, 412 and 428.

        A write without the header is refused with 428, so a client generated from the document must be made
        to send it; 412 is a stale tag and 400 the wildcard.
        """
        problems: set[str] = set()
        for method, path, operation in _operations():
            headers = [p for p in operation.get("parameters", []) if p["in"] == "header" and p["name"] == "If-Match"]
            if not headers:
                continue
            route = f"{method.upper()} {path}"
            if not headers[0].get("required"):
                problems.add(f"{route}: If-Match is not required")
            problems |= {f"{route}: no {code}" for code in ("400", "412", "428") if code not in operation["responses"]}

        _compare("An If-Match operation is not fully declared", problems, {}, "Declare it in core.openapi_contract")

    def test_a_header_a_handler_sets_is_declared(self):
        """An operation whose handler sets ``Location``, ``ETag``, ``Retry-After`` or ``no-store`` declares it.

        OpenAPI is the only description a generated client reads; a header it does not list is invisible to it.
        ``Location`` belongs to the ``201``, ``ETag`` to the success response that carries the version and
        ``Retry-After`` to the polled status read; a response that carries a token or a secret declares
        ``Cache-Control`` and ``Pragma`` (``core.openapi_contract.NO_STORE_RESPONSE_HEADERS``).
        """
        undeclared: set[str] = set()
        for (method, path), (_, function) in _handlers().items():
            calls = _calls(function)
            success = {
                code: response for code, response in _paths()[path][method]["responses"].items() if code.startswith("2")
            }
            declared = {name for response in success.values() for name in response.get("headers", {})}
            if "set_location" in calls and "Location" not in success.get("201", {}).get("headers", {}):
                undeclared.add(f"{method.upper()} {path}: Location on 201")
            if "set_etag" in calls and "ETag" not in declared:
                undeclared.add(f"{method.upper()} {path}: ETag")
            if "ETag" in declared and "set_etag" not in calls:
                undeclared.add(f"{method.upper()} {path}: ETag declared but not sent")
            if "set_retry_after_while_running" in calls and "Retry-After" not in declared:
                undeclared.add(f"{method.upper()} {path}: Retry-After")
            sends_no_store = calls & {"set_no_store", "deliver_auth_outcome"} or "NO_STORE_HEADERS" in {
                node.attr for node in ast.walk(function) if isinstance(node, ast.Attribute)
            }
            if sends_no_store and not {"Cache-Control", "Pragma"} <= declared:
                undeclared.add(f"{method.upper()} {path}: Cache-Control and Pragma")

        _compare("A header the handler sets is not declared", undeclared, {}, "Declare it in core.openapi_contract")

    def test_every_operation_documents_the_errors_it_can_answer(self):
        """The error statuses an operation can answer are documented, from what the operation declares.

        Authentication answers 401 and 403, a path parameter a 404, a body a 413, an upload a 415, a write a
        409, and the default rate limit and an unavailable database 429 and 503 for every operation.
        """
        missing: set[str] = set()
        for method, path, operation in _operations():
            wanted = {"429", "503"}
            if operation.get("security"):
                wanted |= {"401", "403"}
            if any(p["in"] == "path" for p in operation.get("parameters", [])):
                wanted.add("404")
            if "requestBody" in operation:
                wanted.add("413")
            if "x-max-body-bytes" in operation:
                wanted.add("415")
            if method != "get":
                wanted.add("409")
            missing |= {f"{method.upper()} {path}: {code}" for code in wanted - operation["responses"].keys()}

        _compare("An operation does not document an error", missing, {}, "Derive it in core.openapi_contract")

    def test_security_requirements_name_only_the_schemes_an_operation_accepts(self):
        """Each operation lists its credentials, and request headers and the ``api_key`` query are not among them."""
        document = _openapi()
        assert set(document["components"]["securitySchemes"]) == {
            "HTTPBearer",
            "ApiKey",
            "RefreshTokenCookie",
        }
        cookie_routes = {"POST /auth/refresh", "POST /auth/logout"}
        wrong: set[str] = set()
        for method, path, operation in _operations():
            schemes = {name for requirement in operation.get("security", []) for name in requirement}
            if ("RefreshTokenCookie" in schemes) != (f"{method.upper()} {path}" in cookie_routes):
                wrong.add(f"{method.upper()} {path}: the cookie scheme")
            if any(parameter["name"] == "api_key" for parameter in operation.get("parameters", [])):
                wrong.add(f"{method.upper()} {path}: advertises ?api_key=")

        _compare("An operation lists the wrong credentials", wrong, {}, "Fix the dependency that declares it")

    def test_the_bearer_scheme_is_http_bearer_and_lists_the_scope_catalogue(self):
        """The access token is a plain HTTP bearer JWT, not an OAuth2 flow, and its description names every scope."""
        import modules.auth.constants as auth_constants

        schemes = _openapi()["components"]["securitySchemes"]

        assert {name for name, scheme in schemes.items() if scheme["type"] == "oauth2"} == set()
        bearer = schemes["HTTPBearer"]
        assert (bearer["type"], bearer["scheme"], bearer["bearerFormat"]) == ("http", "bearer", "JWT")
        assert all(f"`{scope}`" in bearer["description"] for scope in auth_constants.SCOPE_DICT)

    def test_a_protected_route_lists_its_required_scopes_under_the_bearer_scheme(self):
        """A route that needs a scope names it in its ``HTTPBearer`` requirement."""
        operation = _openapi()["paths"][f"{_API_PREFIX}/profile/password/change"]["post"]

        assert {"HTTPBearer": ["profile:security"]} in operation["security"]

    def test_the_profile_scopes_split_by_what_a_route_changes(self):
        """Export and import need ``profile:export``; credentials, sessions and account closure ``profile:security``."""
        security = (
            "/profile/password/change",
            "/profile/email/change",
            "/profile/delete-account",
            "/profile/sessions",
            "/profile/mfa",
            "/profile/identity-providers",
            "/profile/api-keys",
        )
        wrong: set[str] = set()
        for method, path, operation in _operations():
            requirement = next((r["HTTPBearer"] for r in operation.get("security", []) if "HTTPBearer" in r), [])
            if path.startswith(("/profile/export", "/profile/import")):
                wanted = {"profile:export"}
            elif path.startswith(security):
                wanted = {"profile:security"}
            else:
                continue
            other = {"profile:export", "profile:security"} - wanted
            if not wanted <= set(requirement) or other & set(requirement):
                wrong.add(f"{method.upper()} {path}: requires {sorted(requirement)}, wanted {sorted(wanted)}")

        _compare("A profile route requires the wrong scope", wrong, {}, "Use profile:export or profile:security")

    def test_operation_ids_are_unique_handler_names(self):
        """An operation id is its handler's name, so it survives a route moving, and no two handlers share one."""
        ids: dict[str, list[str]] = {}
        for method, path, operation in _operations():
            ids.setdefault(operation["operationId"], []).append(f"{method.upper()} {path}")
        duplicated = {f"{name}: {', '.join(operations)}" for name, operations in ids.items() if len(operations) > 1}
        path_derived = {
            f"{method.upper()} {path}: {operation['operationId']}"
            for method, path, operation in _operations()
            if "api_v1" in operation["operationId"]
        }

        _compare("Two operations share an id", duplicated, {}, "Rename one handler")
        _compare("An operation id is derived from its path", path_derived, {}, "Name the operation by its handler")

    def test_error_headers_are_declared(self):
        """401 declares ``WWW-Authenticate`` and 429 and 503 declare ``Retry-After``."""
        wanted = {"401": "WWW-Authenticate", "429": "Retry-After", "503": "Retry-After"}
        missing = {
            f"{method.upper()} {path}: {header} on {code}"
            for method, path, operation in _operations()
            for code, header in wanted.items()
            if code in operation["responses"] and header not in operation["responses"][code].get("headers", {})
        }

        _compare("An error response does not declare its header", missing, {}, "Declare it in core.openapi_contract")

    def test_a_success_response_names_its_real_content(self):
        """No success response declares an empty JSON body: a binary route lists the media type it sends."""
        empty = {
            f"{method.upper()} {path}: {code}"
            for method, path, operation in _operations()
            for code, response in operation["responses"].items()
            if code.startswith("2") and response.get("content", {}).get("application/json", {}).get("schema") == {}
        }

        _compare(
            "A success response declares an empty JSON body", empty, {}, "Use core.openapi_contract.binary_response"
        )

    def test_the_document_has_servers_and_described_tags(self):
        """The document states its server and describes every tag an operation uses."""
        document = _openapi()
        used = {tag for _, _, operation in _operations() for tag in operation.get("tags", [])}
        described = {tag["name"] for tag in document.get("tags", []) if tag.get("description")}

        assert document.get("servers"), "the document declares no servers"
        assert not used - described, f"tags without a description: {sorted(used - described)}"

    def test_server_owned_response_fields_are_read_only(self):
        """``id``, ``version``, ``created_at`` and ``updated_at`` are ``readOnly`` in every non-request schema."""
        requests = {name for _, _, name, _ in _request_schemas()}
        pending = list(requests)
        while pending:
            for ref in re.findall(r"#/components/schemas/(\w+)", str(_schemas().get(pending.pop(), {}))):
                if ref not in requests:
                    requests.add(ref)
                    pending.append(ref)
        writable = {
            f"{name}.{field}"
            for name, schema in _schemas().items()
            if name not in requests
            for field, prop in schema.get("properties", {}).items()
            if field in {"id", "version", "created_at", "updated_at"} and not prop.get("readOnly")
        }

        _compare("A server-owned response field is not readOnly", writable, {}, "Mark it in core.openapi_contract")

    def test_the_headers_the_api_reads_are_declared_on_the_operations_that_read_them(self):
        """``X-Device-Id``, ``X-Client-Type`` and ``X-CSRF-Token`` are described on every operation that reads them.

        The device id is read by the sign-ins; the client type by the sign-ins and by the CSRF middleware, which
        needs the CSRF token from a web client on every write it does not exempt.
        """
        import core.middleware as core_middleware

        def headers(operation: dict[str, Any]) -> dict[str, dict[str, Any]]:
            return {item["name"]: item for item in operation.get("parameters", []) if item["in"] == "header"}

        device_routes = {
            ("post", "/auth/login"),
            ("post", "/auth/mfa/verify"),
            ("post", "/auth/password-change"),
            ("post", "/auth/sessions/{session_id}/tokens"),
        }
        wrong: set[str] = set()
        for method, path, operation in _operations():
            declared = headers(operation)
            if (method, path) in device_routes and not _described(declared.get("X-Device-Id")):
                wrong.add(f"{method.upper()} {path}: X-Device-Id")
            if core_middleware.CSRFMiddleware.enforces(method.upper(), f"{_API_PREFIX}{path}"):
                token, client_type = declared.get("X-CSRF-Token"), declared.get("X-Client-Type")
                if not _described(token) or token["required"]:
                    wrong.add(f"{method.upper()} {path}: X-CSRF-Token")
                if not _described(client_type) or set(_resolve(client_type["schema"]).get("enum", [])) != {
                    "web",
                    "mobile",
                }:
                    wrong.add(f"{method.upper()} {path}: X-Client-Type")
            elif method == "get" and "X-CSRF-Token" in declared:
                wrong.add(f"{method.upper()} {path}: X-CSRF-Token is not read")

        _compare("A header the API reads is not declared", wrong, {}, "Declare it in the OpenAPI document")

    def test_errors_are_problem_documents(self):
        """Outside ``core.exceptions`` and ``core.problem_details``, no 4xx/5xx is built with a response class.

        An error answered with ``JSONResponse(status_code=4xx)`` skips the RFC 9457 handlers, so a client
        meets a second error shape. Raise a ``core.exceptions`` error and let the handler build the document.
        """
        owners = {"core/exceptions.py", "core/problem_details.py"}
        found: set[str] = set()
        for path in sorted(_APP.rglob("*.py")):
            relative = path.relative_to(_APP).as_posix()
            if relative in owners or {"migrations", "alembic", "__pycache__"} & set(path.parts):
                continue
            for node in ast.walk(ast.parse(path.read_text())):
                if (
                    isinstance(node, ast.Call)
                    and _call_name(node) in {"JSONResponse", "Response", "ORJSONResponse"}
                    and _is_error_status(node)
                ):
                    found.add(relative)

        _compare("A file builds an error response by hand", found, {}, "Raise a core.exceptions error")

    def test_documented_api_paths_exist(self):
        """Every API path in backticks in the integration and reference docs and in route docstrings exists.

        A page that names a route that was renamed or never existed sends an integrator to a 404. Paths are
        compared segment by segment with ``{...}`` standing for any value, and a path that is a prefix of a
        route (a cookie scope, a group of routes) counts as existing; frontend routes are ignored by keeping
        only paths whose first segment belongs to the API.
        """
        known = [path.strip("/").split("/") for path in _paths()]
        first_segments = {segments[0] for segments in known}
        sources: dict[str, str] = {}
        for pattern in ("integrate/*.md", "reference/**/*.md"):
            for page in sorted(_DOCS.glob(pattern)):
                sources[page.relative_to(_DOCS).as_posix()] = page.read_text()
        for file, function in router_functions():
            sources[file.relative_to(_APP).as_posix()] = ast.get_docstring(function) or ""

        missing: set[str] = set()
        for name, text in sources.items():
            for span in re.findall(r"`([^`\n]+)`", text):
                match = re.fullmatch(r"(?:(?:GET|POST|PUT|PATCH|DELETE)\s+)?(/[^\s?#]*)(?:\?\S*)?", span.strip())
                if match is None:
                    continue
                segments = match.group(1).removeprefix(_API_PREFIX).split("?")[0].strip("/").split("/")
                if segments[0] not in first_segments or _is_reserved(segments):
                    continue
                if not any(_same_path(segments, other[: len(segments)]) for other in known):
                    missing.add(f"{name}: /{'/'.join(segments)}")

        _compare("A documented path is not in the API", missing, {}, "Fix the page or the route")

    def test_no_route_uses_a_reserved_path(self):
        """No route lives under a path reserved for a planned feature, so adding that feature stays additive."""
        found = {f"/{path.strip('/')}" for path in _paths() if _is_reserved(path.strip("/").split("/"))}

        _compare("A route uses a reserved path", found, {}, "Move the route out of the reserved path")


# --- Helpers for the rules ------------------------------------------------------------------------------------


def _is_reserved(segments: list[str]) -> bool:
    """Return whether a path, as segments under the API root, is or lies under a reserved path."""
    return any(tuple(segments[: len(reserved)]) == reserved for reserved in _RESERVED_PATHS)


def _same_path(left: list[str], right: list[str]) -> bool:
    """Return whether two paths have the same segments, a ``{...}`` segment matching any value."""
    return len(left) == len(right) and all(
        a == b or (a.startswith("{") and a.endswith("}")) or (b.startswith("{") and b.endswith("}"))
        for a, b in zip(left, right, strict=True)
    )


def _api_routes() -> Iterator[APIRoute]:
    """Yield every ``APIRoute`` of the API router, walking the lazily included routers."""
    import api

    pending = [api.router]
    while pending:
        router = pending.pop()
        for route in router.routes:
            if isinstance(route, APIRoute):
                yield route
            elif hasattr(route, "original_router"):
                pending.append(route.original_router)


def _unwrap(annotation: Any) -> Iterator[Any]:
    """Yield the leaf types of an annotation: through ``Optional``, unions, ``Annotated`` and generics."""
    arguments = typing.get_args(annotation)
    if not arguments:
        yield annotation
        return
    for argument in arguments:
        yield from _unwrap(argument)


def _call_name(call: ast.Call) -> str:
    """Return the called name of ``f(...)`` or ``module.f(...)``."""
    func = call.func
    return func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""


def _is_error_status(call: ast.Call) -> bool:
    """Return whether a response call passes a 4xx/5xx ``status_code`` (keyword or second positional)."""
    candidates = [keyword.value for keyword in call.keywords if keyword.arg == "status_code"]
    candidates += call.args[1:2]
    for value in candidates:
        if isinstance(value, ast.Constant) and isinstance(value.value, int) and value.value >= 400:
            return True
        if isinstance(value, ast.Attribute) and re.fullmatch(r"HTTP_[45]\d\d_\w+", value.attr):
            return True
    return False
