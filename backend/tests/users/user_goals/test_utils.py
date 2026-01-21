"""Tests for user goals utility functions."""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

import users.users_goals.utils as user_goals_utils
import users.users_goals.schema as user_goals_schema
import users.users_goals.models as user_goals_models


class TestCalculateUserGoals:
    """
    Test suite for calculate_user_goals function.
    """

    @patch("users.users_goals.utils.user_goals_crud.get_user_goals_by_user_id")
    @patch("users.users_goals.utils.calculate_goal_progress_by_activity_type")
    def test_calculate_user_goals_success(self, mock_calc_progress, mock_get_goals):
        """Test successful calculation of user goals."""
        # Arrange
        user_id = 1
        date = "2024-01-15"
        mock_db = MagicMock(spec=Session)

        mock_goal1 = MagicMock(spec=user_goals_models.UsersGoal)
        mock_goal2 = MagicMock(spec=user_goals_models.UsersGoal)
        mock_get_goals.return_value = [mock_goal1, mock_goal2]

        mock_progress1 = MagicMock(spec=user_goals_schema.UsersGoalProgress)
        mock_progress2 = MagicMock(spec=user_goals_schema.UsersGoalProgress)
        mock_calc_progress.side_effect = [mock_progress1, mock_progress2]

        # Act
        result = user_goals_utils.calculate_user_goals(user_id, date, mock_db)

        # Assert
        assert result == [mock_progress1, mock_progress2]
        mock_get_goals.assert_called_once_with(user_id, mock_db)
        assert mock_calc_progress.call_count == 2

    @patch("users.users_goals.utils.user_goals_crud.get_user_goals_by_user_id")
    def test_calculate_user_goals_no_goals(self, mock_get_goals):
        """Test calculation returns None when no goals exist."""
        # Arrange
        user_id = 1
        date = "2024-01-15"
        mock_db = MagicMock(spec=Session)
        mock_get_goals.return_value = []

        # Act
        result = user_goals_utils.calculate_user_goals(user_id, date, mock_db)

        # Assert
        assert result is None

    @patch("users.users_goals.utils.user_goals_crud.get_user_goals_by_user_id")
    def test_calculate_user_goals_no_date(self, mock_get_goals):
        """Test calculation uses current date when None provided."""
        # Arrange
        user_id = 1
        mock_db = MagicMock(spec=Session)
        mock_get_goals.return_value = []

        # Act
        result = user_goals_utils.calculate_user_goals(user_id, None, mock_db)

        # Assert
        assert result is None
        mock_get_goals.assert_called_once()

    @patch("users.users_goals.utils.user_goals_crud.get_user_goals_by_user_id")
    def test_calculate_user_goals_value_error(self, mock_get_goals):
        """Test ValueError handling."""
        # Arrange
        user_id = 1
        date = "2024-01-15"
        mock_db = MagicMock(spec=Session)
        mock_get_goals.side_effect = ValueError("Invalid value")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            user_goals_utils.calculate_user_goals(user_id, date, mock_db)

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert exc_info.value.detail == "Invalid data provided"


class TestCalculateGoalProgressByActivityType:
    """
    Test suite for calculate_goal_progress_by_activity_type.
    """

    @patch(
        "users.users_goals.utils.activity_crud.get_user_activities_per_timeframe_and_activity_types"
    )
    @patch("users.users_goals.utils.get_start_end_date_by_interval")
    def test_calculate_progress_calories_goal(
        self, mock_get_dates, mock_get_activities
    ):
        """Test calculation for calories goal."""
        # Arrange
        mock_db = MagicMock(spec=Session)
        mock_goal = MagicMock(spec=user_goals_models.UsersGoal)
        mock_goal.id = 1
        mock_goal.user_id = 1
        mock_goal.interval = "weekly"
        mock_goal.activity_type = user_goals_schema.ActivityType.RUN
        mock_goal.goal_type = user_goals_schema.GoalType.CALORIES
        mock_goal.goal_calories = 5000
        mock_goal.goal_activities_number = None
        mock_goal.goal_distance = None
        mock_goal.goal_elevation = None
        mock_goal.goal_duration = None

        mock_start = datetime(2024, 1, 15)
        mock_end = datetime(2024, 1, 21)
        mock_get_dates.return_value = (mock_start, mock_end)

        mock_activity = MagicMock()
        mock_activity.calories = 1500
        mock_get_activities.return_value = [mock_activity]

        # Act
        result = user_goals_utils.calculate_goal_progress_by_activity_type(
            mock_goal, "2024-01-15", mock_db
        )

        # Assert
        assert result.goal_id == 1
        assert result.total_calories == 1500
        assert result.percentage_completed == 30

    @patch(
        "users.users_goals.utils.activity_crud.get_user_activities_per_timeframe_and_activity_types"
    )
    @patch("users.users_goals.utils.get_start_end_date_by_interval")
    def test_calculate_progress_distance_goal(
        self, mock_get_dates, mock_get_activities
    ):
        """Test calculation for distance goal."""
        # Arrange
        mock_db = MagicMock(spec=Session)
        mock_goal = MagicMock(spec=user_goals_models.UsersGoal)
        mock_goal.id = 1
        mock_goal.user_id = 1
        mock_goal.interval = "weekly"
        mock_goal.activity_type = user_goals_schema.ActivityType.RUN
        mock_goal.goal_type = user_goals_schema.GoalType.DISTANCE
        mock_goal.goal_calories = None
        mock_goal.goal_activities_number = None
        mock_goal.goal_distance = 50000
        mock_goal.goal_elevation = None
        mock_goal.goal_duration = None

        mock_start = datetime(2024, 1, 15)
        mock_end = datetime(2024, 1, 21)
        mock_get_dates.return_value = (mock_start, mock_end)

        mock_activity = MagicMock()
        mock_activity.distance = 10000
        mock_activity.calories = None
        mock_get_activities.return_value = [mock_activity]

        # Act
        result = user_goals_utils.calculate_goal_progress_by_activity_type(
            mock_goal, "2024-01-15", mock_db
        )

        # Assert
        assert result.total_distance == 10000
        assert result.percentage_completed == 20

    @patch(
        "users.users_goals.utils.activity_crud.get_user_activities_per_timeframe_and_activity_types"
    )
    @patch("users.users_goals.utils.get_start_end_date_by_interval")
    def test_calculate_progress_activities_goal(
        self, mock_get_dates, mock_get_activities
    ):
        """Test calculation for activities count goal."""
        # Arrange
        mock_db = MagicMock(spec=Session)
        mock_goal = MagicMock(spec=user_goals_models.UsersGoal)
        mock_goal.id = 1
        mock_goal.user_id = 1
        mock_goal.interval = "weekly"
        mock_goal.activity_type = user_goals_schema.ActivityType.RUN
        mock_goal.goal_type = user_goals_schema.GoalType.ACTIVITIES
        mock_goal.goal_calories = None
        mock_goal.goal_activities_number = 5
        mock_goal.goal_distance = None
        mock_goal.goal_elevation = None
        mock_goal.goal_duration = None

        mock_start = datetime(2024, 1, 15)
        mock_end = datetime(2024, 1, 21)
        mock_get_dates.return_value = (mock_start, mock_end)

        mock_get_activities.return_value = [MagicMock(), MagicMock()]

        # Act
        result = user_goals_utils.calculate_goal_progress_by_activity_type(
            mock_goal, "2024-01-15", mock_db
        )

        # Assert
        assert result.total_activities_number == 2
        assert result.percentage_completed == 40

    @patch(
        "users.users_goals.utils.activity_crud.get_user_activities_per_timeframe_and_activity_types"
    )
    @patch("users.users_goals.utils.get_start_end_date_by_interval")
    def test_calculate_progress_caps_at_100_percent(
        self, mock_get_dates, mock_get_activities
    ):
        """Test percentage is capped at 100."""
        # Arrange
        mock_db = MagicMock(spec=Session)
        mock_goal = MagicMock(spec=user_goals_models.UsersGoal)
        mock_goal.id = 1
        mock_goal.user_id = 1
        mock_goal.interval = "weekly"
        mock_goal.activity_type = user_goals_schema.ActivityType.RUN
        mock_goal.goal_type = user_goals_schema.GoalType.CALORIES
        mock_goal.goal_calories = 1000
        mock_goal.goal_activities_number = None
        mock_goal.goal_distance = None
        mock_goal.goal_elevation = None
        mock_goal.goal_duration = None

        mock_start = datetime(2024, 1, 15)
        mock_end = datetime(2024, 1, 21)
        mock_get_dates.return_value = (mock_start, mock_end)

        mock_activity = MagicMock()
        mock_activity.calories = 5000  # Exceeds goal
        mock_get_activities.return_value = [mock_activity]

        # Act
        result = user_goals_utils.calculate_goal_progress_by_activity_type(
            mock_goal, "2024-01-15", mock_db
        )

        # Assert
        assert result.percentage_completed == 100


class TestGetStartEndDateByInterval:
    """
    Test suite for get_start_end_date_by_interval function.
    """

    def test_get_dates_daily_interval(self):
        """Test date calculation for daily interval."""
        # Act
        start, end = user_goals_utils.get_start_end_date_by_interval(
            "daily", "2024-01-15"
        )

        # Assert
        assert start == datetime(2024, 1, 15, 0, 0, 0)
        assert end == datetime(2024, 1, 15, 23, 59, 59)

    def test_get_dates_weekly_interval(self):
        """Test date calculation for weekly interval."""
        # Act
        start, end = user_goals_utils.get_start_end_date_by_interval(
            "weekly", "2024-01-15"  # Monday
        )

        # Assert
        assert start.weekday() == 0  # Monday
        assert end.weekday() == 6  # Sunday

    def test_get_dates_monthly_interval(self):
        """Test date calculation for monthly interval."""
        # Act
        start, end = user_goals_utils.get_start_end_date_by_interval(
            "monthly", "2024-01-15"
        )

        # Assert
        assert start.day == 1
        assert start.month == 1
        assert end.month == 1

    def test_get_dates_yearly_interval(self):
        """Test date calculation for yearly interval."""
        # Act
        start, end = user_goals_utils.get_start_end_date_by_interval(
            "yearly", "2024-06-15"
        )

        # Assert
        assert start == datetime(2024, 1, 1, 0, 0, 0)
        assert end == datetime(2024, 12, 31, 23, 59, 59)

    def test_get_dates_invalid_interval(self):
        """Test invalid interval raises exception."""
        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            user_goals_utils.get_start_end_date_by_interval("invalid", "2024-01-15")

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        assert "Invalid interval" in exc_info.value.detail


class TestActivityTypeMap:
    """
    Test suite for activity type mapping constants.
    """

    def test_activity_type_map_exists(self):
        """Test _ACTIVITY_TYPE_MAP constant exists."""
        assert hasattr(user_goals_utils, "_ACTIVITY_TYPE_MAP")
        assert isinstance(user_goals_utils._ACTIVITY_TYPE_MAP, dict)

    def test_default_activity_types_exists(self):
        """Test _DEFAULT_ACTIVITY_TYPES constant exists."""
        assert hasattr(user_goals_utils, "_DEFAULT_ACTIVITY_TYPES")
        assert isinstance(user_goals_utils._DEFAULT_ACTIVITY_TYPES, list)

    def test_activity_type_map_has_expected_types(self):
        """Test mapping contains expected activity types."""
        map = user_goals_utils._ACTIVITY_TYPE_MAP

        assert user_goals_schema.ActivityType.RUN in map
        assert user_goals_schema.ActivityType.BIKE in map
        assert user_goals_schema.ActivityType.SWIM in map
        assert user_goals_schema.ActivityType.WALK in map
        assert user_goals_schema.ActivityType.CARDIO in map

    def test_strength_uses_default_types(self):
        """Test STRENGTH not in map, uses default."""
        map = user_goals_utils._ACTIVITY_TYPE_MAP

        # STRENGTH should NOT be in map (uses defaults)
        assert user_goals_schema.ActivityType.STRENGTH not in map
