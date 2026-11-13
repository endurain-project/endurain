"""The Strava routes sit behind scope checks, and the long-running ones answer 202."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import Response

import modules.gears.gear.schema as gears_schema
import modules.strava.router as strava_router
import modules.strava.schema as strava_schema
from tests._helpers.auth import MOCK_USER_ID


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
        ("/import/gear", "POST", "gears:write"),
        ("/gear", "POST", "gears:write"),
        ("/activities", "POST", "activities:write"),
        ("/link", "POST", "account:integrations"),
        ("/link", "DELETE", "account:integrations"),
        ("/state", "POST", "account:integrations"),
        ("/client", "PUT", "account:integrations"),
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
    ):
        client_result = strava_router.strava_set_user_client(
            request=MagicMock(),
            client=strava_schema.StravaClientCredentials(client_id=1, client_secret="s"),
            token_user_id=MOCK_USER_ID,
            db=MagicMock(),
            response=MagicMock(headers={}),
            if_match='"1"',
        )
        state = strava_router.strava_begin_state(
            request=MagicMock(), token_user_id=MOCK_USER_ID, oauth_states=MagicMock()
        )

    assert client_result is None
    assert state.state == "s" * 43


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
        strava_schema.StravaLinkRequest(state="abc", code="c", scope="read")


@pytest.mark.parametrize(
    ("gear_type", "expected"),
    [
        (strava_schema.StravaGearImportType.BIKE, gears_schema.GearType.BIKE),
        (strava_schema.StravaGearImportType.SHOES, gears_schema.GearType.SHOES),
    ],
)
def test_a_gear_import_reports_how_many_gears_it_created(gear_type, expected):
    with patch.object(strava_router.strava_gear_service, "import_gear", return_value=4) as import_gear:
        result = strava_router.import_gear_from_strava_export(
            request=MagicMock(), file=MagicMock(), gear_type=gear_type, token_user_id=MOCK_USER_ID, db=MagicMock()
        )

    assert result == strava_schema.StravaGearImportResult(imported=4)
    assert import_gear.call_args.args[2] is expected


def test_a_gear_import_declares_its_result_and_still_answers_201():
    route = _routes()[("/import/gear", ("POST",))]

    assert route.status_code == 201
    assert route.response_model is strava_schema.StravaGearImportResult


def test_the_per_type_gear_imports_and_the_state_delete_are_gone():
    routes = _routes()

    assert ("/import/bikes", ("POST",)) not in routes
    assert ("/import/shoes", ("POST",)) not in routes
    assert ("/state", ("DELETE",)) not in routes


@pytest.mark.parametrize("gear_type", ["wetsuit", "ski", "1", ""])
def test_only_bikes_and_shoes_can_be_imported(gear_type):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import core.exceptions as core_exceptions
    import modules.auth.dependencies as auth_deps

    app = FastAPI()
    core_exceptions.register_exception_handlers(app)
    app.include_router(strava_router.router, prefix="/strava")
    app.dependency_overrides[auth_deps.check_scopes] = lambda: None
    app.dependency_overrides[auth_deps.get_current_user_id] = lambda: MOCK_USER_ID

    response = TestClient(app).post(f"/strava/import/gear?gear_type={gear_type}", files={"file": ("g.csv", b"x")})

    assert response.status_code == 422


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
    app.dependency_overrides[auth_deps.get_current_user_id] = lambda: MOCK_USER_ID
    app.dependency_overrides[core_db.get_db] = lambda: MagicMock()

    with patch.object(strava_router.strava_service, "set_client") as set_client:
        response = TestClient(app).put(
            "/strava/client", json={"client_id": 1, "client_secret": "s"}, headers={"Authorization": "Bearer x"}
        )

    assert response.status_code == 428
    set_client.assert_not_called()


@pytest.mark.parametrize(
    ("call", "queued", "kind"),
    [
        ("strava_link", "start_link", "strava_link"),
        ("strava_retrieve_gear", "request_gear_sync", "strava_gear"),
        ("strava_unlink", "request_unlink", "strava_unlink"),
    ],
)
def test_a_queued_sync_names_its_job_in_content_location(call, queued, kind):
    status = strava_schema.StravaSyncStatus.model_validate(
        {"id": "job-1", "kind": kind, "created_at": "2026-01-01T00:00:00Z", "status": "queued"}
    )
    response = Response()
    kwargs = {"request": MagicMock(), "response": response, "token_user_id": MOCK_USER_ID, "sync_states": MagicMock()}
    if call == "strava_link":
        kwargs.update(link=MagicMock(), oauth_states=MagicMock())
        service = strava_router.strava_link_service
    else:
        kwargs.update(db=MagicMock(), rate_limits=MagicMock())
        service = strava_router.strava_sync_service
    with (
        patch.object(service, queued, return_value=status),
        patch.object(strava_router.core_location, "set_job_location") as set_location,
    ):
        result = getattr(strava_router, call)(**kwargs)

    assert result is status
    assert set_location.call_args.args[:1] == (response,)
    assert set_location.call_args.args[2] == "job-1"


def test_the_per_kind_status_route_is_gone():
    assert not [path for path, _methods in _routes() if path.startswith("/sync")]
