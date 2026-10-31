"""Strava link is only reachable by the user who owns the state."""

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

import modules.strava.router as strava_router


def _link(token_user_id: int, owner_id: int = 1):
    integrations = SimpleNamespace(user_id=owner_id, strava_client_id="id", strava_client_secret="secret")
    with (
        patch.object(
            strava_router.user_integrations_crud, "get_user_integrations_by_strava_state", return_value=integrations
        ),
        patch.object(strava_router.user_integrations_crud, "link_strava_account") as link,
        patch.object(strava_router.user_integrations_crud, "unlink_strava_account") as unlink,
        patch.object(strava_router.strava_utils, "create_strava_client"),
        patch.object(strava_router.core_cryptography, "decrypt_token_fernet", return_value="x"),
    ):
        error = None
        try:
            asyncio.run(
                strava_router.strava_link(
                    state="s",
                    code="c",
                    _validate_access_token=None,
                    _check_scopes=None,
                    token_user_id=token_user_id,
                    db=MagicMock(),
                )
            )
        except HTTPException as exc:
            error = exc
        return link, unlink, error


def test_the_owner_can_link():
    link, unlink, error = _link(token_user_id=1)
    assert error is None
    link.assert_called_once()
    unlink.assert_not_called()


def test_another_users_state_is_refused_and_left_untouched():
    link, unlink, error = _link(token_user_id=2)
    assert error is not None and error.status_code == 404
    link.assert_not_called()
    unlink.assert_not_called()


def test_the_route_requires_authentication():
    deps = {d.call for d in strava_router.router.routes[0].dependant.dependencies}
    assert strava_router.auth_dependencies.validate_access_token in deps
