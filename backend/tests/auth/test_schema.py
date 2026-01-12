"""
Tests for auth.schema module.

This module tests Pydantic schemas and dependency classes for authentication,
including login requests, MFA management, and failed attempt tracking.
"""

import pytest
from datetime import datetime, timedelta, timezone
from pydantic import ValidationError

import auth.schema as auth_schema


class TestLoginRequest:
    """Tests for LoginRequest Pydantic model."""

    def test_login_request_valid(self):
        """Test valid login request."""
        request = auth_schema.LoginRequest(username="testuser", password="Password1!")
        assert request.username == "testuser"
        assert request.password == "Password1!"

    def test_login_request_username_too_short(self):
        """Test login request with empty username."""
        with pytest.raises(ValidationError) as exc_info:
            auth_schema.LoginRequest(username="", password="Password1!")
        assert "username" in str(exc_info.value)

    def test_login_request_username_too_long(self):
        """Test login request with username exceeding max length."""
        with pytest.raises(ValidationError) as exc_info:
            auth_schema.LoginRequest(username="a" * 251, password="Password1!")
        assert "username" in str(exc_info.value)

    def test_login_request_password_too_short(self):
        """Test login request with password less than 8 characters."""
        with pytest.raises(ValidationError) as exc_info:
            auth_schema.LoginRequest(username="testuser", password="Pass1!")
        assert "password" in str(exc_info.value)


class TestMFALoginRequest:
    """Tests for MFALoginRequest Pydantic model."""

    def test_mfa_login_request_valid(self):
        """Test valid MFA login request with 6-digit code."""
        request = auth_schema.MFALoginRequest(username="testuser", mfa_code="123456")
        assert request.username == "testuser"
        assert request.mfa_code == "123456"

    def test_mfa_login_request_invalid_code_format_letters(self):
        """Test MFA login request with non-numeric code."""
        with pytest.raises(ValidationError) as exc_info:
            auth_schema.MFALoginRequest(username="testuser", mfa_code="12345a")
        assert "mfa_code" in str(exc_info.value)

    def test_mfa_login_request_invalid_code_too_short(self):
        """Test MFA login request with code less than 6 digits."""
        with pytest.raises(ValidationError) as exc_info:
            auth_schema.MFALoginRequest(username="testuser", mfa_code="12345")
        assert "mfa_code" in str(exc_info.value)

    def test_mfa_login_request_invalid_code_too_long(self):
        """Test MFA login request with code more than 6 digits."""
        with pytest.raises(ValidationError) as exc_info:
            auth_schema.MFALoginRequest(username="testuser", mfa_code="1234567")
        assert "mfa_code" in str(exc_info.value)


class TestMFARequiredResponse:
    """Tests for MFARequiredResponse Pydantic model."""

    def test_mfa_required_response_defaults(self):
        """Test MFA required response with default values."""
        response = auth_schema.MFARequiredResponse(username="testuser")
        assert response.mfa_required is True
        assert response.username == "testuser"
        assert response.message == "MFA verification required"

    def test_mfa_required_response_custom_message(self):
        """Test MFA required response with custom message."""
        response = auth_schema.MFARequiredResponse(
            username="testuser", message="Custom MFA message"
        )
        assert response.mfa_required is True
        assert response.message == "Custom MFA message"

    def test_mfa_required_response_explicit_false(self):
        """Test MFA required response with explicit False."""
        response = auth_schema.MFARequiredResponse(
            mfa_required=False, username="testuser"
        )
        assert response.mfa_required is False


class TestPendingMFALogin:
    """Tests for PendingMFALogin class."""

    def test_add_and_get_pending_login(self):
        """Test adding and retrieving pending MFA login."""
        store = auth_schema.PendingMFALogin()
        store.add_pending_login("testuser", 123)
        assert store.get_pending_login("testuser") == 123

    def test_get_pending_login_not_found(self):
        """Test getting non-existent pending login returns None."""
        store = auth_schema.PendingMFALogin()
        assert store.get_pending_login("nonexistent") is None

    def test_has_pending_login(self):
        """Test checking if username has pending login."""
        store = auth_schema.PendingMFALogin()
        store.add_pending_login("testuser", 123)
        assert store.has_pending_login("testuser") is True
        assert store.has_pending_login("nonexistent") is False

    def test_delete_pending_login(self):
        """Test deleting pending login."""
        store = auth_schema.PendingMFALogin()
        store.add_pending_login("testuser", 123)
        store.delete_pending_login("testuser")
        assert store.get_pending_login("testuser") is None

    def test_delete_nonexistent_pending_login(self):
        """Test deleting non-existent pending login doesn't raise error."""
        store = auth_schema.PendingMFALogin()
        store.delete_pending_login("nonexistent")  # Should not raise

    def test_clear_all(self):
        """Test clearing all pending logins."""
        store = auth_schema.PendingMFALogin()
        store.add_pending_login("user1", 1)
        store.add_pending_login("user2", 2)
        store.clear_all()
        assert store.get_pending_login("user1") is None
        assert store.get_pending_login("user2") is None

    def test_is_not_locked_out_initially(self):
        """Test user is not locked out initially."""
        store = auth_schema.PendingMFALogin()
        assert store.is_locked_out("testuser") is False

    def test_lockout_after_5_failures(self):
        """Test 5-minute lockout after 5 failed attempts."""
        store = auth_schema.PendingMFALogin()
        for _ in range(5):
            store.record_failed_attempt("testuser")
        assert store.is_locked_out("testuser") is True
        lockout_time = store.get_lockout_time("testuser")
        assert lockout_time is not None
        assert lockout_time > datetime.now(timezone.utc)

    def test_lockout_after_10_failures(self):
        """Test 30-minute lockout after 10 failed attempts."""
        store = auth_schema.PendingMFALogin()
        for _ in range(10):
            store.record_failed_attempt("testuser")
        assert store.is_locked_out("testuser") is True

    def test_lockout_after_15_failures(self):
        """Test 2-hour lockout after 15 failed attempts."""
        store = auth_schema.PendingMFALogin()
        for _ in range(15):
            store.record_failed_attempt("testuser")
        assert store.is_locked_out("testuser") is True

    def test_failed_attempt_count_doesnt_increment_while_locked(self):
        """Test failed attempt counter doesn't increment during lockout."""
        store = auth_schema.PendingMFALogin()
        for _ in range(5):
            store.record_failed_attempt("testuser")
        # Try to increment during lockout
        count_before = store.record_failed_attempt("testuser")
        count_after = store.record_failed_attempt("testuser")
        assert count_before == count_after

    def test_reset_failed_attempts(self):
        """Test resetting failed attempts on successful verification."""
        store = auth_schema.PendingMFALogin()
        store.record_failed_attempt("testuser")
        store.record_failed_attempt("testuser")
        store.reset_failed_attempts("testuser")
        assert store.is_locked_out("testuser") is False
        assert store.get_lockout_time("testuser") is None

    def test_get_lockout_time_returns_none_when_not_locked(self):
        """Test get_lockout_time returns None when user not locked."""
        store = auth_schema.PendingMFALogin()
        assert store.get_lockout_time("testuser") is None

    def test_clear_all_clears_failed_attempts(self):
        """Test clear_all() clears both pending logins and failed attempts."""
        store = auth_schema.PendingMFALogin()
        store.add_pending_login("testuser", 123)
        for _ in range(5):
            store.record_failed_attempt("testuser")
        store.clear_all()
        assert store.is_locked_out("testuser") is False


class TestFailedLoginAttempts:
    """Tests for FailedLoginAttempts class."""

    def test_is_not_locked_out_initially(self):
        """Test user is not locked out initially."""
        tracker = auth_schema.FailedLoginAttempts()
        assert tracker.is_locked_out("testuser") is False

    def test_lockout_after_5_failures(self):
        """Test 5-minute lockout after 5 failed login attempts."""
        tracker = auth_schema.FailedLoginAttempts()
        for _ in range(5):
            tracker.record_failed_attempt("testuser")
        assert tracker.is_locked_out("testuser") is True
        lockout_time = tracker.get_lockout_time("testuser")
        assert lockout_time is not None
        assert lockout_time > datetime.now(timezone.utc)

    def test_lockout_after_10_failures(self):
        """Test 30-minute lockout after 10 failed login attempts."""
        tracker = auth_schema.FailedLoginAttempts()
        for _ in range(10):
            tracker.record_failed_attempt("testuser")
        assert tracker.is_locked_out("testuser") is True

    def test_lockout_after_20_failures(self):
        """Test 24-hour lockout after 20 failed login attempts."""
        tracker = auth_schema.FailedLoginAttempts()
        for _ in range(20):
            tracker.record_failed_attempt("testuser")
        assert tracker.is_locked_out("testuser") is True

    def test_failed_attempt_count_returns_correctly(self):
        """Test record_failed_attempt returns current count."""
        tracker = auth_schema.FailedLoginAttempts()
        count1 = tracker.record_failed_attempt("testuser")
        count2 = tracker.record_failed_attempt("testuser")
        count3 = tracker.record_failed_attempt("testuser")
        assert count1 == 1
        assert count2 == 2
        assert count3 == 3

    def test_failed_attempt_count_doesnt_increment_while_locked(self):
        """Test failed attempt counter doesn't increment during lockout."""
        tracker = auth_schema.FailedLoginAttempts()
        for _ in range(5):
            tracker.record_failed_attempt("testuser")
        # Try to increment during lockout
        count_before = tracker.record_failed_attempt("testuser")
        count_after = tracker.record_failed_attempt("testuser")
        assert count_before == count_after

    def test_reset_attempts(self):
        """Test resetting failed attempts on successful login."""
        tracker = auth_schema.FailedLoginAttempts()
        tracker.record_failed_attempt("testuser")
        tracker.record_failed_attempt("testuser")
        tracker.reset_attempts("testuser")
        assert tracker.is_locked_out("testuser") is False
        assert tracker.get_lockout_time("testuser") is None

    def test_get_lockout_time_returns_none_when_not_locked(self):
        """Test get_lockout_time returns None when user not locked."""
        tracker = auth_schema.FailedLoginAttempts()
        assert tracker.get_lockout_time("testuser") is None

    def test_clear_all(self):
        """Test clearing all failed attempt records."""
        tracker = auth_schema.FailedLoginAttempts()
        tracker.record_failed_attempt("user1")
        tracker.record_failed_attempt("user2")
        tracker.clear_all()
        assert tracker.is_locked_out("user1") is False
        assert tracker.is_locked_out("user2") is False

    def test_different_users_tracked_independently(self):
        """Test different users have independent failed attempt tracking."""
        tracker = auth_schema.FailedLoginAttempts()
        for _ in range(3):
            tracker.record_failed_attempt("user1")
        for _ in range(5):
            tracker.record_failed_attempt("user2")
        assert tracker.is_locked_out("user1") is False
        assert tracker.is_locked_out("user2") is True


class TestDependencyFunctions:
    """Tests for dependency injection functions."""

    def test_get_pending_mfa_store(self):
        """Test get_pending_mfa_store returns PendingMFALogin instance."""
        store = auth_schema.get_pending_mfa_store()
        assert isinstance(store, auth_schema.PendingMFALogin)

    def test_get_pending_mfa_store_returns_singleton(self):
        """Test get_pending_mfa_store returns same instance."""
        store1 = auth_schema.get_pending_mfa_store()
        store2 = auth_schema.get_pending_mfa_store()
        assert store1 is store2

    def test_get_failed_login_attempts(self):
        """Test get_failed_login_attempts returns FailedLoginAttempts instance."""
        tracker = auth_schema.get_failed_login_attempts()
        assert isinstance(tracker, auth_schema.FailedLoginAttempts)

    def test_get_failed_login_attempts_returns_singleton(self):
        """Test get_failed_login_attempts returns same instance."""
        tracker1 = auth_schema.get_failed_login_attempts()
        tracker2 = auth_schema.get_failed_login_attempts()
        assert tracker1 is tracker2

    def test_pending_mfa_login_record_attempt_while_locked(self):
        """
        Test that failed attempts don't increment while locked.
        """
        store = auth_schema.PendingMFALogin()

        # Record 5 failures to trigger lockout
        for _ in range(5):
            store.record_failed_attempt("testuser")

        # Verify user is locked out
        assert store.is_locked_out("testuser") is True

        # Try to record more failures during lockout
        count1 = store.record_failed_attempt("testuser")
        count2 = store.record_failed_attempt("testuser")

        # Count should not increase
        assert count1 == count2

    def test_failed_login_attempts_record_attempt_while_locked(self):
        """
        Test that failed attempts don't increment while locked.
        """
        store = auth_schema.FailedLoginAttempts()

        # Record 5 failures to trigger lockout
        for _ in range(5):
            store.record_failed_attempt("testuser")

        # Verify user is locked out
        assert store.is_locked_out("testuser") is True

        # Try to record more failures during lockout
        count1 = store.record_failed_attempt("testuser")
        count2 = store.record_failed_attempt("testuser")

        # Count should not increase
        assert count1 == count2

    def test_pending_mfa_login_lockout_10_attempts(self):
        """
        Test 30-minute lockout logging after 10 MFA failures.
        """
        store = auth_schema.PendingMFALogin()

        # Record 10 failures to trigger 30-min lockout
        for _ in range(10):
            store.record_failed_attempt("testuser")

        # Verify user is locked out
        assert store.is_locked_out("testuser") is True
        lockout_time = store.get_lockout_time("testuser")
        assert lockout_time is not None

    def test_pending_mfa_login_lockout_15_attempts(self):
        """
        Test 2-hour lockout logging after 15 MFA failures.
        """
        store = auth_schema.PendingMFALogin()

        # Record 15 failures to trigger 2-hour lockout
        for _ in range(15):
            store.record_failed_attempt("testuser")

        # Verify user is locked out
        assert store.is_locked_out("testuser") is True
        lockout_time = store.get_lockout_time("testuser")
        assert lockout_time is not None

    def test_failed_login_attempts_lockout_10_attempts(self):
        """
        Test 30-minute lockout logging after 10 login failures.
        """
        store = auth_schema.FailedLoginAttempts()

        # Record 10 failures to trigger 30-min lockout
        for _ in range(10):
            store.record_failed_attempt("testuser")

        # Verify user is locked out
        assert store.is_locked_out("testuser") is True
        lockout_time = store.get_lockout_time("testuser")
        assert lockout_time is not None

    def test_failed_login_attempts_lockout_20_attempts(self):
        """
        Test 24-hour lockout logging after 20 login failures.
        """
        store = auth_schema.FailedLoginAttempts()

        # Record 20 failures to trigger 24-hour lockout
        for _ in range(20):
            store.record_failed_attempt("testuser")

        # Verify user is locked out
        assert store.is_locked_out("testuser") is True
        lockout_time = store.get_lockout_time("testuser")
        assert lockout_time is not None

    def test_pending_mfa_login_lockout_expired_auto_reset(self):
        """Test that expired lockout is automatically reset when checking."""
        from unittest.mock import patch
        from datetime import timedelta

        store = auth_schema.PendingMFALogin()

        # Simulate lockout in the past
        past_time = datetime.now(timezone.utc) - timedelta(hours=1)
        store._failed_attempts["testuser"] = (5, past_time)

        # Check if locked out - should return False and reset
        assert store.is_locked_out("testuser") is False
        assert "testuser" not in store._failed_attempts

    def test_failed_login_attempts_lockout_expired_auto_reset(self):
        """Test that expired lockout is automatically reset when checking."""
        from datetime import timedelta

        store = auth_schema.FailedLoginAttempts()

        # Simulate lockout in the past
        past_time = datetime.now(timezone.utc) - timedelta(hours=1)
        store._attempts["testuser"] = (5, past_time)

        # Check if locked out - should return False and reset
        assert store.is_locked_out("testuser") is False
        assert "testuser" not in store._attempts

    def test_pending_mfa_get_lockout_time_expired(self):
        """Test get_lockout_time returns None for expired lockouts."""
        from datetime import timedelta

        store = auth_schema.PendingMFALogin()

        # Simulate expired lockout
        past_time = datetime.now(timezone.utc) - timedelta(hours=1)
        store._failed_attempts["testuser"] = (5, past_time)

        # Should return None for expired lockout
        assert store.get_lockout_time("testuser") is None

    def test_failed_login_attempts_get_lockout_time_expired(self):
        """Test get_lockout_time returns None for expired lockouts."""
        from datetime import timedelta

        store = auth_schema.FailedLoginAttempts()

        # Simulate expired lockout
        past_time = datetime.now(timezone.utc) - timedelta(hours=1)
        store._attempts["testuser"] = (5, past_time)

        # Should return None for expired lockout
        assert store.get_lockout_time("testuser") is None
