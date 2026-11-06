"""An access token is honoured only while its session exists, with the rights its scope and the user's role share."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import core.exceptions as core_exceptions
import modules.auth.authentication.principal_service as principal_service
import modules.auth.constants as auth_constants

_MODULE = "modules.auth.authentication.principal_service"


def _token_manager(scope=None):
    claims = {"sub": "1", "sid": "session-1", "scope": scope or " ".join(auth_constants.ADMIN_ACCESS_SCOPE)}
    manager = MagicMock()
    manager.get_token_claim.side_effect = lambda _token, name: claims[name]
    return manager


def _user(access_type="regular"):
    return SimpleNamespace(id=1, username="u", email="u@example.com", active=True, access_type=access_type)


def _resolve(*, session, user, scope=None):
    with (
        patch(f"{_MODULE}.users_integration.get_user", return_value=user),
        patch(f"{_MODULE}.sessions_integration.get_session_by_id_not_expired", return_value=session) as lookup,
    ):
        principal = principal_service.resolve_from_access_token("token", _token_manager(scope), MagicMock())
    return principal, lookup


def test_a_token_of_a_live_session_is_accepted():
    principal, lookup = _resolve(session=SimpleNamespace(user_id=1), user=_user())

    assert principal.user_id == 1
    assert lookup.call_args.args[0] == "session-1"


def test_a_token_of_a_deleted_user_is_an_invalid_token():
    with pytest.raises(core_exceptions.InvalidTokenError):
        _resolve(session=SimpleNamespace(user_id=1), user=None)


def test_a_token_of_a_deactivated_user_is_an_invalid_token():
    user = _user()
    user.active = False

    with pytest.raises(core_exceptions.InvalidTokenError):
        _resolve(session=SimpleNamespace(user_id=1), user=user)


def test_a_token_whose_session_was_revoked_is_refused():
    """Logging out, revoking sessions or a detected token theft must end the access token too."""
    with pytest.raises(core_exceptions.InvalidTokenError):
        _resolve(session=None, user=_user())


def test_a_token_naming_another_users_session_is_refused():
    with pytest.raises(core_exceptions.UnauthenticatedError):
        _resolve(session=SimpleNamespace(user_id=2), user=_user())


def test_a_demoted_admin_loses_the_admin_scopes_of_a_token_issued_before():
    principal, _ = _resolve(session=SimpleNamespace(user_id=1), user=_user("regular"))

    assert principal.scopes == frozenset(auth_constants.REGULAR_ACCESS_SCOPE)
    assert "users:write" not in principal.scopes


def test_an_admin_has_the_admin_scopes():
    principal, _ = _resolve(session=SimpleNamespace(user_id=1), user=_user("admin"))

    assert principal.scopes == frozenset(auth_constants.ADMIN_ACCESS_SCOPE)


def test_a_token_narrower_than_the_role_holds_only_its_own_scopes():
    principal, _ = _resolve(
        session=SimpleNamespace(user_id=1), user=_user("admin"), scope="activities:read profile:export"
    )

    assert principal.scopes == frozenset({"activities:read", "profile:export"})


def test_a_token_cannot_claim_a_scope_its_users_role_lacks():
    principal, _ = _resolve(
        session=SimpleNamespace(user_id=1), user=_user("regular"), scope="activities:read users:write"
    )

    assert principal.scopes == frozenset({"activities:read"})


def test_a_token_scope_the_server_never_mints_grants_nothing():
    principal, _ = _resolve(session=SimpleNamespace(user_id=1), user=_user("admin"), scope="activities:read root")

    assert principal.scopes == frozenset({"activities:read"})


def test_a_token_without_scopes_holds_none():
    principal, _ = _resolve(session=SimpleNamespace(user_id=1), user=_user("admin"), scope=" ")

    assert principal.scopes == frozenset()


def test_a_scope_claim_that_is_not_a_string_is_refused():
    with pytest.raises(core_exceptions.InvalidTokenError):
        _resolve(session=SimpleNamespace(user_id=1), user=_user("admin"), scope=["activities:read"])
