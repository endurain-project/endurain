"""A job is read with the scope of the route that starts it."""

import pytest
from fastapi.routing import APIRoute
from fastapi.security import SecurityScopes

import modules.activities.activity.router as activity_router
import modules.activities.activity_ingestion.router as ingestion_router
import modules.garmin.router as garmin_router
import modules.gears.gear.router as gear_router
import modules.jobs.schema as jobs_schema
import modules.jobs.service as jobs_service
import modules.strava.router as strava_router
import modules.users.users_profile.router as profile_router

_Kind = jobs_schema.JobKind

#: Each kind and the routes that start it, as ``(router module, method, path)``.
_STARTING_ROUTES = {
    _Kind.ACTIVITY_UPLOAD: [(ingestion_router, "POST", "/upload")],
    _Kind.ACTIVITY_REFRESH: [
        (ingestion_router, "POST", "/refresh"),
        (garmin_router, "POST", "/activities"),
        (strava_router, "POST", "/activities"),
    ],
    _Kind.ACTIVITY_BULK_IMPORT: [
        (ingestion_router, "POST", "/bulk-import"),
        (ingestion_router, "POST", "/bulk-import/folder"),
    ],
    _Kind.ACTIVITIES_BULK_EDIT: [(activity_router, "PATCH", "")],
    _Kind.GARMIN_LINK: [(garmin_router, "POST", "/link")],
    _Kind.GARMIN_SYNC_GEAR: [(garmin_router, "POST", "/gear")],
    _Kind.GARMIN_SYNC_HEALTH: [(garmin_router, "POST", "/health")],
    _Kind.STRAVA_LINK: [(strava_router, "POST", "/link")],
    _Kind.STRAVA_GEAR: [(strava_router, "POST", "/gear")],
    _Kind.STRAVA_UNLINK: [(strava_router, "POST", "/unlink")],
    _Kind.PROFILE_EXPORT: [(profile_router, "POST", "/export")],
    _Kind.PROFILE_IMPORT: [(profile_router, "POST", "/import")],
    _Kind.GEAR_DELETION: [(gear_router, "DELETE", "/{gear_id}")],
}

#: Started by an administrator (``users:write``) or by the user themselves (``account:security``) and read by
#: administrators through ``users:read-all``, so no single starting scope names it.
_READ_BY_ADMINISTRATORS = {_Kind.USER_DELETION}


def _scopes_of(module, method: str, path: str) -> set[str]:
    route = next(
        route
        for route in module.router.routes
        if isinstance(route, APIRoute) and route.path == path and method in route.methods
    )
    scopes: set[str] = set()
    for dependency in route.dependencies:
        scopes.update(SecurityScopes(getattr(dependency, "scopes", None) or []).scopes)
    return scopes


def test_every_kind_is_covered_by_this_table():
    assert set(_STARTING_ROUTES) | _READ_BY_ADMINISTRATORS == set(_Kind)


@pytest.mark.parametrize(("kind", "routes"), _STARTING_ROUTES.items(), ids=[kind.value for kind in _STARTING_ROUTES])
def test_a_kind_is_read_with_the_scope_of_the_route_that_starts_it(kind, routes):
    required = [_scopes_of(*route) for route in routes]

    assert all(len(scopes) == 1 for scopes in required)
    assert {scope for (scope,) in required} == {jobs_service._RULES[kind].scope}
