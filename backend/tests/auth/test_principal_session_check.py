"""An access token is honoured only while its session exists, with the rights the user has now."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import core.exceptions as core_exceptions
import modules.auth.authentication.principal_service as principal_service
import modules.auth.constants as auth_constants

_MODULE = "modules.auth.authentication.principal_service"


def _token_manager(scope=None):
    claims = {"sub": "1", "sid": "session-1", "scope": scope or list(auth_constants.ADMIN_ACCESS_SCOPE)}
    manager = MagicMock()
    manager.get_token_claim.side_effect = lambda _token, name: claims[name]
    return manager


def _user(access_type="regular"):
    return SimpleNamespace(id=1, username="u", email="u@example.com", active=True, access_type=access_type)


def _resolve(*, session, user, scope=None):
    with (
        patch(f"{_MODULE}.users_integration.require_user", return_value=user),
        patch(f"{_MODULE}.users_integration.require_active_user"),
        patch(f"{_MODULE}.sessions_integration.get_session_by_id_not_expired", return_value=session) as lookup,
    ):
        principal = principal_service.resolve_from_access_token("token", _token_manager(scope), MagicMock())
    return principal, lookup


def test_a_token_of_a_live_session_is_accepted():
    principal, lookup = _resolve(session=SimpleNamespace(user_id=1), user=_user())

    assert principal.user_id == 1
    assert lookup.call_args.args[0] == "session-1"


def test_a_token_whose_session_was_revoked_is_refused():
    """Logging out, revoking sessions or a detected token theft must end the access token too."""
    with pytest.raises(core_exceptions.UnauthenticatedError):
        _resolve(session=None, user=_user())


def test_a_token_naming_another_users_session_is_refused():
    with pytest.raises(core_exceptions.UnauthenticatedError):
        _resolve(session=SimpleNamespace(user_id=2), user=_user())


def test_a_demoted_admin_loses_the_admin_scopes_of_a_token_issued_before():
    principal, _ = _resolve(session=SimpleNamespace(user_id=1), user=_user("regular"))

    assert principal.scopes == frozenset(auth_constants.REGULAR_ACCESS_SCOPE)
    assert "users:write" not in principal.scopes


def test_an_admin_has_the_admin_scopes():
    principal, _ = _resolve(session=SimpleNamespace(user_id=1), user=_user("admin"), scope=[])

    assert principal.scopes == frozenset(auth_constants.ADMIN_ACCESS_SCOPE)
