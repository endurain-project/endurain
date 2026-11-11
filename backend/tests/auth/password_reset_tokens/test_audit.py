"""Audit rows and the completion event of a password reset."""

from unittest.mock import MagicMock, patch

import jasil.audit as jasil_audit
import jasil.publisher as platform_publisher
import jasil.testing as jasil_testing
import pytest
from jasil.backends.state_memory import MemoryState
from jasil.providers import StateBackendUnavailableError
from sqlalchemy.orm import Session

import core.email_cooldown as core_email_cooldown
import core.exceptions as core_exceptions
import modules.auth.password_reset_tokens.audit_actions as password_reset_audit_actions
import modules.auth.password_reset_tokens.events as password_reset_events
import modules.auth.password_reset_tokens.service as password_reset_service
from tests._helpers.db import create_sqlite_session_factory, ensure_user


def test_a_reset_is_audited_and_announced(mock_db):
    with (
        patch.object(password_reset_service.password_reset_crud, "claim_password_reset_token", return_value=7),
        patch.object(password_reset_service.server_settings_integration, "get_server_settings"),
        patch.object(password_reset_service.users_integration, "require_user") as require_user,
        patch.object(password_reset_service, "_may_reset_password", return_value=True),
        patch.object(password_reset_service.credentials_integration, "ensure_password_differs_from_current"),
        patch.object(password_reset_service.credentials_integration, "validate_and_hash_password_for_user"),
        patch.object(password_reset_service.credentials_integration, "set_local_password_hash"),
        patch.object(password_reset_service.password_reset_crud, "mark_user_password_reset_tokens_used"),
        patch.object(password_reset_service.sessions_integration, "delete_sessions_by_user"),
        patch.object(password_reset_service.authentication_integration, "clear_account_login_lockout") as clear_lock,
        patch.object(password_reset_service.lockout_integration, "clear_step_up_account_lockout") as clear_step_up,
        patch.object(platform_publisher, "publish_on_commit") as publish,
        jasil_testing.capture_audit() as audit,
    ):
        require_user.return_value.access_type = "regular"
        require_user.return_value.username = "alice"
        password_reset_service.use_password_reset_token("raw-token", "new-password", mock_db)

    clear_lock.assert_called_once_with("alice")
    clear_step_up.assert_called_once_with(7)
    audit.assert_audited(
        password_reset_audit_actions.PASSWORD_RESET.id, target_type="user", target_id="7", target_owner_id="7"
    )
    publish.assert_called_once()
    assert publish.call_args.args[0] == "auth.password_reset_completed"
    assert publish.call_args.args[1] == {"user_id": 7}


def test_a_reset_revokes_the_users_api_keys(mock_db):
    """Whoever held the old password may hold a key, so a recovery ends the keys with the sessions."""
    with (
        patch.object(password_reset_service.password_reset_crud, "claim_password_reset_token", return_value=7),
        patch.object(password_reset_service.server_settings_integration, "get_server_settings"),
        patch.object(password_reset_service.users_integration, "require_user") as require_user,
        patch.object(password_reset_service, "_may_reset_password", return_value=True),
        patch.object(password_reset_service.credentials_integration, "ensure_password_differs_from_current"),
        patch.object(password_reset_service.credentials_integration, "validate_and_hash_password_for_user"),
        patch.object(password_reset_service.credentials_integration, "set_local_password_hash"),
        patch.object(password_reset_service.password_reset_crud, "mark_user_password_reset_tokens_used"),
        patch.object(password_reset_service.sessions_integration, "delete_sessions_by_user"),
        patch.object(password_reset_service.authentication_integration, "clear_account_login_lockout"),
        patch.object(password_reset_service.api_keys_integration, "revoke_user_api_keys") as revoke_keys,
        patch.object(platform_publisher, "publish_on_commit"),
    ):
        require_user.return_value.access_type = "regular"
        require_user.return_value.username = "alice"
        password_reset_service.use_password_reset_token("raw-token", "new-password", mock_db)

    revoke_keys.assert_called_once_with(7, mock_db)


def test_an_invalid_token_is_recorded_without_a_target(mock_db):
    with (
        patch.object(
            password_reset_service.server_settings_integration,
            "get_server_settings",
            return_value=MagicMock(password_breach_check_enabled=False),
        ),
        patch.object(password_reset_service.password_reset_crud, "claim_password_reset_token", return_value=None),
        jasil_testing.capture_audit() as audit,
        pytest.raises(core_exceptions.InvalidInputError),
    ):
        password_reset_service.use_password_reset_token("raw-token", "new-password", mock_db)

    entry = audit.assert_audited(password_reset_audit_actions.PASSWORD_RESET.id, outcome="failure")
    assert entry.target_type is None
    assert "raw-token" not in repr(entry)


_REQUEST = password_reset_audit_actions.PASSWORD_RESET_REQUEST.id
_SERVICE = "modules.auth.password_reset_tokens.service"
_IP = "203.0.113.7"
_AGENT = "reset-test-agent/1.0"
_HOST = "https://example.test"


class TestResetRequest:
    """The request does the same work for every address and records nothing about the account."""

    @pytest.fixture(autouse=True)
    def _collaborators(self):
        with (
            patch(f"{_SERVICE}.server_settings_integration.is_mail_configured", return_value=True),
            patch(f"{_SERVICE}.server_settings_integration.get_server_settings") as settings,
            patch(f"{_SERVICE}.credentials_integration.has_local_password") as has_password,
            patch(f"{_SERVICE}.core_email_cooldown.claim_email") as claim,
            patch.object(platform_publisher, "publish_on_commit") as publish,
        ):
            self.settings, self.has_password, self.claim, self.publish = settings, has_password, claim, publish
            yield

    @pytest.mark.parametrize("known", [True, False])
    def test_stages_one_event_and_nothing_else_for_any_address(self, mock_db, known):
        user = MagicMock(id=9, active=True) if known else None
        with (
            patch(f"{_SERVICE}.users_integration.get_user_by_email", return_value=user) as lookup,
            jasil_testing.capture_audit() as audit,
        ):
            password_reset_service.request_password_reset_email("user@example.com", _IP, _AGENT, mock_db)

        lookup.assert_called_once_with("user@example.com", mock_db)
        self.publish.assert_called_once()
        assert self.publish.call_args.args[0] == "auth.password_reset_requested"
        assert self.publish.call_args.args[1] == {
            "user_id": 9 if known else None,
            "ip_address": _IP,
            "user_agent": _AGENT,
        }
        assert "user@example.com" not in repr(self.publish.call_args)
        mock_db.commit.assert_called_once()
        self.claim.assert_not_called()
        self.settings.assert_not_called()
        self.has_password.assert_not_called()
        assert audit.entries == []

    def test_mail_not_configured_is_a_domain_error_and_adds_no_row(self, mock_db):
        with (
            patch(f"{_SERVICE}.server_settings_integration.is_mail_configured", return_value=False),
            jasil_testing.capture_audit() as audit,
            pytest.raises(core_exceptions.ServiceUnavailableError),
        ):
            password_reset_service.request_password_reset_email("user@example.com", _IP, _AGENT, mock_db)

        audit.assert_not_audited(_REQUEST)
        self.publish.assert_not_called()


def _payload(user_id):
    return password_reset_events.PasswordResetRequestedPayload(user_id=user_id, ip_address=_IP, user_agent=_AGENT)


def _active_user(**fields):
    return MagicMock(
        id=9, active=True, access_type="regular", preferred_language="en", name="Ana", email="ana@x.test", **fields
    )


class TestResetWorkerAudit:
    """The worker decides, and every row it writes names the requester's client."""

    @pytest.fixture
    def factory(self):
        session_factory = create_sqlite_session_factory()
        ensure_user(session_factory, 9)
        yield session_factory
        session_factory.kw["bind"].dispose()

    @staticmethod
    def _run(factory, payload, *, state=None, event_id="event-1", user=None, may_reset=True):
        with (
            patch(f"{_SERVICE}.users_integration.get_user", return_value=user),
            patch.object(password_reset_service, "_may_reset_password", return_value=may_reset),
            patch(
                f"{_SERVICE}.password_reset_email_messages.get_password_reset_email",
                return_value=("subject", "html", "text"),
            ),
            factory() as db,
        ):
            return password_reset_service.prepare_password_reset_email(
                payload, event_id, _HOST, state if state is not None else MemoryState(), db
            )

    @staticmethod
    def _requests(audit):
        return audit.matching(_REQUEST)

    def test_an_unknown_address_is_a_failure_without_a_target(self, factory):
        with jasil_testing.capture_audit() as audit:
            assert self._run(factory, _payload(None)) is None

        (entry,) = self._requests(audit)
        assert entry.outcome == "failure"
        assert entry.target_type is None
        assert (entry.ip_address, entry.user_agent) == (_IP, _AGENT)

    def test_a_user_deleted_since_is_skipped_without_a_row(self, factory):
        with jasil_testing.capture_audit() as audit:
            assert self._run(factory, _payload(9), user=None) is None

        assert self._requests(audit) == []

    def test_an_inactive_account_is_denied(self, factory):
        with jasil_testing.capture_audit() as audit:
            result = self._run(factory, _payload(9), user=MagicMock(id=9, active=False))

        assert result is None
        (entry,) = self._requests(audit)
        assert (entry.outcome, entry.target_id, entry.target_owner_id) == ("denied", "9", "9")
        assert (entry.ip_address, entry.user_agent) == (_IP, _AGENT)

    def test_an_account_that_may_not_reset_is_denied(self, factory):
        with jasil_testing.capture_audit() as audit:
            result = self._run(factory, _payload(9), user=_active_user(), may_reset=False)

        assert result is None
        (entry,) = self._requests(audit)
        assert (entry.outcome, entry.target_id, entry.target_owner_id) == ("denied", "9", "9")
        assert (entry.ip_address, entry.user_agent) == (_IP, _AGENT)

    def test_a_request_inside_the_cooldown_adds_no_row_and_sends_nothing(self, factory):
        state = MemoryState()
        with jasil_testing.capture_audit() as audit:
            first = self._run(factory, _payload(9), state=state, user=_active_user())
            second = self._run(factory, _payload(9), state=state, user=_active_user(), event_id="event-2")

        assert first is not None
        assert second is None
        assert len(self._requests(audit)) == 1

    def test_a_retry_after_the_commit_failed_still_sends_with_one_row(self, factory):
        state = MemoryState()
        real_commit = Session.commit
        staged_at_commit = []

        def commit_failing_once(session):
            staged_at_commit.append(len(self._requests(audit)))
            if len(staged_at_commit) == 1:
                raise RuntimeError("commit failed")
            real_commit(session)

        with jasil_testing.capture_audit() as audit, patch.object(Session, "commit", commit_failing_once):
            with pytest.raises(RuntimeError):
                self._run(factory, _payload(9), state=state, user=_active_user())
            retry = self._run(factory, _payload(9), state=state, user=_active_user())

        assert retry == ("ana@x.test", "subject", "html", "text")
        # One row staged by the failed attempt (rolled back with it) and one by the retry that committed.
        assert staged_at_commit == [1, 2]

    def test_a_cooldown_store_that_is_down_sends_nothing_and_adds_no_row(self, factory):
        broken = MagicMock()
        broken.set_if_absent.side_effect = StateBackendUnavailableError("down")
        with jasil_testing.capture_audit() as audit:
            assert self._run(factory, _payload(9), state=broken, user=_active_user()) is None

        assert self._requests(audit) == []

    def test_an_admitted_request_is_audited_with_the_requesters_client(self, factory):
        with jasil_testing.capture_audit() as audit:
            result = self._run(factory, _payload(9), user=_active_user())

        assert result == ("ana@x.test", "subject", "html", "text")
        (entry,) = self._requests(audit)
        assert (entry.outcome, entry.target_type, entry.target_id, entry.target_owner_id) == (
            "success",
            "user",
            "9",
            "9",
        )
        assert entry.details is None
        assert (entry.ip_address, entry.user_agent) == (_IP, _AGENT)
        assert "ana@x.test" not in repr(entry)

    def test_the_row_keeps_the_workers_actor_and_event(self, factory):
        with (
            jasil_testing.capture_audit() as audit,
            jasil_audit.audit_context(
                actor_type=jasil_audit.ActorType.SYSTEM, source=jasil_audit.Source.WORKER, event_id="evt-1"
            ),
        ):
            self._run(factory, _payload(9), user=_active_user())

        (entry,) = self._requests(audit)
        assert (entry.actor_type, entry.source, entry.event_id) == ("system", "worker", "evt-1")
        assert (entry.ip_address, entry.user_agent) == (_IP, _AGENT)

    def test_a_redelivery_resends_the_same_link_without_a_second_claim_or_row(self, factory):
        state = MemoryState()
        with (
            patch(f"{_SERVICE}.core_email_cooldown.claim_email", wraps=core_email_cooldown.claim_email) as claim,
            jasil_testing.capture_audit() as audit,
        ):
            first = self._run(factory, _payload(9), state=state, user=_active_user())
            second = self._run(factory, _payload(9), state=state, user=_active_user())

        assert first is not None
        assert second == first
        claim.assert_called_once()
        assert len(self._requests(audit)) == 1
