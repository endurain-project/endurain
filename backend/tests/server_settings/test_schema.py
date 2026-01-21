"""
Tests for server_settings.schema module.

This module tests Pydantic schemas for server settings,
including validation rules and field constraints.
"""

import pytest
from pydantic import ValidationError

import server_settings.schema as server_settings_schema


class TestUnitsEnum:
    """Tests for Units enum."""

    def test_units_enum_values(self):
        """Test Units enum has correct values."""
        assert server_settings_schema.Units.METRIC.value == "metric"
        assert server_settings_schema.Units.IMPERIAL.value == "imperial"


class TestCurrencyEnum:
    """Tests for Currency enum."""

    def test_currency_enum_values(self):
        """Test Currency enum has correct values."""
        assert server_settings_schema.Currency.EURO.value == "euro"
        assert server_settings_schema.Currency.DOLLAR.value == "dollar"
        assert server_settings_schema.Currency.POUND.value == "pound"


class TestPasswordTypeEnum:
    """Tests for PasswordType enum."""

    def test_password_type_enum_values(self):
        """Test PasswordType enum has correct values."""
        assert server_settings_schema.PasswordType.STRICT.value == "strict"
        assert server_settings_schema.PasswordType.LENGTH_ONLY.value == "length_only"


class TestServerSettingsBase:
    """Tests for ServerSettingsBase schema."""

    def test_server_settings_base_valid(self):
        """Test valid ServerSettingsBase creation."""
        settings = server_settings_schema.ServerSettingsBase(
            units=server_settings_schema.Units.METRIC,
            public_shareable_links=False,
            public_shareable_links_user_info=False,
            login_photo_set=False,
            currency=server_settings_schema.Currency.EURO,
            num_records_per_page=25,
            signup_enabled=False,
            sso_enabled=False,
            local_login_enabled=True,
            sso_auto_redirect=False,
            tileserver_url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
            tileserver_attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
            map_background_color="#dddddd",
            password_type="strict",
            password_length_regular_users=8,
            password_length_admin_users=12,
        )
        assert settings.units == server_settings_schema.Units.METRIC.value
        assert settings.public_shareable_links is False
        assert settings.tileserver_url.startswith("https://")

    def test_tileserver_url_missing_protocol(self):
        """Test validation fails when URL missing protocol."""
        with pytest.raises(ValidationError) as exc_info:
            server_settings_schema.ServerSettingsBase(
                units=server_settings_schema.Units.METRIC,
                public_shareable_links=False,
                public_shareable_links_user_info=False,
                login_photo_set=False,
                currency=server_settings_schema.Currency.EURO,
                num_records_per_page=25,
                signup_enabled=False,
                sso_enabled=False,
                local_login_enabled=True,
                sso_auto_redirect=False,
                tileserver_url="tiles.example.com/{z}/{x}/{y}.png",
                tileserver_attribution="Test",
                map_background_color="#dddddd",
                password_type="strict",
                password_length_regular_users=8,
                password_length_admin_users=12,
            )
        assert "must use http:// or https://" in str(exc_info.value)

    def test_tileserver_url_http_non_localhost(self):
        """Test validation fails for http:// on non-localhost."""
        with pytest.raises(ValidationError) as exc_info:
            server_settings_schema.ServerSettingsBase(
                units=server_settings_schema.Units.METRIC,
                public_shareable_links=False,
                public_shareable_links_user_info=False,
                login_photo_set=False,
                currency=server_settings_schema.Currency.EURO,
                num_records_per_page=25,
                signup_enabled=False,
                sso_enabled=False,
                local_login_enabled=True,
                sso_auto_redirect=False,
                tileserver_url="http://tiles.example.com/{z}/{x}/{y}.png",
                tileserver_attribution="Test",
                map_background_color="#dddddd",
                password_type="strict",
                password_length_regular_users=8,
                password_length_admin_users=12,
            )
        assert "must use https://" in str(exc_info.value)

    def test_tileserver_url_http_localhost_allowed(self):
        """Test http:// is allowed for localhost."""
        settings = server_settings_schema.ServerSettingsBase(
            units=server_settings_schema.Units.METRIC,
            public_shareable_links=False,
            public_shareable_links_user_info=False,
            login_photo_set=False,
            currency=server_settings_schema.Currency.EURO,
            num_records_per_page=25,
            signup_enabled=False,
            sso_enabled=False,
            local_login_enabled=True,
            sso_auto_redirect=False,
            tileserver_url="http://localhost:8080/{z}/{x}/{y}.png",
            tileserver_attribution="Test",
            map_background_color="#dddddd",
            password_type="strict",
            password_length_regular_users=8,
            password_length_admin_users=12,
        )
        assert settings.tileserver_url == "http://localhost:8080/{z}/{x}/{y}.png"

    def test_tileserver_url_missing_placeholders(self):
        """Test validation fails when required placeholders missing."""
        with pytest.raises(ValidationError) as exc_info:
            server_settings_schema.ServerSettingsBase(
                units=server_settings_schema.Units.METRIC,
                public_shareable_links=False,
                public_shareable_links_user_info=False,
                login_photo_set=False,
                currency=server_settings_schema.Currency.EURO,
                num_records_per_page=25,
                signup_enabled=False,
                sso_enabled=False,
                local_login_enabled=True,
                sso_auto_redirect=False,
                tileserver_url="https://tiles.example.com/test.png",
                tileserver_attribution="Test",
                map_background_color="#dddddd",
                password_type="strict",
                password_length_regular_users=8,
                password_length_admin_users=12,
            )
        assert "must contain placeholders" in str(exc_info.value)

    def test_tileserver_url_dangerous_pattern_javascript(self):
        """Test validation fails for dangerous javascript: pattern."""
        with pytest.raises(ValidationError) as exc_info:
            server_settings_schema.ServerSettingsBase(
                units=server_settings_schema.Units.METRIC,
                public_shareable_links=False,
                public_shareable_links_user_info=False,
                login_photo_set=False,
                currency=server_settings_schema.Currency.EURO,
                num_records_per_page=25,
                signup_enabled=False,
                sso_enabled=False,
                local_login_enabled=True,
                sso_auto_redirect=False,
                tileserver_url="javascript:alert(1)/{z}/{x}/{y}",
                tileserver_attribution="Test",
                map_background_color="#dddddd",
                password_type="strict",
                password_length_regular_users=8,
                password_length_admin_users=12,
            )
        # javascript: gets caught by http/https protocol check first
        assert "must use http://" in str(
            exc_info.value
        ) or "contains disallowed" in str(exc_info.value)

    def test_tileserver_url_dangerous_pattern_data(self):
        """Test validation fails for dangerous data: pattern."""
        with pytest.raises(ValidationError) as exc_info:
            server_settings_schema.ServerSettingsBase(
                units=server_settings_schema.Units.METRIC,
                public_shareable_links=False,
                public_shareable_links_user_info=False,
                login_photo_set=False,
                currency=server_settings_schema.Currency.EURO,
                num_records_per_page=25,
                signup_enabled=False,
                sso_enabled=False,
                local_login_enabled=True,
                sso_auto_redirect=False,
                tileserver_url="https://example.com/data:image/{z}/{x}/{y}",
                tileserver_attribution="Test",
                map_background_color="#dddddd",
                password_type="strict",
                password_length_regular_users=8,
                password_length_admin_users=12,
            )
        assert "contains disallowed" in str(exc_info.value)

    def test_map_background_color_valid(self):
        """Test valid hex color for map background."""
        settings = server_settings_schema.ServerSettingsBase(
            units=server_settings_schema.Units.METRIC,
            public_shareable_links=False,
            public_shareable_links_user_info=False,
            login_photo_set=False,
            currency=server_settings_schema.Currency.EURO,
            num_records_per_page=25,
            signup_enabled=False,
            sso_enabled=False,
            local_login_enabled=True,
            sso_auto_redirect=False,
            tileserver_url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
            tileserver_attribution="Test",
            map_background_color="#FF0000",
            password_type="strict",
            password_length_regular_users=8,
            password_length_admin_users=12,
        )
        assert settings.map_background_color == "#FF0000"

    def test_map_background_color_invalid_format(self):
        """Test invalid hex color format."""
        with pytest.raises(ValidationError) as exc_info:
            server_settings_schema.ServerSettingsBase(
                units=server_settings_schema.Units.METRIC,
                public_shareable_links=False,
                public_shareable_links_user_info=False,
                login_photo_set=False,
                currency=server_settings_schema.Currency.EURO,
                num_records_per_page=25,
                signup_enabled=False,
                sso_enabled=False,
                local_login_enabled=True,
                sso_auto_redirect=False,
                tileserver_url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
                tileserver_attribution="Test",
                map_background_color="red",
                password_type="strict",
                password_length_regular_users=8,
                password_length_admin_users=12,
            )
        assert "map_background_color" in str(exc_info.value)

    def test_tileserver_attribution_sanitized(self):
        """Test that tileserver attribution is sanitized."""
        settings = server_settings_schema.ServerSettingsBase(
            units=server_settings_schema.Units.METRIC,
            public_shareable_links=False,
            public_shareable_links_user_info=False,
            login_photo_set=False,
            currency=server_settings_schema.Currency.EURO,
            num_records_per_page=25,
            signup_enabled=False,
            sso_enabled=False,
            local_login_enabled=True,
            sso_auto_redirect=False,
            tileserver_url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
            tileserver_attribution='&copy; <a href="https://example.com">Example</a>',
            map_background_color="#dddddd",
            password_type="strict",
            password_length_regular_users=8,
            password_length_admin_users=12,
        )
        # Sanitization should preserve safe HTML
        assert "href=" in settings.tileserver_attribution


class TestServerSettings:
    """Tests for ServerSettings schema."""

    def test_server_settings_with_id(self):
        """Test ServerSettings schema with id field."""
        settings = server_settings_schema.ServerSettings(
            id=1,
            units=server_settings_schema.Units.METRIC,
            public_shareable_links=False,
            public_shareable_links_user_info=False,
            login_photo_set=False,
            currency=server_settings_schema.Currency.EURO,
            num_records_per_page=25,
            signup_enabled=False,
            sso_enabled=False,
            local_login_enabled=True,
            sso_auto_redirect=False,
            tileserver_url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
            tileserver_attribution="Test",
            map_background_color="#dddddd",
            password_type="strict",
            password_length_regular_users=8,
            password_length_admin_users=12,
        )
        assert settings.id == 1


class TestServerSettingsEdit:
    """Tests for ServerSettingsEdit schema."""

    def test_server_settings_edit_with_signup_fields(self):
        """Test ServerSettingsEdit includes signup requirement fields."""
        settings = server_settings_schema.ServerSettingsEdit(
            id=1,
            units=server_settings_schema.Units.METRIC,
            public_shareable_links=False,
            public_shareable_links_user_info=False,
            login_photo_set=False,
            currency=server_settings_schema.Currency.EURO,
            num_records_per_page=25,
            signup_enabled=True,
            signup_require_admin_approval=True,
            signup_require_email_verification=False,
            sso_enabled=False,
            local_login_enabled=True,
            sso_auto_redirect=False,
            tileserver_url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
            tileserver_attribution="Test",
            map_background_color="#dddddd",
            password_type="strict",
            password_length_regular_users=8,
            password_length_admin_users=12,
        )
        assert settings.signup_require_admin_approval is True
        assert settings.signup_require_email_verification is False


class TestTileMapsTemplate:
    """Tests for TileMapsTemplate schema."""

    def test_tile_maps_template_valid(self):
        """Test valid TileMapsTemplate creation."""
        template = server_settings_schema.TileMapsTemplate(
            template_id="openstreetmap",
            name="OpenStreetMap",
            url_template="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
            map_background_color="#e8e8e8",
            requires_api_key_frontend=False,
            requires_api_key_backend=False,
        )
        assert template.template_id == "openstreetmap"
        assert template.name == "OpenStreetMap"
        assert template.requires_api_key_frontend is False
        assert template.requires_api_key_backend is False

    def test_tile_maps_template_invalid_background_color(self):
        """Test TileMapsTemplate with invalid background color."""
        with pytest.raises(ValidationError) as exc_info:
            server_settings_schema.TileMapsTemplate(
                template_id="test",
                name="Test",
                url_template="https://example.com/{z}/{x}/{y}.png",
                attribution="Test",
                map_background_color="invalid",
                requires_api_key_frontend=False,
                requires_api_key_backend=False,
            )
        assert "map_background_color" in str(exc_info.value)
