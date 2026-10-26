"""The Strava routes sit behind scope checks, and the long-running ones answer 202."""

from unittest.mock import MagicMock, patch

import pytest

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
        ("/link", "PUT", "profile"),
        ("/unlink", "DELETE", "profile"),
    ],
)
def test_routes_require_the_matching_scope(path, method, scope):
    assert scope in _scopes(_routes()[(path, (method,))])


@pytest.mark.parametrize(("path", "method"), [("/gear", "POST"), ("/activities", "POST"), ("/unlink", "DELETE")])
def test_slow_work_is_accepted_not_done_inline(path, method):
    assert _routes()[(path, (method,))].status_code == 202


def test_client_and_state_answer_with_a_detail_body():
    with (
        patch.object(strava_router.strava_service, "set_client"),
        patch.object(strava_router.strava_service, "set_state"),
        patch.object(strava_router.strava_service, "clear_state"),
    ):
        client = strava_router.strava_set_user_client(
            request=MagicMock(),
            client=strava_schema.StravaClientCredentials(client_id=1, client_secret="s"),
            token_user_id=7,
            db=MagicMock(),
        )
        state = strava_router.strava_set_user_unique_state(
            request=MagicMock(), state="abc", token_user_id=7, oauth_states=MagicMock()
        )
        cleared = strava_router.strava_clear_user_state(request=MagicMock(), token_user_id=7, oauth_states=MagicMock())

    assert client.detail == "Strava client edited successfully"
    assert state.detail == "Strava state edited successfully"
    assert cleared.detail == "Strava state cleared successfully"


def test_client_credentials_are_validated():
    with pytest.raises(ValueError):
        strava_schema.StravaClientCredentials(client_id=0, client_secret="s")
    with pytest.raises(ValueError):
        strava_schema.StravaClientCredentials(client_id=1, client_secret="")
    with pytest.raises(ValueError):
        strava_schema.StravaClientCredentials(client_id=1, client_secret="s", extra="x")
