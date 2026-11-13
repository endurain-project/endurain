"""An access token is honoured only while its session exists, with the rights its scope and the user's role share."""

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import core.exceptions as core_exceptions
import modules.auth.authentication.principal_service as principal_service
import modules.auth.constants as auth_constants
import modules.server_settings.contracts as server_settings_contracts
from modules.auth.access_tokens.contracts import TokenType
from tests._helpers.auth import MOCK_USER_ID

_MODULE = "modules.auth.authentication.principal_service"


def _token_manager(scope=None, sub=str(MOCK_USER_ID)):
    claims = {"sub": sub, "sid": "session-1", "scope": scope or " ".join(auth_constants.ADMIN_ACCESS_SCOPE)}
    manager = MagicMock()

    def claim(_token, name, token_type):
        assert token_type is TokenType.ACCESS
        return claims[name]

    manager.get_token_claim.side_effect = claim
    return manager


def _user(access_type="regular"):
    return SimpleNamespace(id=MOCK_USER_ID, username="u", email="u@example.com", active=True, access_type=access_type)


def _policy(*, idle_timeout=None, absolute_timeout=timedelta(days=30)):
    return server_settings_contracts.SessionPolicy(
        access_token_ttl=timedelta(minutes=15),
        refresh_token_ttl=timedelta(days=7),
        idle_timeout=idle_timeout,
        absolute_timeout=absolute_timeout,
        api_key_max_lifetime=timedelta(days=365),
    )


def _session(user_id=MOCK_USER_ID, *, idle_for=timedelta(0), age=timedelta(0)):
    now = datetime.now(UTC)
    return SimpleNamespace(user_id=user_id, last_activity_at=now - idle_for, created_at=now - age)


def _resolve(*, session, user, scope=None, policy=None, sub=str(MOCK_USER_ID)):
    with (
        patch(f"{_MODULE}.users_integration.get_user", return_value=user),
        patch(f"{_MODULE}.sessions_integration.get_session_by_id_not_expired", return_value=session) as lookup,
        patch(
            f"{_MODULE}.server_settings_integration.get_access_policy",
            return_value=server_settings_contracts.AccessPolicy(
                session=policy or _policy(), require_mfa=server_settings_contracts.RequireMfa.OFF
            ),
        ),
    ):
        principal = principal_service.resolve_from_access_token("token", _token_manager(scope, sub), MagicMock())
    return principal, lookup


def test_the_user_is_looked_up_by_the_uuid_in_the_sub_claim():
    other = uuid.uuid4()
    with (
        patch(f"{_MODULE}.users_integration.get_user", return_value=None) as get_user,
        pytest.raises(core_exceptions.InvalidTokenError),
    ):
        principal_service.resolve_from_access_token("token", _token_manager(sub=str(other)), MagicMock())

    assert get_user.call_args.args[0] == other


@pytest.mark.parametrize("sub", ["1", "123456", "not-a-user-id", "", "../1", 7, None])
def test_a_sub_that_is_not_a_user_id_is_refused(sub):
    with pytest.raises(core_exceptions.InvalidTokenError):
        _resolve(session=_session(), user=_user(), sub=sub)


def test_a_token_of_a_live_session_is_accepted():
    principal, lookup = _resolve(session=_session(), user=_user())

    assert principal.user_id == MOCK_USER_ID
    assert lookup.call_args.args[0] == "session-1"


def test_a_token_of_a_deleted_user_is_an_invalid_token():
    with pytest.raises(core_exceptions.InvalidTokenError):
        _resolve(session=_session(), user=None)


def test_a_token_of_a_deactivated_user_is_an_invalid_token():
    user = _user()
    user.active = False

    with pytest.raises(core_exceptions.InvalidTokenError):
        _resolve(session=_session(), user=user)


def test_a_token_whose_session_was_revoked_is_refused():
    """Logging out, revoking sessions or a detected token theft must end the access token too."""
    with pytest.raises(core_exceptions.InvalidTokenError):
        _resolve(session=None, user=_user())


def test_a_token_naming_another_users_session_is_refused():
    with pytest.raises(core_exceptions.UnauthenticatedError):
        _resolve(session=_session(2), user=_user())


def test_a_demoted_admin_loses_the_admin_scopes_of_a_token_issued_before():
    principal, _ = _resolve(session=_session(), user=_user("regular"))

    assert principal.scopes == frozenset(auth_constants.REGULAR_ACCESS_SCOPE)
    assert "users:write" not in principal.scopes


def test_an_admin_has_the_admin_scopes():
    principal, _ = _resolve(session=_session(), user=_user("admin"))

    assert principal.scopes == frozenset(auth_constants.ADMIN_ACCESS_SCOPE)


def test_a_token_narrower_than_the_role_holds_only_its_own_scopes():
    principal, _ = _resolve(session=_session(), user=_user("admin"), scope="activities:read account:export")

    assert principal.scopes == frozenset({"activities:read", "account:export"})


def test_a_token_cannot_claim_a_scope_its_users_role_lacks():
    principal, _ = _resolve(session=_session(), user=_user("regular"), scope="activities:read users:write")

    assert principal.scopes == frozenset({"activities:read"})


def test_a_token_scope_the_server_never_mints_grants_nothing():
    principal, _ = _resolve(session=_session(), user=_user("admin"), scope="activities:read root")

    assert principal.scopes == frozenset({"activities:read"})


def test_a_token_without_scopes_holds_none():
    principal, _ = _resolve(session=_session(), user=_user("admin"), scope=" ")

    assert principal.scopes == frozenset()


def test_a_scope_claim_that_is_not_a_string_is_refused():
    with pytest.raises(core_exceptions.InvalidTokenError):
        _resolve(session=_session(), user=_user("admin"), scope=["activities:read"])


def test_a_session_idle_beyond_the_policy_is_an_invalid_token():
    """The access token outlives the idle window, so the request itself must end the session."""
    with pytest.raises(core_exceptions.InvalidTokenError):
        _resolve(
            session=_session(idle_for=timedelta(hours=2)),
            user=_user(),
            policy=_policy(idle_timeout=timedelta(hours=1)),
        )


def test_a_session_inside_the_idle_window_is_accepted():
    principal, _ = _resolve(
        session=_session(idle_for=timedelta(minutes=30)),
        user=_user(),
        policy=_policy(idle_timeout=timedelta(hours=1)),
    )

    assert principal.user_id == MOCK_USER_ID


def test_inactivity_is_ignored_while_the_idle_timeout_is_off():
    principal, _ = _resolve(session=_session(idle_for=timedelta(days=3)), user=_user(), policy=_policy())

    assert principal.user_id == MOCK_USER_ID


def test_a_session_older_than_the_absolute_timeout_is_an_invalid_token():
    with pytest.raises(core_exceptions.InvalidTokenError):
        _resolve(
            session=_session(age=timedelta(days=40)),
            user=_user(),
            policy=_policy(absolute_timeout=timedelta(days=30)),
        )


def test_a_shortened_policy_applies_to_a_session_that_was_valid_before():
    session = _session(idle_for=timedelta(minutes=90))

    principal, _ = _resolve(session=session, user=_user(), policy=_policy(idle_timeout=timedelta(hours=2)))
    assert principal.user_id == MOCK_USER_ID

    with pytest.raises(core_exceptions.InvalidTokenError):
        _resolve(session=session, user=_user(), policy=_policy(idle_timeout=timedelta(hours=1)))
