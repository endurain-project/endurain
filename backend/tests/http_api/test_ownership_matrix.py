"""User B acting on user A's resources through the production application is refused and changes nothing.

Every route of the application whose path names a resource owned by a user (a resource id) or a user (``{user_id}``)
is either in :data:`CASES`, which proves the refusal and that A's rows are untouched, or in :data:`REGISTER`, with the
reason the matrix does not cover it. A route added with an id parameter and no entry fails
:class:`TestEveryRouteIsAccountedFor`.
"""

import hashlib
import re
import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

import pytest
from fastapi.routing import iter_route_contexts
from sqlalchemy import inspect, select

import core.config as core_config
import modules.activities.activity.constants as activity_constants
import modules.activities.activity.models as activity_models
import modules.activities.activity_ingestion.models as ingestion_models
import modules.activities.activity_laps.models as laps_models
import modules.activities.activity_media.models as media_models
import modules.activities.activity_sets.models as sets_models
import modules.activities.activity_streams.models as streams_models
import modules.activities.activity_workout_steps.models as steps_models
import modules.auth.api_keys.constants as api_keys_constants
import modules.auth.api_keys.models as api_keys_models
import modules.auth.identity_provider_links.models as identity_link_models
import modules.auth.known_devices.models as device_models
import modules.auth.sessions.models as session_models
import modules.followers.models as follower_models
import modules.gears.gear.models as gear_models
import modules.gears.gear_components.models as gear_component_models
import modules.health.health_fasting.models as fasting_models
import modules.health.health_poop.models as poop_models
import modules.health.health_sleep.models as sleep_models
import modules.health.health_steps.models as steps_record_models
import modules.health.health_water.models as water_models
import modules.health.health_weight.models as weight_models
import modules.notifications.models as notification_models
import modules.users.users.models as user_models
import modules.users.users_goals.models as goal_models
from tests._factories import activities as activity_factories
from tests._factories import api_keys as api_key_factories
from tests._factories import devices as device_factories
from tests._factories import followers as follower_factories
from tests._factories import gears as gear_factories
from tests._factories import goals as goal_factories
from tests._factories import health as health_factories
from tests._factories import identity_links as identity_link_factories
from tests._factories import jobs as job_factories
from tests._factories import notifications as notification_factories
from tests._factories.users import PASSWORD, make_user

_IF_MATCH = {"If-Match": '"1"'}
_STEP_UP = {"step_up": {"current_password": PASSWORD}}
_PLACEHOLDER = re.compile(r"\{(\w+)\}")
_NOT_FOUND_TYPE = "urn:endurain:error:not-found"


@dataclass
class World:
    """Two users and everything user A owns, committed.

    Attributes:
        a: The owner.
        b: The user who acts on A's resources.
        b_client: Sends B's access token.
        follower_client: Sends the access token of an accepted follower of A.
        ids: The ids of A's resources and of the users around A, by the name of the path parameter that takes them.
        tracked: What A's data is: every row a refused request must leave as it was.
    """

    a: Any
    b: Any
    b_client: Any
    follower_client: Any
    ids: dict[str, uuid.UUID] = field(default_factory=dict)
    tracked: list[tuple[str, type, dict[str, object]]] = field(default_factory=list)


def _track(world: World, model: type, **where: object) -> None:
    world.tracked.append((f"{model.__name__}{where}", model, where))


def _rows(db, model: type, where: dict[str, object]) -> list[dict[str, object]]:
    columns = [column.key for column in inspect(model).mapper.column_attrs]
    rows = db.scalars(select(model).filter_by(**where)).all()
    return sorted(({name: getattr(row, name) for name in columns} for row in rows), key=str)


def _snapshot(committed_sessions, world: World) -> dict[str, list[dict[str, object]]]:
    """Read everything A owns back in a new session."""
    with committed_sessions() as db:
        return {label: _rows(db, model, where) for label, model, where in world.tracked}


@pytest.fixture
def world(committed_sessions, sign_in) -> World:
    """Users A and B, and one of everything A owns."""
    with committed_sessions() as db:
        a = make_user(db, timezone="UTC")
        b = make_user(db, timezone="UTC")
        follower = make_user(db)
        requester = make_user(db)

        private = activity_factories.make_activity(db, a.id, private_notes="secret notes")
        # Each activity starts at its own time: one that repeats a start time is stored as a hidden duplicate.
        shared_with_followers = activity_factories.make_activity(
            db,
            a.id,
            visibility=activity_constants.ActivityVisibility.FOLLOWERS,
            name="Followers run",
            start_time=activity_factories.DEFAULT_START + timedelta(days=1),
            end_time=activity_factories.DEFAULT_START + timedelta(days=1, hours=1),
            private_notes="secret notes",
        )
        public = activity_factories.make_activity(
            db,
            a.id,
            visibility=activity_constants.ActivityVisibility.PUBLIC,
            name="Public run",
            start_time=activity_factories.DEFAULT_START + timedelta(days=2),
            end_time=activity_factories.DEFAULT_START + timedelta(days=2, hours=1),
            private_notes="secret notes",
        )
        for activity in (private, shared_with_followers, public):
            activity_factories.make_activity_children(db, activity)
        media = activity_factories.make_activity_media(db, private, f"{private.id}_photo.png")
        gear = gear_factories.make_gear(db, a.id)
        component = gear_factories.make_gear_component(db, a.id, gear.id)
        weight = health_factories.make_health_weight(db, a.id)
        steps = health_factories.make_health_steps(db, a.id)
        water = health_factories.make_health_water(db, a.id)
        sleep = health_factories.make_health_sleep(db, a.id)
        poop = health_factories.make_health_poop(db, a.id)
        fasting = health_factories.make_health_fasting(db, a.id)
        goal = goal_factories.make_goal(db, a.id)
        notification = notification_factories.make_notification(db, a.id)
        follower_factories.make_follow(db, follower.id, a.id, accepted=True)
        follower_factories.make_follow(db, requester.id, a.id, accepted=False)
        device_id = device_factories.make_known_device(db, a.id, hashlib.sha256(b"device-of-a").hexdigest())
        key, _ = api_key_factories.make_api_key(db, a, scopes=[api_keys_constants.ApiKeyScope.ACTIVITIES_READ])
        idp_id = identity_link_factories.make_identity_provider(db, "provider-of-a")
        link = identity_link_factories.make_identity_link(db, a.id, idp_id, "subject-of-a")
        ingestion = job_factories.make_ingestion_job(db, a.id)
        db.commit()

    a_second_session = sign_in(a)
    world = World(a=a, b=b, b_client=sign_in(b).client, follower_client=sign_in(follower).client)
    world.ids = {
        "activity_id": private.id,
        "media_id": media.id,
        "gear_id": gear.id,
        "gear_component_id": component.id,
        "health_weight_id": weight.id,
        "health_steps_id": steps.id,
        "health_water_id": water.id,
        "health_sleep_id": sleep.id,
        "health_poop_id": poop.id,
        "health_fasting_id": fasting.id,
        "goal_id": goal.id,
        "notification_id": notification.id,
        "session_id": a_second_session.session_id,
        "device_id": device_id,
        "api_key_id": key.id,
        "idp_id": idp_id,
        "job_id": ingestion.id,
        "bulk_edit_job_id": job_factories.make_bulk_edit_job(a.id),
        "user_id": a.id,
        "follower_id": follower.id,
        "requester_id": requester.id,
        "public_activity_id": public.id,
        "followers_activity_id": shared_with_followers.id,
    }
    for model, key_name, row_id in (
        (activity_models.Activity, "id", private.id),
        (activity_models.Activity, "id", shared_with_followers.id),
        (activity_models.Activity, "id", public.id),
        (media_models.ActivityMedia, "activity_id", private.id),
        (laps_models.ActivityLaps, "activity_id", private.id),
        (sets_models.ActivitySets, "activity_id", private.id),
        (steps_models.ActivityWorkoutSteps, "activity_id", private.id),
        (streams_models.ActivitySamples, "activity_id", private.id),
        (laps_models.ActivityLaps, "activity_id", public.id),
        (gear_models.Gear, "id", gear.id),
        (gear_component_models.GearComponents, "id", component.id),
        (weight_models.HealthWeight, "id", weight.id),
        (steps_record_models.HealthSteps, "id", steps.id),
        (water_models.HealthWater, "id", water.id),
        (sleep_models.HealthSleep, "id", sleep.id),
        (poop_models.HealthPoop, "id", poop.id),
        (fasting_models.HealthFasting, "id", fasting.id),
        (goal_models.UsersGoal, "id", goal.id),
        (notification_models.Notification, "id", notification.id),
        (session_models.UsersSessions, "id", a_second_session.session_id),
        (device_models.KnownDevice, "id", device_id),
        (api_keys_models.UsersApiKeys, "id", key.id),
        (identity_link_models.IdentityLink, "id", link.id),
        (ingestion_models.ActivityIngestionJob, "id", ingestion.id),
        (user_models.Users, "id", a.id),
        (follower_models.Follower, "followee_id", a.id),
    ):
        _track(world, model, **{key_name: row_id})
    return world


@dataclass(frozen=True)
class Case:
    """One route, and the request B sends to it.

    Attributes:
        route: ``METHOD /path`` as the application declares it, relative to the API root.
        body: The JSON body, or ``None``.
        files: A multipart upload, or ``None``.
        use: Path parameters that name a different id of the world than their own name.
        missing: Path parameters replaced with an id that does not exist, for the answer B must not tell from it.
        status: The status B gets.
        same_detail: Whether the answer to a missing id is word for word the refusal; a route that answers about the
            caller's own account (it has no link to the provider) says so in its detail.
    """

    route: str
    body: dict[str, object] | None = None
    files: dict[str, object] | None = None
    use: dict[str, str] = field(default_factory=dict)
    missing: tuple[str, ...] | None = None
    status: int = 404
    same_detail: bool = True

    @property
    def label(self) -> str:
        return self.route + "".join(f" [{value}]" for value in self.use.values())


_UPLOAD = {"files": {"file": ("photo.png", b"not-a-real-image", "image/png")}}
_ACTIVITY = "/activities/{activity_id}"
_EMPTY_PAGE_STATUS = 200


def _health(name: str, patch: dict[str, object]) -> list[Case]:
    path = f"/health/{name}/{{health_{name}_id}}"
    return [Case(f"GET {path}"), Case(f"PATCH {path}", body=patch), Case(f"DELETE {path}")]


#: Routes on a resource of A, which B answers as if it did not exist.
CASES: list[Case] = [
    Case(f"GET {_ACTIVITY}"),
    Case(f"GET {_ACTIVITY}/detail"),
    Case(f"PATCH {_ACTIVITY}", body={"name": "hijacked"}),
    Case(f"DELETE {_ACTIVITY}"),
    # A child collection answers a refusal with the empty page, as it answers an activity that has none.
    Case(f"GET {_ACTIVITY}/laps", status=_EMPTY_PAGE_STATUS),
    Case(f"GET {_ACTIVITY}/legs", status=_EMPTY_PAGE_STATUS),
    Case(f"GET {_ACTIVITY}/sets", status=_EMPTY_PAGE_STATUS),
    Case(f"GET {_ACTIVITY}/workout-steps", status=_EMPTY_PAGE_STATUS),
    Case(f"GET {_ACTIVITY}/media", status=_EMPTY_PAGE_STATUS),
    # The streams are one object, so a refusal is the 404 a missing activity gets.
    Case(f"GET {_ACTIVITY}/streams"),
    Case(f"POST {_ACTIVITY}/media", **_UPLOAD),
    Case(f"DELETE {_ACTIVITY}/media/{{media_id}}"),
    Case("GET /gears/{gear_id}"),
    Case("PATCH /gears/{gear_id}", body={"nickname": "hijacked"}),
    Case("DELETE /gears/{gear_id}"),
    Case("GET /gears/{gear_id}/components", status=_EMPTY_PAGE_STATUS),
    Case("GET /gear-components/{gear_component_id}"),
    Case("PATCH /gear-components/{gear_component_id}", body={"brand": "hijacked"}),
    Case("DELETE /gear-components/{gear_component_id}"),
    *_health("weight", {"weight_kg": 99.0}),
    *_health("steps", {"steps": 1}),
    *_health("water", {"amount_ml": 1}),
    *_health("sleep", {"total_sleep_seconds": 1}),
    *_health("poop", {"notes": "hijacked"}),
    *_health("fasting", {"notes": "hijacked"}),
    Case("POST /health/fasting/{health_fasting_id}/complete", body={"fast_end_time": "2025-01-02T12:00:00+00:00"}),
    Case("GET /profile/goals/{goal_id}"),
    Case(
        "PUT /profile/goals/{goal_id}",
        body={"interval": "weekly", "activity_type": "run", "goal_type": "distance", "goal_distance": 1},
    ),
    Case("DELETE /profile/goals/{goal_id}"),
    Case("GET /notifications/{notification_id}"),
    Case("POST /notifications/{notification_id}/read"),
    Case("DELETE /notifications/{notification_id}"),
    Case("DELETE /profile/sessions/{session_id}"),
    Case("POST /profile/devices/{device_id}/delete", body=_STEP_UP),
    Case("POST /profile/api-keys/{api_key_id}/revoke"),
    Case("DELETE /profile/api-keys/{api_key_id}"),
    Case("POST /profile/identity-providers/{idp_id}/unlink", body=_STEP_UP, same_detail=False),
    Case("GET /jobs/{job_id}", use={"job_id": "job_id"}),
    Case("GET /jobs/{job_id}", use={"job_id": "bulk_edit_job_id"}),
    Case("POST /profile/follow-requests/{follower_id}/accept", use={"follower_id": "requester_id"}),
    Case("DELETE /profile/follow-requests/{follower_id}", use={"follower_id": "requester_id"}),
    Case("DELETE /users/{user_id}/followers/{follower_id}"),
    Case("GET /users/{user_id}/followers"),
    Case("GET /users/{user_id}/following"),
]

#: Routes with an id parameter the matrix does not drive, and why.
REGISTER: dict[str, str] = {
    "GET /activities/{activity_id}/thumbnail": "public: the signed token in the query is the capability",
    "GET /activities/{activity_id}/media/{media_id}/file": "public: the signed token in the query is the capability",
    "GET /users/{user_id}/photo": "public: the signed token in the query is the capability",
    "GET /public/activities/{activity_id}": "public share link: served only while public links are on and public",
    "GET /public/activities/{activity_id}/detail": "public share link",
    "GET /public/activities/{activity_id}/laps": "public share link",
    "GET /public/activities/{activity_id}/legs": "public share link",
    "GET /public/activities/{activity_id}/sets": "public share link",
    "GET /public/activities/{activity_id}/streams": "public share link",
    "GET /public/activities/{activity_id}/workout-steps": "public share link",
    "GET /public/idp/callback/{idp_slug}": "provider sign-in flow, no user-owned resource",
    "GET /public/idp/login/{idp_slug}": "provider sign-in flow, no user-owned resource",
    "GET /public/idp/{idp_slug}/icon": "public provider icon",
    "POST /public/idp/{idp_slug}/backchannel-logout": "provider call, authenticated by its signed logout token",
    "POST /auth/sessions/{session_id}/tokens": "single-use token exchange, authenticated by the sign-in's own secrets",
    "GET /users/{user_id}": "public projection any signed-in user may read; see TestPublicUserRoutes",
    "GET /users/{user_id}/overview": "public projection; see TestPublicUserRoutes",
    "GET /users/{user_id}/activities": "lists only what B may see; see TestPublicUserRoutes",
    "GET /users/{user_id}/activities/stats": "totals only what B may see; see TestPublicUserRoutes",
    "GET /users/{user_id}/relationship": "reports only B's own relationship; see TestPublicUserRoutes",
    "POST /users/{user_id}/followers": "any user may ask to follow any other; the request is pending",
    "PUT /profile/blocked-users/{user_id}": "the caller's own block list; the id names the user to block",
    "DELETE /profile/blocked-users/{user_id}": "the caller's own block list; the id names the user to unblock",
    "POST /profile/identity-providers/{idp_id}/link": "a provider is shared configuration; the link binds the caller",
    "POST /profile/identity-providers/{idp_id}/step-up": "a provider is shared configuration; binds the caller",
}

#: Routes that need an administrator scope, with the body a valid request carries.
ADMINISTRATOR_ROUTES: dict[str, dict[str, object] | None] = {
    "PATCH /users/{user_id}": {"name": "hijacked"},
    "DELETE /users/{user_id}/photo": None,
    "POST /users/{user_id}/approve": None,
    "POST /users/{user_id}/delete": _STEP_UP,
    "POST /users/{user_id}/mfa/reset": _STEP_UP,
    "POST /users/{user_id}/password/change": {"password": "Another-Password-1234!", **_STEP_UP},
    "POST /users/{user_id}/password/require-change": None,
    "POST /users/{user_id}/identity-providers/{idp_id}/unlink": _STEP_UP,
    "GET /users/{user_id}/identity-providers": None,
    "GET /users/{user_id}/api-keys": None,
    "POST /users/{user_id}/api-keys/revoke": _STEP_UP,
    "POST /users/{user_id}/api-keys/{api_key_id}/revoke": _STEP_UP,
    "GET /users/{user_id}/sessions": None,
    "POST /users/{user_id}/sessions/revoke": _STEP_UP,
    "POST /users/{user_id}/sessions/{session_id}/revoke": _STEP_UP,
    "PUT /users/{user_id}/photo": None,
    "GET /identity-providers/{idp_id}": None,
    "PATCH /identity-providers/{idp_id}": {"name": "hijacked", **_STEP_UP},
    "POST /identity-providers/{idp_id}/delete": _STEP_UP,
    "PUT /identity-providers/{idp_id}/icon": None,
    "DELETE /identity-providers/{idp_id}/icon": None,
}


def _application_routes(app) -> set[str]:
    """Every ``METHOD /path`` of the application whose path names a resource id or a user."""
    found = set()
    for context in iter_route_contexts(app.routes):
        path = context.path or ""
        if not path.startswith(core_config.ROOT_PATH):
            continue
        relative = path.removeprefix(core_config.ROOT_PATH)
        if any(
            name == "user_id" or name.endswith("id") or name.endswith("_slug")
            for name in _PLACEHOLDER.findall(relative)
        ):
            found.update(f"{method} {relative}" for method in context.methods if method not in {"HEAD", "OPTIONS"})
    return found


def _url(route: str, ids: dict[str, str]) -> tuple[str, str]:
    method, path = route.split(" ", 1)
    return method, core_config.ROOT_PATH + _PLACEHOLDER.sub(lambda match: ids[match.group(1)], path)


def _send(client, case_route: str, ids: dict[str, str], body, files) -> Any:
    method, url = _url(case_route, ids)
    kwargs: dict[str, Any] = {"headers": _IF_MATCH}
    if body is not None:
        kwargs["json"] = body
    if files is not None:
        kwargs["files"] = files
    return client.request(method, url, **kwargs)


class TestEveryRouteIsAccountedFor:
    def test_a_route_with_an_id_parameter_is_in_the_matrix_or_the_register(self, app):
        routes = _application_routes(app)
        covered = {case.route for case in CASES} | set(REGISTER) | set(ADMINISTRATOR_ROUTES)

        assert sorted(routes - covered) == []

    def test_every_entry_names_a_route_the_application_has(self, app):
        routes = _application_routes(app)
        listed = {case.route for case in CASES} | set(REGISTER) | set(ADMINISTRATOR_ROUTES)

        assert sorted(listed - routes) == []

    def test_a_route_is_not_both_in_the_matrix_and_the_register(self):
        matrix = {case.route for case in CASES} | set(ADMINISTRATOR_ROUTES)

        assert sorted(matrix & set(REGISTER)) == []


class TestResourcesOfAnotherUser:
    @pytest.mark.parametrize("case", CASES, ids=lambda case: case.label)
    def test_another_users_resource_is_refused_like_a_missing_one_and_stays_as_it_was(
        self, case, world, committed_sessions
    ):
        before = _snapshot(committed_sessions, world)
        ids = {name: str(value) for name, value in world.ids.items()}
        ids.update({name: ids[source] for name, source in case.use.items()})
        absent = dict(ids)
        for name in _PLACEHOLDER.findall(case.route):
            absent[name] = str(uuid.uuid4())

        refused = _send(world.b_client, case.route, ids, case.body, case.files)
        missing = _send(world.b_client, case.route, absent, case.body, case.files)

        assert refused.status_code == case.status, refused.text
        assert missing.status_code == case.status, missing.text
        if case.same_detail:
            assert _shape(refused, ids) == _shape(missing, absent)
        else:
            assert (_problem_type(refused), refused.status_code) == (_problem_type(missing), missing.status_code)
        assert _snapshot(committed_sessions, world) == before


def _shape(response, ids: dict[str, str]) -> Any:
    """The response with the ids the request named replaced and its per-request id dropped.

    Two requests for different ids then compare equal exactly when the answer does not depend on which exists.
    """
    text = re.sub(r'"request_id":"[^"]*"', '"request_id":"-"', response.text)
    for name, value in ids.items():
        text = text.replace(value, f"<{name}>")
    return response.status_code, response.headers.get("content-type"), text


def _problem_type(response) -> str | None:
    return response.json().get("type")


class TestAdministratorRoutes:
    @pytest.mark.parametrize("route", sorted(ADMINISTRATOR_ROUTES))
    def test_a_regular_user_is_refused_by_the_scope_and_a_stays_as_it_was(self, route, world, committed_sessions):
        before = _snapshot(committed_sessions, world)
        ids = {name: str(value) for name, value in world.ids.items()}

        response = _send(world.b_client, route, ids, ADMINISTRATOR_ROUTES[route], None)

        assert response.status_code == 403, response.text
        assert _snapshot(committed_sessions, world) == before


class TestPublicUserRoutes:
    def test_another_user_reads_only_the_public_projection_of_a_profile(self, world):
        response = world.b_client.get(f"{core_config.ROOT_PATH}/users/{world.a.id}")

        assert response.status_code == 200
        assert set(response.json()) == {"id", "name", "username", "city", "photo_path"}

    def test_another_user_reads_only_the_public_projection_in_the_profile_overview(self, world):
        response = world.b_client.get(f"{core_config.ROOT_PATH}/users/{world.a.id}/overview")

        assert response.status_code == 200
        assert set(response.json()["user"]) == {"id", "name", "username", "city", "photo_path"}

    def test_a_stranger_lists_only_the_public_activities_of_a_user(self, world):
        response = world.b_client.get(f"{core_config.ROOT_PATH}/users/{world.a.id}/activities")

        assert response.status_code == 200
        assert [item["id"] for item in response.json()["items"]] == [str(world.ids["public_activity_id"])]
        assert response.json()["total"] == 1

    def test_an_accepted_follower_lists_the_public_and_the_followers_activities(self, world):
        response = world.follower_client.get(f"{core_config.ROOT_PATH}/users/{world.a.id}/activities")

        assert response.status_code == 200
        assert {item["id"] for item in response.json()["items"]} == {
            str(world.ids["public_activity_id"]),
            str(world.ids["followers_activity_id"]),
        }

    def test_the_activity_totals_of_a_user_count_only_what_the_viewer_may_see(self, world):
        url = f"{core_config.ROOT_PATH}/users/{world.a.id}/activities/stats"

        week = {"period": "week", "date": "2025-03-12"}
        stranger = world.b_client.get(url, params=week).json()
        follower = world.follower_client.get(url, params=week).json()

        assert stranger["run"]["distance"] == 10000
        assert follower["run"]["distance"] == 20000

    @pytest.mark.parametrize("listing", ["followers", "following"])
    def test_a_stranger_cannot_list_the_network_of_a_user_and_is_told_nothing_more_than_for_a_missing_user(
        self, listing, world
    ):
        known = world.b_client.get(f"{core_config.ROOT_PATH}/users/{world.a.id}/{listing}")
        missing = world.b_client.get(f"{core_config.ROOT_PATH}/users/{uuid.uuid4()}/{listing}")

        assert (known.status_code, _problem_type(known)) == (404, _NOT_FOUND_TYPE)
        assert (missing.status_code, _problem_type(missing)) == (404, _NOT_FOUND_TYPE)

    @pytest.mark.parametrize("listing", ["followers", "following"])
    def test_an_accepted_follower_may_list_the_network_of_a_user(self, listing, world):
        response = world.follower_client.get(f"{core_config.ROOT_PATH}/users/{world.a.id}/{listing}")

        assert response.status_code == 200

    def test_a_relationship_reports_only_the_callers_own_follows(self, world):
        a_follower = world.ids["follower_id"]

        response = world.b_client.get(f"{core_config.ROOT_PATH}/users/{a_follower}/relationship")

        assert response.json() == {"outgoing": None, "incoming": None, "is_blocked": False}


class TestActivityVisibility:
    @pytest.mark.parametrize(
        ("activity", "stranger", "follower"),
        [("activity_id", 404, 404), ("followers_activity_id", 404, 200), ("public_activity_id", 200, 200)],
        ids=["private", "followers", "public"],
    )
    @pytest.mark.parametrize("suffix", ["", "/detail"], ids=["activity", "detail"])
    def test_an_activity_is_read_only_by_those_its_visibility_admits(self, activity, stranger, follower, suffix, world):
        url = f"{core_config.ROOT_PATH}/activities/{world.ids[activity]}{suffix}"

        seen_by_stranger = world.b_client.get(url)
        seen_by_follower = world.follower_client.get(url)

        assert (seen_by_stranger.status_code, seen_by_follower.status_code) == (stranger, follower)
        for response in (seen_by_stranger, seen_by_follower):
            assert "secret notes" not in response.text

    @pytest.mark.parametrize(
        ("activity", "stranger", "follower"),
        [("activity_id", 0, 0), ("followers_activity_id", 0, 1), ("public_activity_id", 1, 1)],
        ids=["private", "followers", "public"],
    )
    @pytest.mark.parametrize("collection", ["laps", "sets", "workout-steps"])
    def test_the_children_of_an_activity_follow_its_visibility(self, activity, stranger, follower, collection, world):
        url = f"{core_config.ROOT_PATH}/activities/{world.ids[activity]}/{collection}"

        totals = (world.b_client.get(url).json()["total"], world.follower_client.get(url).json()["total"])

        assert totals == (stranger, follower)

    @pytest.mark.parametrize("activity", ["followers_activity_id", "public_activity_id"])
    @pytest.mark.parametrize("viewer", ["b_client", "follower_client"])
    def test_a_viewer_who_may_read_an_activity_may_not_change_or_delete_it(
        self, activity, viewer, world, committed_sessions
    ):
        before = _snapshot(committed_sessions, world)
        url = f"{core_config.ROOT_PATH}/activities/{world.ids[activity]}"
        client = getattr(world, viewer)

        edited = client.patch(url, json={"name": "hijacked"}, headers=_IF_MATCH)
        deleted = client.delete(url, headers=_IF_MATCH)

        assert (edited.status_code, _problem_type(edited)) == (404, _NOT_FOUND_TYPE)
        assert (deleted.status_code, _problem_type(deleted)) == (404, _NOT_FOUND_TYPE)
        assert _snapshot(committed_sessions, world) == before
