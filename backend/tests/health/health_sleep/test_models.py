import pytest
from datetime import date as datetime_date

import health.health_sleep.models as health_sleep_models


class TestHealthSleepModel:
    """
    Test suite for HealthSleep SQLAlchemy model.
    """

    def test_health_sleep_model_table_name(self):
        """
        Test HealthSleep model has correct table name.
        """
        # Assert
        assert health_sleep_models.HealthSleep.__tablename__ == "health_sleep"

    def test_health_sleep_model_columns_exist(self):
        """
        Test HealthSleep model has all expected columns.
        """
        # Assert
        assert hasattr(health_sleep_models.HealthSleep, "id")
        assert hasattr(health_sleep_models.HealthSleep, "user_id")
        assert hasattr(health_sleep_models.HealthSleep, "date")
        assert hasattr(health_sleep_models.HealthSleep, "sleep_start_time_gmt")
        assert hasattr(health_sleep_models.HealthSleep, "sleep_end_time_gmt")
        assert hasattr(health_sleep_models.HealthSleep, "total_sleep_seconds")
        assert hasattr(health_sleep_models.HealthSleep, "deep_sleep_seconds")
        assert hasattr(health_sleep_models.HealthSleep, "light_sleep_seconds")
        assert hasattr(health_sleep_models.HealthSleep, "rem_sleep_seconds")
        assert hasattr(health_sleep_models.HealthSleep, "avg_heart_rate")
        assert hasattr(health_sleep_models.HealthSleep, "sleep_score_overall")
        assert hasattr(health_sleep_models.HealthSleep, "source")

    def test_health_sleep_model_primary_key(self):
        """
        Test HealthSleep model has correct primary key.
        """
        # Arrange
        id_column = health_sleep_models.HealthSleep.id

        # Assert
        assert id_column.primary_key is True
        assert id_column.autoincrement is True

    def test_health_sleep_model_foreign_key(self):
        """
        Test HealthSleep model has correct foreign key.
        """
        # Arrange
        user_id_column = health_sleep_models.HealthSleep.user_id

        # Assert
        assert user_id_column.nullable is False
        assert user_id_column.index is True

    def test_health_sleep_model_nullable_fields(self):
        """
        Test HealthSleep model nullable fields.
        """
        # Assert
        assert health_sleep_models.HealthSleep.sleep_start_time_gmt.nullable is True
        assert health_sleep_models.HealthSleep.total_sleep_seconds.nullable is True
        assert health_sleep_models.HealthSleep.deep_sleep_seconds.nullable is True
        assert health_sleep_models.HealthSleep.avg_heart_rate.nullable is True
        assert health_sleep_models.HealthSleep.sleep_score_overall.nullable is True
        assert health_sleep_models.HealthSleep.source.nullable is True

    def test_health_sleep_model_required_fields(self):
        """
        Test HealthSleep model required fields.
        """
        # Assert
        assert health_sleep_models.HealthSleep.user_id.nullable is False
        assert health_sleep_models.HealthSleep.date.nullable is False

    def test_health_sleep_model_column_types(self):
        """
        Test HealthSleep model column types.
        """
        # Assert
        assert health_sleep_models.HealthSleep.id.type.python_type == int
        assert health_sleep_models.HealthSleep.user_id.type.python_type == int
        assert health_sleep_models.HealthSleep.date.type.python_type == datetime_date
        assert (
            health_sleep_models.HealthSleep.total_sleep_seconds.type.python_type == int
        )
        assert health_sleep_models.HealthSleep.min_heart_rate.type.python_type == int
        assert health_sleep_models.HealthSleep.awake_count.type.python_type == int

    def test_health_sleep_model_relationship(self):
        """
        Test HealthSleep model has relationship to User.
        """
        # Assert
        assert hasattr(health_sleep_models.HealthSleep, "users")

    def test_health_sleep_model_integer_fields(self):
        """
        Test HealthSleep model integer fields.
        """
        # Arrange
        avg_heart_rate_column = health_sleep_models.HealthSleep.avg_heart_rate
        avg_spo2_column = health_sleep_models.HealthSleep.avg_spo2

        # Assert
        assert avg_heart_rate_column.type.python_type == int
        assert avg_spo2_column.type.python_type == int

    def test_health_sleep_model_string_field_lengths(self):
        """
        Test HealthSleep model string field max lengths.
        """
        # Assert
        assert health_sleep_models.HealthSleep.source.type.length == 250
        assert health_sleep_models.HealthSleep.garminconnect_sleep_id.type.length == 250
        assert health_sleep_models.HealthSleep.sleep_score_duration.type.length == 50

    def test_health_sleep_model_date_indexed(self):
        """
        Test HealthSleep model date field is indexed.
        """
        # Arrange
        date_column = health_sleep_models.HealthSleep.date

        # Assert
        assert date_column.index is True
