import pytest
from datetime import datetime

import health.health_intraday_steps.models as health_intraday_steps_models


class TestHealthIntradayStepsModel:
    """
    Test suite for HealthIntradaySteps SQLAlchemy model.
    """

    def test_health_intraday_steps_model_table_name(self):
        """
        Test HealthIntradaySteps model has correct table name.
        """
        # Assert
        assert health_intraday_steps_models.HealthIntradaySteps.__tablename__ == "health_intraday_steps"

    def test_health_intraday_steps_model_columns_exist(self):
        """
        Test HealthIntradaySteps model has all expected columns.
        """
        # Assert
        assert hasattr(health_intraday_steps_models.HealthIntradaySteps, "id")
        assert hasattr(health_intraday_steps_models.HealthIntradaySteps, "user_id")
        assert hasattr(health_intraday_steps_models.HealthIntradaySteps, "timestamp")
        assert hasattr(health_intraday_steps_models.HealthIntradaySteps, "steps")
        assert hasattr(health_intraday_steps_models.HealthIntradaySteps, "source")
        assert hasattr(health_intraday_steps_models.HealthIntradaySteps, "activity_type")
        assert hasattr(health_intraday_steps_models.HealthIntradaySteps, "intensity")

    def test_health_intraday_steps_model_primary_key(self):
        """
        Test HealthIntradaySteps model has correct primary key.
        """
        # Arrange
        id_column = health_intraday_steps_models.HealthIntradaySteps.id

        # Assert
        assert id_column.primary_key is True
        assert id_column.autoincrement is True

    def test_health_intraday_steps_model_foreign_key(self):
        """
        Test HealthIntradaySteps model has correct foreign key.
        """
        # Arrange
        user_id_column = health_intraday_steps_models.HealthIntradaySteps.user_id

        # Assert
        assert user_id_column.nullable is False
        assert user_id_column.index is True

    def test_health_intraday_steps_model_nullable_fields(self):
        """
        Test HealthIntradaySteps model nullable fields.
        """
        # Assert
        assert health_intraday_steps_models.HealthIntradaySteps.source.nullable is True
        assert health_intraday_steps_models.HealthIntradaySteps.activity_type.nullable is True
        assert health_intraday_steps_models.HealthIntradaySteps.intensity.nullable is True

    def test_health_intraday_steps_model_required_fields(self):
        """
        Test HealthIntradaySteps model required fields.
        """
        # Assert
        assert health_intraday_steps_models.HealthIntradaySteps.user_id.nullable is False
        assert health_intraday_steps_models.HealthIntradaySteps.timestamp.nullable is False
        assert health_intraday_steps_models.HealthIntradaySteps.steps.nullable is False

    def test_health_intraday_steps_model_column_types(self):
        """
        Test HealthIntradaySteps model column types.
        """
        # Assert
        assert health_intraday_steps_models.HealthIntradaySteps.id.type.python_type == int
        assert health_intraday_steps_models.HealthIntradaySteps.user_id.type.python_type == int
        assert health_intraday_steps_models.HealthIntradaySteps.timestamp.type.python_type == datetime
        assert health_intraday_steps_models.HealthIntradaySteps.steps.type.python_type == int
        assert health_intraday_steps_models.HealthIntradaySteps.source.type.python_type == str

    def test_health_intraday_steps_model_relationship(self):
        """
        Test HealthIntradaySteps model has relationship to User.
        """
        # Assert
        assert hasattr(health_intraday_steps_models.HealthIntradaySteps, "user")

    def test_health_intraday_steps_model_source_max_length(self):
        """
        Test HealthIntradaySteps model source field has correct max length.
        """
        # Arrange
        source_column = health_intraday_steps_models.HealthIntradaySteps.source

        # Assert
        assert source_column.type.length == 250

    def test_health_intraday_steps_model_unique_constraint(self):
        """
        Test HealthIntradaySteps model has unique constraint on user_id and timestamp.
        """
        # Arrange
        table_args = health_intraday_steps_models.HealthIntradaySteps.__table_args__

        # Assert
        assert table_args is not None
        assert len(table_args) > 0
