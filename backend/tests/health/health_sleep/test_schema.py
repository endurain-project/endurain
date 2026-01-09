import pytest
from datetime import datetime, date as datetime_date
from decimal import Decimal
from pydantic import ValidationError

import health.health_sleep.schema as health_sleep_schema


class TestHealthSleepSchema:
    """
    Test suite for HealthSleep Pydantic schema.
    """

    def test_health_sleep_valid_full_data(self):
        """
        Test HealthSleepRead schema with all valid fields.
        """
        # Arrange & Act
        health_sleep = health_sleep_schema.HealthSleepRead(
            id=1,
            user_id=1,
            date=datetime_date(2024, 1, 15),
            sleep_start_time_gmt=datetime(2024, 1, 14, 22, 0, 0),
            sleep_end_time_gmt=datetime(2024, 1, 15, 6, 0, 0),
            total_sleep_seconds=28800,
            deep_sleep_seconds=7200,
            light_sleep_seconds=14400,
            rem_sleep_seconds=7200,
            avg_heart_rate=55,
            min_heart_rate=45,
            max_heart_rate=75,
            sleep_score_overall=85,
            source=health_sleep_schema.Source.GARMIN,
        )

        # Assert
        assert health_sleep.id == 1
        assert health_sleep.user_id == 1
        assert health_sleep.date == datetime_date(2024, 1, 15)
        assert health_sleep.total_sleep_seconds == 28800
        assert health_sleep.sleep_score_overall == 85
        assert health_sleep.source == "garmin"

    def test_health_sleep_minimal_data(self):
        """
        Test HealthSleepBase schema with minimal required fields.
        """
        # Arrange & Act
        health_sleep = health_sleep_schema.HealthSleepBase()

        # Assert
        assert health_sleep.date is None
        assert health_sleep.total_sleep_seconds is None

    def test_health_sleep_with_none_values(self):
        """
        Test HealthSleepRead schema allows None for optional fields.
        """
        # Arrange & Act
        health_sleep = health_sleep_schema.HealthSleepRead(
            id=1,
            user_id=1,
            date=datetime_date(2024, 1, 15),
            total_sleep_seconds=28800,
            deep_sleep_seconds=None,
            avg_heart_rate=None,
        )

        # Assert
        assert health_sleep.id == 1
        assert health_sleep.total_sleep_seconds == 28800
        assert health_sleep.deep_sleep_seconds is None
        assert health_sleep.avg_heart_rate is None

    def test_health_sleep_forbid_extra_fields(self):
        """
        Test that HealthSleepBase schema forbids extra fields.
        """
        # Arrange & Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            health_sleep_schema.HealthSleepBase(
                total_sleep_seconds=28800, extra_field="not allowed"
            )

        assert "extra_field" in str(exc_info.value)

    def test_health_sleep_from_attributes(self):
        """
        Test HealthSleepRead schema can be created from ORM model.
        """

        # Arrange
        class MockORMModel:
            """Mock ORM model for testing."""

            id = 1
            user_id = 1
            date = datetime_date(2024, 1, 15)
            sleep_start_time_gmt = datetime(2024, 1, 14, 22, 0, 0)
            sleep_end_time_gmt = datetime(2024, 1, 15, 6, 0, 0)
            sleep_start_time_local = None
            sleep_end_time_local = None
            total_sleep_seconds = 28800
            nap_time_seconds = None
            unmeasurable_sleep_seconds = None
            deep_sleep_seconds = 7200
            light_sleep_seconds = 14400
            rem_sleep_seconds = 7200
            awake_sleep_seconds = 0
            avg_heart_rate = 55
            min_heart_rate = 45
            max_heart_rate = 75
            avg_spo2 = 97
            lowest_spo2 = 95
            highest_spo2 = 99
            avg_respiration = None
            lowest_respiration = None
            highest_respiration = None
            avg_stress_level = None
            awake_count = 2
            restless_moments_count = 5
            sleep_score_overall = 85
            sleep_score_duration = "GOOD"
            sleep_score_quality = "GOOD"
            garminconnect_sleep_id = None
            sleep_stages = None
            source = "garmin"
            hrv_status = None
            resting_heart_rate = 50
            avg_skin_temp_deviation = None
            awake_count_score = None
            rem_percentage_score = None
            deep_percentage_score = None
            light_percentage_score = None
            avg_sleep_stress = None
            sleep_stress_score = None

        # Act
        health_sleep = health_sleep_schema.HealthSleepRead.model_validate(
            MockORMModel()
        )

        # Assert
        assert health_sleep.id == 1
        assert health_sleep.total_sleep_seconds == 28800
        assert health_sleep.source == "garmin"

    def test_health_sleep_validate_assignment(self):
        """
        Test that validate_assignment works correctly.
        """
        # Arrange
        health_sleep = health_sleep_schema.HealthSleepBase(total_sleep_seconds=28800)

        # Act
        health_sleep.total_sleep_seconds = 32400
        health_sleep.sleep_score_overall = 90

        # Assert
        assert health_sleep.total_sleep_seconds == 32400
        assert health_sleep.sleep_score_overall == 90

    def test_health_sleep_heart_rate_validation_valid(self):
        """
        Test heart rate validation with valid values.
        """
        # Arrange & Act
        health_sleep = health_sleep_schema.HealthSleepBase(
            avg_heart_rate=60,
            min_heart_rate=45,
            max_heart_rate=85,
        )

        # Assert
        assert health_sleep.avg_heart_rate == 60
        assert health_sleep.min_heart_rate == 45
        assert health_sleep.max_heart_rate == 85

    def test_health_sleep_heart_rate_validation_invalid_low(self):
        """
        Test heart rate validation rejects values below 20 bpm.
        """
        # Arrange & Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            health_sleep_schema.HealthSleepBase(min_heart_rate=15)

        assert "greater than or equal to 20" in str(exc_info.value)

    def test_health_sleep_heart_rate_validation_invalid_high(self):
        """
        Test heart rate validation rejects values above 220 bpm.
        """
        # Arrange & Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            health_sleep_schema.HealthSleepBase(max_heart_rate=250)

        assert "less than or equal to 220" in str(exc_info.value)

    def test_health_sleep_spo2_validation_valid(self):
        """
        Test SpO2 validation with valid values.
        """
        # Arrange & Act
        health_sleep = health_sleep_schema.HealthSleepBase(
            avg_spo2=97,
            lowest_spo2=95,
            highest_spo2=99,
        )

        # Assert
        assert health_sleep.avg_spo2 == 97
        assert health_sleep.lowest_spo2 == 95
        assert health_sleep.highest_spo2 == 99

    def test_health_sleep_spo2_validation_invalid_low(self):
        """
        Test SpO2 validation rejects values below 70%.
        """
        # Arrange & Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            health_sleep_schema.HealthSleepBase(lowest_spo2=65)

        assert "greater than or equal to 70" in str(exc_info.value)

    def test_health_sleep_spo2_validation_invalid_high(self):
        """
        Test SpO2 validation rejects values above 100%.
        """
        # Arrange & Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            health_sleep_schema.HealthSleepBase(highest_spo2=105)

        assert "less than or equal to 100" in str(exc_info.value)

    def test_health_sleep_time_validation_valid(self):
        """
        Test sleep time validation with valid start < end times.
        """
        # Arrange & Act
        health_sleep = health_sleep_schema.HealthSleepBase(
            sleep_start_time_gmt=datetime(2024, 1, 14, 22, 0, 0),
            sleep_end_time_gmt=datetime(2024, 1, 15, 6, 0, 0),
        )

        # Assert
        assert health_sleep.sleep_start_time_gmt < health_sleep.sleep_end_time_gmt

    def test_health_sleep_time_validation_invalid(self):
        """
        Test sleep time validation rejects start >= end times.
        """
        # Arrange & Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            health_sleep_schema.HealthSleepBase(
                sleep_start_time_gmt=datetime(2024, 1, 15, 6, 0, 0),
                sleep_end_time_gmt=datetime(2024, 1, 14, 22, 0, 0),
            )

        assert "before" in str(exc_info.value)


class TestSourceEnum:
    """
    Test suite for Source enum.
    """

    def test_source_enum_garmin(self):
        """
        Test Source enum has GARMIN value.
        """
        # Arrange & Act
        source = health_sleep_schema.Source.GARMIN

        # Assert
        assert source.value == "garmin"

    def test_source_enum_use_in_schema(self):
        """
        Test Source enum can be used in HealthSleepBase schema.
        """
        # Arrange & Act
        health_sleep = health_sleep_schema.HealthSleepBase(
            source=health_sleep_schema.Source.GARMIN
        )

        # Assert
        assert health_sleep.source == "garmin"


class TestSleepScoreEnum:
    """
    Test suite for SleepScore enum.
    """

    def test_sleep_score_enum_values(self):
        """
        Test SleepScore enum has all expected values.
        """
        # Assert
        assert health_sleep_schema.SleepScore.EXCELLENT.value == "EXCELLENT"
        assert health_sleep_schema.SleepScore.GOOD.value == "GOOD"
        assert health_sleep_schema.SleepScore.FAIR.value == "FAIR"
        assert health_sleep_schema.SleepScore.POOR.value == "POOR"


class TestHRVStatusEnum:
    """
    Test suite for HRVStatus enum.
    """

    def test_hrv_status_enum_values(self):
        """
        Test HRVStatus enum has all expected values.
        """
        # Assert
        assert health_sleep_schema.HRVStatus.BALANCED.value == "BALANCED"
        assert health_sleep_schema.HRVStatus.UNBALANCED.value == "UNBALANCED"
        assert health_sleep_schema.HRVStatus.LOW.value == "LOW"
        assert health_sleep_schema.HRVStatus.POOR.value == "POOR"


class TestHealthSleepListResponse:
    """
    Test suite for HealthSleepListResponse schema.
    """

    def test_health_sleep_list_response_valid(self):
        """
        Test HealthSleepListResponse with valid data.
        """
        # Arrange & Act
        health_sleep1 = health_sleep_schema.HealthSleepRead(
            id=1,
            user_id=1,
            date=datetime_date(2024, 1, 15),
            total_sleep_seconds=28800,
        )
        health_sleep2 = health_sleep_schema.HealthSleepRead(
            id=2,
            user_id=1,
            date=datetime_date(2024, 1, 16),
            total_sleep_seconds=32400,
        )

        response = health_sleep_schema.HealthSleepListResponse(
            total=2, records=[health_sleep1, health_sleep2]
        )

        # Assert
        assert response.total == 2
        assert len(response.records) == 2
        assert response.records[0].total_sleep_seconds == 28800
        assert response.records[1].total_sleep_seconds == 32400

    def test_health_sleep_list_response_empty(self):
        """
        Test HealthSleepListResponse with empty records.
        """
        # Arrange & Act
        response = health_sleep_schema.HealthSleepListResponse(total=0, records=[])

        # Assert
        assert response.total == 0
        assert response.records == []
