"""The Strava routes sit behind the access-token check."""

import modules.strava.router as strava_router


def test_the_link_route_requires_authentication():
    deps = {d.call for d in strava_router.router.routes[0].dependant.dependencies}
    assert strava_router.auth_dependencies.validate_access_token in deps


def test_client_and_state_answer_with_a_detail_body():
    from unittest.mock import MagicMock, patch

    import modules.strava.schema as strava_schema

    with (
        patch.object(strava_router.strava_service, "set_client"),
        patch.object(strava_router.strava_service, "set_state"),
    ):
        client = strava_router.strava_set_user_client(
            request=MagicMock(),
            client=strava_schema.StravaClient(client_id=1, client_secret="s"),
            _validate_access_token=None,
            token_user_id=7,
            db=MagicMock(),
        )
        state = strava_router.strava_set_user_unique_state(
            request=MagicMock(), state="abc", _validate_access_token=None, token_user_id=7, db=MagicMock()
        )

    assert client.detail == "Strava client for user 7 edited successfully"
    assert state.detail == "Strava state for user 7 edited successfully"
