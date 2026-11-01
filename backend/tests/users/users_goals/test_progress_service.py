"""Tests for user goals progress calculation."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import core.pagination as core_pagination
import modules.activities.activity.contracts as activity_contracts
import modules.users.users_goals.models as user_goals_models
import modules.users.users_goals.progress_service as user_goals_progress_service
import modules.users.users_goals.schema as user_goals_schema

_PAGE = core_pagination.PageParams(1, 25)


def _progress(goal_id: int) -> user_goals_schema.UsersGoalProgress:
    return user_goals_schema.UsersGoalProgress(
        goal_id=goal_id,
        interval="weekly",
        activity_type="run",
        goal_type="calories",
        start_date="2024-01-15",
        end_date="2024-01-21",
        percentage_completed=0,
    )


class TestCalculateUserGoals:
    """
    Test suite for calculate_user_goals function.
    """

    @patch("modules.users.users_goals.progress_service.user_goals_crud.get_user_goals_page")
    @patch("modules.users.users_goals.progress_service.user_goals_crud.count_user_goals", return_value=5)
    @patch("modules.users.users_goals.progress_service.calculate_goal_progress_by_activity_type")
    def test_calculate_user_goals_success(self, mock_calc_progress, mock_count, mock_get_goals):
        """Test successful calculation of user goals."""
        # Arrange
        user_id = 1
        date = "2024-01-15"
        mock_db = MagicMock(spec=Session)

        mock_goal1 = MagicMock(spec=user_goals_models.UsersGoal)
        mock_goal2 = MagicMock(spec=user_goals_models.UsersGoal)
        mock_get_goals.return_value = [mock_goal1, mock_goal2]

        mock_progress1 = _progress(1)
        mock_progress2 = _progress(2)
        mock_calc_progress.side_effect = [mock_progress1, mock_progress2]

        # Act
        page = core_pagination.PageParams(2, 2)
        result = user_goals_progress_service.calculate_user_goals(user_id, date, "sunday", page, mock_db)

        # Assert
        assert result.items == [mock_progress1, mock_progress2]
        assert (result.total, result.page, result.num_records, result.next) == (5, 2, 2, 3)
        mock_get_goals.assert_called_once_with(user_id, mock_db, limit=2, offset=2)
        mock_count.assert_called_once_with(user_id, mock_db)
        assert mock_calc_progress.call_args_list == [
            ((mock_goal1, date, "sunday", mock_db),),
            ((mock_goal2, date, "sunday", mock_db),),
        ]

    @patch("modules.users.users_goals.progress_service.user_goals_crud.count_user_goals", return_value=0)
    @patch("modules.users.users_goals.progress_service.user_goals_crud.get_user_goals_page")
    def test_calculate_user_goals_no_goals(self, mock_get_goals, mock_count):
        """Test calculation returns an empty list when no goals exist."""
        # Arrange
        user_id = 1
        date = "2024-01-15"
        mock_db = MagicMock(spec=Session)
        mock_get_goals.return_value = []

        # Act
        result = user_goals_progress_service.calculate_user_goals(user_id, date, "monday", _PAGE, mock_db)

        # Assert
        assert result.items == []
        assert result.total == 0 and result.next is None

    @patch("modules.users.users_goals.progress_service.users_integration.local_today")
    @patch("modules.users.users_goals.progress_service.user_goals_crud.count_user_goals", return_value=0)
    @patch("modules.users.users_goals.progress_service.user_goals_crud.get_user_goals_page")
    def test_calculate_user_goals_no_date(self, mock_get_goals, mock_count, mock_today):
        """Omitting the date anchors the period on the athlete's own calendar day."""
        # Arrange
        from datetime import date as date_type

        user_id = 1
        mock_db = MagicMock(spec=Session)
        mock_get_goals.return_value = []
        mock_today.return_value = date_type(2024, 1, 15)

        # Act
        result = user_goals_progress_service.calculate_user_goals(user_id, None, "monday", _PAGE, mock_db)

        # Assert
        assert result.items == []
        mock_get_goals.assert_called_once()
        # Resolved from the user's timezone, not the server's UTC clock.
        mock_today.assert_called_once_with(user_id, mock_db)

    @patch("modules.users.users_goals.progress_service.user_goals_crud.get_user_goals_page")
    def test_calculate_user_goals_value_error(self, mock_get_goals):
        """Test ValueError handling."""
        # Arrange
        user_id = 1
        date = "2024-01-15"
        mock_db = MagicMock(spec=Session)
        mock_get_goals.side_effect = ValueError("Invalid value")

        # Act & Assert
        with pytest.raises(core_exceptions.InvalidInputError):
            user_goals_progress_service.calculate_user_goals(user_id, date, "monday", _PAGE, mock_db)


class TestCalculateGoalProgressByActivityType:
    """
    Test suite for calculate_goal_progress_by_activity_type.
    """

    @patch(
        "modules.users.users_goals.progress_service.activity_integration.total_user_activities_in_timeframe_by_types"
    )
    @patch("modules.users.users_goals.progress_service.user_goals_utils.get_start_end_date_by_interval")
    def test_calculate_progress_calories_goal(self, mock_get_dates, mock_get_activities):
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

        mock_get_activities.return_value = activity_contracts.ActivityTotals(count=1, calories=1500)

        # Act
        result = user_goals_progress_service.calculate_goal_progress_by_activity_type(
            mock_goal,
            "2024-01-15",
            "monday",
            mock_db,
        )

        # Assert
        assert result.goal_id == 1
        assert result.total_calories == 1500
        assert result.percentage_completed == 30

    @patch(
        "modules.users.users_goals.progress_service.activity_integration.total_user_activities_in_timeframe_by_types"
    )
    @patch("modules.users.users_goals.progress_service.user_goals_utils.get_start_end_date_by_interval")
    def test_calculate_progress_distance_goal(self, mock_get_dates, mock_get_activities):
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

        mock_get_activities.return_value = activity_contracts.ActivityTotals(count=1, distance=10000)

        # Act
        result = user_goals_progress_service.calculate_goal_progress_by_activity_type(
            mock_goal,
            "2024-01-15",
            "monday",
            mock_db,
        )

        # Assert
        assert result.total_distance == 10000
        assert result.percentage_completed == 20

    @patch(
        "modules.users.users_goals.progress_service.activity_integration.total_user_activities_in_timeframe_by_types"
    )
    @patch("modules.users.users_goals.progress_service.user_goals_utils.get_start_end_date_by_interval")
    def test_calculate_progress_activities_goal(self, mock_get_dates, mock_get_activities):
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

        mock_get_activities.return_value = activity_contracts.ActivityTotals(count=2)

        # Act
        result = user_goals_progress_service.calculate_goal_progress_by_activity_type(
            mock_goal,
            "2024-01-15",
            "monday",
            mock_db,
        )

        # Assert
        assert result.total_activities_number == 2
        assert result.percentage_completed == 40

    @patch(
        "modules.users.users_goals.progress_service.activity_integration.total_user_activities_in_timeframe_by_types"
    )
    @patch("modules.users.users_goals.progress_service.user_goals_utils.get_start_end_date_by_interval")
    def test_calculate_progress_caps_at_100_percent(self, mock_get_dates, mock_get_activities):
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

        mock_get_activities.return_value = activity_contracts.ActivityTotals(count=1, calories=5000)  # Exceeds goal

        # Act
        result = user_goals_progress_service.calculate_goal_progress_by_activity_type(
            mock_goal,
            "2024-01-15",
            "monday",
            mock_db,
        )

        # Assert
        assert result.percentage_completed == 100

    @patch(
        "modules.users.users_goals.progress_service.activity_integration.total_user_activities_in_timeframe_by_types"
    )
    @patch("modules.users.users_goals.progress_service.user_goals_utils.get_start_end_date_by_interval")
    def test_calculate_progress_excludes_hidden_activities(self, mock_get_dates, mock_get_activities):
        """Test that hidden activities are excluded from goal progress."""
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

        mock_get_activities.return_value = activity_contracts.ActivityTotals(count=1)

        # Act
        user_goals_progress_service.calculate_goal_progress_by_activity_type(
            mock_goal,
            "2024-01-15",
            "monday",
            mock_db,
        )

        # Assert - verify exclude_hidden=True is passed
        mock_get_activities.assert_called_once()
        call_kwargs = mock_get_activities.call_args
        assert call_kwargs.kwargs.get("exclude_hidden") is True

    @patch(
        "modules.users.users_goals.progress_service.activity_integration.total_user_activities_in_timeframe_by_types"
    )
    @patch("modules.users.users_goals.progress_service.user_goals_utils.get_start_end_date_by_interval")
    @pytest.mark.parametrize(
        ("goal_type", "goal_field", "totals", "field", "expected", "percent"),
        [
            (
                user_goals_schema.GoalType.ELEVATION,
                "goal_elevation",
                {"elevation_gain": 400.4},
                "total_elevation",
                400,
                40,
            ),
            (
                user_goals_schema.GoalType.DURATION,
                "goal_duration",
                {"elapsed_time": 1800.0},
                "total_duration",
                1800,
                50,
            ),
        ],
    )
    def test_elevation_and_duration_goals_use_the_summed_totals(
        self, mock_get_dates, mock_get_totals, goal_type, goal_field, totals, field, expected, percent
    ):
        mock_goal = MagicMock(spec=user_goals_models.UsersGoal)
        mock_goal.id = 1
        mock_goal.user_id = 1
        mock_goal.interval = "weekly"
        mock_goal.activity_type = user_goals_schema.ActivityType.RUN
        mock_goal.goal_type = goal_type
        for name in ("goal_calories", "goal_activities_number", "goal_distance", "goal_elevation", "goal_duration"):
            setattr(mock_goal, name, None)
        setattr(mock_goal, goal_field, {"goal_elevation": 1000, "goal_duration": 3600}[goal_field])
        mock_get_dates.return_value = (datetime(2024, 1, 15), datetime(2024, 1, 21))
        mock_get_totals.return_value = activity_contracts.ActivityTotals(count=1, **totals)

        result = user_goals_progress_service.calculate_goal_progress_by_activity_type(
            mock_goal, "2024-01-15", "monday", MagicMock(spec=Session)
        )

        assert getattr(result, field) == expected
        assert result.percentage_completed == percent

    @patch(
        "modules.users.users_goals.progress_service.activity_integration.total_user_activities_in_timeframe_by_types"
    )
    @patch("modules.users.users_goals.progress_service.user_goals_utils.get_start_end_date_by_interval")
    def test_no_matching_activities_is_zero_progress(self, mock_get_dates, mock_get_totals):
        mock_goal = MagicMock(spec=user_goals_models.UsersGoal)
        mock_goal.id = 1
        mock_goal.user_id = 1
        mock_goal.interval = "weekly"
        mock_goal.activity_type = user_goals_schema.ActivityType.RUN
        mock_goal.goal_type = user_goals_schema.GoalType.CALORIES
        mock_goal.goal_calories = 5000
        for name in ("goal_activities_number", "goal_distance", "goal_elevation", "goal_duration"):
            setattr(mock_goal, name, None)
        mock_get_dates.return_value = (datetime(2024, 1, 15), datetime(2024, 1, 21))
        mock_get_totals.return_value = activity_contracts.ActivityTotals()

        result = user_goals_progress_service.calculate_goal_progress_by_activity_type(
            mock_goal, "2024-01-15", "monday", MagicMock(spec=Session)
        )

        assert result.total_calories == 0
        assert result.percentage_completed == 0


class TestActivityTypeMap:
    """
    Test suite for activity type mapping constants.
    """

    def test_activity_type_map_exists(self):
        """Test _ACTIVITY_TYPE_MAP constant exists."""
        assert hasattr(user_goals_progress_service, "_ACTIVITY_TYPE_MAP")
        assert isinstance(user_goals_progress_service._ACTIVITY_TYPE_MAP, dict)

    def test_default_activity_types_exists(self):
        """Test _DEFAULT_ACTIVITY_TYPES constant exists."""
        assert hasattr(user_goals_progress_service, "_DEFAULT_ACTIVITY_TYPES")
        assert isinstance(user_goals_progress_service._DEFAULT_ACTIVITY_TYPES, list)

    def test_activity_type_map_has_expected_types(self):
        """Test mapping contains expected activity types."""
        type_map = user_goals_progress_service._ACTIVITY_TYPE_MAP

        assert user_goals_schema.ActivityType.RUN in type_map
        assert user_goals_schema.ActivityType.BIKE in type_map
        assert user_goals_schema.ActivityType.SWIM in type_map
        assert user_goals_schema.ActivityType.WALK in type_map
        assert user_goals_schema.ActivityType.CARDIO in type_map

    def test_cardio_includes_jump_rope_id(self):
        """Test CARDIO mapping includes the jump rope activity ID (47)."""
        type_map = user_goals_progress_service._ACTIVITY_TYPE_MAP

        assert 47 in type_map[user_goals_schema.ActivityType.CARDIO]

    def test_strength_uses_default_types(self):
        """Test STRENGTH not in map, uses default."""
        type_map = user_goals_progress_service._ACTIVITY_TYPE_MAP

        # STRENGTH should NOT be in map (uses defaults)
        assert user_goals_schema.ActivityType.STRENGTH not in type_map


class TestGetGoalsProgress:
    """Test suite for get_goals_progress function."""

    @patch("modules.users.users_goals.progress_service.calculate_user_goals")
    @patch("modules.users.users_goals.progress_service.core_timezone.today_in")
    @patch("modules.users.users_goals.progress_service.users_integration")
    def test_anchors_on_the_users_own_day(self, mock_users, mock_today, mock_calculate):
        from datetime import date as date_type

        mock_db = MagicMock(spec=Session)
        mock_users.get_user.return_value.first_day_of_week = "sunday"
        mock_today.return_value = date_type(2026, 3, 12)

        result = user_goals_progress_service.get_goals_progress(1, _PAGE, mock_db)

        assert result == mock_calculate.return_value
        mock_calculate.assert_called_once_with(1, "2026-03-12", "sunday", _PAGE, mock_db)

    @patch("modules.users.users_goals.progress_service.users_integration")
    def test_unknown_user_is_not_found(self, mock_users):
        mock_users.get_user.return_value = None

        with pytest.raises(core_exceptions.NotFoundError):
            user_goals_progress_service.get_goals_progress(1, _PAGE, MagicMock(spec=Session))
