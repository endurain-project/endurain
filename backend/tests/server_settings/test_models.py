"""
Tests for server_settings.models module.

This module tests the ServerSettings SQLAlchemy model,
including field defaults and constraints.
"""

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

import modules.server_settings.models as server_settings_models
from tests._helpers.db import create_sqlite_session


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
        assert hasattr(server_settings_models.ServerSettings, "public_shareable_links_user_info")
        assert hasattr(server_settings_models.ServerSettings, "login_photo_set")
        assert hasattr(server_settings_models.ServerSettings, "currency")
        assert hasattr(server_settings_models.ServerSettings, "num_records_per_page")
        assert hasattr(server_settings_models.ServerSettings, "signup_enabled")
        assert hasattr(server_settings_models.ServerSettings, "signup_require_admin_approval")
        assert hasattr(server_settings_models.ServerSettings, "signup_require_email_verification")
        assert hasattr(server_settings_models.ServerSettings, "sso_enabled")
        assert hasattr(server_settings_models.ServerSettings, "local_login_enabled")
        assert hasattr(server_settings_models.ServerSettings, "sso_auto_redirect")
        assert hasattr(server_settings_models.ServerSettings, "tileserver_url")
        assert hasattr(server_settings_models.ServerSettings, "tileserver_attribution")
        assert hasattr(server_settings_models.ServerSettings, "map_background_color")
        assert not hasattr(server_settings_models.ServerSettings, "password_type")
        assert hasattr(server_settings_models.ServerSettings, "password_length_regular_users")
        assert hasattr(server_settings_models.ServerSettings, "password_length_admin_users")

    def test_server_settings_default_values(self):
        """Test default values for ServerSettings fields."""
        # Test defaults by inspecting column definitions
        assert server_settings_models.ServerSettings.id.default.arg == 1
        assert server_settings_models.ServerSettings.units.default.arg == "metric"
        assert server_settings_models.ServerSettings.public_shareable_links.default.arg is False
        assert server_settings_models.ServerSettings.public_shareable_links_user_info.default.arg is False
        assert server_settings_models.ServerSettings.login_photo_set.default.arg is False
        assert server_settings_models.ServerSettings.currency.default.arg == "euro"
        assert server_settings_models.ServerSettings.num_records_per_page.default.arg == 25
        assert server_settings_models.ServerSettings.signup_enabled.default.arg is False
        assert server_settings_models.ServerSettings.signup_require_admin_approval.default.arg is True
        assert server_settings_models.ServerSettings.signup_require_email_verification.default.arg is True
        assert server_settings_models.ServerSettings.sso_enabled.default.arg is False
        assert server_settings_models.ServerSettings.local_login_enabled.default.arg is True
        assert server_settings_models.ServerSettings.sso_auto_redirect.default.arg is False
        assert (
            server_settings_models.ServerSettings.tileserver_url.default.arg
            == "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        )
        assert server_settings_models.ServerSettings.map_background_color.default.arg == "#dddddd"
        assert server_settings_models.ServerSettings.password_length_regular_users.default.arg == 15
        assert server_settings_models.ServerSettings.password_length_admin_users.default.arg == 15

    def test_breach_check_is_off_by_default(self):
        """Hash prefixes go to a third party only after an administrator opts in (docs/features/server-settings.md)."""
        column = server_settings_models.ServerSettings.password_breach_check_enabled
        assert column.default.arg is False
        assert str(column.server_default.arg) == "false"
        assert column.nullable is False

    def test_sso_sign_up_is_off_by_default(self):
        """A public identity provider must not open registration until an administrator opts in
        (docs/features/single-sign-on.md)."""
        column = server_settings_models.ServerSettings.signup_sso_enabled
        assert column.default.arg is False
        assert str(column.server_default.arg) == "false"
        assert column.nullable is False

    def test_server_settings_nullable_fields(self):
        """Test ServerSettings model nullable configuration."""
        # All fields should be non-nullable
        assert server_settings_models.ServerSettings.id.nullable is False
        assert server_settings_models.ServerSettings.units.nullable is False
        assert server_settings_models.ServerSettings.public_shareable_links.nullable is False
        assert server_settings_models.ServerSettings.currency.nullable is False
        assert server_settings_models.ServerSettings.num_records_per_page.nullable is False

    def test_server_settings_primary_key(self):
        """Test that id is the primary key."""
        mapper = inspect(server_settings_models.ServerSettings)
        primary_keys = [key.name for key in mapper.primary_key]
        assert primary_keys == ["id"]

    def test_server_settings_check_constraint(self):
        """Test that single_row_check constraint exists."""
        constraints = server_settings_models.ServerSettings.__table_args__
        assert {c.name for c in constraints} == {
            "single_row_check",
            "geocoding_service_check",
            "geocoding_rate_limit_check",
            "session_absolute_not_below_idle_check",
            "session_idle_timeout_hours_check",
            "session_absolute_timeout_hours_check",
            "access_token_expire_minutes_check",
            "refresh_token_expire_days_check",
            "api_key_max_lifetime_days_check",
            "read_notification_retention_days_check",
            "audit_retention_days_check",
        }


class TestSessionAbsoluteTimeoutDefault:
    """The absolute session timeout defaults to 30 days."""

    def test_default_and_server_default_are_720_hours(self):
        column = server_settings_models.ServerSettings.__table__.c.session_absolute_timeout_hours
        assert column.default.arg == 720
        assert str(column.server_default.arg) == "720"


class TestApiKeyMaxLifetimeDefault:
    """New API keys last at most 365 days unless an administrator changes it (docs/features and docs/integrate)."""

    def test_default_and_server_default_are_365_days(self):
        column = server_settings_models.ServerSettings.__table__.c.api_key_max_lifetime_days
        assert column.default.arg == 365
        assert str(column.server_default.arg) == "365"


class TestAuditRetentionColumns:
    """Audit-trail retention and legal hold, kept with the other data-retention settings."""

    def test_defaults_keep_ninety_days_without_a_hold(self):
        table = server_settings_models.ServerSettings.__table__
        assert (table.c.audit_retention_days.default.arg, str(table.c.audit_retention_days.server_default.arg)) == (
            90,
            "90",
        )
        assert (table.c.audit_legal_hold.default.arg, str(table.c.audit_legal_hold.server_default.arg)) == (
            False,
            "false",
        )
        assert not table.c.audit_retention_days.nullable
        assert not table.c.audit_legal_hold.nullable

    @staticmethod
    def _store(days: int) -> None:
        db = create_sqlite_session()
        try:
            db.add(server_settings_models.ServerSettings(audit_retention_days=days))
            db.commit()
        finally:
            db.close()

    @pytest.mark.parametrize("days", [0, 30, 36500])
    def test_the_constraint_accepts_zero_or_the_floor_to_the_maximum(self, days):
        self._store(days)

    @pytest.mark.parametrize("days", [-1, 1, 29, 36501])
    def test_the_constraint_refuses_anything_else(self, days):
        with pytest.raises(IntegrityError, match="audit_retention_days_check"):
            self._store(days)
