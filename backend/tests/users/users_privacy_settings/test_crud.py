from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

import core.exceptions as core_exceptions
import modules.users.users_privacy_settings.crud as users_privacy_settings_crud
import modules.users.users_privacy_settings.models as users_privacy_settings_models
import modules.users.users_privacy_settings.schema as users_privacy_settings_schema


@pytest.fixture(autouse=True)
def _patch_serializer():
    """Patch the serializer to a passthrough for MagicMock compatibility."""
    with patch(
        "modules.users.users_privacy_settings.crud.users_privacy_settings_serializers.to_read_schema",
        side_effect=lambda x: x,
    ):
        yield


def _found(mock_db, row):
    """Make the session's SELECT return ``row`` (or None)."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = row
    mock_db.execute.return_value = mock_result


class TestGetUserPrivacySettingsByUserId:
    def test_returns_the_settings(self, mock_db):
        row = MagicMock(spec=users_privacy_settings_models.UsersPrivacySettings)
        _found(mock_db, row)

        assert users_privacy_settings_crud.get_user_privacy_settings_by_user_id(1, mock_db) == row
        mock_db.execute.assert_called_once()

    def test_returns_none_when_missing(self, mock_db):
        _found(mock_db, None)

        assert users_privacy_settings_crud.get_user_privacy_settings_by_user_id(1, mock_db) is None


class TestCreateUserPrivacySettings:
    def test_stages_without_committing(self, mock_db):
        row = MagicMock(spec=users_privacy_settings_models.UsersPrivacySettings)

        with patch.object(users_privacy_settings_models, "UsersPrivacySettings", return_value=row):
            result = users_privacy_settings_crud.create_user_privacy_settings(1, mock_db)

        assert result == row
        mock_db.add.assert_called_once_with(row)
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_not_called()

    def test_duplicate_is_a_conflict(self, mock_db):
        mock_db.flush.side_effect = IntegrityError("Duplicate entry", None, None)

        with pytest.raises(core_exceptions.ConflictError):
            users_privacy_settings_crud.create_user_privacy_settings(1, mock_db)


class TestEditUserPrivacySettings:
    def test_applies_only_the_set_fields_and_stages(self, mock_db):
        row = MagicMock(spec=users_privacy_settings_models.UsersPrivacySettings)
        _found(mock_db, row)
        update = users_privacy_settings_schema.UsersPrivacySettingsUpdate(
            default_activity_visibility=users_privacy_settings_schema.ActivityVisibility.PRIVATE,
            hide_activity_map=True,
        )

        result = users_privacy_settings_crud.edit_user_privacy_settings(1, update, mock_db, if_match="*")

        assert result == row
        assert row.hide_activity_map is True
        assert row.default_activity_visibility == update.default_activity_visibility
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_not_called()

    def test_missing_settings_are_not_found(self, mock_db):
        _found(mock_db, None)
        update = users_privacy_settings_schema.UsersPrivacySettingsUpdate(hide_activity_map=True)

        with pytest.raises(core_exceptions.NotFoundError):
            users_privacy_settings_crud.edit_user_privacy_settings(1, update, mock_db, if_match="*")
