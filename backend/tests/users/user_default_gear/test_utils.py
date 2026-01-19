"""
Tests for users.users_default_gear.utils module.

This module tests utility functions for user default gear management.
"""

import pytest
from unittest.mock import MagicMock, patch

import users.users_default_gear.utils as user_default_gear_utils
import users.users_default_gear.models as user_default_gear_models


class TestGetUserDefaultGearByActivityType:
    """Test suite for get_user_default_gear_by_activity_type function."""

    @patch("users.users_default_gear.utils.user_default_gear_crud")
    def test_run_activity_type(self, mock_crud):
        """Test retrieval for run activity type."""
        # Arrange
        mock_db = MagicMock()
        mock_user_gear = MagicMock(spec=user_default_gear_models.UsersDefaultGear)
        mock_user_gear.run_gear_id = 5

        mock_crud.get_user_default_gear_by_user_id.return_value = mock_user_gear

        # Act
        result = user_default_gear_utils.get_user_default_gear_by_activity_type(
            user_id=1, activity_type=1, db=mock_db
        )

        # Assert
        assert result == 5

    @patch("users.users_default_gear.utils.user_default_gear_crud")
    def test_ride_activity_type(self, mock_crud):
        """Test retrieval for ride activity type."""
        # Arrange
        mock_db = MagicMock()
        mock_user_gear = MagicMock(spec=user_default_gear_models.UsersDefaultGear)
        mock_user_gear.ride_gear_id = 6

        mock_crud.get_user_default_gear_by_user_id.return_value = mock_user_gear

        # Act
        result = user_default_gear_utils.get_user_default_gear_by_activity_type(
            user_id=1, activity_type=4, db=mock_db
        )

        # Assert
        assert result == 6

    @patch("users.users_default_gear.utils.user_default_gear_crud")
    def test_unknown_activity_type(self, mock_crud):
        """Test retrieval for unknown activity type."""
        # Arrange
        mock_db = MagicMock()
        mock_user_gear = MagicMock(spec=user_default_gear_models.UsersDefaultGear)

        mock_crud.get_user_default_gear_by_user_id.return_value = mock_user_gear

        # Act
        result = user_default_gear_utils.get_user_default_gear_by_activity_type(
            user_id=1, activity_type=999, db=mock_db
        )

        # Assert
        assert result is None

    @patch("users.users_default_gear.utils.user_default_gear_crud")
    def test_user_gear_not_found(self, mock_crud):
        """Test retrieval when user gear is not found."""
        # Arrange
        mock_db = MagicMock()

        mock_crud.get_user_default_gear_by_user_id.return_value = None

        # Act
        result = user_default_gear_utils.get_user_default_gear_by_activity_type(
            user_id=1, activity_type=1, db=mock_db
        )

        # Assert
        assert result is None

    @patch("users.users_default_gear.utils.user_default_gear_crud")
    def test_gear_id_none_for_activity_type(self, mock_crud):
        """Test retrieval when gear ID is None for activity type."""
        # Arrange
        mock_db = MagicMock()
        mock_user_gear = MagicMock(spec=user_default_gear_models.UsersDefaultGear)
        mock_user_gear.run_gear_id = None

        mock_crud.get_user_default_gear_by_user_id.return_value = mock_user_gear

        # Act
        result = user_default_gear_utils.get_user_default_gear_by_activity_type(
            user_id=1, activity_type=1, db=mock_db
        )

        # Assert
        assert result is None
