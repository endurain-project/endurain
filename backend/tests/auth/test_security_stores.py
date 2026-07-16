"""Tests for auth._internal.security_stores (provider-backed)."""

import hashlib
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

import auth._internal.security_stores as security_stores
from infra.backends.state_memory import MemoryState
from infra.providers import StateBackendUnavailableError


class TestNormalizeUsernameKey:
    """Tests for the normalize_username_key helper function."""

    def test_lowercases_ascii(self):
        assert security_stores.normalize_username_key("TestUser") == "testuser"

    def test_strips_leading_trailing_whitespace(self):
        assert security_stores.normalize_username_key("  testuser  ") == "testuser"

    def test_url_decodes_percent_at(self):
        assert security_stores.normalize_username_key("test%40example.com") == "test@example.com"

    def test_url_decodes_percent_20_space(self):
        assert security_stores.normalize_username_key("test%20user") == "test user"

    def test_plus_sign_converted_to_space(self):
        assert security_stores.normalize_username_key("test+user") == "test user"

    def test_percent_2b_url_decoded_then_converted_to_space(self):
        assert security_stores.normalize_username_key("test%2Buser") == "test user"

    def test_combined_casing_whitespace_and_url_encoding(self):
        assert security_stores.normalize_username_key("  Test%40Example.COM  ") == "test@example.com"

    def test_empty_string_returns_empty_string(self):
        assert security_stores.normalize_username_key("") == ""

    def test_unicode_casefold(self):
        assert security_stores.normalize_username_key("StraBe") == "strabe"

    def test_whitespace_only_returns_empty_string(self):
        assert security_stores.normalize_username_key("   ") == ""


class TestUsernameLogIdentifier:
    """Tests for the username_log_identifier helper function."""

    def test_returns_hash_prefix_format(self):
        assert security_stores.username_log_identifier("alice").startswith("username_hash=")

    def test_does_not_contain_raw_username(self):
        identifier = security_stores.username_log_identifier("supersensitive@example.com")
        assert "supersensitive" not in identifier
        assert "example.com" not in identifier

    def test_hash_matches_sha256_of_normalized_username(self):
        expected = hashlib.sha256(b"alice@example.com").hexdigest()
        assert security_stores.username_log_identifier(" Alice%40Example.COM ") == f"username_hash={expected}"

    def test_same_canonical_form_same_identifier(self):
        assert security_stores.username_log_identifier(
            "Alice%40Example.COM"
        ) == security_stores.username_log_identifier("alice@example.com")

    def test_different_usernames_different_identifiers(self):
        assert security_stores.username_log_identifier("alice") != security_stores.username_log_identifier("bob")


class TestFailedLoginAttempts:
    """Login lockout: 5/10/20 failures -> 5m/30m/24h."""

    def _store(self) -> security_stores.FailedLoginAttempts:
        return security_stores.FailedLoginAttempts(state=MemoryState())

    def test_not_locked_initially(self):
        store = self._store()
        assert store.is_locked_out("alice") is False
        assert store.get_lockout_time("alice") is None

    def test_record_returns_incrementing_count(self):
        store = self._store()
        assert store.record_failed_attempt("alice") == 1
        assert store.record_failed_attempt("alice") == 2

    def test_lockout_applied_at_5(self):
        store = self._store()
        for _ in range(5):
            store.record_failed_attempt("alice")
        assert store.is_locked_out("alice") is True
        lockout = store.get_lockout_time("alice")
        assert lockout is not None
        assert lockout > datetime.now(UTC)

    def test_locked_does_not_increment(self):
        store = self._store()
        for _ in range(5):
            store.record_failed_attempt("alice")
        assert store.record_failed_attempt("alice") == 5

    def test_reset_clears_lockout(self):
        store = self._store()
        for _ in range(5):
            store.record_failed_attempt("alice")
        store.reset_attempts("alice")
        assert store.is_locked_out("alice") is False
        assert store.record_failed_attempt("alice") == 1

    def test_username_is_normalized(self):
        store = self._store()
        store.record_failed_attempt("Alice")
        assert store.record_failed_attempt("  alice  ") == 2

    def test_clear_all(self):
        store = self._store()
        for _ in range(5):
            store.record_failed_attempt("alice")
        store.clear_all()
        assert store.is_locked_out("alice") is False

    def test_distinct_users_isolated(self):
        store = self._store()
        for _ in range(5):
            store.record_failed_attempt("alice")
        assert store.is_locked_out("bob") is False


class TestPendingMFALogin:
    """Pending MFA bookkeeping plus MFA lockout (5/10/15)."""

    def _store(self) -> security_stores.PendingMFALogin:
        return security_stores.PendingMFALogin(state=MemoryState())

    def test_add_and_get(self):
        store = self._store()
        store.add_pending_login("alice", 42)
        assert store.get_pending_login("alice") == 42
        assert store.has_pending_login("alice") is True

    def test_claim_is_single_use(self):
        store = self._store()
        store.add_pending_login("alice", 42)
        assert store.claim_pending_login("alice") == 42
        assert store.claim_pending_login("alice") is None

    def test_delete(self):
        store = self._store()
        store.add_pending_login("alice", 42)
        store.delete_pending_login("alice")
        assert store.get_pending_login("alice") is None

    def test_missing_returns_none(self):
        store = self._store()
        assert store.get_pending_login("nobody") is None
        assert store.has_pending_login("nobody") is False

    def test_username_is_normalized(self):
        store = self._store()
        store.add_pending_login("Alice", 7)
        assert store.get_pending_login("  alice ") == 7

    def test_clear_for_user_removes_only_matching(self):
        store = self._store()
        store.add_pending_login("alice", 5)
        store.add_pending_login("bob", 9)
        assert store.clear_for_user(5) == 1
        assert store.get_pending_login("alice") is None
        assert store.get_pending_login("bob") == 9

    def test_clear_for_user_no_match_returns_zero(self):
        store = self._store()
        store.add_pending_login("alice", 5)
        assert store.clear_for_user(999) == 0
        assert store.get_pending_login("alice") == 5

    def test_get_pending_evicts_corrupt_value(self):
        state = MemoryState()
        store = security_stores.PendingMFALogin(state=state)
        state.set(store._pending_key("alice"), b"not-an-int")
        assert store.get_pending_login("alice") is None
        assert state.get(store._pending_key("alice")) is None

    def test_cleanup_expired_returns_zero(self):
        assert self._store().cleanup_expired() == 0

    def test_mfa_lockout_applied_at_5(self):
        store = self._store()
        for _ in range(5):
            store.record_failed_attempt("alice")
        assert store.is_locked_out("alice") is True

    def test_mfa_reset_clears_lockout(self):
        store = self._store()
        for _ in range(5):
            store.record_failed_attempt("alice")
        store.reset_attempts("alice")
        assert store.is_locked_out("alice") is False

    def test_clear_all_clears_pending_and_lockout(self):
        store = self._store()
        store.add_pending_login("alice", 1)
        for _ in range(5):
            store.record_failed_attempt("alice")
        store.clear_all()
        assert store.get_pending_login("alice") is None
        assert store.is_locked_out("alice") is False

    def test_mfa_and_login_use_separate_namespaces(self):
        state = MemoryState()
        pending = security_stores.PendingMFALogin(state=state)
        login = security_stores.FailedLoginAttempts(state=state)
        pending.add_pending_login("alice", 1)
        for _ in range(5):
            login.record_failed_attempt("alice")
        assert pending.is_locked_out("alice") is False
        assert pending.get_pending_login("alice") == 1


class TestStepUpAttempts:
    """Step-up lockout (5/10/15); keys are stable user identifiers, not normalized."""

    def _store(self) -> security_stores.StepUpAttempts:
        return security_stores.StepUpAttempts(state=MemoryState())

    def test_lockout_applied_at_5(self):
        store = self._store()
        for _ in range(5):
            store.record_failed_attempt("user:1")
        assert store.is_locked_out("user:1") is True

    def test_reset_clears_lockout(self):
        store = self._store()
        for _ in range(5):
            store.record_failed_attempt("user:1")
        store.reset_attempts("user:1")
        assert store.is_locked_out("user:1") is False

    def test_distinct_keys_isolated(self):
        store = self._store()
        for _ in range(5):
            store.record_failed_attempt("user:1")
        assert store.is_locked_out("user:2") is False

    def test_clear_all(self):
        store = self._store()
        for _ in range(5):
            store.record_failed_attempt("user:1")
        store.clear_all()
        assert store.is_locked_out("user:1") is False


class TestUnavailable:
    """State outages surface as AuthSecurityStoreUnavailableError (503 upstream)."""

    def _failing_state(self) -> MagicMock:
        state = MagicMock()
        for method in ("get", "set", "delete", "delete_prefix", "get_and_delete", "iter_keys", "record_tiered_failure"):
            getattr(state, method).side_effect = StateBackendUnavailableError("down")
        return state

    def test_record_failed_attempt_raises(self):
        store = security_stores.FailedLoginAttempts(state=self._failing_state())
        with pytest.raises(security_stores.AuthSecurityStoreUnavailableError):
            store.record_failed_attempt("alice")

    def test_is_locked_out_raises(self):
        store = security_stores.FailedLoginAttempts(state=self._failing_state())
        with pytest.raises(security_stores.AuthSecurityStoreUnavailableError):
            store.is_locked_out("alice")

    def test_reset_raises(self):
        store = security_stores.FailedLoginAttempts(state=self._failing_state())
        with pytest.raises(security_stores.AuthSecurityStoreUnavailableError):
            store.reset_attempts("alice")

    def test_clear_all_raises(self):
        store = security_stores.FailedLoginAttempts(state=self._failing_state())
        with pytest.raises(security_stores.AuthSecurityStoreUnavailableError):
            store.clear_all()

    def test_add_pending_raises(self):
        store = security_stores.PendingMFALogin(state=self._failing_state())
        with pytest.raises(security_stores.AuthSecurityStoreUnavailableError):
            store.add_pending_login("alice", 1)

    def test_get_pending_raises(self):
        store = security_stores.PendingMFALogin(state=self._failing_state())
        with pytest.raises(security_stores.AuthSecurityStoreUnavailableError):
            store.get_pending_login("alice")

    def test_claim_pending_raises(self):
        store = security_stores.PendingMFALogin(state=self._failing_state())
        with pytest.raises(security_stores.AuthSecurityStoreUnavailableError):
            store.claim_pending_login("alice")

    def test_clear_for_user_raises(self):
        store = security_stores.PendingMFALogin(state=self._failing_state())
        with pytest.raises(security_stores.AuthSecurityStoreUnavailableError):
            store.clear_for_user(1)


class TestDependencyFunctions:
    """Module-level singletons and helpers."""

    def test_get_failed_login_attempts_returns_singleton(self):
        assert security_stores.get_failed_login_attempts() is security_stores.failed_login_attempts

    def test_get_pending_mfa_store_returns_singleton(self):
        assert security_stores.get_pending_mfa_store() is security_stores.pending_mfa_store

    def test_get_step_up_attempts_returns_singleton(self):
        assert security_stores.get_step_up_attempts() is security_stores.step_up_attempts

    def test_cleanup_expired_pending_mfa_logins_is_noop(self):
        security_stores.cleanup_expired_pending_mfa_logins()

    def test_clear_pending_mfa_for_user_swallows_outage(self):
        failing = MagicMock()
        failing.iter_keys.side_effect = StateBackendUnavailableError("down")
        with patch.object(security_stores, "pending_mfa_store", security_stores.PendingMFALogin(state=failing)):
            assert security_stores.clear_pending_mfa_for_user(1) == 0
