"""The last per-session step-up tier ends the session; 100 failures across an account's sessions lock step-up."""

import uuid
from contextlib import ExitStack
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import jasil.testing as jasil_testing
import pytest
from jasil.backends.state_memory import MemoryState
from jasil.providers import StateBackendUnavailableError
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import modules.auth.account_security.events as account_security_events
import modules.auth.account_security.step_up_service as step_up_service
import modules.auth.account_security.step_up_store as step_up_store_module
import modules.auth.lockout.contracts as lockout_contracts
import modules.auth.lockout.integration_service as lockout_integration

_SID = uuid.UUID("00000000-0000-4000-8000-0000000000a1")
_SID_2 = uuid.UUID("00000000-0000-4000-8000-0000000000a2")

_SERVICE = "modules.auth.account_security.step_up_service"
_PUBLISH = "modules.auth.account_security.event_publishers.platform_publisher"
_LAST_TIER = lockout_contracts.STEP_UP_LOCKOUT_TIERS[-1][0]
_ACCOUNT_CAP = lockout_contracts.ACCOUNT_STEP_UP_LOCKOUT_TIERS[0][0]
_USER_ID = uuid.UUID(int=1)


def _store() -> step_up_store_module.StepUpAttempts:
    return step_up_store_module.StepUpAttempts(MemoryState())


def _spend_session_failures(store: step_up_store_module.StepUpAttempts, session_id: str, count: int) -> None:
    """Count failures against one session as earlier attempts would have, with no lock standing."""
    key = step_up_service._step_up_key(_USER_ID, session_id)
    for _ in range(count):
        store.record_failed_attempt(key)
        store._state.delete(store._lockout._gate_key(key))


def _spend_account_failures(store: step_up_store_module.StepUpAttempts, count: int) -> None:
    for _ in range(count):
        store.record_account_failure(_USER_ID)


def _verify(store, session_id=_SID, *, password_valid=False, db=None, session_present=True):
    """Run one step-up with a wrong (or right) password."""
    db = db or MagicMock(spec=Session)
    with ExitStack() as stack:
        stack.enter_context(patch(f"{_SERVICE}.users_integration.require_user", return_value=MagicMock()))
        stack.enter_context(patch(f"{_SERVICE}.credentials_integration.get_password_hash", return_value="hash"))
        stack.enter_context(
            patch(f"{_SERVICE}.credentials_integration.verify_and_update_password", return_value=(password_valid, None))
        )
        stack.enter_context(patch(f"{_SERVICE}.mfa_integration.is_mfa_enabled_for_user", return_value=False))
        stack.enter_context(
            patch(f"{_SERVICE}.sessions_integration.delete_session_if_present", return_value=session_present)
        )
        step_up_service.verify_step_up_credentials(_USER_ID, "pw", None, store, db, session_id=session_id)


def _fail(store, session_id=_SID, *, db=None, session_present=True):
    with pytest.raises(core_exceptions.StepUpFailedError):
        _verify(store, session_id, db=db, session_present=session_present)


class _Spy:
    """Patch the publishers and collect what each one was asked to publish."""

    def __enter__(self):
        self._stack = ExitStack()
        self.on_commit = self._stack.enter_context(patch(f"{_PUBLISH}.publish_on_commit"))
        self.now = self._stack.enter_context(patch(f"{_PUBLISH}.publish"))
        return self

    def __exit__(self, *exc):
        return self._stack.__exit__(*exc)

    def sent(self, channel: str) -> list:
        calls = [*self.on_commit.call_args_list, *self.now.call_args_list]
        return [c for c in calls if c.args[0] == channel]


class TestDocumentedLimits:
    """docs/features/accounts-and-sign-in.md states these limits."""

    def test_a_session_ends_at_the_fifteenth_failure(self):
        assert _LAST_TIER == 15

    def test_the_account_locks_for_thirty_days_at_the_hundredth_failure(self):
        assert lockout_contracts.ACCOUNT_STEP_UP_LOCKOUT_TIERS == ((100, 30 * 24 * 60 * 60, "30 days"),)
        assert lockout_contracts.ACCOUNT_STEP_UP_ATTEMPTS_TTL_SECONDS == 30 * 24 * 60 * 60


class TestSessionCounterLifetime:
    """The per-session count outlives the failures the account-wide count keeps, so a session reaches its end tier."""

    def test_failures_spaced_beyond_two_hours_still_end_the_session(self):
        store = _store()
        now = [1_000_000.0]
        db = MagicMock(spec=Session)

        def advance(seconds: float) -> None:
            now[0] += seconds

        with (
            _Spy(),
            patch("jasil.backends.state_memory.time.monotonic", side_effect=lambda: now[0]),
            patch("jasil.backends.state_memory.time.time", side_effect=lambda: now[0]),
            jasil_testing.capture_audit() as audit,
        ):
            for _ in range(_LAST_TIER - 1):
                _fail(store, db=db)
                advance(2 * 60 * 60 + 1)
            assert not any(e.action_id == "auth.session.step_up_end" for e in audit.entries)
            _fail(store, db=db)

        audit.assert_audited("auth.session.step_up_end", outcome="success")

    def test_the_session_counter_lives_as_long_as_the_account_counter(self):
        store = _store()
        assert store._lockout._attempts_ttl_seconds == lockout_contracts.ACCOUNT_STEP_UP_ATTEMPTS_TTL_SECONDS
        assert store._by_account._attempts_ttl_seconds == lockout_contracts.ACCOUNT_STEP_UP_ATTEMPTS_TTL_SECONDS


class TestLastPerSessionTier:
    def test_the_last_tier_ends_the_session_audits_why_and_tells_the_owner(self):
        store = _store()
        _spend_session_failures(store, _SID, _LAST_TIER - 1)
        db = MagicMock(spec=Session)

        with _Spy() as spy, jasil_testing.capture_audit() as audit:
            _fail(store, db=db)
        entry = audit.assert_audited(
            "auth.session.step_up_end",
            outcome="success",
            target_type="user",
            target_id=str(_USER_ID),
            target_owner_id=str(_USER_ID),
        )
        assert entry.details == {"sessions_revoked": 1}
        events = spy.sent(account_security_events.STEP_UP_SESSION_ENDED)
        assert len(events) == 1
        assert events[0].args[1] == {"user_id": str(_USER_ID)}
        db.commit.assert_called()

    def test_the_callers_staged_work_is_discarded_before_the_session_end_commits(self):
        store = _store()
        _spend_session_failures(store, _SID, _LAST_TIER - 1)
        db = MagicMock(spec=Session)
        order = MagicMock()
        order.attach_mock(db.rollback, "rollback")
        order.attach_mock(db.commit, "commit")

        with _Spy():
            _fail(store, db=db)

        names = [name for name, *_ in order.mock_calls]
        assert names.index("rollback") < names.index("commit")

    def test_the_session_deleted_is_the_callers_own(self):
        store = _store()
        _spend_session_failures(store, _SID_2, _LAST_TIER - 1)

        with (
            _Spy(),
            patch(f"{_SERVICE}.sessions_integration.delete_session_if_present", return_value=True) as delete,
            patch(f"{_SERVICE}.users_integration.require_user"),
            patch(f"{_SERVICE}.credentials_integration.get_password_hash", return_value="hash"),
            patch(f"{_SERVICE}.credentials_integration.verify_and_update_password", return_value=(False, None)),
            patch(f"{_SERVICE}.mfa_integration.is_mfa_enabled_for_user", return_value=False),
            pytest.raises(core_exceptions.StepUpFailedError),
        ):
            step_up_service.verify_step_up_credentials(
                _USER_ID, "x", None, store, MagicMock(spec=Session), session_id=_SID_2
            )

        delete.assert_called_once()
        assert delete.call_args.args[:2] == (_SID_2, _USER_ID)

    def test_the_failure_before_the_last_tier_keeps_the_session(self):
        store = _store()
        _spend_session_failures(store, _SID, _LAST_TIER - 2)

        with _Spy() as spy, jasil_testing.capture_audit() as audit:
            _fail(store)

        audit.assert_not_audited("auth.session.step_up_end")
        assert spy.sent(account_security_events.STEP_UP_SESSION_ENDED) == []

    def test_a_session_that_is_already_gone_stages_nothing(self):
        store = _store()
        _spend_session_failures(store, _SID, _LAST_TIER - 1)

        with _Spy() as spy, jasil_testing.capture_audit() as audit:
            _fail(store, session_present=False)

        audit.assert_not_audited("auth.session.step_up_end")
        assert spy.sent(account_security_events.STEP_UP_SESSION_ENDED) == []


class TestAccountWideCap:
    def test_failures_across_sessions_add_up_and_the_hundredth_locks_for_thirty_days(self):
        store = _store()
        with _Spy() as spy, jasil_testing.capture_audit() as audit:
            for session in range(25):
                for _ in range(4):
                    if store.get_account_lockout_time(_USER_ID) is None:
                        _fail(store, uuid.UUID(int=session))
            locked_until = store.get_account_lockout_time(_USER_ID)

        assert locked_until is not None
        assert timedelta(days=29) < locked_until - datetime.now(UTC) <= timedelta(days=30)
        rows = [r for r in audit.matching("auth.lockout.apply") if r.details["counter"] == "step_up_account"]
        assert [r.details for r in rows] == [{"counter": "step_up_account", "failed_attempts": 100}]
        assert (rows[0].target_type, rows[0].target_id, rows[0].target_owner_id) == (
            "user",
            str(_USER_ID),
            str(_USER_ID),
        )
        events = spy.sent(account_security_events.STEP_UP_LOCKED)
        assert len(events) == 1
        assert events[0].args[1] == {"user_id": str(_USER_ID)}

    def test_the_callers_staged_work_is_discarded_before_the_lock_notice_is_published(self):
        store = _store()
        _spend_account_failures(store, _ACCOUNT_CAP - 1)
        db = MagicMock(spec=Session)
        order = MagicMock()

        with _Spy() as spy:
            order.attach_mock(db.rollback, "rollback")
            order.attach_mock(spy.now, "publish")
            _fail(store, db=db)

        names = [name for name, *_ in order.mock_calls]
        assert "publish" in names
        assert names.index("rollback") < names.index("publish")

    def test_the_ninety_ninth_failure_locks_nothing_and_tells_nobody(self):
        store = _store()
        _spend_account_failures(store, _ACCOUNT_CAP - 2)

        with _Spy() as spy, jasil_testing.capture_audit() as audit:
            _fail(store)

        assert store.get_account_lockout_time(_USER_ID) is None
        assert spy.sent(account_security_events.STEP_UP_LOCKED) == []
        assert [r for r in audit.matching("auth.lockout.apply") if r.details["counter"] == "step_up_account"] == []

    def test_a_locked_account_is_refused_in_every_session_even_with_the_right_password(self):
        store = _store()
        _spend_account_failures(store, _ACCOUNT_CAP)

        with (
            jasil_testing.capture_audit() as audit,
            pytest.raises(core_exceptions.TooManyRequestsError) as refused,
        ):
            _verify(store, uuid.UUID(int=999), password_valid=True)

        assert refused.value.retry_at is not None
        assert refused.value.retry_at - datetime.now(UTC) > timedelta(days=29)
        entry = audit.assert_audited("auth.step_up.verify", outcome="denied")
        assert entry.details["reason"] == "locked_out"

    def test_a_locked_account_does_not_start_an_identity_provider_step_up(self):
        store = _store()
        _spend_account_failures(store, _ACCOUNT_CAP)
        with pytest.raises(core_exceptions.TooManyRequestsError):
            step_up_service.require_not_locked_out(_USER_ID, _SID, store)

    def test_another_account_is_not_locked(self):
        store = _store()
        _spend_account_failures(store, _ACCOUNT_CAP)

        assert store.get_account_lockout_time(uuid.UUID(int=2)) is None


class TestAccountCounterReset:
    def test_a_successful_step_up_forgets_the_accounts_failures(self):
        store = _store()
        _spend_account_failures(store, _ACCOUNT_CAP - 1)

        _verify(store, _SID, password_valid=True)
        with _Spy() as spy:
            _fail(store)

        assert store.get_account_lockout_time(_USER_ID) is None
        assert spy.sent(account_security_events.STEP_UP_LOCKED) == []

    def test_clearing_the_account_lifts_the_lock(self):
        store = _store()
        _spend_account_failures(store, _ACCOUNT_CAP)

        store.reset_account(_USER_ID)

        assert store.get_account_lockout_time(_USER_ID) is None

    def test_the_integration_operation_lifts_the_lock_through_the_platform_state(self):
        state = MemoryState()
        store = step_up_store_module.StepUpAttempts(state)
        _spend_account_failures(store, _ACCOUNT_CAP)

        with patch("core.dependencies.get_platform_state", return_value=state):
            lockout_integration.clear_step_up_account_lockout(_USER_ID)

        assert store.get_account_lockout_time(_USER_ID) is None

    def test_a_lift_that_meets_an_outage_does_not_fail_the_credential_change(self):
        with patch("core.dependencies.get_platform_state", return_value=_failing_state()):
            lockout_integration.clear_step_up_account_lockout(_USER_ID)


def _failing_state() -> MagicMock:
    state = MagicMock()
    for method in ("get", "set", "delete", "delete_prefix", "get_and_delete", "iter_keys", "record_tiered_failure"):
        getattr(state, method).side_effect = StateBackendUnavailableError("down")
    return state


class TestStoreUnavailable:
    def test_the_account_counter_fails_closed(self):
        store = step_up_store_module.StepUpAttempts(_failing_state())

        with pytest.raises(core_exceptions.ServiceUnavailableError):
            store.get_account_lockout_time(_USER_ID)
        with pytest.raises(core_exceptions.ServiceUnavailableError):
            store.record_account_failure(_USER_ID)
        with pytest.raises(core_exceptions.ServiceUnavailableError):
            store.reset_account(_USER_ID)

    def test_a_step_up_is_refused_before_any_credential_is_checked(self):
        store = step_up_store_module.StepUpAttempts(_failing_state())

        with (
            patch(f"{_SERVICE}.credentials_integration.verify_and_update_password") as verify,
            patch(f"{_SERVICE}.credentials_integration.get_password_hash", return_value="hash"),
            patch(f"{_SERVICE}.users_integration.require_user"),
            pytest.raises(core_exceptions.ServiceUnavailableError),
        ):
            step_up_service.verify_step_up_credentials(
                _USER_ID, "pw", None, store, MagicMock(spec=Session), session_id=_SID
            )

        verify.assert_not_called()
