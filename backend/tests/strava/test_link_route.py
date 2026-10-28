"""The Strava routes sit behind scope checks, and the long-running ones answer 202."""

from unittest.mock import MagicMock, patch

import pytest

import modules.gears.gear.schema as gears_schema
import modules.strava.router as strava_router
import modules.strava.schema as strava_schema


def _routes():
    return {(route.path, tuple(sorted(route.methods))): route for route in strava_router.router.routes}


def _scopes(route) -> set[str]:
    return {
        scope
        for dependency in route.dependant.dependencies
        if dependency.call is strava_router.auth_dependencies.check_scopes
        for scope in dependency.own_oauth_scopes or []
    }


def test_every_route_checks_a_scope():
    for (path, methods), route in _routes().items():
        assert _scopes(route), f"{methods} {path} has no scope check"


@pytest.mark.parametrize(
    ("path", "method", "scope"),
    [
        ("/import/bikes", "POST", "gears:write"),
        ("/import/shoes", "POST", "gears:write"),
        ("/gear", "POST", "gears:write"),
        ("/activities", "POST", "activities:write"),
        ("/link", "POST", "profile"),
        ("/link", "DELETE", "profile"),
        ("/state", "POST", "profile"),
    ],
)
def test_routes_require_the_matching_scope(path, method, scope):
    assert scope in _scopes(_routes()[(path, (method,))])


@pytest.mark.parametrize(
    ("path", "method"), [("/link", "POST"), ("/gear", "POST"), ("/activities", "POST"), ("/link", "DELETE")]
)
def test_slow_work_is_accepted_not_done_inline(path, method):
    assert _routes()[(path, (method,))].status_code == 202


def test_client_and_state_answer_with_their_bodies():
    with (
        patch.object(strava_router.strava_service, "set_client", return_value=4),
        patch.object(strava_router.strava_service, "begin_state", return_value="s" * 43),
        patch.object(strava_router.strava_service, "clear_state"),
    ):
        client = strava_router.strava_set_user_client(
            request=MagicMock(),
            client=strava_schema.StravaClientCredentials(client_id=1, client_secret="s"),
            token_user_id=7,
            db=MagicMock(),
            response=MagicMock(headers={}),
            if_match='"1"',
        )
        state = strava_router.strava_begin_state(request=MagicMock(), token_user_id=7, oauth_states=MagicMock())
        cleared = strava_router.strava_clear_user_state(request=MagicMock(), token_user_id=7, oauth_states=MagicMock())

    assert client.detail == "Strava client edited successfully"
    assert state.state == "s" * 43
    assert cleared is None


def test_client_credentials_are_validated():
    with pytest.raises(ValueError):
        strava_schema.StravaClientCredentials(client_id=0, client_secret="s")
    with pytest.raises(ValueError):
        strava_schema.StravaClientCredentials(client_id=1, client_secret="")
    with pytest.raises(ValueError):
        strava_schema.StravaClientCredentials(client_id=1, client_secret="s", extra="x")


def test_the_client_secret_does_not_appear_in_a_repr_or_a_validation_error():
    credentials = strava_schema.StravaClientCredentials(client_id=1, client_secret="hunter2-secret")
    assert "hunter2-secret" not in repr(credentials)
    assert credentials.client_secret.get_secret_value() == "hunter2-secret"

    with pytest.raises(ValueError) as error:
        strava_schema.StravaClientCredentials(client_id=0, client_secret="hunter2-secret")
    assert "hunter2-secret" not in str(error.value)


def test_a_link_must_carry_a_state_as_long_as_the_server_issues():
    with pytest.raises(ValueError):
        strava_schema.StravaLinkRequest(state="abc", code="c")


@pytest.mark.parametrize(
    ("route", "gear_type"),
    [
        ("import_bikes_from_strava_export", gears_schema.GearType.BIKE),
        ("import_shoes_from_strava_export", gears_schema.GearType.SHOES),
    ],
)
def test_a_gear_import_reports_how_many_gears_it_created(route, gear_type):
    with patch.object(strava_router.strava_gear_service, "import_gear", return_value=4) as import_gear:
        result = getattr(strava_router, route)(request=MagicMock(), file=MagicMock(), token_user_id=7, db=MagicMock())

    assert result == strava_schema.StravaGearImportResult(imported=4)
    assert import_gear.call_args.args[2] is gear_type


@pytest.mark.parametrize("path", ["/import/bikes", "/import/shoes"])
def test_a_gear_import_declares_its_result_and_still_answers_201(path):
    route = _routes()[(path, ("POST",))]

    assert route.status_code == 201
    assert route.response_model is strava_schema.StravaGearImportResult


def test_setting_the_client_requires_the_version_that_was_read():
    """The credentials are an editable resource, so a write must name the version it read (428 without it)."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import core.database as core_db
    import core.exceptions as core_exceptions
    import modules.auth.dependencies as auth_deps

    app = FastAPI()
    core_exceptions.register_exception_handlers(app)
    app.include_router(strava_router.router, prefix="/strava")
    app.dependency_overrides[auth_deps.check_scopes] = lambda: None
    app.dependency_overrides[auth_deps.get_sub_from_access_token] = lambda: 1
    app.dependency_overrides[core_db.get_db] = lambda: MagicMock()

    with patch.object(strava_router.strava_service, "set_client") as set_client:
        response = TestClient(app).put(
            "/strava/client", json={"client_id": 1, "client_secret": "s"}, headers={"Authorization": "Bearer x"}
        )

    assert response.status_code == 428
    set_client.assert_not_called()


def test_clearing_the_state_answers_no_content():
    assert _routes()[("/state", ("DELETE",))].status_code == 204
