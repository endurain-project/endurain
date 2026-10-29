"""
Tests for server_settings.crud module.

This module tests the persistence of the singleton server settings row.
"""

from unittest.mock import MagicMock, patch

import pytest

import core.exceptions as core_exceptions
import modules.server_settings.crud as server_settings_crud
import modules.server_settings.models as server_settings_models
import modules.server_settings.schema as server_settings_schema


def _settings_row(**overrides):
    """Build a settings row with every column the read schema requires."""
    values = dict(
        id=1,
        units="metric",
        public_shareable_links=False,
        public_shareable_links_user_info=False,
        login_photo_set=False,
        version=1,
        currency="euro",
        num_records_per_page=25,
        signup_enabled=False,
        signup_require_admin_approval=True,
        signup_require_email_verification=True,
        sso_enabled=False,
        local_login_enabled=True,
        sso_auto_redirect=False,
        tileserver_url="https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        tileserver_attribution="Test",
        map_background_color="#dddddd",
        tileserver_regenerate_thumbnails_on_change=False,
        password_type="strict",
        password_length_regular_users=8,
        password_length_admin_users=12,
        geocoding_service="nominatim",
        geocoding_host=None,
        geocoding_use_https=True,
        geocoding_rate_limit=1.0,
        session_idle_timeout_enabled=False,
        session_idle_timeout_hours=1,
        session_absolute_timeout_hours=24,
        access_token_expire_minutes=15,
        refresh_token_expire_days=7,
        read_notification_retention_days=90,
        tileserver_api_key=None,
        geocoding_api_key=None,
    )
    values.update(overrides)
    row = MagicMock(spec=server_settings_models.ServerSettings)
    for key, value in values.items():
        setattr(row, key, value)
    return row


def _mock_row(mock_db, row):
    """Make the session's select return ``row``."""
    mock_execute = MagicMock()
    mock_execute.scalar_one_or_none.return_value = row
    mock_db.execute.return_value = mock_execute


def _edit(**overrides):
    """Build a complete edit payload."""
    values = dict(
        units=server_settings_schema.Units.IMPERIAL,
        public_shareable_links=True,
        public_shareable_links_user_info=True,
        currency=server_settings_schema.Currency.DOLLAR,
        num_records_per_page=50,
        signup_enabled=True,
        signup_require_admin_approval=False,
        signup_require_email_verification=True,
        sso_enabled=False,
        local_login_enabled=True,
        sso_auto_redirect=False,
        tileserver_url="https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        tileserver_attribution="Test",
        map_background_color="#dddddd",
        password_type="strict",
        tileserver_regenerate_thumbnails_on_change=False,
        password_length_regular_users=8,
        password_length_admin_users=12,
        geocoding_service="nominatim",
        geocoding_host=None,
        geocoding_use_https=True,
        geocoding_rate_limit=1.0,
        session_idle_timeout_enabled=False,
        session_idle_timeout_hours=1,
        session_absolute_timeout_hours=24,
        access_token_expire_minutes=15,
        refresh_token_expire_days=7,
        read_notification_retention_days=90,
    )
    values.update(overrides)
    return server_settings_schema.ServerSettingsEdit(**values)


class TestGetServerSettings:
    """Test suite for get_server_settings function."""

    def test_get_server_settings_success(self, mock_db):
        """Test the stored row is returned as the read schema."""
        _mock_row(mock_db, _settings_row())

        result = server_settings_crud.get_server_settings(mock_db)

        assert isinstance(result, server_settings_schema.ServerSettingsRead)
        assert result.id == 1
        mock_db.execute.assert_called_once()

    def test_get_server_settings_not_found(self, mock_db):
        """Test retrieval when settings don't exist."""
        _mock_row(mock_db, None)

        assert server_settings_crud.get_server_settings(mock_db) is None


class TestEditServerSettings:
    """Test suite for edit_server_settings function."""

    def test_edit_server_settings_stages_without_committing(self, mock_db):
        """Test the update is flushed, never committed, and the row refreshed."""
        row = _settings_row()
        _mock_row(mock_db, row)

        result = server_settings_crud.edit_server_settings(_edit(), mock_db)

        assert row.num_records_per_page == 50
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_not_called()
        mock_db.refresh.assert_called_once_with(row)
        assert isinstance(result, server_settings_schema.ServerSettingsRead)

    def test_edit_server_settings_writes_only_the_fields_that_were_set(self, mock_db):
        """Test a field the caller did not set is left alone."""
        row = _settings_row(tileserver_api_key="existing")
        _mock_row(mock_db, row)
        payload = server_settings_schema.ServerSettingsEdit.model_construct(
            _fields_set={"num_records_per_page"}, num_records_per_page=50
        )

        server_settings_crud.edit_server_settings(payload, mock_db)

        assert row.num_records_per_page == 50
        assert row.tileserver_api_key == "existing"

    def test_edit_server_settings_not_found(self, mock_db):
        """Test update when settings don't exist."""
        _mock_row(mock_db, None)

        with pytest.raises(core_exceptions.ServiceUnavailableError):
            server_settings_crud.edit_server_settings(_edit(), mock_db)


class TestSetLoginPhoto:
    """Test suite for set_login_photo function."""

    def test_set_login_photo_stages_the_flag(self, mock_db):
        """Test the flag is flushed, not committed, and marked modified so the version moves."""
        row = _settings_row()
        _mock_row(mock_db, row)

        with patch.object(server_settings_crud, "flag_modified") as flag_modified:
            version = server_settings_crud.set_login_photo(True, mock_db)

        assert version == row.version
        assert row.login_photo_set is True
        flag_modified.assert_called_once_with(row, "login_photo_set")
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_not_called()

    def test_set_login_photo_not_found(self, mock_db):
        """Test the flag cannot be set when settings don't exist."""
        _mock_row(mock_db, None)

        with pytest.raises(core_exceptions.ServiceUnavailableError):
            server_settings_crud.set_login_photo(True, mock_db)


def _mail_row(**overrides):
    values = dict(
        id=1,
        version=1,
        host="mail.example.com",
        port=587,
        security="starttls",
        username=None,
        password=None,
        from_address=None,
    )
    values.update(overrides)
    row = MagicMock(spec=server_settings_models.MailSettings)
    for key, value in values.items():
        setattr(row, key, value)
    return row


def _mail_edit(**overrides):
    values = dict(host="smtp.example.org", port=465, security="ssl", username=None, from_address=None)
    values.update(overrides)
    return server_settings_schema.MailSettingsEdit(**values)


class TestGetMailSettings:
    def test_returns_the_stored_row_as_the_read_schema(self, mock_db):
        _mock_row(mock_db, _mail_row())

        result = server_settings_crud.get_mail_settings(mock_db)

        assert isinstance(result, server_settings_schema.MailSettingsRead)
        assert result.host == "mail.example.com"

    def test_returns_none_when_missing(self, mock_db):
        _mock_row(mock_db, None)

        assert server_settings_crud.get_mail_settings(mock_db) is None

    def test_for_update_locks_the_row(self, mock_db):
        _mock_row(mock_db, _mail_row())

        server_settings_crud.get_mail_settings(mock_db, for_update=True)

        assert mock_db.execute.call_args.args[0]._for_update_arg is not None

    def test_a_plain_read_does_not_lock(self, mock_db):
        _mock_row(mock_db, _mail_row())

        server_settings_crud.get_mail_settings(mock_db)

        assert mock_db.execute.call_args.args[0]._for_update_arg is None


class TestEditMailSettings:
    def test_stages_without_committing_and_locks(self, mock_db):
        row = _mail_row()
        _mock_row(mock_db, row)

        result = server_settings_crud.edit_mail_settings(_mail_edit(), mock_db)

        assert row.host == "smtp.example.org"
        assert row.port == 465
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_not_called()
        mock_db.refresh.assert_called_once_with(row)
        assert mock_db.execute.call_args.args[0]._for_update_arg is not None
        assert isinstance(result, server_settings_schema.MailSettingsRead)

    def test_writes_only_the_fields_that_were_set(self, mock_db):
        row = _mail_row(password="enc")
        _mock_row(mock_db, row)
        payload = server_settings_schema.MailSettingsEdit.model_construct(_fields_set={"port"}, port=25)

        server_settings_crud.edit_mail_settings(payload, mock_db)

        assert row.port == 25
        assert row.password == "enc"
        assert row.host == "mail.example.com"

    def test_missing_row_raises_service_unavailable(self, mock_db):
        _mock_row(mock_db, None)

        with pytest.raises(core_exceptions.ServiceUnavailableError):
            server_settings_crud.edit_mail_settings(_mail_edit(), mock_db)
