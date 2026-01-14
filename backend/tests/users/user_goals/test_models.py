"""Tests for user goals database models."""

import pytest

import users.user_goals.models as user_goals_models


class TestUserGoalModel:
    """
    Test suite for UserGoal SQLAlchemy model.
    """

    def test_user_goal_model_table_name(self):
        """
        Test UserGoal model has correct table name.
        """
        # Assert
        assert user_goals_models.UserGoal.__tablename__ == "users_goals"

    def test_user_goal_model_columns_exist(self):
        """
        Test UserGoal model has all expected columns.
        """
        # Assert
        model = user_goals_models.UserGoal
        assert hasattr(model, "id")
        assert hasattr(model, "user_id")
        assert hasattr(model, "interval")
        assert hasattr(model, "activity_type")
        assert hasattr(model, "goal_type")
        assert hasattr(model, "goal_calories")
        assert hasattr(model, "goal_activities_number")
        assert hasattr(model, "goal_distance")
        assert hasattr(model, "goal_elevation")
        assert hasattr(model, "goal_duration")
        assert hasattr(model, "user")

    def test_user_goal_model_primary_key(self):
        """
        Test UserGoal model has correct primary key.
        """
        # Arrange
        id_column = user_goals_models.UserGoal.id

        # Assert
        assert id_column.primary_key is True
        assert id_column.autoincrement is True

    def test_user_goal_model_foreign_key(self):
        """
        Test UserGoal model has correct foreign key to users table.
        """
        # Arrange
        user_id_column = user_goals_models.UserGoal.user_id

        # Assert
        assert user_id_column.nullable is False
        assert user_id_column.index is True

    def test_user_goal_model_required_fields(self):
        """
        Test UserGoal model required fields are not nullable.
        """
        # Arrange
        model = user_goals_models.UserGoal

        # Assert - Required fields
        assert model.user_id.nullable is False
        assert model.interval.nullable is False
        assert model.activity_type.nullable is False
        assert model.goal_type.nullable is False

    def test_user_goal_model_optional_fields(self):
        """
        Test UserGoal model optional fields are nullable.
        """
        # Arrange
        model = user_goals_models.UserGoal

        # Assert - Optional goal fields
        assert model.goal_calories.nullable is True
        assert model.goal_activities_number.nullable is True
        assert model.goal_distance.nullable is True
        assert model.goal_elevation.nullable is True
        assert model.goal_duration.nullable is True

    def test_user_goal_model_column_types(self):
        """
        Test UserGoal model column types are correct.
        """
        # Arrange
        model = user_goals_models.UserGoal

        # Assert
        assert model.id.type.python_type == int
        assert model.user_id.type.python_type == int
        assert model.interval.type.python_type == str
        assert model.activity_type.type.python_type == str
        assert model.goal_type.type.python_type == str
