import pytest
from datetime import datetime
from pydantic import ValidationError

import health.health_intraday_steps.schema as health_intraday_steps_schema


class TestHealthIntradayStepsSchema:
    """
    Test suite for HealthIntradaySteps Pydantic schema.
    """

    def test_health_intraday_steps_valid_full_data(self):
        """
        Test HealthIntradayStepsRead schema with all valid fields.
        """
        # Arrange & Act
        test_timestamp = datetime(2024, 1, 15, 10, 30, 0)
        health_intraday_steps = health_intraday_steps_schema.HealthIntradayStepsRead(
            id=1,
            user_id=1,
            timestamp=test_timestamp,
            steps=1000,
            activity_type=1,
            intensity=2,
            source=health_intraday_steps_schema.Source.GARMIN,
        )

        # Assert
        assert health_intraday_steps.id == 1
        assert health_intraday_steps.user_id == 1
        assert health_intraday_steps.timestamp == test_timestamp
        assert health_intraday_steps.steps == 1000
        assert health_intraday_steps.activity_type == 1
        assert health_intraday_steps.intensity == 2
        assert health_intraday_steps.source == "garmin"

    def test_health_intraday_steps_minimal_data(self):
        """
        Test HealthIntradayStepsBase schema with minimal required fields.
        """
        # Arrange & Act
        health_intraday_steps = health_intraday_steps_schema.HealthIntradayStepsBase()

        # Assert
        assert health_intraday_steps.timestamp is None
        assert health_intraday_steps.steps is None
        assert health_intraday_steps.activity_type is None
        assert health_intraday_steps.intensity is None
        assert health_intraday_steps.source is None

    def test_health_intraday_steps_with_none_values(self):
        """
        Test HealthIntradayStepsRead schema allows None for optional fields.
        """
        # Arrange & Act
        test_timestamp = datetime(2024, 1, 15, 10, 30, 0)
        health_intraday_steps = health_intraday_steps_schema.HealthIntradayStepsRead(
            id=1,
            user_id=1,
            timestamp=test_timestamp,
            steps=1000,
            activity_type=None,
            intensity=None,
            source=None,
        )

        # Assert
        assert health_intraday_steps.id == 1
        assert health_intraday_steps.steps == 1000
        assert health_intraday_steps.activity_type is None
        assert health_intraday_steps.intensity is None
        assert health_intraday_steps.source is None

    def test_health_intraday_steps_with_integer_steps(self):
        """
        Test HealthIntradayStepsBase schema with integer steps values.
        """
        # Arrange & Act
        health_intraday_steps = health_intraday_steps_schema.HealthIntradayStepsBase(steps=500)

        # Assert
        assert health_intraday_steps.steps == 500
        assert isinstance(health_intraday_steps.steps, int)

    def test_health_intraday_steps_forbid_extra_fields(self):
        """
        Test that HealthIntradayStepsBase schema forbids extra fields.
        """
        # Arrange & Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            health_intraday_steps_schema.HealthIntradayStepsBase(steps=1000, extra_field="not allowed")

        assert "extra_field" in str(exc_info.value)

    def test_health_intraday_steps_from_attributes(self):
        """
        Test HealthIntradayStepsRead schema can be created from ORM model.
        """
        # Arrange
        test_timestamp = datetime(2024, 1, 15, 10, 30, 0)

        class MockORMModel:
            """Mock ORM model for testing."""

            id = 1
            user_id = 1
            timestamp = test_timestamp
            steps = 1000
            activity_type = 1
            intensity = 2
            source = "garmin"

        # Act
        health_intraday_steps = health_intraday_steps_schema.HealthIntradayStepsRead.model_validate(
            MockORMModel()
        )

        # Assert
        assert health_intraday_steps.id == 1
        assert health_intraday_steps.steps == 1000
        assert health_intraday_steps.source == "garmin"

    def test_health_intraday_steps_validate_assignment(self):
        """
        Test that validate_assignment works correctly.
        """
        # Arrange
        test_timestamp = datetime(2024, 1, 15, 10, 30, 0)
        health_intraday_steps = health_intraday_steps_schema.HealthIntradayStepsBase(steps=1000)

        # Act
        health_intraday_steps.steps = 1200
        health_intraday_steps.timestamp = test_timestamp

        # Assert
        assert health_intraday_steps.steps == 1200
        assert health_intraday_steps.timestamp == test_timestamp

    def test_health_intraday_steps_timestamp_validation(self):
        """
        Test timestamp field validation.
        """
        # Arrange & Act
        test_timestamp = datetime(2024, 12, 31, 23, 59, 59)
        health_intraday_steps = health_intraday_steps_schema.HealthIntradayStepsBase(
            timestamp=test_timestamp
        )

        # Assert
        assert health_intraday_steps.timestamp == test_timestamp

    def test_health_intraday_steps_zero_steps(self):
        """
        Test HealthIntradayStepsBase schema accepts zero steps.
        """
        # Arrange & Act
        health_intraday_steps = health_intraday_steps_schema.HealthIntradayStepsBase(steps=0)

        # Assert
        assert health_intraday_steps.steps == 0

    def test_health_intraday_steps_large_steps_value(self):
        """
        Test HealthIntradayStepsBase schema with large steps values.
        """
        # Arrange & Act
        health_intraday_steps = health_intraday_steps_schema.HealthIntradayStepsBase(steps=50000)

        # Assert
        assert health_intraday_steps.steps == 50000

    def test_health_intraday_steps_create_sets_default_timestamp(self):
        """
        Test HealthIntradayStepsCreate automatically sets timestamp if None.
        """
        # Arrange & Act
        health_intraday_steps = health_intraday_steps_schema.HealthIntradayStepsCreate(
            steps=1000
        )

        # Assert
        assert health_intraday_steps.timestamp is not None
        assert isinstance(health_intraday_steps.timestamp, datetime)


class TestSourceEnum:
    """
    Test suite for Source enum.
    """

    def test_source_enum_garmin(self):
        """
        Test Source enum has GARMIN value.
        """
        # Arrange & Act
        source = health_intraday_steps_schema.Source.GARMIN

        # Assert
        assert source.value == "garmin"

    def test_source_enum_use_in_schema(self):
        """
        Test Source enum can be used in HealthIntradayStepsBase schema.
        """
        # Arrange & Act
        health_intraday_steps = health_intraday_steps_schema.HealthIntradayStepsBase(
            source=health_intraday_steps_schema.Source.GARMIN
        )

        # Assert
        assert health_intraday_steps.source == "garmin"

    def test_source_enum_string_value(self):
        """
        Test Source enum accepts string value directly.
        """
        # Arrange & Act
        health_intraday_steps = health_intraday_steps_schema.HealthIntradayStepsBase(source="garmin")

        # Assert
        assert health_intraday_steps.source == "garmin"

    def test_source_enum_invalid_value(self):
        """
        Test Source enum rejects invalid values.
        """
        # Arrange & Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            health_intraday_steps_schema.HealthIntradayStepsBase(source="invalid")

        assert "source" in str(exc_info.value)


class TestHealthIntradayStepsListResponse:
    """
    Test suite for HealthIntradayStepsListResponse schema.
    """

    def test_health_intraday_steps_list_response_valid(self):
        """
        Test HealthIntradayStepsListResponse with valid data.
        """
        # Arrange & Act
        test_timestamp1 = datetime(2024, 1, 15, 10, 30, 0)
        test_timestamp2 = datetime(2024, 1, 15, 11, 30, 0)
        health_intraday_steps1 = health_intraday_steps_schema.HealthIntradayStepsRead(
            id=1,
            user_id=1,
            timestamp=test_timestamp1,
            steps=1000,
        )
        health_intraday_steps2 = health_intraday_steps_schema.HealthIntradayStepsRead(
            id=2,
            user_id=1,
            timestamp=test_timestamp2,
            steps=1200,
        )

        response = health_intraday_steps_schema.HealthIntradayStepsListResponse(
            total=2, records=[health_intraday_steps1, health_intraday_steps2]
        )

        # Assert
        assert response.total == 2
        assert len(response.records) == 2
        assert response.records[0].steps == 1000
        assert response.records[1].steps == 1200

    def test_health_intraday_steps_list_response_empty(self):
        """
        Test HealthIntradayStepsListResponse with empty records.
        """
        # Arrange & Act
        response = health_intraday_steps_schema.HealthIntradayStepsListResponse(total=0, records=[])

        # Assert
        assert response.total == 0
        assert response.records == []

    def test_health_intraday_steps_list_response_forbid_extra(self):
        """
        Test that HealthIntradayStepsListResponse forbids extra fields.
        """
        # Arrange & Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            health_intraday_steps_schema.HealthIntradayStepsListResponse(
                total=1, records=[], extra="not allowed"
            )

        assert "extra" in str(exc_info.value)
