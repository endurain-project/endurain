import pytest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

import users.users_privacy_settings.crud as users_privacy_settings_crud
import users.users_privacy_settings.schema as users_privacy_settings_schema
import users.users_privacy_settings.models as users_privacy_settings_models


class TestGetUserPrivacySettingsByUserId:
    """
    Test suite for get_user_privacy_settings_by_user_id function.
    """

    def test_get_user_privacy_settings_by_user_id_success(self, mock_db):
        """
        Test successful retrieval of privacy settings for a user.
        """
        # Arrange
        user_id = 1
        mock_settings = MagicMock(
            spec=users_privacy_settings_models.UsersPrivacySettings
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_settings
        mock_db.execute.return_value = mock_result

        # Act
        result = users_privacy_settings_crud.get_user_privacy_settings_by_user_id(
            user_id, mock_db
        )

        # Assert
        assert result == mock_settings
        mock_db.execute.assert_called_once()

    def test_get_user_privacy_settings_by_user_id_not_found(self, mock_db):
        """
        Test retrieval when no privacy settings exist for user.
        """
        # Arrange
        user_id = 1
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        # Act
        result = users_privacy_settings_crud.get_user_privacy_settings_by_user_id(
            user_id, mock_db
        )

        # Assert
        assert result is None

    def test_get_user_privacy_settings_by_user_id_db_error(self, mock_db):
        """
        Test exception handling when database error occurs.
        """
        # Arrange
        user_id = 1
        mock_db.execute.side_effect = SQLAlchemyError("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            users_privacy_settings_crud.get_user_privacy_settings_by_user_id(
                user_id, mock_db
            )

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert exc_info.value.detail == "Database error occurred"


class TestCreateUserPrivacySettings:
    """
    Test suite for create_user_privacy_settings function.
    """

    def test_create_user_privacy_settings_success(self, mock_db):
        """
        Test successful creation of privacy settings.
        """
        # Arrange
        user_id = 1

        mock_db_settings = MagicMock(
            spec=users_privacy_settings_models.UsersPrivacySettings
        )
        mock_db_settings.id = 1
        mock_db_settings.user_id = user_id
        mock_db.add.return_value = None
        mock_db.commit.return_value = None
        mock_db.refresh.return_value = None

        with patch.object(
            users_privacy_settings_models,
            "UsersPrivacySettings",
            return_value=mock_db_settings,
        ):
            # Act
            result = users_privacy_settings_crud.create_user_privacy_settings(
                user_id, mock_db
            )

            # Assert
            assert result == mock_db_settings
            mock_db.add.assert_called_once()
            mock_db.commit.assert_called_once()
            mock_db.refresh.assert_called_once()

    def test_create_user_privacy_settings_duplicate_entry(self, mock_db):
        """
        Test creation with duplicate entry raises conflict error.
        """
        # Arrange
        user_id = 1

        mock_db_settings = MagicMock()
        mock_db.add.return_value = None
        mock_db.commit.side_effect = IntegrityError("Duplicate entry", None, None)

        with patch.object(
            users_privacy_settings_models,
            "UsersPrivacySettings",
            return_value=mock_db_settings,
        ):
            # Act & Assert
            with pytest.raises(HTTPException) as exc_info:
                users_privacy_settings_crud.create_user_privacy_settings(
                    user_id, mock_db
                )

            assert exc_info.value.status_code == status.HTTP_409_CONFLICT
            assert "Privacy settings already exist" in exc_info.value.detail
            mock_db.rollback.assert_called_once()

    def test_create_user_privacy_settings_db_error(self, mock_db):
        """
        Test exception handling in create_user_privacy_settings.
        """
        # Arrange
        user_id = 1
        mock_db.add.side_effect = SQLAlchemyError("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            users_privacy_settings_crud.create_user_privacy_settings(user_id, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert exc_info.value.detail == "Database error occurred"
        mock_db.rollback.assert_called_once()


class TestEditUserPrivacySettings:
    """
    Test suite for edit_user_privacy_settings function.
    """

    def test_edit_user_privacy_settings_success(self, mock_db):
        """
        Test successful edit of privacy settings.
        """
        # Arrange
        user_id = 1
        update_data = users_privacy_settings_schema.UsersPrivacySettingsUpdate(
            default_activity_visibility=2,
            hide_activity_map=True,
        )

        mock_db_settings = MagicMock(
            spec=users_privacy_settings_models.UsersPrivacySettings
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_db_settings
        mock_db.execute.return_value = mock_result

        # Act
        result = users_privacy_settings_crud.edit_user_privacy_settings(
            user_id, update_data, mock_db
        )

        # Assert
        assert result == mock_db_settings
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()

    def test_edit_user_privacy_settings_not_found(self, mock_db):
        """
        Test edit when privacy settings not found.
        """
        # Arrange
        user_id = 1
        update_data = users_privacy_settings_schema.UsersPrivacySettingsUpdate(
            hide_activity_map=True
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            users_privacy_settings_crud.edit_user_privacy_settings(
                user_id, update_data, mock_db
            )

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert exc_info.value.detail == "User privacy settings not found"

    def test_edit_user_privacy_settings_partial_update(self, mock_db):
        """
        Test edit with partial field updates.
        """
        # Arrange
        user_id = 1
        update_data = users_privacy_settings_schema.UsersPrivacySettingsUpdate(
            hide_activity_hr=True
        )

        mock_db_settings = MagicMock(
            spec=users_privacy_settings_models.UsersPrivacySettings
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_db_settings
        mock_db.execute.return_value = mock_result

        # Act
        result = users_privacy_settings_crud.edit_user_privacy_settings(
            user_id, update_data, mock_db
        )

        # Assert
        mock_db.commit.assert_called_once()

    def test_edit_user_privacy_settings_all_fields(self, mock_db):
        """
        Test edit updates all fields correctly.
        """
        # Arrange
        user_id = 1
        update_data = users_privacy_settings_schema.UsersPrivacySettingsUpdate(
            default_activity_visibility=1,
            hide_activity_start_time=True,
            hide_activity_location=True,
            hide_activity_map=True,
            hide_activity_hr=True,
            hide_activity_power=True,
            hide_activity_cadence=True,
            hide_activity_elevation=True,
            hide_activity_speed=True,
            hide_activity_pace=True,
            hide_activity_laps=True,
            hide_activity_workout_sets_steps=True,
            hide_activity_gear=True,
        )

        mock_db_settings = MagicMock(
            spec=users_privacy_settings_models.UsersPrivacySettings
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_db_settings
        mock_db.execute.return_value = mock_result

        # Act
        result = users_privacy_settings_crud.edit_user_privacy_settings(
            user_id, update_data, mock_db
        )

        # Assert
        mock_db.commit.assert_called_once()

    def test_edit_user_privacy_settings_db_error(self, mock_db):
        """
        Test exception handling in edit_user_privacy_settings.
        """
        # Arrange
        user_id = 1
        update_data = users_privacy_settings_schema.UsersPrivacySettingsUpdate(
            hide_activity_map=True
        )

        # Mock successful get but fail on commit
        mock_db_settings = MagicMock(
            spec=users_privacy_settings_models.UsersPrivacySettings
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_db_settings
        mock_db.execute.return_value = mock_result
        mock_db.commit.side_effect = SQLAlchemyError("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            users_privacy_settings_crud.edit_user_privacy_settings(
                user_id, update_data, mock_db
            )

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert exc_info.value.detail == "Database error occurred"
        mock_db.rollback.assert_called_once()

    def test_edit_user_privacy_settings_visibility_change(self, mock_db):
        """
        Test changing only visibility setting.
        """
        # Arrange
        user_id = 1
        update_data = users_privacy_settings_schema.UsersPrivacySettingsUpdate(
            default_activity_visibility=2
        )

        mock_db_settings = MagicMock(
            spec=users_privacy_settings_models.UsersPrivacySettings
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_db_settings
        mock_db.execute.return_value = mock_result

        # Act
        result = users_privacy_settings_crud.edit_user_privacy_settings(
            user_id, update_data, mock_db
        )

        # Assert
        assert result == mock_db_settings
        mock_db.commit.assert_called_once()
