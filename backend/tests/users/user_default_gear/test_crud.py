"""
Tests for users.user_default_gear.crud module.

This module tests CRUD operations for user default gear.
"""

import pytest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

import users.user_default_gear.crud as user_default_gear_crud
import users.user_default_gear.schema as user_default_gear_schema
import users.user_default_gear.models as user_default_gear_models


@pytest.fixture
def mock_db():
    """Create a mock database session."""
    return MagicMock(spec=Session)


class TestGetUserDefaultGearByUserId:
    """Test suite for get_user_default_gear_by_user_id function."""

    def test_get_user_default_gear_by_user_id_success(self, mock_db):
        """Test successful retrieval of user default gear."""
        # Arrange
        user_id = 1
        mock_gear = MagicMock(spec=user_default_gear_models.UsersDefaultGear)
        mock_gear.id = 1
        mock_gear.user_id = user_id

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_gear
        mock_db.execute.return_value = mock_result

        # Act
        result = user_default_gear_crud.get_user_default_gear_by_user_id(
            user_id, mock_db
        )

        # Assert
        assert result == mock_gear
        assert result.user_id == user_id

    def test_get_user_default_gear_by_user_id_not_found(self, mock_db):
        """Test retrieval when gear settings not found."""
        # Arrange
        user_id = 999
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        # Act
        result = user_default_gear_crud.get_user_default_gear_by_user_id(
            user_id, mock_db
        )

        # Assert
        assert result is None

    def test_get_user_default_gear_by_user_id_db_error(self, mock_db):
        """Test database error handling."""
        # Arrange
        user_id = 1
        mock_db.execute.side_effect = SQLAlchemyError("DB error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            user_default_gear_crud.get_user_default_gear_by_user_id(user_id, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestCreateUserDefaultGear:
    """Test suite for create_user_default_gear function."""

    def test_create_user_default_gear_success(self, mock_db):
        """Test successful creation of user default gear."""
        # Arrange
        user_id = 1
        mock_created_gear = MagicMock(spec=user_default_gear_models.UsersDefaultGear)
        mock_created_gear.id = 1
        mock_created_gear.user_id = user_id

        def mock_refresh(obj):
            obj.id = 1
            obj.user_id = user_id

        mock_db.refresh.side_effect = mock_refresh

        # Act
        with patch.object(
            user_default_gear_models,
            "UsersDefaultGear",
            return_value=mock_created_gear,
        ):
            result = user_default_gear_crud.create_user_default_gear(user_id, mock_db)

        # Assert
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    def test_create_user_default_gear_db_error(self, mock_db):
        """Test database error handling during creation."""
        # Arrange
        user_id = 1
        mock_db_gear = MagicMock(spec=user_default_gear_models.UsersDefaultGear)
        mock_db_gear.user_id = user_id
        mock_db.commit.side_effect = SQLAlchemyError("DB error")

        # Act & Assert
        with patch.object(
            user_default_gear_models,
            "UsersDefaultGear",
            return_value=mock_db_gear,
        ):
            with pytest.raises(HTTPException) as exc_info:
                user_default_gear_crud.create_user_default_gear(user_id, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        # Decorator should call rollback when catching SQLAlchemyError
        mock_db.rollback.assert_called_once()


class TestEditUserDefaultGear:
    """Test suite for edit_user_default_gear function."""

    @patch("users.user_default_gear.crud.get_user_default_gear_by_user_id")
    def test_edit_user_default_gear_success(self, mock_get_gear, mock_db):
        """Test successful update of user default gear."""
        # Arrange
        user_id = 1
        gear_update = user_default_gear_schema.UserDefaultGearUpdate(
            id=1,
            user_id=user_id,
            run_gear_id=10,
        )

        mock_db_gear = MagicMock(spec=user_default_gear_models.UsersDefaultGear)
        mock_db_gear.id = 1
        mock_db_gear.user_id = user_id
        mock_get_gear.return_value = mock_db_gear

        # Act
        result = user_default_gear_crud.edit_user_default_gear(
            gear_update, user_id, mock_db
        )

        # Assert
        assert result == mock_db_gear
        mock_db.commit.assert_called_once()

    @patch("users.user_default_gear.crud.get_user_default_gear_by_user_id")
    def test_edit_user_default_gear_not_found(self, mock_get_gear, mock_db):
        """Test update fails when gear settings not found."""
        # Arrange
        user_id = 1
        gear_update = user_default_gear_schema.UserDefaultGearUpdate(
            id=1,
            user_id=user_id,
            run_gear_id=10,
        )
        mock_get_gear.return_value = None

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            user_default_gear_crud.edit_user_default_gear(gear_update, user_id, mock_db)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    @patch("users.user_default_gear.crud.get_user_default_gear_by_user_id")
    def test_edit_user_default_gear_wrong_user(self, mock_get_gear, mock_db):
        """Test update fails when user IDs don't match."""
        # Arrange
        user_id = 1
        gear_update = user_default_gear_schema.UserDefaultGearUpdate(
            id=1,
            user_id=2,  # Different user
            run_gear_id=10,
        )

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            user_default_gear_crud.edit_user_default_gear(gear_update, user_id, mock_db)

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
