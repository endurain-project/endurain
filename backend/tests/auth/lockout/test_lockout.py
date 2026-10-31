"""Tests for provider-backed authentication security stores."""

import hashlib
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from jasil.backends.state_memory import MemoryState
from jasil.providers import StateBackendUnavailableError

import modules.auth.account_security.step_up_store as step_up_store_module
import modules.auth.authentication.failed_login_store as failed_login_store
import modules.auth.lockout.contracts as lockout_contracts
import modules.auth.lockout.integration_service as lockout_integration


class TestNormalizeUsernameKey:
    """Tests for the normalize_username_key helper function."""

    def test_lowercases_ascii(self):
        assert lockout_integration.normalize_username_key("TestUser") == "testuser"

    def test_strips_leading_trailing_whitespace(self):
        assert lockout_integration.normalize_username_key("  testuser  ") == "testuser"

    def test_url_decodes_percent_at(self):
        assert lockout_integration.normalize_username_key("test%40example.com") == "test@example.com"

    def test_url_decodes_percent_20_space(self):
        assert lockout_integration.normalize_username_key("test%20user") == "test user"

    def test_plus_sign_converted_to_space(self):
        assert lockout_integration.normalize_username_key("test+user") == "test user"

    def test_percent_2b_url_decoded_then_converted_to_space(self):
        assert lockout_integration.normalize_username_key("test%2Buser") == "test user"

    def test_combined_casing_whitespace_and_url_encoding(self):
        assert lockout_integration.normalize_username_key("  Test%40Example.COM  ") == "test@example.com"

    def test_empty_string_returns_empty_string(self):
        assert lockout_integration.normalize_username_key("") == ""

    def test_unicode_casefold(self):
        assert lockout_integration.normalize_username_key("StraBe") == "strabe"

    def test_whitespace_only_returns_empty_string(self):
        assert lockout_integration.normalize_username_key("   ") == ""


class TestUsernameLogIdentifier:
    """Tests for the username_log_identifier helper function."""

    def test_returns_hash_prefix_format(self):
        assert lockout_integration.username_log_identifier("alice").startswith("username_hash=")

    def test_does_not_contain_raw_username(self):
        identifier = lockout_integration.username_log_identifier("supersensitive@example.com")
        assert "supersensitive" not in identifier
        assert "example.com" not in identifier

    def test_hash_matches_sha256_of_normalized_username(self):
        expected = hashlib.sha256(b"alice@example.com").hexdigest()
        assert lockout_integration.username_log_identifier(" Alice%40Example.COM ") == f"username_hash={expected}"

    def test_same_canonical_form_same_identifier(self):
        assert lockout_integration.username_log_identifier(
            "Alice%40Example.COM"
        ) == lockout_integration.username_log_identifier("alice@example.com")

    def test_different_usernames_different_identifiers(self):
        assert lockout_integration.username_log_identifier("alice") != lockout_integration.username_log_identifier(
            "bob"
        )


class TestFailedLoginAttempts:
    """Login lockout: 5/10/20 failures per username and address -> 5m/30m/24h."""

    IP = "203.0.113.1"
    OTHER_IP = "203.0.113.2"

    def _store(self) -> failed_login_store.FailedLoginAttempts:
        return failed_login_store.FailedLoginAttempts(state=MemoryState())

    def _fail(self, store, times, username="alice", ip=IP):
        for _ in range(times):
            store.record_failed_attempt(username, ip)

    def test_not_locked_initially(self):
        store = self._store()
        assert store.is_locked_out("alice", self.IP) is False
        assert store.get_lockout_time("alice", self.IP) is None

    def test_record_returns_incrementing_count(self):
        store = self._store()
        assert store.record_failed_attempt("alice", self.IP) == 1
        assert store.record_failed_attempt("alice", self.IP) == 2

    def test_lockout_applied_at_5(self):
        store = self._store()
        self._fail(store, 5)
        assert store.is_locked_out("alice", self.IP) is True
        lockout = store.get_lockout_time("alice", self.IP)
        assert lockout is not None
        assert lockout > datetime.now(UTC)

    def test_locked_does_not_increment(self):
        store = self._store()
        self._fail(store, 5)
        assert store.record_failed_attempt("alice", self.IP) == 5

    def test_reset_clears_lockout(self):
        store = self._store()
        self._fail(store, 5)
        store.reset_attempts("alice", self.IP)
        assert store.is_locked_out("alice", self.IP) is False
        assert store.record_failed_attempt("alice", self.IP) == 1

    def test_username_is_normalized(self):
        store = self._store()
        store.record_failed_attempt("Alice", self.IP)
        assert store.record_failed_attempt("  alice  ", self.IP) == 2

    def test_clear_all(self):
        store = self._store()
        self._fail(store, 5)
        store.clear_all()
        assert store.is_locked_out("alice", self.IP) is False

    def test_distinct_users_isolated(self):
        store = self._store()
        self._fail(store, 5)
        assert store.is_locked_out("bob", self.IP) is False

    def test_failures_from_one_address_do_not_lock_another(self):
        store = self._store()
        self._fail(store, 5)
        assert store.is_locked_out("alice", self.IP) is True
        assert store.is_locked_out("alice", self.OTHER_IP) is False
        assert store.get_lockout_time("alice", self.OTHER_IP) is None

    def test_an_address_counts_separately_per_username(self):
        store = self._store()
        self._fail(store, 5, username="alice")
        assert store.is_locked_out("bob", self.IP) is False

    def test_failures_across_addresses_lock_the_account_for_every_address(self):
        store = self._store()
        threshold = lockout_contracts.ACCOUNT_LOGIN_LOCKOUT_TIERS[0][0]
        for i in range(threshold):
            store.record_failed_attempt("alice", f"198.51.100.{i}")
        assert store.is_locked_out("alice", self.IP) is True
        assert store.get_lockout_time("alice", self.IP) > datetime.now(UTC)
        assert store.is_locked_out("bob", self.IP) is False

    def test_reset_clears_the_account_wide_count(self):
        store = self._store()
        threshold = lockout_contracts.ACCOUNT_LOGIN_LOCKOUT_TIERS[0][0]
        for i in range(threshold):
            store.record_failed_attempt("alice", f"198.51.100.{i}")
        store.reset_attempts("alice", self.IP)
        assert store.is_locked_out("alice", self.IP) is False

    def test_lockout_time_is_the_later_of_the_two(self):
        store = self._store()
        self._fail(store, 5)
        threshold = lockout_contracts.ACCOUNT_LOGIN_LOCKOUT_TIERS[0][0]
        for i in range(threshold):
            store.record_failed_attempt("alice", f"198.51.100.{i}")
        assert store.get_lockout_time("alice", self.IP) > datetime.now(UTC) + timedelta(minutes=10)


class TestStepUpAttempts:
    """Step-up lockout (5/10/15); keys are stable user identifiers, not normalized."""

    def _store(self) -> step_up_store_module.StepUpAttempts:
        return step_up_store_module.StepUpAttempts(state=MemoryState())

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
        store = failed_login_store.FailedLoginAttempts(state=self._failing_state())
        with pytest.raises(lockout_contracts.AuthSecurityStoreUnavailableError):
            store.record_failed_attempt("alice", "203.0.113.1")

    def test_is_locked_out_raises(self):
        store = failed_login_store.FailedLoginAttempts(state=self._failing_state())
        with pytest.raises(lockout_contracts.AuthSecurityStoreUnavailableError):
            store.is_locked_out("alice", "203.0.113.1")

    def test_reset_raises(self):
        store = failed_login_store.FailedLoginAttempts(state=self._failing_state())
        with pytest.raises(lockout_contracts.AuthSecurityStoreUnavailableError):
            store.reset_attempts("alice", "203.0.113.1")

    def test_clear_all_raises(self):
        store = failed_login_store.FailedLoginAttempts(state=self._failing_state())
        with pytest.raises(lockout_contracts.AuthSecurityStoreUnavailableError):
            store.clear_all()


class TestDependencyFunctions:
    """Module-level singletons and helpers."""

    def test_get_failed_login_attempts_returns_singleton(self):
        assert failed_login_store.get_failed_login_attempts(
            MemoryState()
        ) != failed_login_store.get_failed_login_attempts(MemoryState())

    def test_get_step_up_attempts_uses_injected_provider(self):
        state = MemoryState()
        assert isinstance(step_up_store_module.get_step_up_attempts(state), step_up_store_module.StepUpAttempts)


class TestReportLockoutApplied:
    """The services report a lockout; the stores stay silent."""

    def test_below_the_first_tier_logs_nothing(self, caplog):
        with caplog.at_level("WARNING"):
            lockout_integration.report_lockout_applied("login", lockout_contracts.LOGIN_LOCKOUT_TIERS, 4, username="a")
        assert caplog.records == []

    def test_at_the_first_tier_logs_without_the_raw_username(self, caplog):
        with caplog.at_level("WARNING"):
            lockout_integration.report_lockout_applied(
                "login", lockout_contracts.LOGIN_LOCKOUT_TIERS, 5, username="alice@example.com"
            )
        assert [r.getMessage() for r in caplog.records] == ["Progressive authentication lockout applied"]
        assert "alice@example.com" not in repr(caplog.records[0].__dict__)

    def test_a_store_does_not_log_when_it_locks(self, caplog):
        store = failed_login_store.FailedLoginAttempts(state=MemoryState())
        with caplog.at_level("DEBUG"):
            for _ in range(5):
                store.record_failed_attempt("alice", "203.0.113.1")
        assert caplog.records == []

    def test_the_outage_error_is_a_503_domain_error(self):
        assert lockout_contracts.AuthSecurityStoreUnavailableError.status_code == 503
