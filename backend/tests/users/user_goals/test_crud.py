"""Tests for user goals CRUD operations."""

import pytest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException, status
from sqlalchemy.exc import SQLAlchemyError

import users.user_goals.crud as user_goals_crud
import users.user_goals.schema as user_goals_schema
import users.user_goals.models as user_goals_models


class TestGetUserGoalsByUserId:
    """
    Test suite for get_user_goals_by_user_id function.
    """

    def test_get_user_goals_by_user_id_success(self, mock_db):
        """Test successful retrieval of user goals."""
        # Arrange
        user_id = 1
        mock_goal1 = MagicMock(spec=user_goals_models.UserGoal)
        mock_goal2 = MagicMock(spec=user_goals_models.UserGoal)

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_goal1, mock_goal2]
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_result

        # Act
        result = user_goals_crud.get_user_goals_by_user_id(user_id, mock_db)

        # Assert
        assert result == [mock_goal1, mock_goal2]
        mock_db.execute.assert_called_once()

    def test_get_user_goals_by_user_id_empty(self, mock_db):
        """Test retrieval when user has no goals."""
        # Arrange
        user_id = 1
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_result

        # Act
        result = user_goals_crud.get_user_goals_by_user_id(user_id, mock_db)

        # Assert
        assert result == []

    def test_get_user_goals_by_user_id_db_error(self, mock_db):
        """Test database error handling."""
        # Arrange
        user_id = 1
        mock_db.execute.side_effect = SQLAlchemyError("DB error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            user_goals_crud.get_user_goals_by_user_id(user_id, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert exc_info.value.detail == "Database error occurred"


class TestGetUserGoalByUserAndGoalId:
    """
    Test suite for get_user_goal_by_user_and_goal_id function.
    """

    def test_get_user_goal_by_user_and_goal_id_success(self, mock_db):
        """Test successful retrieval of specific goal."""
        # Arrange
        user_id = 1
        goal_id = 1
        mock_goal = MagicMock(spec=user_goals_models.UserGoal)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_goal
        mock_db.execute.return_value = mock_result

        # Act
        result = user_goals_crud.get_user_goal_by_user_and_goal_id(
            user_id, goal_id, mock_db
        )

        # Assert
        assert result == mock_goal

    def test_get_user_goal_by_user_and_goal_id_not_found(self, mock_db):
        """Test retrieval when goal not found."""
        # Arrange
        user_id = 1
        goal_id = 999
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        # Act
        result = user_goals_crud.get_user_goal_by_user_and_goal_id(
            user_id, goal_id, mock_db
        )

        # Assert
        assert result is None

    def test_get_user_goal_by_user_and_goal_id_db_error(self, mock_db):
        """Test database error handling."""
        # Arrange
        user_id = 1
        goal_id = 1
        mock_db.execute.side_effect = SQLAlchemyError("DB error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            user_goals_crud.get_user_goal_by_user_and_goal_id(user_id, goal_id, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestCreateUserGoal:
    """
    Test suite for create_user_goal function.
    """

    def test_create_user_goal_duplicate(self, mock_db):
        """Test creation fails when duplicate goal exists."""
        # Arrange
        user_id = 1
        user_goal = user_goals_schema.UserGoalCreate(
            interval=user_goals_schema.Interval.WEEKLY,
            activity_type=user_goals_schema.ActivityType.RUN,
            goal_type=user_goals_schema.GoalType.CALORIES,
            goal_calories=5000,
            goal_activities_number=None,
            goal_distance=None,
            goal_elevation=None,
            goal_duration=None,
        )

        # Mock existing goal
        mock_existing = MagicMock(spec=user_goals_models.UserGoal)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_existing
        mock_db.execute.return_value = mock_result

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            user_goals_crud.create_user_goal(user_id, user_goal, mock_db)

        assert exc_info.value.status_code == status.HTTP_409_CONFLICT
        assert "already has a goal" in exc_info.value.detail

    def test_create_user_goal_db_error(self, mock_db):
        """Test database error handling during creation."""
        # Arrange
        user_id = 1
        user_goal = user_goals_schema.UserGoalCreate(
            interval=user_goals_schema.Interval.WEEKLY,
            activity_type=user_goals_schema.ActivityType.RUN,
            goal_type=user_goals_schema.GoalType.CALORIES,
            goal_calories=5000,
            goal_activities_number=None,
            goal_distance=None,
            goal_elevation=None,
            goal_duration=None,
        )

        mock_db.execute.side_effect = SQLAlchemyError("DB error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            user_goals_crud.create_user_goal(user_id, user_goal, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        mock_db.rollback.assert_called_once()


class TestUpdateUserGoal:
    """
    Test suite for update_user_goal function.
    """

    @patch("users.user_goals.crud.get_user_goal_by_user_and_goal_id")
    def test_update_user_goal_success(self, mock_get_goal, mock_db):
        """Test successful goal update."""
        # Arrange
        user_id = 1
        goal_id = 1
        user_goal = user_goals_schema.UserGoalEdit(
            interval=user_goals_schema.Interval.MONTHLY,
            activity_type=user_goals_schema.ActivityType.RUN,
            goal_type=user_goals_schema.GoalType.CALORIES,
            goal_calories=10000,
            goal_activities_number=None,
            goal_distance=None,
            goal_elevation=None,
            goal_duration=None,
        )

        mock_db_goal = MagicMock(spec=user_goals_models.UserGoal)
        mock_db_goal.user_id = user_id
        mock_get_goal.return_value = mock_db_goal

        # Act
        result = user_goals_crud.update_user_goal(user_id, goal_id, user_goal, mock_db)

        # Assert
        assert result == mock_db_goal
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once_with(mock_db_goal)

    @patch("users.user_goals.crud.get_user_goal_by_user_and_goal_id")
    def test_update_user_goal_not_found(self, mock_get_goal, mock_db):
        """Test update fails when goal not found."""
        # Arrange
        user_id = 1
        goal_id = 999
        user_goal = user_goals_schema.UserGoalEdit(
            interval=user_goals_schema.Interval.WEEKLY,
            activity_type=user_goals_schema.ActivityType.RUN,
            goal_type=user_goals_schema.GoalType.CALORIES,
            goal_calories=5000,
            goal_activities_number=None,
            goal_distance=None,
            goal_elevation=None,
            goal_duration=None,
        )

        mock_get_goal.return_value = None

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            user_goals_crud.update_user_goal(user_id, goal_id, user_goal, mock_db)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    @patch("users.user_goals.crud.get_user_goal_by_user_and_goal_id")
    def test_update_user_goal_wrong_user(self, mock_get_goal, mock_db):
        """Test update fails when user doesn't own goal."""
        # Arrange
        user_id = 1
        goal_id = 1
        user_goal = user_goals_schema.UserGoalEdit(
            interval=user_goals_schema.Interval.WEEKLY,
            activity_type=user_goals_schema.ActivityType.RUN,
            goal_type=user_goals_schema.GoalType.CALORIES,
            goal_calories=5000,
            goal_activities_number=None,
            goal_distance=None,
            goal_elevation=None,
            goal_duration=None,
        )

        mock_db_goal = MagicMock(spec=user_goals_models.UserGoal)
        mock_db_goal.user_id = 2  # Different user
        mock_get_goal.return_value = mock_db_goal

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            user_goals_crud.update_user_goal(user_id, goal_id, user_goal, mock_db)

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


class TestDeleteUserGoal:
    """
    Test suite for delete_user_goal function.
    """

    @patch("users.user_goals.crud.get_user_goal_by_user_and_goal_id")
    def test_delete_user_goal_success(self, mock_get_goal, mock_db):
        """Test successful goal deletion."""
        # Arrange
        user_id = 1
        goal_id = 1
        mock_db_goal = MagicMock(spec=user_goals_models.UserGoal)
        mock_get_goal.return_value = mock_db_goal

        # Act
        user_goals_crud.delete_user_goal(user_id, goal_id, mock_db)

        # Assert
        mock_db.delete.assert_called_once_with(mock_db_goal)
        mock_db.commit.assert_called_once()

    @patch("users.user_goals.crud.get_user_goal_by_user_and_goal_id")
    def test_delete_user_goal_not_found(self, mock_get_goal, mock_db):
        """Test deletion fails when goal not found."""
        # Arrange
        user_id = 1
        goal_id = 999
        mock_get_goal.return_value = None

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            user_goals_crud.delete_user_goal(user_id, goal_id, mock_db)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    @patch("users.user_goals.crud.get_user_goal_by_user_and_goal_id")
    def test_delete_user_goal_db_error(self, mock_get_goal, mock_db):
        """Test database error handling during deletion."""
        # Arrange
        user_id = 1
        goal_id = 1
        mock_db_goal = MagicMock(spec=user_goals_models.UserGoal)
        mock_get_goal.return_value = mock_db_goal
        mock_db.delete.side_effect = SQLAlchemyError("DB error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            user_goals_crud.delete_user_goal(user_id, goal_id, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        mock_db.rollback.assert_called_once()
