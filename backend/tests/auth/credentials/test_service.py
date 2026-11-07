"""Tests for credential policy helpers."""

from unittest.mock import MagicMock, patch

import pytest

import core.exceptions as core_exceptions
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


def test_require_password_change_flags_the_credential_without_touching_the_hash(mock_db):
    with (
        patch.object(credentials_service, "has_local_password", return_value=True),
        patch.object(credentials_service.credentials_crud, "set_password_change_required") as mark,
    ):
        credentials_service.require_password_change(3, mock_db)

    mark.assert_called_once_with(3, mock_db)


def test_require_password_change_refuses_an_account_without_a_local_password(mock_db):
    with (
        patch.object(credentials_service, "has_local_password", return_value=False),
        patch.object(credentials_service.credentials_crud, "set_password_change_required") as mark,
        pytest.raises(core_exceptions.ConflictError),
    ):
        credentials_service.require_password_change(3, mock_db)

    mark.assert_not_called()
