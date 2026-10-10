"""Tests for auth.password_policy helpers."""

from unittest.mock import MagicMock

import modules.auth.password_policy as password_policy


class TestResolvePasswordMinLength:
    """Tests for resolve_password_min_length."""

    def test_admin_access_type_returns_admin_length(self):
        """Admin access type uses the admin password minimum length."""
        settings = MagicMock()
        settings.password_length_admin_users = 16
        settings.password_length_regular_users = 8

        result = password_policy.resolve_password_min_length(settings, "admin")

        assert result == 16

    def test_regular_access_type_returns_regular_length(self):
        """Non-admin access type uses the regular password minimum length."""
        settings = MagicMock()
        settings.password_length_admin_users = 16
        settings.password_length_regular_users = 8

        result = password_policy.resolve_password_min_length(settings, "regular")

        assert result == 8

    def test_unknown_access_type_falls_back_to_regular_length(self):
        """Any unrecognised access type falls back to regular minimum length."""
        settings = MagicMock()
        settings.password_length_admin_users = 16
        settings.password_length_regular_users = 8

        result = password_policy.resolve_password_min_length(settings, "superuser")

        assert result == 8


class TestValidateAndHashForUser:
    """Tests for validate_and_hash_for_user."""

    def test_regular_user_delegates_with_correct_min_length(self):
        """Regular-user call passes the regular min-length to identity service."""
        identity_service = MagicMock()
        identity_service.validate_and_hash_password.return_value = "hashed"

        settings = MagicMock()
        settings.password_length_regular_users = 8
        settings.password_length_admin_users = 16
        settings.password_type = "strict"

        result = password_policy.validate_and_hash_for_user(identity_service, settings, "regular", "secret123")

        identity_service.validate_and_hash_password.assert_called_once_with("secret123", 8, "strict")
        assert result == "hashed"

    def test_admin_user_delegates_with_admin_min_length(self):
        """Admin-user call passes the admin min-length to identity service."""
        identity_service = MagicMock()
        identity_service.validate_and_hash_password.return_value = "admin-hashed"

        settings = MagicMock()
        settings.password_length_regular_users = 8
        settings.password_length_admin_users = 16
        settings.password_type = "bcrypt"

        result = password_policy.validate_and_hash_for_user(identity_service, settings, "admin", "adminpass")

        identity_service.validate_and_hash_password.assert_called_once_with("adminpass", 16, "bcrypt")
        assert result == "admin-hashed"

    def test_password_type_is_coerced_to_string(self):
        """password_type is passed as str() even if settings returns an object."""
        identity_service = MagicMock()
        identity_service.validate_and_hash_password.return_value = "ok"

        settings = MagicMock()
        settings.password_length_regular_users = 8
        settings.password_length_admin_users = 12
        settings.password_type = object()  # non-string value

        password_policy.validate_and_hash_for_user(identity_service, settings, "regular", "pw")

        _call_args = identity_service.validate_and_hash_password.call_args
        assert isinstance(_call_args[0][2], str)
