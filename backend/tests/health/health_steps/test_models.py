import pytest
from datetime import date as datetime_date

import health.health_steps.models as health_steps_models


class TestHealthStepsModel:
    """
    Test suite for HealthSteps SQLAlchemy model.
    """

    def test_health_steps_model_table_name(self):
        """
        Test HealthSteps model has correct table name.
        """
        # Assert
        assert health_steps_models.HealthSteps.__tablename__ == "health_steps"

    def test_health_steps_model_columns_exist(self):
        """
        Test HealthSteps model has all expected columns.
        """
        # Assert
        assert hasattr(health_steps_models.HealthSteps, "id")
        assert hasattr(health_steps_models.HealthSteps, "user_id")
        assert hasattr(health_steps_models.HealthSteps, "date")
        assert hasattr(health_steps_models.HealthSteps, "steps")
        assert hasattr(health_steps_models.HealthSteps, "source")

    def test_health_steps_model_primary_key(self):
        """
        Test HealthSteps model has correct primary key.
        """
        # Arrange
        id_column = health_steps_models.HealthSteps.id

        # Assert
        assert id_column.primary_key is True
        assert id_column.autoincrement is True

    def test_health_steps_model_foreign_key(self):
        """
        Test HealthSteps model has correct foreign key.
        """
        # Arrange
        user_id_column = health_steps_models.HealthSteps.user_id

        # Assert
        assert user_id_column.nullable is False
        assert user_id_column.index is True

    def test_health_steps_model_nullable_fields(self):
        """
        Test HealthSteps model nullable fields.
        """
        # Assert
        assert health_steps_models.HealthSteps.source.nullable is True

    def test_health_steps_model_required_fields(self):
        """
        Test HealthSteps model required fields.
        """
        # Assert
        assert health_steps_models.HealthSteps.user_id.nullable is False
        assert health_steps_models.HealthSteps.date.nullable is False
        assert health_steps_models.HealthSteps.steps.nullable is False

    def test_health_steps_model_column_types(self):
        """
        Test HealthSteps model column types.
        """
        # Assert
        assert health_steps_models.HealthSteps.id.type.python_type == int
        assert health_steps_models.HealthSteps.user_id.type.python_type == int
        assert health_steps_models.HealthSteps.date.type.python_type == datetime_date
        assert health_steps_models.HealthSteps.steps.type.python_type == int
        assert health_steps_models.HealthSteps.source.type.python_type == str

    def test_health_steps_model_relationship(self):
        """
        Test HealthSteps model has relationship to User.
        """
        # Assert
        assert hasattr(health_steps_models.HealthSteps, "users")

    def test_health_steps_model_source_max_length(self):
        """
        Test HealthSteps model source field has correct max length.
        """
        # Arrange
        source_column = health_steps_models.HealthSteps.source

        # Assert
        assert source_column.type.length == 250
