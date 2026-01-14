"""Tests for user goals Pydantic schemas."""

import pytest
from pydantic import ValidationError
from pydantic_core import PydanticCustomError

import users.user_goals.schema as user_goals_schema


class TestIntervalEnum:
    """
    Test suite for Interval enum.
    """

    def test_interval_daily_value(self):
        """Test Interval.DAILY has correct value."""
        assert user_goals_schema.Interval.DAILY == "daily"

    def test_interval_weekly_value(self):
        """Test Interval.WEEKLY has correct value."""
        assert user_goals_schema.Interval.WEEKLY == "weekly"

    def test_interval_monthly_value(self):
        """Test Interval.MONTHLY has correct value."""
        assert user_goals_schema.Interval.MONTHLY == "monthly"

    def test_interval_yearly_value(self):
        """Test Interval.YEARLY has correct value."""
        assert user_goals_schema.Interval.YEARLY == "yearly"


class TestActivityTypeEnum:
    """
    Test suite for ActivityType enum.
    """

    def test_activity_type_run_value(self):
        """Test ActivityType.RUN has correct value."""
        assert user_goals_schema.ActivityType.RUN == "run"

    def test_activity_type_bike_value(self):
        """Test ActivityType.BIKE has correct value."""
        assert user_goals_schema.ActivityType.BIKE == "bike"

    def test_activity_type_swim_value(self):
        """Test ActivityType.SWIM has correct value."""
        assert user_goals_schema.ActivityType.SWIM == "swim"

    def test_activity_type_walk_value(self):
        """Test ActivityType.WALK has correct value."""
        assert user_goals_schema.ActivityType.WALK == "walk"

    def test_activity_type_strength_value(self):
        """Test ActivityType.STRENGTH has correct value."""
        assert user_goals_schema.ActivityType.STRENGTH == "strength"

    def test_activity_type_cardio_value(self):
        """Test ActivityType.CARDIO has correct value."""
        assert user_goals_schema.ActivityType.CARDIO == "cardio"


class TestGoalTypeEnum:
    """
    Test suite for GoalType enum.
    """

    def test_goal_type_calories_value(self):
        """Test GoalType.CALORIES has correct value."""
        assert user_goals_schema.GoalType.CALORIES == "calories"

    def test_goal_type_activities_value(self):
        """Test GoalType.ACTIVITIES has correct value."""
        assert user_goals_schema.GoalType.ACTIVITIES == "activities"

    def test_goal_type_distance_value(self):
        """Test GoalType.DISTANCE has correct value."""
        assert user_goals_schema.GoalType.DISTANCE == "distance"

    def test_goal_type_elevation_value(self):
        """Test GoalType.ELEVATION has correct value."""
        assert user_goals_schema.GoalType.ELEVATION == "elevation"

    def test_goal_type_duration_value(self):
        """Test GoalType.DURATION has correct value."""
        assert user_goals_schema.GoalType.DURATION == "duration"


class TestUserGoalBaseSchema:
    """
    Test suite for UserGoalBase Pydantic schema.
    """

    def test_base_schema_with_calories_goal(self):
        """Test UserGoalBase with calories goal."""
        # Act
        goal = user_goals_schema.UserGoalBase(
            interval=user_goals_schema.Interval.WEEKLY,
            activity_type=user_goals_schema.ActivityType.RUN,
            goal_type=user_goals_schema.GoalType.CALORIES,
            goal_calories=5000,
            goal_activities_number=None,
            goal_distance=None,
            goal_elevation=None,
            goal_duration=None,
        )

        # Assert
        assert goal.interval == "weekly"
        assert goal.activity_type == "run"
        assert goal.goal_type == "calories"
        assert goal.goal_calories == 5000
        assert goal.goal_activities_number is None

    def test_base_schema_with_distance_goal(self):
        """Test UserGoalBase with distance goal."""
        # Act
        goal = user_goals_schema.UserGoalBase(
            interval=user_goals_schema.Interval.MONTHLY,
            activity_type=user_goals_schema.ActivityType.BIKE,
            goal_type=user_goals_schema.GoalType.DISTANCE,
            goal_calories=None,
            goal_activities_number=None,
            goal_distance=100000,
            goal_elevation=None,
            goal_duration=None,
        )

        # Assert
        assert goal.goal_distance == 100000
        assert goal.goal_calories is None

    def test_base_schema_with_activities_goal(self):
        """Test UserGoalBase with activities count goal."""
        # Act
        goal = user_goals_schema.UserGoalBase(
            interval=user_goals_schema.Interval.DAILY,
            activity_type=user_goals_schema.ActivityType.CARDIO,
            goal_type=user_goals_schema.GoalType.ACTIVITIES,
            goal_calories=None,
            goal_activities_number=3,
            goal_distance=None,
            goal_elevation=None,
            goal_duration=None,
        )

        # Assert
        assert goal.goal_activities_number == 3

    def test_base_schema_missing_required_goal_field(self):
        """Test validation fails when required goal field missing."""
        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            user_goals_schema.UserGoalBase(
                interval=user_goals_schema.Interval.WEEKLY,
                activity_type=user_goals_schema.ActivityType.RUN,
                goal_type=user_goals_schema.GoalType.CALORIES,
                goal_calories=None,  # Missing required field
                goal_activities_number=None,
                goal_distance=None,
                goal_elevation=None,
                goal_duration=None,
            )

        assert "missing_goal_value" in str(exc_info.value)

    def test_base_schema_extra_goal_fields_set(self):
        """Test validation fails with multiple goal fields."""
        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            user_goals_schema.UserGoalBase(
                interval=user_goals_schema.Interval.WEEKLY,
                activity_type=user_goals_schema.ActivityType.RUN,
                goal_type=user_goals_schema.GoalType.CALORIES,
                goal_calories=5000,
                goal_distance=10000,  # Extra field
                goal_activities_number=None,
                goal_elevation=None,
                goal_duration=None,
            )

        assert "exclusive_goal_value" in str(exc_info.value)

    def test_base_schema_negative_values_rejected(self):
        """Test negative values are rejected."""
        # Act & Assert
        with pytest.raises(ValidationError):
            user_goals_schema.UserGoalBase(
                interval=user_goals_schema.Interval.WEEKLY,
                activity_type=user_goals_schema.ActivityType.RUN,
                goal_type=user_goals_schema.GoalType.CALORIES,
                goal_calories=-100,
                goal_activities_number=None,
                goal_distance=None,
                goal_elevation=None,
                goal_duration=None,
            )

    def test_base_schema_extra_fields_forbidden(self):
        """Test extra fields are forbidden."""
        # Act & Assert
        with pytest.raises(ValidationError):
            user_goals_schema.UserGoalBase(
                interval=user_goals_schema.Interval.WEEKLY,
                activity_type=user_goals_schema.ActivityType.RUN,
                goal_type=user_goals_schema.GoalType.CALORIES,
                goal_calories=5000,
                goal_activities_number=None,
                goal_distance=None,
                goal_elevation=None,
                goal_duration=None,
                extra_field="not_allowed",
            )


class TestUserGoalCreateSchema:
    """
    Test suite for UserGoalCreate schema.
    """

    def test_create_schema_inherits_validation(self):
        """Test UserGoalCreate inherits validation from base."""
        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            user_goals_schema.UserGoalCreate(
                interval=user_goals_schema.Interval.WEEKLY,
                activity_type=user_goals_schema.ActivityType.RUN,
                goal_type=user_goals_schema.GoalType.CALORIES,
                goal_calories=None,  # Missing required
                goal_activities_number=None,
                goal_distance=None,
                goal_elevation=None,
                goal_duration=None,
            )

        assert "missing_goal_value" in str(exc_info.value)


class TestUserGoalEditSchema:
    """
    Test suite for UserGoalEdit schema.
    """

    def test_edit_schema_allows_partial_updates(self):
        """Test UserGoalEdit supports partial updates."""
        # Act
        goal = user_goals_schema.UserGoalEdit(
            interval=user_goals_schema.Interval.DAILY,
            activity_type=user_goals_schema.ActivityType.RUN,
            goal_type=user_goals_schema.GoalType.DISTANCE,
            goal_calories=None,
            goal_activities_number=None,
            goal_distance=5000,
            goal_elevation=None,
            goal_duration=None,
        )

        # Assert
        assert goal.goal_distance == 5000


class TestUserGoalReadSchema:
    """
    Test suite for UserGoalRead schema.
    """

    def test_read_schema_includes_id_and_user_id(self):
        """Test UserGoalRead includes id and user_id."""
        # Act
        goal = user_goals_schema.UserGoalRead(
            id=1,
            user_id=1,
            interval=user_goals_schema.Interval.WEEKLY,
            activity_type=user_goals_schema.ActivityType.RUN,
            goal_type=user_goals_schema.GoalType.CALORIES,
            goal_calories=5000,
            goal_activities_number=None,
            goal_distance=None,
            goal_elevation=None,
            goal_duration=None,
        )

        # Assert
        assert goal.id == 1
        assert goal.user_id == 1


class TestUserGoalProgressSchema:
    """
    Test suite for UserGoalProgress schema.
    """

    def test_progress_schema_creation(self):
        """Test UserGoalProgress schema creation."""
        # Act
        progress = user_goals_schema.UserGoalProgress(
            goal_id=1,
            interval=user_goals_schema.Interval.WEEKLY,
            activity_type=user_goals_schema.ActivityType.RUN,
            goal_type=user_goals_schema.GoalType.CALORIES,
            start_date="2024-01-01",
            end_date="2024-01-07",
            percentage_completed=75,
            total_calories=3750,
            total_activities_number=5,
            total_distance=25000,
            total_elevation=500,
            total_duration=7200,
            goal_calories=5000,
            goal_activities_number=None,
            goal_distance=None,
            goal_elevation=None,
            goal_duration=None,
        )

        # Assert
        assert progress.goal_id == 1
        assert progress.percentage_completed == 75
        assert progress.total_calories == 3750
        assert progress.goal_calories == 5000

    def test_progress_schema_percentage_max(self):
        """Test percentage_completed max is 100."""
        # Act & Assert
        with pytest.raises(ValidationError):
            user_goals_schema.UserGoalProgress(
                goal_id=1,
                interval=user_goals_schema.Interval.WEEKLY,
                activity_type=user_goals_schema.ActivityType.RUN,
                goal_type=user_goals_schema.GoalType.CALORIES,
                start_date="2024-01-01",
                end_date="2024-01-07",
                percentage_completed=150,  # Exceeds max
                total_calories=7500,
                total_activities_number=None,
                total_distance=None,
                total_elevation=None,
                total_duration=None,
                goal_calories=5000,
                goal_activities_number=None,
                goal_distance=None,
                goal_elevation=None,
                goal_duration=None,
            )

    def test_progress_schema_has_model_config(self):
        """Test UserGoalProgress has model_config."""
        # Assert
        assert hasattr(user_goals_schema.UserGoalProgress, "model_config")
        assert (
            user_goals_schema.UserGoalProgress.model_config["from_attributes"] is True
        )
