"""Tests for provider-backed authentication security stores."""

import hashlib
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from jasil.backends.state_memory import MemoryState
from jasil.providers import StateBackendUnavailableError

import core.key_derivation as core_key_derivation
import modules.auth.account_security.step_up_store as step_up_store_module
import modules.auth.authentication.failed_login_store as failed_login_store
import modules.auth.lockout.contracts as lockout_contracts
import modules.auth.lockout.integration_service as lockout_integration
import modules.auth.lockout.lockout_store as lockout_store


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

    def test_identifier_is_not_the_plain_sha256_of_the_username(self):
        plain = hashlib.sha256(b"alice@example.com").hexdigest()
        identifier = lockout_integration.username_log_identifier(" Alice%40Example.COM ")
        assert identifier != f"username_hash={plain}"
        assert plain not in identifier

    def test_identifier_is_stable_and_as_long_as_the_plain_digest(self):
        identifier = lockout_integration.username_log_identifier("alice")
        assert identifier == lockout_integration.username_log_identifier("alice")
        assert len(identifier.removeprefix("username_hash=")) == 64

    def test_refuses_to_fingerprint_without_a_secret_key(self):
        with patch("core.key_derivation.core_config.read_secret", return_value=""):
            core_key_derivation.derive_keys.cache_clear()
            try:
                with pytest.raises(ValueError, match="SECRET_KEY"):
                    lockout_integration.username_log_identifier("alice")
            finally:
                core_key_derivation.derive_keys.cache_clear()

    def test_lockout_state_key_still_uses_the_plain_digest(self):
        plain = hashlib.sha256(b"alice@example.com").hexdigest()
        assert lockout_store._username_digest(" Alice%40Example.COM ") == plain

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
        assert store.record_failed_attempt("alice", self.IP).client_count == 1
        assert store.record_failed_attempt("alice", self.IP).client_count == 2

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
        assert store.record_failed_attempt("alice", self.IP).client_count == 5

    def test_reset_clears_lockout(self):
        store = self._store()
        self._fail(store, 5)
        store.reset_attempts("alice", self.IP)
        assert store.is_locked_out("alice", self.IP) is False
        assert store.record_failed_attempt("alice", self.IP).client_count == 1

    def test_username_is_normalized(self):
        store = self._store()
        store.record_failed_attempt("Alice", self.IP)
        assert store.record_failed_attempt("  alice  ", self.IP).client_count == 2

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

    def test_the_account_locks_after_100_failures_from_any_addresses(self):
        store = self._store()
        assert lockout_contracts.ACCOUNT_LOGIN_LOCKOUT_TIERS[0][0] == 100
        for i in range(99):
            store.record_failed_attempt("alice", f"198.51.100.{i}")
        assert store.is_locked_out("alice", self.IP) is False
        store.record_failed_attempt("alice", "198.51.100.200")
        assert store.is_locked_out("alice", self.IP) is True
        assert store.get_lockout_time("alice", self.IP) > datetime.now(UTC) + timedelta(days=29)
        assert store.is_locked_out("bob", self.IP) is False

    def test_only_the_failure_that_reaches_100_reports_the_account_lock(self):
        store = self._store()
        records = [store.record_failed_attempt("alice", f"198.51.100.{i}") for i in range(101)]
        assert [i for i, record in enumerate(records) if record.account_locked_now] == [99]

    def test_a_known_device_is_not_refused_by_the_account_lock(self):
        store = self._store()
        for i in range(100):
            store.record_failed_attempt("alice", f"198.51.100.{i}")
        assert store.is_locked_out("alice", self.IP, known_device=True) is False
        assert store.get_lockout_time("alice", self.IP, known_device=True) is None

    def test_a_known_device_is_still_refused_by_the_client_lock(self):
        store = self._store()
        self._fail(store, 5)
        assert store.is_locked_out("alice", self.IP, known_device=True) is True

    def test_reset_clears_the_account_wide_count(self):
        store = self._store()
        for i in range(100):
            store.record_failed_attempt("alice", f"198.51.100.{i}")
        store.reset_attempts("alice", self.IP)
        assert store.is_locked_out("alice", self.IP) is False

    def test_reset_account_clears_the_account_lock_for_every_address(self):
        store = self._store()
        for i in range(100):
            store.record_failed_attempt("alice", f"198.51.100.{i}")
        store.reset_account("Alice")
        assert store.is_locked_out("alice", self.IP) is False
        assert store.record_failed_attempt("alice", "198.51.100.1").account_locked_now is False

    def test_lockout_time_is_the_later_of_the_two(self):
        store = self._store()
        self._fail(store, 5)
        for i in range(100):
            store.record_failed_attempt("alice", f"198.51.100.{i}")
        assert store.get_lockout_time("alice", self.IP) > datetime.now(UTC) + timedelta(days=29)

    def test_an_ipv6_address_counts_by_its_64_network(self):
        store = self._store()
        for host in range(5):
            store.record_failed_attempt("alice", f"2001:db8:1:2::{host + 1:x}")
        assert store.is_locked_out("alice", "2001:db8:1:2:ffff:ffff:ffff:ffff") is True
        assert store.is_locked_out("alice", "2001:db8:1:3::1") is False

    def test_an_ipv4_mapped_ipv6_address_counts_as_its_ipv4_address(self):
        store = self._store()
        self._fail(store, 5, ip="::ffff:203.0.113.1")
        assert store.is_locked_out("alice", "203.0.113.1") is True

    def test_an_address_that_is_not_an_ip_is_kept_as_it_is(self):
        store = self._store()
        self._fail(store, 5, ip="unknown")
        assert store.is_locked_out("alice", "unknown") is True
        assert store.is_locked_out("alice", self.IP) is False


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
