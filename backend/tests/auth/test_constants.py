"""Tests for auth.constants module."""

import pytest

import auth.constants as auth_constants


class TestJWTConstants:
    """Test JWT configuration constants."""

    def test_jwt_algorithm_is_set(self):
        """Test that JWT algorithm is defined and is a valid algorithm."""
        assert auth_constants.JWT_ALGORITHM is not None
        assert isinstance(auth_constants.JWT_ALGORITHM, str)
        assert auth_constants.JWT_ALGORITHM in ["HS256", "HS384", "HS512"]

    def test_access_token_expiry_is_positive(self):
        """Test that access token expiry is a positive integer."""
        assert auth_constants.JWT_ACCESS_TOKEN_EXPIRE_MINUTES > 0
        assert isinstance(auth_constants.JWT_ACCESS_TOKEN_EXPIRE_MINUTES, int)

    def test_refresh_token_expiry_is_positive(self):
        """Test that refresh token expiry is a positive integer."""
        assert auth_constants.JWT_REFRESH_TOKEN_EXPIRE_DAYS > 0
        assert isinstance(auth_constants.JWT_REFRESH_TOKEN_EXPIRE_DAYS, int)

    def test_secret_key_is_set(self):
        """Test that SECRET_KEY is configured."""
        assert auth_constants.JWT_SECRET_KEY is not None
        assert isinstance(auth_constants.JWT_SECRET_KEY, str)
        assert len(auth_constants.JWT_SECRET_KEY) >= 32

    def test_session_timeout_constants(self):
        """Test that session timeout constants are valid."""
        assert isinstance(auth_constants.SESSION_IDLE_TIMEOUT_ENABLED, bool)
        assert auth_constants.SESSION_IDLE_TIMEOUT_HOURS >= 0
        assert isinstance(auth_constants.SESSION_IDLE_TIMEOUT_HOURS, int)
        assert auth_constants.SESSION_ABSOLUTE_TIMEOUT_HOURS > 0
        assert isinstance(auth_constants.SESSION_ABSOLUTE_TIMEOUT_HOURS, int)


class TestScopeConstants:
    """Test scope configuration constants."""

    def test_users_regular_scope_defined(self):
        """Test that users regular scope is properly defined."""
        assert auth_constants.USERS_REGULAR_SCOPE is not None
        assert isinstance(auth_constants.USERS_REGULAR_SCOPE, tuple)
        assert "profile" in auth_constants.USERS_REGULAR_SCOPE
        assert "users:read" in auth_constants.USERS_REGULAR_SCOPE

    def test_users_admin_scope_defined(self):
        """Test that users admin scope is properly defined."""
        assert auth_constants.USERS_ADMIN_SCOPE is not None
        assert isinstance(auth_constants.USERS_ADMIN_SCOPE, tuple)
        assert "users:write" in auth_constants.USERS_ADMIN_SCOPE
        assert "sessions:read" in auth_constants.USERS_ADMIN_SCOPE
        assert "sessions:write" in auth_constants.USERS_ADMIN_SCOPE

    def test_gears_scope_defined(self):
        """Test that gears scope is properly defined."""
        assert auth_constants.GEARS_SCOPE is not None
        assert isinstance(auth_constants.GEARS_SCOPE, tuple)
        assert "gears:read" in auth_constants.GEARS_SCOPE
        assert "gears:write" in auth_constants.GEARS_SCOPE

    def test_activities_scope_defined(self):
        """Test that activities scope is properly defined."""
        assert auth_constants.ACTIVITIES_SCOPE is not None
        assert isinstance(auth_constants.ACTIVITIES_SCOPE, tuple)
        assert "activities:read" in auth_constants.ACTIVITIES_SCOPE
        assert "activities:write" in auth_constants.ACTIVITIES_SCOPE

    def test_health_scope_defined(self):
        """Test that health scope is properly defined."""
        assert auth_constants.HEALTH_SCOPE is not None
        assert isinstance(auth_constants.HEALTH_SCOPE, tuple)
        assert "health:read" in auth_constants.HEALTH_SCOPE
        assert "health:write" in auth_constants.HEALTH_SCOPE
        assert "health_targets:read" in auth_constants.HEALTH_SCOPE
        assert "health_targets:write" in auth_constants.HEALTH_SCOPE

    def test_identity_providers_scope_defined(self):
        """Test that identity providers scopes are properly defined."""
        assert auth_constants.IDENTITY_PROVIDERS_REGULAR_SCOPE is not None
        assert isinstance(auth_constants.IDENTITY_PROVIDERS_REGULAR_SCOPE, tuple)
        assert (
            "identity_providers:read" in auth_constants.IDENTITY_PROVIDERS_REGULAR_SCOPE
        )

        assert auth_constants.IDENTITY_PROVIDERS_ADMIN_SCOPE is not None
        assert isinstance(auth_constants.IDENTITY_PROVIDERS_ADMIN_SCOPE, tuple)
        assert (
            "identity_providers:write" in auth_constants.IDENTITY_PROVIDERS_ADMIN_SCOPE
        )

    def test_server_settings_scope_defined(self):
        """Test that server settings scopes are properly defined."""
        assert auth_constants.SERVER_SETTINGS_REGULAR_SCOPE is not None
        assert isinstance(auth_constants.SERVER_SETTINGS_REGULAR_SCOPE, tuple)

        assert auth_constants.SERVER_SETTINGS_ADMIN_SCOPE is not None
        assert isinstance(auth_constants.SERVER_SETTINGS_ADMIN_SCOPE, tuple)
        assert "server_settings:read" in auth_constants.SERVER_SETTINGS_ADMIN_SCOPE
        assert "server_settings:write" in auth_constants.SERVER_SETTINGS_ADMIN_SCOPE

    def test_scope_dict_contains_all_scopes(self):
        """Test that SCOPE_DICT contains descriptions for all defined scopes."""
        assert auth_constants.SCOPE_DICT is not None
        assert isinstance(auth_constants.SCOPE_DICT, dict)

        # Check key scopes are documented
        expected_scopes = [
            "profile",
            "users:read",
            "users:write",
            "gears:read",
            "gears:write",
            "activities:read",
            "activities:write",
            "health:read",
            "health:write",
            "server_settings:read",
            "server_settings:write",
        ]

        for scope in expected_scopes:
            assert scope in auth_constants.SCOPE_DICT
            assert isinstance(auth_constants.SCOPE_DICT[scope], str)
            assert len(auth_constants.SCOPE_DICT[scope]) > 0

    def test_regular_access_scope_composition(self):
        """Test that REGULAR_ACCESS_SCOPE includes all expected regular scopes."""
        assert auth_constants.REGULAR_ACCESS_SCOPE is not None
        assert isinstance(auth_constants.REGULAR_ACCESS_SCOPE, tuple)

        # Should include users regular scope
        for scope in auth_constants.USERS_REGULAR_SCOPE:
            assert scope in auth_constants.REGULAR_ACCESS_SCOPE

        # Should include gears scope
        for scope in auth_constants.GEARS_SCOPE:
            assert scope in auth_constants.REGULAR_ACCESS_SCOPE

        # Should include activities scope
        for scope in auth_constants.ACTIVITIES_SCOPE:
            assert scope in auth_constants.REGULAR_ACCESS_SCOPE

        # Should include health scope
        for scope in auth_constants.HEALTH_SCOPE:
            assert scope in auth_constants.REGULAR_ACCESS_SCOPE

    def test_admin_access_scope_composition(self):
        """Test that ADMIN_ACCESS_SCOPE includes all regular and admin scopes."""
        assert auth_constants.ADMIN_ACCESS_SCOPE is not None
        assert isinstance(auth_constants.ADMIN_ACCESS_SCOPE, tuple)

        # Should include all regular scopes
        for scope in auth_constants.REGULAR_ACCESS_SCOPE:
            assert scope in auth_constants.ADMIN_ACCESS_SCOPE

        # Should include users admin scope
        for scope in auth_constants.USERS_ADMIN_SCOPE:
            assert scope in auth_constants.ADMIN_ACCESS_SCOPE

        # Should include identity providers admin scope
        for scope in auth_constants.IDENTITY_PROVIDERS_ADMIN_SCOPE:
            assert scope in auth_constants.ADMIN_ACCESS_SCOPE

        # Should include server settings admin scope
        for scope in auth_constants.SERVER_SETTINGS_ADMIN_SCOPE:
            assert scope in auth_constants.ADMIN_ACCESS_SCOPE

    def test_admin_scope_is_superset_of_regular(self):
        """Test that admin scope contains all permissions from regular scope."""
        regular_set = set(auth_constants.REGULAR_ACCESS_SCOPE)
        admin_set = set(auth_constants.ADMIN_ACCESS_SCOPE)

        assert regular_set.issubset(
            admin_set
        ), "Admin scope should contain all regular scope permissions"
