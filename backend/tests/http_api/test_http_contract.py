"""The HTTP contract on the production application: versioned writes, idempotency keys, paging, errors, size limits."""

import socket
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from urllib.parse import unquote, urlsplit

import pytest
import sqlalchemy as sa
from fastapi import routing
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

import core.config as core_config
import core.dependencies as core_dependencies
import modules.server_settings.integration_service as server_settings_integration
import modules.server_settings.schema as server_settings_schema
from tests._factories.contract import make_activity
from tests._factories.users import PASSWORD, make_admin, make_user

_API = core_config.ROOT_PATH
_STEP_UP = {"step_up": {"current_password": PASSWORD}}
_DAY = date(2025, 3, 10).isoformat()
_START = "2025-03-10T08:00:00Z"
_IDP_HOST = "idp.example.org"
_MAIL_HOST = "smtp.example.org"


@pytest.fixture(autouse=True)
def _identity_provider_host_resolves(monkeypatch) -> None:
    """Make the host an identity provider is created with resolve, as the DNS the check asks is a third party."""
    real = socket.getaddrinfo

    def resolve(name, *args, **kwargs):
        if name in {_IDP_HOST, _MAIL_HOST}:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
        return real(name, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", resolve)


@pytest.fixture
def ctx(app, committed_sessions, sign_in) -> SimpleNamespace:
    """A regular user, an administrator and a client for each, all committed and signed in."""
    with committed_sessions() as db:
        user, admin = make_user(db, timezone="UTC"), make_admin(db, timezone="UTC")
        db.commit()
    return SimpleNamespace(
        app=app,
        sessions=committed_sessions,
        sign_in=sign_in,
        user=user,
        admin=admin,
        client=sign_in(user).client,
        admin_client=sign_in(admin).client,
    )


def _hours_ago(hours: int) -> datetime:
    return datetime.now(UTC) - timedelta(hours=hours)


def _item_path(response) -> str:
    """The path of a created item, from the ``Location`` the create answered, relative to the API root."""
    assert response.status_code == 201, response.text
    return urlsplit(response.headers["Location"]).path.removeprefix(_API)


def _created(client: TestClient, path: str, body: dict) -> str:
    return _item_path(client.post(f"{_API}{path}", json=body))


def _gear(client: TestClient) -> tuple[str, str]:
    """Create a gear and return its path and id."""
    path = _created(client, "/gears", {"nickname": f"Bike {uuid.uuid4().hex[:8]}", "gear_type": "bike"})
    return path, path.rsplit("/", 1)[1]


def _component(client: TestClient) -> str:
    _, gear_id = _gear(client)
    return _created(
        client, "/gear-components", {"type": "cassette", "brand": "Shimano", "model": "105", "gear_id": gear_id}
    )


def _activity(ctx: SimpleNamespace) -> str:
    with ctx.sessions() as db:
        activity = make_activity(db, ctx.user.id)
        db.commit()
    return f"/activities/{activity.id}"


def _provider(ctx: SimpleNamespace) -> str:
    return _created(
        ctx.admin_client,
        "/identity-providers",
        {
            "name": "Company SSO",
            "slug": "company-sso",
            "client_id": "client-id",
            "client_secret": "client-secret",
            "provider_type": "oidc",
            "issuer_url": f"https://{_IDP_HOST}",
            **_STEP_UP,
        },
    )


@dataclass(frozen=True)
class Versioned:
    """One versioned resource: how to get an item of it and which write to refuse and accept.

    Attributes:
        name: The test id.
        resource: The collection path the resource lives under, as the route table names it.
        make: Creates an item over HTTP (or arranges one) and returns its path under the API root.
        method: The verb of the resource's edit.
        body: The edit's request body.
        admin: Whether the resource is the administrator's to edit.
        deletable: Whether the item can be deleted with ``DELETE`` and ``If-Match``.
    """

    name: str
    resource: str
    make: Callable[[SimpleNamespace], str]
    method: str
    body: Callable[[SimpleNamespace], dict]
    admin: bool = False
    deletable: bool = False


def _server_settings_body(ctx: SimpleNamespace) -> dict:
    current = ctx.admin_client.get(f"{_API}/server-settings").json()
    editable = {n: v for n, v in current.items() if n in server_settings_schema.ServerSettingsEdit.model_fields}
    return {**editable, "num_records_per_page": 40, "step_up": None}


_GOAL = {"interval": "weekly", "activity_type": "run", "goal_type": "distance", "goal_distance": 10000}

_VERSIONED = [
    Versioned(
        "gear", "/gears", lambda c: _gear(c.client)[0], "PATCH", lambda c: {"nickname": "Gravel"}, deletable=True
    ),
    Versioned(
        "gear-component",
        "/gear-components",
        lambda c: _component(c.client),
        "PATCH",
        lambda c: {"model": "Ultegra"},
        deletable=True,
    ),
    Versioned(
        "steps",
        "/health/steps",
        lambda c: _created(c.client, "/health/steps", {"date": _DAY, "steps": 1000}),
        "PATCH",
        lambda c: {"steps": 2000},
        deletable=True,
    ),
    Versioned(
        "water",
        "/health/water",
        lambda c: _created(c.client, "/health/water", {"date": _DAY, "amount_ml": 250}),
        "PATCH",
        lambda c: {"amount_ml": 300},
        deletable=True,
    ),
    Versioned(
        "poop",
        "/health/poop",
        lambda c: _created(c.client, "/health/poop", {"date_time": _START}),
        "PATCH",
        lambda c: {"notes": "n"},
        deletable=True,
    ),
    Versioned(
        "fasting",
        "/health/fasting",
        lambda c: _created(c.client, "/health/fasting", {"fast_start_time": _START}),
        "PATCH",
        lambda c: {"notes": "n"},
        deletable=True,
    ),
    Versioned(
        "sleep",
        "/health/sleep",
        lambda c: _created(c.client, "/health/sleep", {"date": _DAY}),
        "PATCH",
        lambda c: {"total_sleep_seconds": 100},
        deletable=True,
    ),
    Versioned(
        "weight",
        "/health/weight",
        lambda c: _created(c.client, "/health/weight", {"date": _DAY, "weight_kg": 70}),
        "PATCH",
        lambda c: {"weight_kg": 71},
        deletable=True,
    ),
    Versioned(
        "goal",
        "/profile/goals",
        lambda c: _created(c.client, "/profile/goals", _GOAL),
        "PUT",
        lambda c: {**_GOAL, "goal_distance": 20000},
        deletable=True,
    ),
    Versioned("targets", "/health/targets", lambda c: "/health/targets", "PATCH", lambda c: {"steps": 9000}),
    Versioned("profile", "/profile", lambda c: "/profile", "PATCH", lambda c: {"name": "Renamed"}),
    Versioned(
        "privacy settings",
        "/profile/privacy",
        lambda c: "/profile/privacy",
        "PATCH",
        lambda c: {"hide_activity_map": True},
    ),
    Versioned("activity", "/activities", _activity, "PATCH", lambda c: {"name": "Evening run"}, deletable=True),
    Versioned(
        "user",
        "/users",
        lambda c: _created(
            c.admin_client,
            "/users",
            {
                "name": "N",
                "username": "new-person",
                "email": "n@example.org",
                "access_type": "regular",
                "active": True,
                "password": "Brand-New-Password-5678!",
            },
        ),
        "PATCH",
        lambda c: {"name": "Renamed"},
        admin=True,
    ),
    Versioned(
        "identity provider",
        "/identity-providers",
        _provider,
        "PATCH",
        lambda c: {"enabled": True, **_STEP_UP},
        admin=True,
    ),
    Versioned(
        "default gear",
        "/profile/default-gear",
        lambda c: "/profile/default-gear",
        "PATCH",
        lambda c: {"run_gear_id": _gear(c.client)[1]},
    ),
    Versioned(
        "mail settings",
        "/server-settings/email/settings",
        lambda c: "/server-settings/email/settings",
        "PUT",
        lambda c: {
            "host": _MAIL_HOST,
            "port": 587,
            "security": "starttls",
            "username": None,
            "from_address": "noreply@example.org",
            **_STEP_UP,
        },
        admin=True,
    ),
    Versioned(
        "server settings", "/server-settings", lambda c: "/server-settings", "PUT", _server_settings_body, admin=True
    ),
]


@dataclass
class Item:
    """An item of a versioned resource, with the client that owns it."""

    client: TestClient
    url: str
    method: str
    body: dict

    def read(self):
        return self.client.get(self.url)

    def write(self, **headers: str):
        return self.client.request(self.method, self.url, json=self.body, headers=headers)


@pytest.fixture(params=_VERSIONED, ids=lambda case: case.name)
def versioned(request, ctx) -> tuple[Versioned, Item]:
    case: Versioned = request.param
    path = case.make(ctx)
    client = ctx.admin_client if case.admin else ctx.client
    return case, Item(client, f"{_API}{path}", case.method, case.body(ctx))


def _version(response) -> int:
    return int(response.headers["ETag"].strip('"'))


class TestVersionedWrites:
    def test_a_read_carries_the_version_as_a_quoted_etag(self, versioned):
        _, item = versioned

        response = item.read()

        assert response.status_code == 200
        assert response.headers["ETag"] == f'"{response.json()["version"]}"' or "version" not in response.json()
        assert response.headers["ETag"].startswith('"') and response.headers["ETag"].endswith('"')

    @pytest.mark.parametrize(
        ("header", "status", "problem"),
        [
            (None, 428, "precondition-required"),
            ('"999"', 412, "precondition-failed"),
            ("*", 400, "invalid-input"),
            ("1", 400, "invalid-input"),
        ],
        ids=["missing", "stale", "wildcard", "unquoted"],
    )
    def test_a_refused_write_answers_its_problem_and_changes_nothing(self, versioned, header, status, problem):
        _, item = versioned
        before = item.read()

        response = item.write(**({} if header is None else {"If-Match": header}))

        assert response.status_code == status, response.text
        assert response.json()["type"] == f"urn:endurain:error:{problem}"
        assert response.headers["Content-Type"].startswith("application/problem+json")
        after = item.read()
        assert (after.json(), after.headers["ETag"]) == (before.json(), before.headers["ETag"])

    def test_an_accepted_write_moves_the_version_on_and_answers_the_new_etag(self, versioned):
        _, item = versioned
        before = item.read()

        response = item.write(**{"If-Match": before.headers["ETag"]})

        assert response.status_code == 200, response.text
        assert _version(response) == _version(before) + 1
        after = item.read()
        assert after.headers["ETag"] == response.headers["ETag"]
        assert after.json() != before.json()

    def test_a_write_with_the_old_tag_is_stale_once_another_write_moved_the_version(self, versioned):
        _, item = versioned
        tag = item.read().headers["ETag"]
        assert item.write(**{"If-Match": tag}).status_code == 200

        response = item.write(**{"If-Match": tag})

        assert response.status_code == 412
        assert response.json()["type"] == "urn:endurain:error:precondition-failed"

    @pytest.mark.parametrize(
        "versioned", [case for case in _VERSIONED if case.deletable], indirect=True, ids=lambda c: c.name
    )
    def test_a_delete_without_the_tag_or_with_a_stale_one_keeps_the_item(self, versioned):
        _, item = versioned

        missing = item.client.delete(item.url)
        stale = item.client.delete(item.url, headers={"If-Match": '"999"'})

        assert (missing.status_code, stale.status_code) == (428, 412)
        assert item.read().status_code == 200


def _version_dependants(dependant) -> bool:
    return dependant.call is core_dependencies.require_if_match_header or any(
        _version_dependants(sub) for sub in dependant.dependencies
    )


def _resource_of(path: str) -> str:
    """The collection a route's path belongs to: id segments and the trailing action are dropped."""
    segments = [s for s in path.removeprefix(_API).split("/") if s and not s.startswith("{")]
    return "/" + "/".join(s for s in segments if s not in {"delete", "complete"})


#: Versioned resources whose route is exercised by a dedicated test below instead of the table.
_ELSEWHERE = {"/strava/client": "it has no item of its own; its version is the profile's integrations_version"}


class TestEveryVersionedRouteIsCovered:
    def test_every_route_that_requires_if_match_belongs_to_a_resource_this_file_exercises(self, app):
        required = {
            (method, route.path)
            for route in routing.iter_route_contexts(app.routes)
            if isinstance(route.original_route, APIRoute) and _version_dependants(route.dependant)
            for method in route.original_route.methods
        }

        resources = {_resource_of(path) for _, path in required}

        assert resources - {case.resource for case in _VERSIONED} == set(_ELSEWHERE)


_STRAVA_CLIENT = {"client_id": 4242, "client_secret": "secret-value", **_STEP_UP}


class TestVersionedWritesToTheProfilesIntegrations:
    """``PUT /strava/client`` is versioned by the ``integrations_version`` of ``GET /profile``."""

    def _integrations_version(self, ctx) -> int:
        return ctx.client.get(f"{_API}/profile").json()["integrations_version"]

    @pytest.mark.parametrize(
        ("header", "status"),
        [(None, 428), ('"999"', 412), ("*", 400), ("1", 400)],
        ids=["missing", "stale", "wildcard", "unquoted"],
    )
    def test_a_refused_write_changes_nothing(self, ctx, header, status):
        response = ctx.client.put(
            f"{_API}/strava/client", json=_STRAVA_CLIENT, headers={} if header is None else {"If-Match": header}
        )

        assert response.status_code == status, response.text
        assert self._integrations_version(ctx) == 1

    def test_an_accepted_write_moves_the_version_on_and_answers_the_new_etag(self, ctx):
        response = ctx.client.put(f"{_API}/strava/client", json=_STRAVA_CLIENT, headers={"If-Match": '"1"'})

        assert response.status_code == 204, response.text
        assert response.headers["ETag"] == '"2"'
        assert self._integrations_version(ctx) == 2


_ACTIONS = {
    "fasting": ("/complete", {"fast_end_time": "2025-03-10T20:00:00Z"}),
    "user": ("/delete", _STEP_UP),
    "identity provider": ("/delete", _STEP_UP),
}


class TestVersionedActions:
    """The routes that change a versioned item with a ``POST`` take the same precondition as its edit."""

    @pytest.mark.parametrize(
        "versioned", [case for case in _VERSIONED if case.name in _ACTIONS], indirect=True, ids=lambda c: c.name
    )
    @pytest.mark.parametrize(
        ("header", "status"),
        [(None, 428), ('"999"', 412), ("*", 400), ("1", 400)],
        ids=["missing", "stale", "wildcard", "unquoted"],
    )
    def test_a_refused_action_leaves_the_item_as_it_was(self, versioned, header, status):
        case, item = versioned
        suffix, body = _ACTIONS[case.name]
        before = item.read()

        response = item.client.post(
            item.url + suffix, json=body, headers={} if header is None else {"If-Match": header}
        )

        assert response.status_code == status, response.text
        assert item.read().json() == before.json()


@dataclass(frozen=True)
class Create:
    """A create route that takes an ``Idempotency-Key``.

    Attributes:
        name: The test id.
        build: ``build(ctx, client, variant)`` returns the path and JSON body of one request of ``client``; variant 1
            is a request that differs from variant 0 in what it asks for.
        admin: Whether only an administrator creates it.
        count: ``count(ctx, client, path)`` returns how many of the resource the caller's reads show.
    """

    name: str
    build: Callable[[SimpleNamespace, TestClient, int], tuple[str, dict | None]]
    count: Callable[[SimpleNamespace, TestClient, str], int]
    admin: bool = False


def _listed(path: str) -> Callable[[SimpleNamespace, TestClient, str], int]:
    def count(ctx: SimpleNamespace, client: TestClient, _created_path: str) -> int:
        body = client.get(f"{_API}{path}").json()
        return body["total"] if isinstance(body, dict) else len(body)

    return count


def _simple(path: str, first: dict, second: dict) -> Callable[[SimpleNamespace, TestClient, int], tuple[str, dict]]:
    return lambda ctx, client, variant: (path, (first, second)[variant])


def _component_request(ctx: SimpleNamespace, client: TestClient, variant: int) -> tuple[str, dict]:
    _, gear_id = _gear(client)
    return "/gear-components", {
        "type": "cassette",
        "brand": "Shimano",
        "model": ("105", "Ultegra")[variant],
        "gear_id": gear_id,
    }


def _follow_request(ctx: SimpleNamespace, client: TestClient, variant: int) -> tuple[str, None]:
    with ctx.sessions() as db:
        target = make_user(db)
        db.commit()
    ctx.followed = getattr(ctx, "followed", {})
    ctx.followed.setdefault(variant, target.id)
    return f"/users/{ctx.followed[variant]}/followers", None


def _followers(ctx: SimpleNamespace, _client: TestClient, path: str) -> int:
    import sqlalchemy as sa

    import modules.followers.models as followers_models

    target = uuid.UUID(path.split("/")[2])
    with ctx.sessions() as db:
        return db.scalar(
            sa.select(sa.func.count())
            .select_from(followers_models.Follower)
            .where(followers_models.Follower.followee_id == target)
        )


def _user_request(ctx: SimpleNamespace, client: TestClient, variant: int) -> tuple[str, dict]:
    unique = uuid.uuid4().hex[:10]
    return "/users", {
        "name": ("Person", "Other Person")[variant],
        "username": f"person-{unique}",
        "email": f"{unique}@example.org",
        "access_type": "regular",
        "active": True,
        "password": "Brand-New-Password-5678!",
    }


def _provider_request(ctx: SimpleNamespace, client: TestClient, variant: int) -> tuple[str, dict]:
    return "/identity-providers", {
        "name": ("Company SSO", "Other SSO")[variant],
        "slug": f"sso-{uuid.uuid4().hex[:10]}",
        "client_id": "client-id",
        "client_secret": "client-secret",
        "provider_type": "oidc",
        "issuer_url": f"https://{_IDP_HOST}/{uuid.uuid4().hex[:10]}",
        **_STEP_UP,
    }


_CREATES = [
    Create(
        "gear",
        _simple("/gears", {"nickname": "A", "gear_type": "bike"}, {"nickname": "B", "gear_type": "bike"}),
        _listed("/gears"),
    ),
    Create("gear component", _component_request, _listed("/gear-components")),
    Create(
        "fasting",
        _simple("/health/fasting", {"fast_start_time": _START}, {"fast_start_time": "2025-03-11T08:00:00Z"}),
        _listed("/health/fasting"),
    ),
    Create(
        "poop",
        _simple("/health/poop", {"date_time": _START}, {"date_time": "2025-03-11T08:00:00Z"}),
        _listed("/health/poop"),
    ),
    Create("sleep", _simple("/health/sleep", {"date": _DAY}, {"date": "2025-03-11"}), _listed("/health/sleep")),
    Create(
        "steps",
        _simple("/health/steps", {"date": _DAY, "steps": 1000}, {"date": _DAY, "steps": 2000}),
        _listed("/health/steps"),
    ),
    Create(
        "water",
        _simple("/health/water", {"date": _DAY, "amount_ml": 250}, {"date": _DAY, "amount_ml": 300}),
        _listed("/health/water"),
    ),
    Create(
        "weight",
        _simple("/health/weight", {"date": _DAY, "weight_kg": 70}, {"date": _DAY, "weight_kg": 71}),
        _listed("/health/weight"),
    ),
    Create("goal", _simple("/profile/goals", _GOAL, {**_GOAL, "goal_distance": 20000}), _listed("/profile/goals")),
    Create("user", _user_request, _listed("/users"), admin=True),
    Create("identity provider", _provider_request, _listed("/identity-providers"), admin=True),
    Create("follow", _follow_request, _followers),
]


@pytest.fixture(params=_CREATES, ids=lambda case: case.name)
def create(request, ctx) -> tuple[Create, TestClient, TestClient]:
    """A create case, the client that sends it and a second client of the same kind for another account."""
    case: Create = request.param
    maker = make_admin if case.admin else make_user
    with ctx.sessions() as db:
        second = maker(db, timezone="UTC")
        db.commit()
    return case, (ctx.admin_client if case.admin else ctx.client), ctx.sign_in(second).client


class TestIdempotencyKey:
    _KEY = '"3f6e1c5a-7d2b-4e0a-9a51-0c4d8b7e2f10"'

    def _request(self, ctx, case, client, variant):
        """The request of a client and variant, built once so a repeat sends the very same one."""
        cache = ctx.__dict__.setdefault("requests", {})
        if (id(client), variant) not in cache:
            cache[id(client), variant] = case.build(ctx, client, variant)
        return cache[id(client), variant]

    def _send(self, ctx, case, client, variant=0, key=_KEY):
        path, body = self._request(ctx, case, client, variant)
        return path, client.post(f"{_API}{path}", json=body, headers={"Idempotency-Key": key})

    def test_a_repeat_returns_the_first_answer_and_creates_one_record(self, ctx, create):
        case, client, _ = create
        path, first = self._send(ctx, case, client)
        before = case.count(ctx, client, path)

        _, second = self._send(ctx, case, client)

        assert first.status_code == 201, first.text
        assert (second.status_code, second.content) == (201, first.content)
        for header in ("Location", "ETag", "Content-Type"):
            assert second.headers.get(header) == first.headers.get(header)
        assert case.count(ctx, client, path) == before

    def test_the_same_key_for_another_request_is_refused_and_creates_nothing(self, ctx, create):
        case, client, _ = create
        path, first = self._send(ctx, case, client)
        before = case.count(ctx, client, path)

        other_path, other = self._send(ctx, case, client, variant=1)

        assert first.status_code == 201, first.text
        assert other.status_code == 422, other.text
        assert other.json()["type"] == "urn:endurain:error:idempotency-key-reused"
        assert other.headers["Link"] == '<https://docs.endurain.com/integrate/idempotency/>; rel="describedby"'
        assert case.count(ctx, client, path) == before
        assert case.count(ctx, client, other_path) == (before if other_path == path else 0)

    def test_a_key_that_is_not_a_quoted_string_is_refused_and_creates_nothing(self, ctx, create):
        case, client, _ = create
        path, _ = self._request(ctx, case, client, 0)
        before = case.count(ctx, client, path)

        _, response = self._send(ctx, case, client, key="3f6e1c5a-7d2b-4e0a-9a51-0c4d8b7e2f10")

        assert response.status_code == 400, response.text
        assert response.json()["type"] == "urn:endurain:error:idempotency-key-invalid"
        assert case.count(ctx, client, path) == before

    def test_another_account_sending_the_same_key_gets_its_own_record(self, ctx, create):
        case, client, second_client = create
        _, mine = self._send(ctx, case, client)

        _, theirs = self._send(ctx, case, second_client)

        assert (mine.status_code, theirs.status_code) == (201, 201), theirs.text
        assert theirs.content != mine.content


#: Paged routes whose largest window is the server's page size (``num_records_per_page``) rather than 200, with the
#: rule that says so.
_WINDOW_OF_THE_SERVER_PAGE_SIZE = {
    "/api/v1/users": "the user search caps num_records at the server's page size (errors-and-limits.md)",
}


def _server_page_size(ctx) -> int:
    with ctx.sessions() as db:
        return server_settings_integration.get_server_settings(db).num_records_per_page


def _query_names(dependant) -> set[str]:
    names = {param.name for param in dependant.query_params}
    for sub in dependant.dependencies:
        names |= _query_names(sub)
    return names


def _paged_routes(app) -> list[str]:
    """The ``GET`` routes without path parameters that take ``page_number`` and ``num_records``, read from the app."""
    return sorted(
        route.path
        for route in routing.iter_route_contexts(app.routes)
        if isinstance(route.original_route, APIRoute)
        and "GET" in route.original_route.methods
        and "{" not in route.path
        and {"page_number", "num_records"} <= _query_names(route.dependant)
    )


class TestPagination:
    def test_the_paged_routes_of_the_app_are_found(self, app):
        assert {"/api/v1/health/steps", "/api/v1/gears", "/api/v1/activities"} <= set(_paged_routes(app))

    @pytest.mark.parametrize(
        ("name", "value"),
        [
            ("page_number", 0),
            ("page_number", -1),
            ("page_number", 100001),
            ("num_records", 0),
            ("num_records", -5),
            ("num_records", 201),
            ("num_records", "many"),
        ],
        ids=lambda value: str(value),
    )
    def test_every_paged_route_refuses_a_window_outside_the_bounds_with_a_validation_problem(self, ctx, name, value):
        refused = {}
        for path in _paged_routes(ctx.app):
            response = ctx.admin_client.get(path, params={name: value})
            body = response.json()
            if response.status_code != 422 or body["type"] != "urn:endurain:error:validation-failed":
                refused[path] = response.status_code
            elif f"query.{name}" not in {error["field"] for error in body["errors"]}:
                refused[path] = body["errors"]

        assert refused == {}

    def test_every_paged_route_answers_the_largest_window_as_a_page_envelope(self, ctx):
        answers = {}
        for path in _paged_routes(ctx.app):
            largest = _server_page_size(ctx) if path in _WINDOW_OF_THE_SERVER_PAGE_SIZE else 200
            response = ctx.admin_client.get(path, params={"page_number": 1, "num_records": largest})
            body = response.json()
            if response.status_code != 200 or not {"items", "total", "page", "num_records", "next"} <= set(body):
                answers[path] = (response.status_code, sorted(body))
            elif (body["page"], body["num_records"]) != (1, largest):
                answers[path] = (body["page"], body["num_records"])

        assert answers == {}

    def test_the_user_search_refuses_a_window_above_the_server_page_size(self, ctx):
        response = ctx.admin_client.get(
            f"{_API}/users", params={"page_number": 1, "num_records": _server_page_size(ctx) + 1}
        )

        assert response.status_code == 422
        assert [error["field"] for error in response.json()["errors"]] == ["query.num_records"]

    def test_a_page_names_the_next_one_until_the_last_and_a_page_past_the_end_is_empty(self, ctx):
        for day in range(1, 6):
            assert (
                ctx.client.post(f"{_API}/health/steps", json={"date": f"2025-03-0{day}", "steps": day}).status_code
                == 201
            )

        pages = [
            ctx.client.get(f"{_API}/health/steps", params={"page_number": number, "num_records": 2}).json()
            for number in (1, 2, 3, 4)
        ]

        assert [(p["total"], p["page"], p["num_records"], p["next"], len(p["items"])) for p in pages] == [
            (5, 1, 2, 2, 2),
            (5, 2, 2, 3, 2),
            (5, 3, 2, None, 1),
            (5, 4, 2, None, 0),
        ]
        walked = [item["id"] for page in pages for item in page["items"]]
        assert len(set(walked)) == 5

    def test_the_default_window_is_the_documented_one(self, ctx):
        body = ctx.client.get(f"{_API}/health/steps").json()

        assert (body["page"], body["num_records"]) == (1, 25)

    def test_the_activity_feed_walks_a_keyset_with_a_cursor_and_no_total(self, ctx):
        with ctx.sessions() as db:
            for hours in (5, 4, 3):
                make_activity(
                    db, ctx.user.id, name=f"Run {hours}", start_time=_hours_ago(hours), end_time=_hours_ago(hours - 1)
                )
            db.commit()
        url = f"{_API}/activities/feed"

        first = ctx.client.get(url, params={"scope": "mine", "num_records": 2}).json()
        second = ctx.client.get(url, params={"scope": "mine", "num_records": 2, "cursor": first["next_cursor"]}).json()

        assert "total" not in first
        assert [item["name"] for item in first["items"]] == ["Run 3", "Run 4"]
        assert first["next_cursor"] is not None
        assert [item["name"] for item in second["items"]] == ["Run 5"]
        assert second["next_cursor"] is None

    def test_a_cursor_the_server_did_not_issue_is_refused(self, ctx):
        response = ctx.client.get(f"{_API}/activities/feed", params={"scope": "mine", "cursor": "not-a-cursor"})

        assert response.status_code == 400
        assert response.json()["type"] == "urn:endurain:error:invalid-input"

    @pytest.mark.parametrize("value", [0, 201])
    def test_the_feed_refuses_a_page_size_outside_the_bounds(self, ctx, value):
        response = ctx.client.get(f"{_API}/activities/feed", params={"num_records": value})

        assert response.status_code == 422


_PROBLEM_MEMBERS = {"type", "title", "status", "detail", "instance", "request_id"}


def _assert_problem(response, status: int, problem: str | None = None) -> dict:
    """Check a response against the documented problem document and return its body."""
    assert response.status_code == status, response.text
    assert response.headers["Content-Type"].startswith("application/problem+json")
    body = response.json()
    assert body.keys() >= _PROBLEM_MEMBERS, body
    assert body["status"] == status
    assert body["type"].startswith("urn:endurain:error:") or body["type"] == "about:blank"
    assert body["instance"] == unquote(urlsplit(str(response.url)).path)
    assert body["request_id"] == response.headers["X-Request-ID"]
    assert "Traceback" not in response.text and ".py" not in response.text
    if problem is not None:
        assert body["type"] == f"urn:endurain:error:{problem}"
    return body


class TestProblemDocuments:
    def test_a_missing_credential_is_an_invalid_token_problem_with_the_bearer_challenge(self, ctx):
        response = TestClient(ctx.app).get(f"{_API}/profile")

        _assert_problem(response, 401, "invalid-token")
        assert response.headers["WWW-Authenticate"].startswith("Bearer")

    def test_a_missing_scope_is_a_permission_problem_naming_the_scopes(self, ctx):
        response = ctx.client.get(f"{_API}/users/{ctx.user.id}/identity-providers")

        body = _assert_problem(response, 403, "permission-denied")
        assert body["missing_scopes"] == ["users:read-all"]

    def test_an_unknown_id_is_a_not_found_problem(self, ctx):
        _assert_problem(ctx.client.get(f"{_API}/gears/{uuid.uuid4()}"), 404, "not-found")

    def test_an_unknown_api_path_is_a_not_found_problem(self, ctx):
        _assert_problem(ctx.client.get(f"{_API}/no-such-resource"), 404)

    def test_a_method_a_path_does_not_offer_is_a_405_problem_with_allow(self, ctx):
        response = ctx.client.delete(f"{_API}/profile")

        _assert_problem(response, 405)
        assert "GET" in response.headers["Allow"]

    def test_a_body_that_does_not_match_the_schema_lists_its_field_errors(self, ctx):
        response = ctx.client.post(f"{_API}/gears", json={"nickname": 5})

        body = _assert_problem(response, 422, "validation-failed")
        assert {"body.nickname", "body.gear_type"} <= {error["field"] for error in body["errors"]}
        assert all({"field", "message", "type"} <= error.keys() for error in body["errors"])

    def test_a_conflict_is_a_problem(self, ctx):
        body = {"nickname": "Same", "gear_type": "bike"}
        ctx.client.post(f"{_API}/gears", json=body)

        _assert_problem(ctx.client.post(f"{_API}/gears", json=body), 409, "conflict")

    def test_a_precondition_refusal_is_a_problem(self, ctx):
        path = _created(ctx.client, "/health/steps", {"date": _DAY, "steps": 10})

        _assert_problem(ctx.client.patch(f"{_API}{path}", json={"steps": 11}), 428, "precondition-required")


def _explodes_with_a_secret() -> None:
    raise RuntimeError("password=hunter2 postgresql://app:s3cret@db.internal/endurain")


def _explodes_in_the_database(db: core_dependencies.DbSession) -> None:
    db.execute(sa.text("SELECT secret_column FROM private_table_xyz"))


class TestAnUnexpectedErrorLeaksNothing:
    @pytest.mark.parametrize(
        ("handler", "leaks"),
        [
            (_explodes_with_a_secret, ["hunter2", "s3cret", "db.internal", "RuntimeError"]),
            (
                _explodes_in_the_database,
                ["private_table_xyz", "secret_column", "ProgrammingError", "psycopg", "SELECT"],
            ),
        ],
        ids=["a raised exception", "a database error"],
    )
    def test_a_500_is_the_generic_problem_without_the_exception_text_or_a_traceback(self, ctx, handler, leaks):
        ctx.app.add_api_route(f"{_API}/_explodes", handler, methods=["GET"])
        # The frontend fallback route is registered already and would answer the path first.
        ctx.app.router.routes.insert(0, ctx.app.router.routes.pop())
        client = TestClient(ctx.app, raise_server_exceptions=False)

        response = client.get(f"{_API}/_explodes")

        body = _assert_problem(response, 500)
        assert body["detail"] and not [text for text in leaks if text in response.text]
        assert "Traceback" not in response.text and 'File "' not in response.text


_JSON = {"Content-Type": "application/json"}
_MIB = 1024 * 1024


def _json_padded_to(size: int) -> bytes:
    """A JSON object of exactly ``size`` bytes."""
    framing = len(b'{"nickname":""}')
    return b'{"nickname":"' + b"a" * (size - framing) + b'"}'


def _chunks(body: bytes, size: int = 64 * 1024):
    for start in range(0, len(body), size):
        yield body[start : start + size]


class TestBodySizeLimit:
    def test_a_body_over_ten_mib_to_an_ordinary_route_is_a_413_problem_before_the_route_runs(self, ctx):
        response = ctx.client.post(f"{_API}/gears", content=_json_padded_to(10 * _MIB + 1), headers=_JSON)

        _assert_problem(response, 413, "payload-too-large")

    def test_a_body_of_exactly_ten_mib_is_read_by_the_route(self, ctx):
        response = ctx.client.post(f"{_API}/gears", content=_json_padded_to(10 * _MIB), headers=_JSON)

        assert response.status_code == 422
        assert response.json()["type"] == "urn:endurain:error:validation-failed"

    def test_a_body_that_declares_no_length_is_refused_once_it_has_grown_past_the_limit(self, ctx):
        response = ctx.client.post(f"{_API}/gears", content=_chunks(_json_padded_to(10 * _MIB + 1)), headers=_JSON)

        _assert_problem(response, 413, "payload-too-large")

    @pytest.mark.parametrize("path", ["/auth/login", "/public/sign-up/request", "/public/password-reset/request"])
    def test_a_body_over_64_kib_to_a_credential_or_public_route_is_a_413_problem(self, ctx, path):
        response = TestClient(ctx.app).post(f"{_API}{path}", content=_json_padded_to(64 * 1024 + 1), headers=_JSON)

        _assert_problem(response, 413, "payload-too-large")

    def test_a_body_of_exactly_64_kib_to_a_public_route_is_not_refused_for_its_size(self, ctx):
        response = TestClient(ctx.app).post(
            f"{_API}/public/sign-up/request", content=_json_padded_to(64 * 1024), headers=_JSON
        )

        assert response.status_code == 422

    def test_an_upload_route_has_its_own_limit_published_in_the_openapi_document(self, ctx):
        spec = ctx.app.openapi()
        operation = spec["paths"][f"{_API}/identity-providers/{{idp_id}}/icon"]["put"]
        limit = operation["x-max-body-bytes"]
        path = f"{_API}/identity-providers/{uuid.uuid4()}/icon"

        over = ctx.admin_client.put(path, files={"file": ("icon.png", b"x" * limit, "image/png")})
        under = ctx.admin_client.put(path, files={"file": ("icon.png", b"x" * 100, "image/png")})

        _assert_problem(over, 413, "payload-too-large")
        assert under.status_code != 413

    def test_a_multipart_body_over_the_ordinary_limit_to_a_route_without_a_file_is_refused(self, ctx):
        response = ctx.client.post(
            f"{_API}/gears", files={"file": ("x.bin", b"x" * (10 * _MIB + 1), "application/octet-stream")}
        )

        _assert_problem(response, 413, "payload-too-large")


class TestNulCharacters:
    def _assert_refused(self, response, field: str) -> None:
        body = _assert_problem(response, 422, "validation-failed")
        assert body["errors"] == [
            {"field": field, "message": "NUL characters are not allowed", "type": "nul_character"}
        ]

    def test_a_nul_in_a_json_string_is_refused_before_the_route_runs(self, ctx):
        response = ctx.client.post(f"{_API}/gears", json={"nickname": "bad\x00name", "gear_type": "bike"})

        self._assert_refused(response, "body")
        assert ctx.client.get(f"{_API}/gears").json()["total"] == 0

    def test_a_nul_in_a_json_key_is_refused(self, ctx):
        response = ctx.client.post(f"{_API}/gears", content=b'{"nick\\u0000name": "x"}', headers=_JSON)

        self._assert_refused(response, "body")

    def test_an_escaped_backslash_followed_by_the_text_u0000_is_not_a_nul(self, ctx):
        response = ctx.client.post(
            f"{_API}/gears", content=b'{"nickname": "back\\\\u0000slash", "gear_type": "bike"}', headers=_JSON
        )

        assert response.status_code == 201, response.text

    def test_a_nul_in_the_query_string_is_refused(self, ctx):
        response = ctx.client.get(f"{_API}/gears?gear_type=a%00b")

        self._assert_refused(response, "query")

    def test_a_nul_in_the_path_is_refused(self, ctx):
        self._assert_refused(ctx.client.get(f"{_API}/gears/%00"), "path")

    def test_a_nul_in_a_form_field_is_refused(self, ctx, app):
        response = TestClient(app, headers={"X-Client-Type": "web"}).post(
            f"{_API}/auth/login", data={"username": "user\x00name", "password": "x"}
        )

        self._assert_refused(response, "body")

    def test_a_password_with_a_nul_is_refused_on_a_real_credential_route(self, ctx):
        response = ctx.client.post(
            f"{_API}/profile/password/change",
            json={"password": "New-Password-1234!", "step_up": {"current_password": "bad\x00password"}},
        )

        self._assert_refused(response, "body")
