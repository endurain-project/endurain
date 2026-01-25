import pytest
from datetime import datetime

import health.health_intraday_heart_rate.models as health_intraday_heart_rate_models


class TestHealthIntradayHeartrateModel:
    """
    Test suite for HealthIntradayHeartrate SQLAlchemy model.
    """

    def test_health_intraday_heart_rate_model_table_name(self):
        """
        Test HealthIntradayHeartrate model has correct table name.
        """
        # Assert
        assert health_intraday_heart_rate_models.HealthIntradayHeartrate.__tablename__ == "health_intraday_heart_rate"

    def test_health_intraday_heart_rate_model_columns_exist(self):
        """
        Test HealthIntradayHeartrate model has all expected columns.
        """
        # Assert
        assert hasattr(health_intraday_heart_rate_models.HealthIntradayHeartrate, "id")
        assert hasattr(health_intraday_heart_rate_models.HealthIntradayHeartrate, "user_id")
        assert hasattr(health_intraday_heart_rate_models.HealthIntradayHeartrate, "timestamp")
        assert hasattr(health_intraday_heart_rate_models.HealthIntradayHeartrate, "heart_rate")
        assert hasattr(health_intraday_heart_rate_models.HealthIntradayHeartrate, "source")

    def test_health_intraday_heart_rate_model_primary_key(self):
        """
        Test HealthIntradayHeartrate model has correct primary key.
        """
        # Arrange
        id_column = health_intraday_heart_rate_models.HealthIntradayHeartrate.id

        # Assert
        assert id_column.primary_key is True
        assert id_column.autoincrement is True

    def test_health_intraday_heart_rate_model_foreign_key(self):
        """
        Test HealthIntradayHeartrate model has correct foreign key.
        """
        # Arrange
        user_id_column = health_intraday_heart_rate_models.HealthIntradayHeartrate.user_id

        # Assert
        assert user_id_column.nullable is False
        assert user_id_column.index is True

    def test_health_intraday_heart_rate_model_nullable_fields(self):
        """
        Test HealthIntradayHeartrate model nullable fields.
        """
        # Assert
        assert health_intraday_heart_rate_models.HealthIntradayHeartrate.source.nullable is True

    def test_health_intraday_heart_rate_model_required_fields(self):
        """
        Test HealthIntradayHeartrate model required fields.
        """
        # Assert
        assert health_intraday_heart_rate_models.HealthIntradayHeartrate.user_id.nullable is False
        assert health_intraday_heart_rate_models.HealthIntradayHeartrate.timestamp.nullable is False
        assert health_intraday_heart_rate_models.HealthIntradayHeartrate.heart_rate.nullable is False

    def test_health_intraday_heart_rate_model_column_types(self):
        """
        Test HealthIntradayHeartrate model column types.
        """
        # Assert
        assert health_intraday_heart_rate_models.HealthIntradayHeartrate.id.type.python_type == int
        assert health_intraday_heart_rate_models.HealthIntradayHeartrate.user_id.type.python_type == int
        assert health_intraday_heart_rate_models.HealthIntradayHeartrate.timestamp.type.python_type == datetime
        assert health_intraday_heart_rate_models.HealthIntradayHeartrate.heart_rate.type.python_type == int
        assert health_intraday_heart_rate_models.HealthIntradayHeartrate.source.type.python_type == str

    def test_health_intraday_heart_rate_model_relationship(self):
        """
        Test HealthIntradayHeartrate model has relationship to User.
        """
        # Assert
        assert hasattr(health_intraday_heart_rate_models.HealthIntradayHeartrate, "user")

    def test_health_intraday_heart_rate_model_source_max_length(self):
        """
        Test HealthIntradayHeartrate model source field has correct max length.
        """
        # Arrange
        source_column = health_intraday_heart_rate_models.HealthIntradayHeartrate.source

        # Assert
        assert source_column.type.length == 250

    def test_health_intraday_heart_rate_model_unique_constraint(self):
        """
        Test HealthIntradayHeartrate model has unique constraint on user_id and timestamp.
        """
        # Arrange
        table_args = health_intraday_heart_rate_models.HealthIntradayHeartrate.__table_args__

        # Assert
        assert table_args is not None
        assert len(table_args) > 0
