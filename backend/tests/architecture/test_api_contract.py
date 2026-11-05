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
_METHODS = ("get", "post", "put", "patch", "delete")

# --- Registers (shrink-only) -------------------------------------------------------------------------------

#: Items with writes but no ``GET``, by design: revocations, relationships and file-served items. Permanent;
#: the value is the reason. Remove an entry when the item gains a ``GET``.
_NOT_READABLE_ITEMS: dict[str, str] = {
    "/activities/{activity_id}/media/{media_id}": "media is served as a file by the signed media route",
    "/followers/follow-requests/{follower_id}": "a follow request is a relationship, read through the lists",
    "/profile/api-keys/{api_key_id}": "an API key is revoked, never read back after creation",
    "/profile/sessions/{session_id}": "a session is revoked, read through the session list",
    "/users/{user_id}/followers/{follower_id}": "a follower link is a relationship, read through the lists",
    "/users/{user_id}/identity-providers/{idp_id}": "an identity link is removed, read through the link list",
    "/users/{user_id}/sessions/{session_id}": "a session is revoked, read through the session list",
}

#: Items with writes but no ``GET`` that should have one. Remove an entry when A1 adds the read.
_MISSING_ITEM_GET: dict[str, str] = {
    "/gear-components/{gear_component_id}": "A1",
    "/health/sleep/{health_sleep_id}": "A1",
    "/health/steps/{health_steps_id}": "A1",
    "/health/water/{health_water_id}": "A1",
    "/health/weight/{health_weight_id}": "A1",
    "/identity-providers/{idp_id}": "A1",
    "/profile/goals/{goal_id}": "A1",
}

#: Creates of a readable resource that do not send a header, as ``"<handler>: <Header>"``. Remove an entry when
#: the create sends the header (A2 for ``Location``, A3 for ``ETag``).
_CREATE_WITHOUT_HEADER: dict[str, str] = {
    "create_gear: ETag": "A3",
    "create_health_fasting: ETag": "A3",
    "create_health_poop: ETag": "A3",
    "create_user: ETag": "A3",
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

#: ``PUT`` routes whose body has optional properties that are kept when omitted, which makes the route a patch,
#: as ``"PUT <route>"``. Remove an entry when B1 turns the route into a ``PATCH``.
_PARTIAL_PUTS: dict[str, str] = {
    "PUT /identity-providers/{idp_id}": "B1",
    "PUT /users/{user_id}": "B1",
}

#: Response schemas that carry only a message, by schema name. Remove an entry when B2 gives the route a
#: representation (or a 204).
_MESSAGE_ONLY_RESPONSES: dict[str, str] = {
    "LogoutRead": "B2",
    "MFADisableRead": "B2",
    "MFAVerifyRead": "B2",
    "PasswordResetRead": "B2",
    "StravaDetail": "B2",
}

#: Request-body properties the server owns, as ``"<schema>.<field>"``. Remove an entry when the audit item
#: drops the field from the request schema (DOM-2 and DOM-17).
_SERVER_OWNED_REQUEST_FIELDS: dict[str, str] = {
    "GearCreateRequest.created_at": "DOM-17",
    "GearUpdate.created_at": "DOM-17",
    "HealthFastingCreate.source": "DOM-2",
    "HealthFastingUpdate.source": "DOM-2",
    "HealthPoopCreate.source": "DOM-2",
    "HealthPoopUpdate.source": "DOM-2",
    "HealthSleepCreate.garminconnect_sleep_id": "DOM-2",
    "HealthSleepCreate.source": "DOM-2",
    "HealthSleepUpdate.garminconnect_sleep_id": "DOM-2",
    "HealthSleepUpdate.source": "DOM-2",
    "HealthStepsCreate.source": "DOM-2",
    "HealthStepsUpdate.source": "DOM-2",
    "HealthWaterCreate.source": "DOM-2",
    "HealthWaterUpdate.source": "DOM-2",
    "HealthWeightCreate.source": "DOM-2",
    "HealthWeightUpdate.source": "DOM-2",
}

#: Request datetime fields that accept a naive value, as ``"<model>.<field>"``. Remove an entry when the field
#: becomes ``pydantic.AwareDatetime`` (DOM-3).
_NAIVE_REQUEST_DATETIMES: dict[str, str] = {
    "GearCreateRequest.created_at": "DOM-3",
    "GearUpdate.created_at": "DOM-3",
    "HealthFastingComplete.fast_end_time": "DOM-3",
    "HealthFastingCreate.fast_end_time": "DOM-3",
    "HealthFastingCreate.fast_start_time": "DOM-3",
    "HealthFastingUpdate.fast_end_time": "DOM-3",
    "HealthFastingUpdate.fast_start_time": "DOM-3",
    "HealthPoopCreate.date_time": "DOM-3",
    "HealthPoopUpdate.date_time": "DOM-3",
    "HealthSleepCreate.sleep_end_time_gmt": "DOM-3",
    "HealthSleepCreate.sleep_end_time_local": "DOM-3",
    "HealthSleepCreate.sleep_start_time_gmt": "DOM-3",
    "HealthSleepCreate.sleep_start_time_local": "DOM-3",
    "HealthSleepUpdate.sleep_end_time_gmt": "DOM-3",
    "HealthSleepUpdate.sleep_end_time_local": "DOM-3",
    "HealthSleepUpdate.sleep_start_time_gmt": "DOM-3",
    "HealthSleepUpdate.sleep_start_time_local": "DOM-3",
    "UsersApiKeyCreate.expires_at": "DOM-3",
}

#: Schema properties typed as an integer or boolean where the contract wants a string or boolean, as
#: ``"<schema>.<property>"`` (``"<enum>"`` for an integer enum). Remove an entry when DOM-11 gives the value a
#: string enum; permanent entries carry their reason.
_NON_STRING_ENUMS: dict[str, str] = {
    "ActivitiesBulkEdit.visibility": "DOM-11",
    "ActivityEdit.activity_type": "DOM-11",
    "ActivityEdit.visibility": "DOM-11",
    "ActivityMediaEmbedded.media_type": "DOM-11",
    "ActivityMediaRead.media_type": "DOM-11",
    "ActivityRead.activity_type": "DOM-11",
    "ActivityRead.visibility": "DOM-11",
    "ActivityStreamsRead.stream_type": "DOM-11",
    "BristolType.<enum>": "DOM-11",
    "GearType.<enum>": "DOM-11",
    "NotificationRead.type": "DOM-11",
    "ProblemDetail.status": "RFC 9457 status is the HTTP status code, an integer by definition",
    "SleepStageType.<enum>": "DOM-11",
    "UsersMe.is_garminconnect_linked": "DOM-11",
    "UsersMe.is_strava_linked": "DOM-11",
}

#: Route handlers whose docstring carries a Google section, as ``{path relative to app/: handlers}``. Move the
#: section's content into ``Field``/``Query`` descriptions or ``responses`` and lower the count (HTTP-10).
_DOCSTRING_SECTIONS: dict[str, int] = {
    "modules/activities/activity/router.py": 2,
    "modules/activities/activity_exercise_titles/public_router.py": 1,
    "modules/activities/activity_exercise_titles/router.py": 1,
    "modules/auth/account_security/api_keys_router.py": 1,
    "modules/auth/account_security/identity_links_router.py": 4,
    "modules/auth/account_security/mfa_router.py": 7,
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
    "modules/notifications/router.py": 5,
    "modules/server_settings/logs_router.py": 4,
    "modules/server_settings/public_router.py": 3,
    "modules/server_settings/router.py": 8,
    "modules/strava/router.py": 1,
    "modules/users/users/photo_router.py": 1,
    "modules/users/users/router.py": 16,
    "modules/users/users_default_gear/router.py": 2,
    "modules/users/users_goals/router.py": 5,
    "modules/users/users_profile/browser_redirect_router.py": 1,
    "modules/users/users_profile/router.py": 15,
    "modules/websocket/router.py": 1,
}

#: Files that build an error response by hand, as ``{path relative to app/: reason}``. Raise a
#: ``core.exceptions`` error instead and remove the entry (HTTP-1).
_HAND_BUILT_ERRORS: dict[str, str] = {
    "core/middleware.py": "HTTP-1",
}

#: Documented API paths that are not in the OpenAPI document, as ``"<file>: <path>"`` (file relative to
#: ``docs/`` or ``app/``). Fix the page or the route and remove the entry.
_DOCUMENTED_PATHS_MISSING: dict[str, str] = {
    "integrate/api-keys.md: /activities/create/upload": "AUTH-6",
    "integrate/authentication.md: /activities/create/upload": "AUTH-6",
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

    FastAPI's operation id is ``<handler><path with non-word characters as _>_<method>``, so a handler is
    matched to the operation whose id it generates for a path ending in the decorator's route.
    """
    operation_ids = {operation["operationId"]: (method, path) for method, path, operation in _operations()}
    found: dict[tuple[str, str], tuple[pathlib.Path, ast.FunctionDef]] = {}
    for file, function in router_functions():
        for method, call in route_decorators(function):
            route = call.args[0].value if call.args and isinstance(call.args[0], ast.Constant) else ""
            for path in _paths():
                operation_id = f"{function.name}{re.sub(r'\W', '_', _API_PREFIX + path)}_{method}"
                if path.endswith(str(route)) and operation_id in operation_ids:
                    found[(method, path)] = (file, function)
    return found


def _calls(function: ast.FunctionDef) -> set[str]:
    """Return the names a function calls (``set_etag`` for both ``set_etag(...)`` and ``mod.set_etag(...)``)."""
    names: set[str] = set()
    for node in ast.walk(function):
        if isinstance(node, ast.Call):
            func = node.func
            names.add(func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else "")
    return names


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
            {**_NOT_READABLE_ITEMS, **_MISSING_ITEM_GET},
            "Add a GET by id",
        )

    def test_a_create_of_a_readable_resource_sends_location_and_etag(self):
        """A ``POST`` answering 201 where ``GET <path>/{x_id}`` exists sets ``Location`` and ``ETag``.

        ``Location`` names where the new record is read and ``ETag`` is the version the client sends back as
        ``If-Match`` on its first edit, so the client needs no second request to learn either.
        """
        paths = _paths()
        missing: set[str] = set()
        for method, path, operation in _operations():
            readable = any(
                other.startswith(path + "/{") and other.count("/") == path.count("/") + 1 and "get" in item
                for other, item in paths.items()
            )
            if method != "post" or "201" not in operation["responses"] or not readable:
                continue
            _, function = _handlers()[(method, path)]
            calls = _calls(function)
            missing |= {
                f"{function.name}: {header}"
                for header, call in (("Location", "set_location"), ("ETag", "set_etag"))
                if call not in calls
            }

        _compare(
            "A create does not send its headers", missing, _CREATE_WITHOUT_HEADER, "Call set_location and set_etag"
        )

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

        _compare(
            "A PUT body has optional properties nobody reviewed",
            partial,
            _PARTIAL_PUTS,
            "Clear the field when omitted and list it in _PUT_OPTIONAL_FIELDS, or make the route a PATCH",
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

        _compare("A success body only carries a message", message_only, _MESSAGE_ONLY_RESPONSES, "Return the resource")

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

        _compare("A request body accepts a server-owned field", found, _SERVER_OWNED_REQUEST_FIELDS, "Drop the field")

    def test_request_datetimes_require_an_offset(self):
        """A datetime field of a request body model is ``pydantic.AwareDatetime`` or otherwise rejects a naive value.

        OpenAPI cannot tell ``datetime`` from ``AwareDatetime``, so the models are read: each field is
        validated with a naive timestamp. A naive one is read in a guessed zone and stored as another instant.
        """
        models: dict[str, type[BaseModel]] = {}
        for route in _api_routes():
            for body in route.dependant.body_params:
                for candidate in (body.field_info.annotation, *typing.get_args(body.field_info.annotation)):
                    if isinstance(candidate, type) and issubclass(candidate, BaseModel):
                        models[candidate.__name__] = candidate

        naive: set[str] = set()
        for name, model in models.items():
            for field, info in model.model_fields.items():
                kinds = [kind for kind in _unwrap(info.annotation) if kind is datetime.datetime]
                if not kinds:
                    continue
                annotation = Annotated[info.annotation, *info.metadata] if info.metadata else info.annotation
                adapter = TypeAdapter(annotation)
                try:
                    adapter.validate_python("2024-01-01T10:00:00")
                except ValidationError:
                    continue
                naive.add(f"{name}.{field}")

        _compare("A request datetime accepts a naive value", naive, _NAIVE_REQUEST_DATETIMES, "Use AwareDatetime")

    def test_enums_are_strings(self):
        """Enumerated values are strings and ``is_*``/``has_*`` properties are booleans.

        An integer code (``type: 3``) says nothing to a reader of the response or the generated client and
        cannot gain a value without renumbering; a flag that is an integer invites ``0``/``1``/``2`` states.
        """
        integer_names = {"type", "visibility", "status", "kind"}
        found: set[str] = set()
        for name, schema in _schemas().items():
            if "enum" in schema and schema.get("type") == "integer":
                found.add(f"{name}.<enum>")
            for field, prop in schema.get("properties", {}).items():
                types = {prop.get("type"), *(option.get("type") for option in prop.get("anyOf", []))} - {None}
                if "integer" in types and (field in integer_names or field.endswith("_type")):
                    found.add(f"{name}.{field}")
                if re.match(r"(is|has)_", field) and "boolean" not in types:
                    found.add(f"{name}.{field}")

        _compare("A schema types a value as an integer", found, _NON_STRING_ENUMS, "Use a string enum or a boolean")

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

        _compare("A file builds an error response by hand", found, _HAND_BUILT_ERRORS, "Raise a core.exceptions error")

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
                if segments[0] not in first_segments:
                    continue
                if not any(_same_path(segments, other[: len(segments)]) for other in known):
                    missing.add(f"{name}: /{'/'.join(segments)}")

        _compare("A documented path is not in the API", missing, _DOCUMENTED_PATHS_MISSING, "Fix the page or the route")


# --- Helpers for the rules ------------------------------------------------------------------------------------


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
