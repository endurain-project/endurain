"""An account locked by 100 failed sign-ins in a row still admits its known devices, and tells its owner."""

from datetime import UTC, datetime
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

_SERVICE = "modules.auth.authentication.service"
_USER = SimpleNamespace(id=5, username="alice", active=True, access_type="regular")
_DEVICE_ID = "d" * 43
_IP = "203.0.113.7"
_TOKENS = ("sid", datetime(2999, 1, 1, tzinfo=UTC), "at", datetime(2999, 1, 1, tzinfo=UTC), "rt", "csrf")


def _store_locked_by_100_failures():
    store = failed_login_store.FailedLoginAttempts(MemoryState())
    for i in range(100):
        store.record_failed_attempt("alice", f"198.51.100.{i}")
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
        patch("modules.auth.authentication.token_service.create_tokens", return_value=_TOKENS),
        patch(f"{_SERVICE}.sessions_integration.create_session"),
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

    def test_a_client_without_a_device_id_is_refused_without_a_lookup(self, mock_db, password_sign_in):
        store = _store_locked_by_100_failures()
        with (
            patch(f"{_SERVICE}.users_integration.get_user_by_username") as get_user,
            pytest.raises(core_exceptions.TooManyRequestsError),
        ):
            _login(mock_db, store, device_id=None)

        get_user.assert_not_called()

    def test_a_known_device_of_the_account_signs_in_and_lifts_the_lock(self, mock_db, password_sign_in):
        store = _store_locked_by_100_failures()
        with (
            patch(f"{_SERVICE}.users_integration.get_user_by_username", return_value=_USER),
            patch(f"{_SERVICE}.known_devices_integration.is_known_device", return_value=True) as known,
        ):
            outcome = _login(mock_db, store)

        known.assert_called_once_with(5, _DEVICE_ID, mock_db)
        assert outcome.body.session_id == "sid"
        assert store.is_locked_out("alice", _IP) is False

    def test_a_known_device_is_still_refused_by_the_client_lock(self, mock_db, password_sign_in):
        store = failed_login_store.FailedLoginAttempts(MemoryState())
        for _ in range(5):
            store.record_failed_attempt("alice", _IP)
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
            store.record_failed_attempt("ghost", f"198.51.100.{i}")
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
            store.record_failed_attempt("alice", f"198.51.100.{i}")
        return store

    def test_the_failure_that_reaches_100_tells_the_owner_once_and_audits_it(self, mock_db):
        store = self._store_one_failure_short()
        with (
            patch(f"{_SERVICE}.authentication_event_publishers.publish_account_locked") as announce,
            jasil_testing.capture_audit() as audit,
        ):
            self._fail_login(mock_db, store, user=_USER)

        announce.assert_called_once_with(5, mock_db)
        entry = audit.assert_audited(
            lockout_audit_actions.LOCKOUT_APPLY.id,
            outcome="success",
            target_type="user",
            target_id="5",
            target_owner_id="5",
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
        authentication_event_publishers.publish_account_locked(5, mock_db)

    event_type, payload = publish.call_args.args
    assert event_type == authentication_events.ACCOUNT_LOCKED
    assert payload == {"user_id": 5}
    assert publish.call_args.kwargs["db"] is mock_db


class TestClearAccountLoginLockout:
    def test_the_account_lock_and_count_are_cleared_for_every_address(self):
        state = MemoryState()
        store = failed_login_store.FailedLoginAttempts(state)
        for i in range(100):
            store.record_failed_attempt("alice", f"198.51.100.{i}")
        assert store.is_locked_out("alice", _IP) is True

        with patch(
            "modules.auth.authentication.integration_service.core_dependencies.get_platform_state", return_value=state
        ):
            authentication_integration.clear_account_login_lockout("Alice")

        assert store.is_locked_out("alice", _IP) is False
        assert store.record_failed_attempt("alice", _IP).account_locked_now is False

    def test_a_state_outage_does_not_fail_the_credential_change(self):
        state = MagicMock()
        state.delete.side_effect = StateBackendUnavailableError("down")

        with patch(
            "modules.auth.authentication.integration_service.core_dependencies.get_platform_state", return_value=state
        ):
            authentication_integration.clear_account_login_lockout("alice")
