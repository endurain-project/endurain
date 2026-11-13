"""A link that a user started is completed only while the account, the starting session and the generation hold.

The flow runs through the real start (``stage_browser_link``), the real security transitions and the real callback.
The database is mocked, so the account security generations and the session lookup are the test doubles.
"""

import uuid
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import jasil.testing as jasil_testing
import pytest

import modules.auth.account_security.account_security_service as account_security_service
import modules.auth.identity_providers.authorization_service as authorization_service
import modules.auth.identity_providers.callback_service as callback_service
import modules.auth.identity_providers.contracts as identity_provider_contracts
import modules.auth.identity_providers.integration_service as idp_integration
import modules.auth.oauth_state.constants as oauth_state_constants
import modules.auth.security_generation.integration_service as security_generation_integration
from modules.auth.identity_providers.audit_actions import IdentityLinkRefusal
from tests._helpers.auth import MOCK_USER_ID, OTHER_USER_ID

IDP_ID = uuid.uuid4()

HOST = "https://app.example.com"
USER_ID = MOCK_USER_ID
SESSION_ID = uuid.UUID("11111111-2222-3333-4444-555555555555")
_ACCOUNT_SECURITY = "modules.auth.account_security.account_security_service."
_LINK_AUDIT = "auth.identity_link.link"
_FAILED_LINK_URL = f"{HOST}/settings?idp_link=error"
_BOTH = pytest.mark.parametrize("ends_other_sessions", [True, False], ids=["ends-others", "keeps-others"])


@pytest.fixture
def service():
    return callback_service.CallbackService(MagicMock(), MagicMock(), MagicMock(), HOST)


def _idp():
    return identity_provider_contracts.IdentityProviderState.model_construct(
        id=IDP_ID, name="Test IdP", slug="test", enabled=True, authorization_endpoint="https://idp.example.com/auth"
    )


def _start_link(ends_other_sessions: bool) -> SimpleNamespace:
    """Start a link through the real staging code and return the OAuth state it stores.

    The generation is read the way the start workflow reads it, before the staging.
    """
    generation = security_generation_integration.current_generation(USER_ID, MagicMock())
    authorization = authorization_service.AuthorizationService(MagicMock(), HOST)
    with (
        patch.object(authorization_service.idp_crud, "get_identity_provider", return_value=_idp()),
        patch.object(idp_integration, "_authorization_service", return_value=authorization),
        patch.object(authorization_service.oauth_state_integration, "create_oauth_state") as create_state,
    ):
        idp_integration.stage_browser_link(
            USER_ID,
            IDP_ID,
            "/settings",
            "10.0.0.1",
            SESSION_ID,
            ends_other_sessions,
            MagicMock(),
            security_generation=generation,
        )
    stored = create_state.call_args.kwargs
    return SimpleNamespace(
        nonce="nonce",
        client_type="web",
        redirect_path="/settings",
        idp_id=IDP_ID,
        id="state-id",
        **{
            key: stored[key]
            for key in (
                "user_id",
                "purpose",
                "session_id",
                "ends_other_sessions",
                "security_generation",
                "idp_code_verifier",
            )
        },
    )


def _callback(service, oauth_state, *, user=None, session="alive"):
    """Run the callback of the link; return its URL, the audit, the link creation and the session deletion."""
    user = SimpleNamespace(id=USER_ID, username="alice", active=True) if user is None else user
    session = SimpleNamespace(user_id=USER_ID) if session == "alive" else session
    oauth_client = MagicMock()
    oauth_client.fetch_token.return_value = {"access_token": "at"}
    idp = MagicMock(
        id=IDP_ID,
        slug="test",
        provider_type="oauth2",
        issuer_url=None,
        userinfo_endpoint="https://x/userinfo",
        sync_user_info=False,
        sync_email=False,
    )
    idp.name = "Test"
    db = MagicMock()
    with ExitStack() as stack:
        enter = stack.enter_context
        enter(patch.object(service._oidc, "decrypt_client_id", return_value="cid"))
        enter(patch.object(service._oidc, "decrypt_client_secret", return_value="secret"))
        enter(patch.object(service._oidc, "resolve_token_endpoint", return_value="https://x/token"))
        enter(patch.object(service._oidc, "create_oauth_client", return_value=oauth_client))
        enter(patch.object(service._oidc, "get_userinfo", return_value={"sub": "s"}))
        enter(patch.object(callback_service.users_integration, "get_user", return_value=user))
        enter(patch.object(callback_service.sessions_integration, "lock_live_session", return_value=session))
        enter(
            patch.object(
                callback_service.identity_provider_links_integration,
                "get_user_identity_provider_by_subject_and_idp_id",
                return_value=None,
            )
        )
        create_link = enter(
            patch.object(callback_service.identity_provider_links_integration, "create_user_identity_provider")
        )
        enter(patch.object(callback_service.idp_event_publishers, "publish_idp_linked"))
        enter(patch.object(callback_service.user_provisioning_service, "update_user_from_idp", return_value=user))
        delete_sessions = enter(
            patch.object(callback_service.sessions_integration, "delete_sessions_by_user", return_value=2)
        )
        audit = enter(jasil_testing.capture_audit())
        url = service.complete_callback(
            idp,
            "code",
            None,
            "state",
            oauth_state,
            "ip",
            "agent",
            MagicMock(),
            db,
        )
    return url, audit, create_link, delete_sessions, db


def _sign_out_everywhere():
    with (
        patch(_ACCOUNT_SECURITY + "sessions_integration.delete_sessions_by_user", return_value=1),
        patch(_ACCOUNT_SECURITY + "_stage_sessions_revoked"),
    ):
        account_security_service.sign_out_everywhere(USER_ID, MagicMock())


def _change_own_password():
    user = MagicMock(access_type="regular", username="alice", email="alice@example.com")
    with (
        patch(_ACCOUNT_SECURITY + "step_up_service.verify_step_up_credentials"),
        patch(_ACCOUNT_SECURITY + "server_settings_integration.get_server_settings"),
        patch(_ACCOUNT_SECURITY + "credentials_integration.has_local_password", return_value=True),
        patch(_ACCOUNT_SECURITY + "credentials_integration.ensure_password_differs_from_current"),
        patch(_ACCOUNT_SECURITY + "users_integration.require_user", return_value=user),
        patch(_ACCOUNT_SECURITY + "credentials_integration.validate_and_hash_password_for_user", return_value="hash"),
        patch(_ACCOUNT_SECURITY + "credentials_integration.set_local_password_hash"),
        patch(_ACCOUNT_SECURITY + "authentication_integration.clear_account_login_lockout"),
        patch(_ACCOUNT_SECURITY + "sessions_integration.delete_sessions_by_user", return_value=0),
        patch(_ACCOUNT_SECURITY + "_stage_credential_changed"),
        patch(_ACCOUNT_SECURITY + "password_reset_tokens_integration.revoke_unused_tokens"),
    ):
        account_security_service.stage_change_own_password(
            USER_ID,
            "old-pass",
            "new-pass",
            None,
            MagicMock(),
            MagicMock(),
            revoke_other_sessions=False,
            current_session_id=SESSION_ID,
        )


def _assert_refused(url, audit, create_link, delete_sessions, db, reason):
    assert url == _FAILED_LINK_URL
    create_link.assert_not_called()
    delete_sessions.assert_not_called()
    db.commit.assert_not_called()
    entry = audit.assert_audited(
        _LINK_AUDIT,
        outcome="denied",
        target_type="user",
        target_id=str(USER_ID),
        target_owner_id=str(USER_ID),
    )
    assert entry.details == {"idp_id": str(IDP_ID), "reason": reason}
    audit.assert_not_audited("auth.session.revoke")


class TestStart:
    @_BOTH
    def test_the_state_records_the_starting_session_and_whether_the_callback_ends_the_others(self, ends_other_sessions):
        state = _start_link(ends_other_sessions)

        assert state.purpose == oauth_state_constants.OAuthStatePurpose.LINK
        assert state.session_id == SESSION_ID
        assert state.ends_other_sessions is ends_other_sessions

    def test_the_state_records_the_generation_it_started_under(self, security_generations):
        security_generations.generations[USER_ID] = 3

        assert _start_link(False).security_generation == 3


class TestUnchangedAccount:
    @_BOTH
    def test_the_link_is_made_and_the_other_sessions_end_only_when_asked(
        self, service, security_generations, ends_other_sessions
    ):
        security_generations.generations[USER_ID] = 5
        state = _start_link(ends_other_sessions)

        url, _, create_link, delete_sessions, db = _callback(service, state)

        assert url == f"{HOST}/settings?idp_link=success&idp_name=Test"
        create_link.assert_called_once()
        db.commit.assert_called_once()
        if ends_other_sessions:
            delete_sessions.assert_called_once_with(USER_ID, db, exclude_session_id=SESSION_ID)
        else:
            delete_sessions.assert_not_called()


class TestChangedAccount:
    @_BOTH
    @pytest.mark.parametrize(
        "transition",
        [_sign_out_everywhere, _change_own_password],
        ids=["sign-out-everywhere", "own-password-change"],
    )
    def test_a_security_change_after_the_start_creates_no_link(
        self, service, security_generations, ends_other_sessions, transition
    ):
        state = _start_link(ends_other_sessions)

        transition()
        assert security_generations.bumps == [USER_ID]
        _assert_refused(*_callback(service, state), IdentityLinkRefusal.SECURITY_CHANGED)

    @_BOTH
    def test_an_administrator_deactivating_the_account_bumps_the_generation_and_creates_no_link(
        self, service, security_generations, ends_other_sessions
    ):
        # The users edit path is too heavy to drive here; the bump it stages is seeded on the fixture.
        state = _start_link(ends_other_sessions)
        security_generations.stage_bump(USER_ID, MagicMock())

        _assert_refused(*_callback(service, state), IdentityLinkRefusal.SECURITY_CHANGED)

    @_BOTH
    def test_ending_the_starting_session_alone_creates_no_link(
        self, service, security_generations, ends_other_sessions
    ):
        state = _start_link(ends_other_sessions)

        _assert_refused(*_callback(service, state, session=None), IdentityLinkRefusal.SESSION_ENDED)
        assert security_generations.bumps == []

    @_BOTH
    def test_another_users_session_is_not_the_starting_session(self, service, ends_other_sessions):
        state = _start_link(ends_other_sessions)

        _assert_refused(
            *_callback(service, state, session=SimpleNamespace(user_id=OTHER_USER_ID)),
            IdentityLinkRefusal.SESSION_ENDED,
        )

    @_BOTH
    def test_an_inactive_account_creates_no_link(self, service, ends_other_sessions):
        state = _start_link(ends_other_sessions)
        inactive = SimpleNamespace(id=USER_ID, username="alice", active=False)

        _assert_refused(*_callback(service, state, user=inactive), IdentityLinkRefusal.USER_INACTIVE)

    def test_a_state_without_a_stamp_creates_no_link(self, service):
        state = _start_link(True)
        state.security_generation = None

        _assert_refused(*_callback(service, state), IdentityLinkRefusal.SECURITY_CHANGED)


class TestStaleFlowLocks:
    """The generation row is locked first and the starting session's row second, both until the commit."""

    @staticmethod
    def _state():
        return SimpleNamespace(session_id=SESSION_ID, security_generation=0)

    def test_the_session_is_read_with_a_lock_after_the_generation_is_locked(self):
        user = SimpleNamespace(id=USER_ID, active=True)
        order = MagicMock()
        with (
            patch.object(
                callback_service.security_generation_integration, "matches_locked", return_value=True
            ) as matches_locked,
            patch.object(
                callback_service.sessions_integration,
                "lock_live_session",
                return_value=SimpleNamespace(user_id=USER_ID),
            ) as lock_session,
            patch.object(callback_service.sessions_integration, "get_session_by_id_not_expired") as plain_read,
        ):
            order.attach_mock(matches_locked, "lock_generation")
            order.attach_mock(lock_session, "lock_session")
            reason = callback_service._stale_flow(user, self._state(), MagicMock())

        assert reason is None
        assert [call[0] for call in order.mock_calls] == ["lock_generation", "lock_session"]
        plain_read.assert_not_called()

    def test_a_changed_generation_is_reported_before_the_session_is_locked(self):
        user = SimpleNamespace(id=USER_ID, active=True)
        with (
            patch.object(callback_service.security_generation_integration, "matches_locked", return_value=False),
            patch.object(callback_service.sessions_integration, "lock_live_session") as lock_session,
        ):
            reason = callback_service._stale_flow(user, self._state(), MagicMock())

        assert reason == callback_service._StaleFlow.SECURITY_CHANGED
        lock_session.assert_not_called()

    def test_an_inactive_user_locks_nothing(self):
        user = SimpleNamespace(id=USER_ID, active=False)
        with (
            patch.object(callback_service.security_generation_integration, "matches_locked") as matches_locked,
            patch.object(callback_service.sessions_integration, "lock_live_session") as lock_session,
        ):
            reason = callback_service._stale_flow(user, self._state(), MagicMock())

        assert reason == callback_service._StaleFlow.USER_INACTIVE
        matches_locked.assert_not_called()
        lock_session.assert_not_called()

    def test_an_ended_session_is_reported_once_the_generation_matches(self):
        user = SimpleNamespace(id=USER_ID, active=True)
        with (
            patch.object(callback_service.security_generation_integration, "matches_locked", return_value=True),
            patch.object(callback_service.sessions_integration, "lock_live_session", return_value=None),
        ):
            reason = callback_service._stale_flow(user, self._state(), MagicMock())

        assert reason == callback_service._StaleFlow.SESSION_ENDED
