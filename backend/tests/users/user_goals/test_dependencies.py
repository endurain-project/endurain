"""Tests for user goals dependencies."""

import pytest
from unittest.mock import patch
from fastapi import HTTPException, status

import users.user_goals.dependencies as user_goals_dependencies


class TestValidateGoalId:
    """
    Test suite for validate_goal_id function.
    """

    @patch("users.user_goals.dependencies.core_dependencies.validate_id")
    def test_validate_goal_id_valid(self, mock_validate_id):
        """Test validation passes for valid goal ID."""
        # Arrange
        goal_id = 1
        mock_validate_id.return_value = None

        # Act
        result = user_goals_dependencies.validate_goal_id(goal_id)

        # Assert
        assert result is None
        mock_validate_id.assert_called_once_with(
            id=goal_id, min=1, message="Invalid goal ID"
        )

    @patch("users.user_goals.dependencies.core_dependencies.validate_id")
    def test_validate_goal_id_zero(self, mock_validate_id):
        """Test validation fails for zero goal ID."""
        # Arrange
        goal_id = 0
        mock_validate_id.side_effect = HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid goal ID",
        )

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            user_goals_dependencies.validate_goal_id(goal_id)

        assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert exc_info.value.detail == "Invalid goal ID"

    @patch("users.user_goals.dependencies.core_dependencies.validate_id")
    def test_validate_goal_id_negative(self, mock_validate_id):
        """Test validation fails for negative goal ID."""
        # Arrange
        goal_id = -1
        mock_validate_id.side_effect = HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid goal ID",
        )

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            user_goals_dependencies.validate_goal_id(goal_id)

        assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
