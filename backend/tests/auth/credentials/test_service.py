"""Tests for credential policy helpers."""

from unittest.mock import MagicMock, patch

import modules.auth.credentials.service as credentials_service


def test_resolve_password_min_length_selects_access_type():
    settings = MagicMock(password_length_admin_users=16, password_length_regular_users=8)
    assert credentials_service.resolve_password_min_length(settings, "admin") == 16
    assert credentials_service.resolve_password_min_length(settings, "regular") == 8
    assert credentials_service.resolve_password_min_length(settings, "other") == 8


def test_validate_and_hash_for_user_checks_the_policy_with_the_account_details():
    settings = MagicMock(password_length_admin_users=16, password_length_regular_users=8)
    with patch("modules.auth.credentials.service.credentials_password_policy.check_password") as check:
        result = credentials_service.validate_and_hash_password_for_user(
            settings, "regular", "secret-pass-1", username="alice", email="alice@example.com"
        )
    check.assert_called_once_with("secret-pass-1", 8, "alice", "alice@example.com")
    assert result.startswith("$")


def test_validate_and_hash_for_user_uses_the_admin_minimum():
    settings = MagicMock(password_length_admin_users=16, password_length_regular_users=8)
    with patch("modules.auth.credentials.service.credentials_password_policy.check_password") as check:
        credentials_service.validate_and_hash_password_for_user(
            settings, "admin", "adminpass-long-1", username="root", email="root@example.com"
        )
    assert check.call_args.args[1] == 16
