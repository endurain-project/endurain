"""
Tests for server_settings.models module.

This module tests the ServerSettings SQLAlchemy model,
including field defaults and constraints.
"""

import pytest
from sqlalchemy import inspect

import server_settings.models as server_settings_models


class TestServerSettingsModel:
    """Test suite for ServerSettings model."""

    def test_server_settings_table_name(self):
        """Test that table name is correct."""
        assert server_settings_models.ServerSettings.__tablename__ == "server_settings"

    def test_server_settings_columns_exist(self):
        """Test ServerSettings model has all expected columns."""
        assert hasattr(server_settings_models.ServerSettings, "id")
        assert hasattr(server_settings_models.ServerSettings, "units")
        assert hasattr(server_settings_models.ServerSettings, "public_shareable_links")
        assert hasattr(
            server_settings_models.ServerSettings, "public_shareable_links_user_info"
        )
        assert hasattr(server_settings_models.ServerSettings, "login_photo_set")
        assert hasattr(server_settings_models.ServerSettings, "currency")
        assert hasattr(server_settings_models.ServerSettings, "num_records_per_page")
        assert hasattr(server_settings_models.ServerSettings, "signup_enabled")
        assert hasattr(
            server_settings_models.ServerSettings, "signup_require_admin_approval"
        )
        assert hasattr(
            server_settings_models.ServerSettings, "signup_require_email_verification"
        )
        assert hasattr(server_settings_models.ServerSettings, "sso_enabled")
        assert hasattr(server_settings_models.ServerSettings, "local_login_enabled")
        assert hasattr(server_settings_models.ServerSettings, "sso_auto_redirect")
        assert hasattr(server_settings_models.ServerSettings, "tileserver_url")
        assert hasattr(server_settings_models.ServerSettings, "tileserver_attribution")
        assert hasattr(server_settings_models.ServerSettings, "map_background_color")
        assert hasattr(server_settings_models.ServerSettings, "password_type")
        assert hasattr(
            server_settings_models.ServerSettings, "password_length_regular_users"
        )
        assert hasattr(
            server_settings_models.ServerSettings, "password_length_admin_users"
        )

    def test_server_settings_default_values(self):
        """Test default values for ServerSettings fields."""
        # Test defaults by inspecting column definitions
        assert server_settings_models.ServerSettings.id.default.arg == 1
        assert server_settings_models.ServerSettings.units.default.arg == "metric"
        assert (
            server_settings_models.ServerSettings.public_shareable_links.default.arg
            is False
        )
        assert (
            server_settings_models.ServerSettings.public_shareable_links_user_info.default.arg
            is False
        )
        assert (
            server_settings_models.ServerSettings.login_photo_set.default.arg is False
        )
        assert server_settings_models.ServerSettings.currency.default.arg == "euro"
        assert (
            server_settings_models.ServerSettings.num_records_per_page.default.arg == 25
        )
        assert server_settings_models.ServerSettings.signup_enabled.default.arg is False
        assert (
            server_settings_models.ServerSettings.signup_require_admin_approval.default.arg
            is True
        )
        assert (
            server_settings_models.ServerSettings.signup_require_email_verification.default.arg
            is True
        )
        assert server_settings_models.ServerSettings.sso_enabled.default.arg is False
        assert (
            server_settings_models.ServerSettings.local_login_enabled.default.arg
            is True
        )
        assert (
            server_settings_models.ServerSettings.sso_auto_redirect.default.arg is False
        )
        assert (
            server_settings_models.ServerSettings.tileserver_url.default.arg
            == "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        )
        assert (
            server_settings_models.ServerSettings.map_background_color.default.arg
            == "#dddddd"
        )
        assert (
            server_settings_models.ServerSettings.password_type.default.arg == "strict"
        )
        assert (
            server_settings_models.ServerSettings.password_length_regular_users.default.arg
            == 8
        )
        assert (
            server_settings_models.ServerSettings.password_length_admin_users.default.arg
            == 12
        )

    def test_server_settings_nullable_fields(self):
        """Test ServerSettings model nullable configuration."""
        # All fields should be non-nullable
        assert server_settings_models.ServerSettings.id.nullable is False
        assert server_settings_models.ServerSettings.units.nullable is False
        assert (
            server_settings_models.ServerSettings.public_shareable_links.nullable
            is False
        )
        assert server_settings_models.ServerSettings.currency.nullable is False
        assert (
            server_settings_models.ServerSettings.num_records_per_page.nullable is False
        )

    def test_server_settings_primary_key(self):
        """Test that id is the primary key."""
        mapper = inspect(server_settings_models.ServerSettings)
        primary_keys = [key.name for key in mapper.primary_key]
        assert primary_keys == ["id"]

    def test_server_settings_check_constraint(self):
        """Test that single_row_check constraint exists."""
        constraints = server_settings_models.ServerSettings.__table_args__
        assert len(constraints) == 1
        constraint = constraints[0]
        assert constraint.name == "single_row_check"
