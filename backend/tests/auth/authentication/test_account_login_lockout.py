"""An account locked by 100 failed sign-ins in a row still admits its known devices, and tells its owner."""

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import jasil.testing as jasil_testing
import pytest
from jasil.backends.state_memory import MemoryState
from jasil.providers import StateBackendUnavailableError

import core.exceptions as core_exceptions
import modules.auth.authentication.event_publishers as authentication_event_publishers
import modules.auth.authentication.events as authentication_events
import modules.auth.authentication.failed_login_store as failed_login_store
import modules.auth.authentication.integration_service as authentication_integration
import modules.auth.authentication.service as authentication_service
import modules.auth.known_devices.contracts as known_devices_contracts
import modules.auth.lockout.audit_actions as lockout_audit_actions

_SESSION_ID = uuid.UUID(int=7)

_USER_ID = uuid.UUID(int=5)

_SERVICE = "modules.auth.authentication.service"
_USER = SimpleNamespace(id=_USER_ID, username="alice", active=True, access_type="regular")
_DEVICE_ID = "d" * 43
_IP = "203.0.113.7"
_TOKENS = (_SESSION_ID, datetime(2999, 1, 1, tzinfo=UTC), "at", datetime(2999, 1, 1, tzinfo=UTC), "rt", "csrf")


def _store_locked_by_100_failures():
    store = failed_login_store.FailedLoginAttempts(MemoryState())
    for i in range(100):
        store.record_failed_attempt("alice", f"198.51.100.{i}", user_id=_USER_ID)
    return store


def _login(db, store, *, device_id=_DEVICE_ID, username="alice"):
    return authentication_service.login_for_access_token(
        _IP,
        "agent",
        username,
        "secret",
        "web",
        store,
        MagicMock(),
        MagicMock(),
        MagicMock(),
        db,
        code_challenge=None,
        code_challenge_method=None,
        password_change_store=MagicMock(),
        device_id=device_id,
    )


@pytest.fixture
def password_sign_in():
    """Let a correct password through to session creation, with no MFA."""
    record = known_devices_contracts.SignInRecord(device_id=_DEVICE_ID, new_device=False)
    with (
        patch(f"{_SERVICE}.authenticate_user", return_value=_USER),
        patch(f"{_SERVICE}.server_settings_integration.get_server_settings"),
        patch(f"{_SERVICE}.server_settings_integration.get_session_policy"),
        patch(f"{_SERVICE}.credentials_integration.allows_password_sign_in", return_value=True),
        patch(f"{_SERVICE}.mfa_integration.is_mfa_enabled_for_user", return_value=False),
        patch(f"{_SERVICE}.credentials_integration.is_password_change_required", return_value=False),
        patch("modules.auth.authentication.token_service.create_tokens", return_value=_TOKENS),
        patch(
            f"{_SERVICE}.sessions_integration.create_session",
            return_value=MagicMock(expires_at=datetime.now(UTC) + timedelta(days=30)),
        ),
        patch(f"{_SERVICE}.known_devices_integration.record_sign_in", return_value=record),
    ):
        yield


class TestKnownDeviceBypass:
    def test_an_unknown_device_is_refused_by_the_account_lock(self, mock_db, password_sign_in):
        store = _store_locked_by_100_failures()
        with (
            patch(f"{_SERVICE}.users_integration.get_user_by_username", return_value=_USER),
            patch(f"{_SERVICE}.known_devices_integration.is_known_device", return_value=False),
            pytest.raises(core_exceptions.TooManyRequestsError),
        ):
            _login(mock_db, store)

    def test_a_client_without_a_device_id_is_refused_with_one_account_lookup(self, mock_db, password_sign_in):
        store = _store_locked_by_100_failures()
        with (
            patch(f"{_SERVICE}.users_integration.get_user_by_username", return_value=_USER) as get_user,
            pytest.raises(core_exceptions.TooManyRequestsError),
        ):
            _login(mock_db, store, device_id=None)

        get_user.assert_called_once_with("alice", mock_db)

    def test_a_known_device_of_the_account_signs_in_and_lifts_the_lock(self, mock_db, password_sign_in):
        store = _store_locked_by_100_failures()
        with (
            patch(f"{_SERVICE}.users_integration.get_user_by_username", return_value=_USER),
            patch(f"{_SERVICE}.known_devices_integration.is_known_device", return_value=True) as known,
        ):
            outcome = _login(mock_db, store)

        known.assert_called_once_with(_USER_ID, _DEVICE_ID, mock_db)
        assert outcome.body.session_id == _SESSION_ID
        assert store.is_locked_out("alice", _IP, user_id=_USER_ID) is False

    def test_a_known_device_is_still_refused_by_the_client_lock(self, mock_db, password_sign_in):
        store = failed_login_store.FailedLoginAttempts(MemoryState())
        for _ in range(5):
            store.record_failed_attempt("alice", _IP, user_id=_USER_ID)
        with (
            patch(f"{_SERVICE}.users_integration.get_user_by_username", return_value=_USER),
            patch(f"{_SERVICE}.known_devices_integration.is_known_device", return_value=True),
            pytest.raises(core_exceptions.TooManyRequestsError),
        ):
            _login(mock_db, store)

    def test_a_known_device_that_gets_the_password_wrong_is_refused_like_any_other(self, mock_db):
        store = _store_locked_by_100_failures()
        with (
            patch(f"{_SERVICE}.users_integration.get_user_by_username", return_value=_USER),
            patch(f"{_SERVICE}.known_devices_integration.is_known_device", return_value=True),
            patch(
                f"{_SERVICE}.authenticate_user",
                side_effect=core_exceptions.UnauthenticatedError("no", scheme="Bearer"),
            ),
            pytest.raises(core_exceptions.UnauthenticatedError),
        ):
            _login(mock_db, store)

    def test_an_unknown_username_is_refused_exactly_like_a_locked_one(self, mock_db):
        store = failed_login_store.FailedLoginAttempts(MemoryState())
        for i in range(100):
            store.record_failed_attempt("ghost", f"198.51.100.{i}", user_id=None)
        with (
            patch(f"{_SERVICE}.users_integration.get_user_by_username", return_value=None),
            pytest.raises(core_exceptions.TooManyRequestsError) as unknown,
        ):
            _login(mock_db, store, username="ghost")
        locked_store = _store_locked_by_100_failures()
        with (
            patch(f"{_SERVICE}.users_integration.get_user_by_username", return_value=_USER),
            patch(f"{_SERVICE}.known_devices_integration.is_known_device", return_value=False),
            pytest.raises(core_exceptions.TooManyRequestsError) as locked,
        ):
            _login(mock_db, locked_store)

        assert type(unknown.value) is type(locked.value)
        assert unknown.value.status_code == locked.value.status_code


class TestRenamedAccount:
    def test_the_lock_follows_the_user_id_across_a_username_change(self):
        store = _store_locked_by_100_failures()

        assert store.is_locked_out("alicia", "192.0.2.1", user_id=_USER_ID) is True
        assert store.is_locked_out("alicia", "192.0.2.1", user_id=_USER_ID, known_device=True) is False
        assert store.record_failed_attempt("alicia", "192.0.2.1", user_id=_USER_ID).account_locked_now is False

    def test_a_sign_in_under_the_new_username_is_refused_while_the_account_is_locked(self, mock_db, password_sign_in):
        store = _store_locked_by_100_failures()
        renamed = SimpleNamespace(id=_USER_ID, username="alicia", active=True, access_type="regular")
        with (
            patch(f"{_SERVICE}.users_integration.get_user_by_username", return_value=renamed),
            patch(f"{_SERVICE}.known_devices_integration.is_known_device", return_value=False),
            pytest.raises(core_exceptions.TooManyRequestsError),
        ):
            _login(mock_db, store, username="alicia")

    def test_the_failures_before_and_after_a_rename_count_together(self):
        store = failed_login_store.FailedLoginAttempts(MemoryState())
        for i in range(50):
            store.record_failed_attempt("alice", f"198.51.100.{i}", user_id=_USER_ID)
        records = [store.record_failed_attempt("alicia", f"198.51.101.{i}", user_id=_USER_ID) for i in range(50)]

        assert [r.account_locked_now for r in records] == [False] * 49 + [True]

    def test_reset_account_by_id_clears_the_lock_under_any_username(self):
        store = _store_locked_by_100_failures()

        store.reset_account(_USER_ID)

        assert store.is_locked_out("alicia", _IP, user_id=_USER_ID) is False


class TestUnknownUsername:
    def test_an_unknown_username_locks_after_100_failures_from_any_addresses(self):
        store = failed_login_store.FailedLoginAttempts(MemoryState())
        records = [store.record_failed_attempt("ghost", f"198.51.100.{i}", user_id=None) for i in range(100)]

        assert [r.account_locked_now for r in records] == [False] * 99 + [True]
        assert store.is_locked_out("Ghost", _IP, user_id=None) is True
        assert store.is_locked_out("ghost", _IP, user_id=None, known_device=True) is False

    def test_an_unknown_username_never_locks_an_account_whose_id_spells_it(self):
        store = failed_login_store.FailedLoginAttempts(MemoryState())
        for i in range(100):
            store.record_failed_attempt("5", f"198.51.100.{i}", user_id=None)

        assert store.is_locked_out("alice", _IP, user_id=_USER_ID) is False

    def test_clear_all_clears_the_unknown_username_counters(self):
        store = failed_login_store.FailedLoginAttempts(MemoryState())
        for i in range(100):
            store.record_failed_attempt("ghost", f"198.51.100.{i}", user_id=None)

        store.clear_all()

        assert store.is_locked_out("ghost", _IP, user_id=None) is False


class TestAccountLockNotice:
    def _fail_login(self, db, store, *, user):
        with (
            patch(f"{_SERVICE}.users_integration.get_user_by_username", return_value=user),
            patch(
                f"{_SERVICE}.authenticate_user",
                side_effect=core_exceptions.UnauthenticatedError("no", scheme="Bearer"),
            ),
            pytest.raises(core_exceptions.UnauthenticatedError),
        ):
            _login(db, store, device_id=None)

    def _store_one_failure_short(self):
        store = failed_login_store.FailedLoginAttempts(MemoryState())
        for i in range(99):
            store.record_failed_attempt("alice", f"198.51.100.{i}", user_id=_USER_ID)
        return store

    def test_the_failure_that_reaches_100_tells_the_owner_once_and_audits_it(self, mock_db):
        store = self._store_one_failure_short()
        with (
            patch(f"{_SERVICE}.authentication_event_publishers.publish_account_locked") as announce,
            jasil_testing.capture_audit() as audit,
        ):
            self._fail_login(mock_db, store, user=_USER)

        announce.assert_called_once_with(_USER_ID, mock_db)
        entry = audit.assert_audited(
            lockout_audit_actions.LOCKOUT_APPLY.id,
            outcome="success",
            target_type="user",
            target_id=str(_USER_ID),
            target_owner_id=str(_USER_ID),
        )
        assert entry.details == {"counter": "login_account", "failed_attempts": 100}
        assert "alice" not in repr(entry)

    def test_a_failure_below_100_tells_nobody(self, mock_db):
        store = failed_login_store.FailedLoginAttempts(MemoryState())
        with (
            patch(f"{_SERVICE}.authentication_event_publishers.publish_account_locked") as announce,
            jasil_testing.capture_audit() as audit,
        ):
            self._fail_login(mock_db, store, user=_USER)

        announce.assert_not_called()
        audit.assert_not_audited(lockout_audit_actions.LOCKOUT_APPLY.id)

    def test_a_username_that_matches_no_user_tells_nobody(self, mock_db):
        store = self._store_one_failure_short()
        with (
            patch(f"{_SERVICE}.authentication_event_publishers.publish_account_locked") as announce,
            jasil_testing.capture_audit() as audit,
        ):
            self._fail_login(mock_db, store, user=None)

        announce.assert_not_called()
        audit.assert_not_audited(lockout_audit_actions.LOCKOUT_APPLY.id)

    def test_a_known_device_failing_while_locked_does_not_tell_again(self, mock_db):
        store = _store_locked_by_100_failures()
        with (
            patch(f"{_SERVICE}.authentication_event_publishers.publish_account_locked") as announce,
            patch(f"{_SERVICE}.known_devices_integration.is_known_device", return_value=True),
            patch(f"{_SERVICE}.users_integration.get_user_by_username", return_value=_USER),
            patch(
                f"{_SERVICE}.authenticate_user",
                side_effect=core_exceptions.UnauthenticatedError("no", scheme="Bearer"),
            ),
            pytest.raises(core_exceptions.UnauthenticatedError),
        ):
            _login(mock_db, store)

        announce.assert_not_called()


def test_the_event_names_the_user_and_nothing_else(mock_db):
    with patch("modules.auth.authentication.event_publishers.platform_publisher.publish") as publish:
        authentication_event_publishers.publish_account_locked(_USER_ID, mock_db)

    event_type, payload = publish.call_args.args
    assert event_type == authentication_events.ACCOUNT_LOCKED
    assert payload == {"user_id": str(_USER_ID)}
    assert publish.call_args.kwargs["db"] is mock_db


class TestClearAccountLoginLockout:
    def test_the_account_lock_and_count_are_cleared_for_every_address(self):
        state = MemoryState()
        store = failed_login_store.FailedLoginAttempts(state)
        for i in range(100):
            store.record_failed_attempt("alice", f"198.51.100.{i}", user_id=_USER_ID)
        assert store.is_locked_out("alice", _IP, user_id=_USER_ID) is True

        with patch(
            "modules.auth.authentication.integration_service.core_dependencies.get_platform_state", return_value=state
        ):
            authentication_integration.clear_account_login_lockout(_USER_ID)

        assert store.is_locked_out("alice", _IP, user_id=_USER_ID) is False
        assert store.record_failed_attempt("alice", _IP, user_id=_USER_ID).account_locked_now is False

    def test_a_state_outage_does_not_fail_the_credential_change(self):
        state = MagicMock()
        state.delete.side_effect = StateBackendUnavailableError("down")

        with patch(
            "modules.auth.authentication.integration_service.core_dependencies.get_platform_state", return_value=state
        ):
            authentication_integration.clear_account_login_lockout(_USER_ID)
