"""Tests for user goals API endpoints."""

import pytest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException, status

import users.user_goals.schema as user_goals_schema
import users.user_goals.models as user_goals_models
import users.user_goals.dependencies as user_goals_dependencies


class TestGetUserGoals:
    """
    Test suite for get_user_goals endpoint.
    """

    @patch("users.user_goals.router.user_goals_crud.get_user_goals_by_user_id")
    def test_get_user_goals_success(
        self, mock_get_goals, fast_api_client, fast_api_app
    ):
        """Test successful retrieval of all user goals."""
        # Arrange
        mock_goal1 = MagicMock(spec=user_goals_models.UserGoal)
        mock_goal1.id = 1
        mock_goal1.user_id = 1
        mock_goal1.interval = "weekly"
        mock_goal1.activity_type = 1
        mock_goal1.goal_type = 1
        mock_goal1.goal_calories = 5000
        mock_goal1.goal_activities_number = None
        mock_goal1.goal_distance = None
        mock_goal1.goal_elevation = None
        mock_goal1.goal_duration = None

        mock_get_goals.return_value = [mock_goal1]

        # Act
        response = fast_api_client.get(
            "/user_goals",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1

    @patch("users.user_goals.router.user_goals_crud.get_user_goals_by_user_id")
    def test_get_user_goals_empty(
        self, mock_get_goals, fast_api_client, fast_api_app
    ):
        """Test retrieval when user has no goals."""
        # Arrange
        mock_get_goals.return_value = []

        # Act
        response = fast_api_client.get(
            "/user_goals",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 200
        assert response.json() == []


class TestGetUserGoalsResults:
    """
    Test suite for get_user_goals_results endpoint.
    """

    @patch("users.user_goals.router.user_goals_utils.calculate_user_goals")
    def test_get_user_goals_results_success(
        self, mock_calculate, fast_api_client, fast_api_app
    ):
        """Test successful calculation of goal progress."""
        # Arrange
        mock_progress = MagicMock(
            spec=user_goals_schema.UserGoalProgress
        )
        mock_progress.goal_id = 1
        mock_progress.interval = "weekly"
        mock_progress.activity_type = 1
        mock_progress.goal_type = 1
        mock_progress.start_date = "2024-01-15"
        mock_progress.end_date = "2024-01-21"
        mock_progress.percentage_completed = 75
        mock_progress.total_calories = 3750
        mock_progress.total_activities_number = None
        mock_progress.total_distance = None
        mock_progress.total_elevation = None
        mock_progress.total_duration = None
        mock_progress.goal_calories = 5000
        mock_progress.goal_activities_number = None
        mock_progress.goal_distance = None
        mock_progress.goal_elevation = None
        mock_progress.goal_duration = None

        mock_calculate.return_value = [mock_progress]

        # Act
        response = fast_api_client.get(
            "/user_goals/results",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1

    @patch("users.user_goals.router.user_goals_utils.calculate_user_goals")
    def test_get_user_goals_results_none(
        self, mock_calculate, fast_api_client, fast_api_app
    ):
        """Test calculation returns null when no goals."""
        # Arrange
        mock_calculate.return_value = None

        # Act
        response = fast_api_client.get(
            "/user_goals/results",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 200
        assert response.json() is None


class TestCreateUserGoal:
    """
    Test suite for create_user_goal endpoint.
    """

    @patch("users.user_goals.router.user_goals_crud.create_user_goal")
    def test_create_user_goal_success(
        self, mock_create, fast_api_client, fast_api_app
    ):
        """Test successful goal creation."""
        # Arrange
        mock_created_goal = MagicMock(spec=user_goals_models.UserGoal)
        mock_created_goal.id = 1
        mock_created_goal.user_id = 1
        mock_created_goal.interval = "weekly"
        mock_created_goal.activity_type = 1
        mock_created_goal.goal_type = 1
        mock_created_goal.goal_calories = 5000
        mock_created_goal.goal_activities_number = None
        mock_created_goal.goal_distance = None
        mock_created_goal.goal_elevation = None
        mock_created_goal.goal_duration = None

        mock_create.return_value = mock_created_goal

        # Act
        response = fast_api_client.post(
            "/user_goals",
            headers={"Authorization": "Bearer mock_token"},
            json={
                "interval": "weekly",
                "activity_type": 1,
                "goal_type": 1,
                "goal_calories": 5000,
                "goal_activities_number": None,
                "goal_distance": None,
                "goal_elevation": None,
                "goal_duration": None,
            },
        )

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["id"] == 1
        assert data["goal_calories"] == 5000

    def test_create_user_goal_invalid_data(
        self, fast_api_client, fast_api_app
    ):
        """Test creation fails with invalid data."""
        # Act
        response = fast_api_client.post(
            "/user_goals",
            headers={"Authorization": "Bearer mock_token"},
            json={
                "interval": "invalid",  # Invalid interval
                "activity_type": 1,
                "goal_type": 1,
                "goal_calories": 5000,
            },
        )

        # Assert
        assert response.status_code == 422


class TestUpdateUserGoal:
    """
    Test suite for update_user_goal endpoint.
    """

    @patch("core.dependencies.validate_id")
    @patch("users.user_goals.router.user_goals_crud.update_user_goal")
    def test_update_user_goal_success(
        self,
        mock_update,
        mock_validate_id,
        fast_api_client,
        fast_api_app,
    ):
        """Test successful goal update."""
        # Arrange
        mock_validate_id.return_value = None
        mock_update.return_value = user_goals_schema.UserGoalRead(
            id=1,
            user_id=1,
            interval=user_goals_schema.Interval.MONTHLY,
            activity_type=user_goals_schema.ActivityType.RUN,
            goal_type=user_goals_schema.GoalType.CALORIES,
            goal_calories=10000,
            goal_activities_number=None,
            goal_distance=None,
            goal_elevation=None,
            goal_duration=None,
        )

        # Act
        response = fast_api_client.put(
            "/user_goals/1",
            headers={"Authorization": "Bearer mock_token"},
            json={
                "interval": "monthly",
                "activity_type": 1,  # RUN
                "goal_type": 1,  # CALORIES
                "goal_calories": 10000,
            },
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert data["goal_calories"] == 10000

    @patch("users.user_goals.router.user_goals_crud.update_user_goal")
    @patch(
        "users.user_goals.router.user_goals_dependencies.validate_goal_id"
    )
    def test_update_user_goal_not_found(
        self,
        mock_validate,
        mock_update,
        fast_api_client,
        fast_api_app,
    ):
        """Test update fails when goal not found."""
        # Arrange
        mock_validate.return_value = None
        mock_update.side_effect = HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User goal not found",
        )

        # Act
        response = fast_api_client.put(
            "/user_goals/999",
            headers={"Authorization": "Bearer mock_token"},
            json={
                "interval": "weekly",
                "activity_type": 1,
                "goal_type": 1,
                "goal_calories": 5000,
                "goal_activities_number": None,
                "goal_distance": None,
                "goal_elevation": None,
                "goal_duration": None,
            },
        )

        # Assert
        assert response.status_code == 404


class TestDeleteUserGoal:
    """
    Test suite for delete_user_goal endpoint.
    """

    @patch("core.dependencies.validate_id")
    @patch("users.user_goals.router.user_goals_crud.delete_user_goal")
    def test_delete_user_goal_success(
        self,
        mock_delete,
        mock_validate_id,
        fast_api_client,
        fast_api_app,
    ):
        """Test successful goal deletion."""
        # Arrange
        mock_validate_id.return_value = None
        mock_delete.return_value = None

        # Act
        response = fast_api_client.delete(
            "/user_goals/1",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 204
        assert response.content == b""

    @patch("users.user_goals.router.user_goals_crud.delete_user_goal")
    @patch(
        "users.user_goals.router.user_goals_dependencies.validate_goal_id"
    )
    def test_delete_user_goal_not_found(
        self,
        mock_validate,
        mock_delete,
        fast_api_client,
        fast_api_app,
    ):
        """Test deletion fails when goal not found."""
        # Arrange
        mock_validate.return_value = None
        mock_delete.side_effect = HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User goal not found",
        )

        # Act
        response = fast_api_client.delete(
            "/user_goals/999",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 404
