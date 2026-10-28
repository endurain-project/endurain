"""Tests for credential policy helpers."""

from unittest.mock import MagicMock, patch

import modules.auth.credentials.service as credentials_service


def test_resolve_password_min_length_selects_access_type():
    settings = MagicMock(password_length_admin_users=16, password_length_regular_users=8)
    assert credentials_service.resolve_password_min_length(settings, "admin") == 16
    assert credentials_service.resolve_password_min_length(settings, "regular") == 8
    assert credentials_service.resolve_password_min_length(settings, "other") == 8


def test_validate_and_hash_for_user_uses_regular_policy():
    settings = MagicMock(password_length_admin_users=16, password_length_regular_users=8, password_type="strict")
    with patch("modules.auth.credentials.service.validate_and_hash_password", return_value="hashed") as validate:
        result = credentials_service.validate_and_hash_password_for_user(settings, "regular", "secret123")
    validate.assert_called_once_with("secret123", 8, "strict")
    assert result == "hashed"


def test_validate_and_hash_for_user_uses_admin_policy():
    settings = MagicMock(password_length_admin_users=16, password_length_regular_users=8, password_type="bcrypt")
    with patch("modules.auth.credentials.service.validate_and_hash_password", return_value="hashed") as validate:
        result = credentials_service.validate_and_hash_password_for_user(settings, "admin", "adminpass")
    validate.assert_called_once_with("adminpass", 16, "bcrypt")
    assert result == "hashed"


def test_validate_and_hash_for_user_coerces_password_type_to_string():
    settings = MagicMock(password_length_admin_users=16, password_length_regular_users=8)
    settings.password_type = object()
    with patch("modules.auth.credentials.service.validate_and_hash_password", return_value="hashed") as validate:
        credentials_service.validate_and_hash_password_for_user(settings, "regular", "pw")
    assert isinstance(validate.call_args.args[2], str)
