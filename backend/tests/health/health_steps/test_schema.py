import pytest
from datetime import date as datetime_date
from pydantic import ValidationError

import health.health_steps.schema as health_steps_schema


class TestHealthStepsSchema:
    """
    Test suite for HealthSteps Pydantic schema.
    """

    def test_health_steps_valid_full_data(self):
        """
        Test HealthStepsRead schema with all valid fields.
        """
        # Arrange & Act
        health_steps = health_steps_schema.HealthStepsRead(
            id=1,
            user_id=1,
            date=datetime_date(2024, 1, 15),
            steps=10000,
            source=health_steps_schema.Source.GARMIN,
        )

        # Assert
        assert health_steps.id == 1
        assert health_steps.user_id == 1
        assert health_steps.date == datetime_date(2024, 1, 15)
        assert health_steps.steps == 10000
        assert health_steps.source == "garmin"

    def test_health_steps_minimal_data(self):
        """
        Test HealthStepsBase schema with minimal required fields.
        """
        # Arrange & Act
        health_steps = health_steps_schema.HealthStepsBase()

        # Assert
        assert health_steps.date is None
        assert health_steps.steps is None
        assert health_steps.source is None

    def test_health_steps_with_none_values(self):
        """
        Test HealthStepsRead schema allows None for optional fields.
        """
        # Arrange & Act
        health_steps = health_steps_schema.HealthStepsRead(
            id=1,
            user_id=1,
            date=datetime_date(2024, 1, 15),
            steps=10000,
            source=None,
        )

        # Assert
        assert health_steps.id == 1
        assert health_steps.steps == 10000
        assert health_steps.source is None

    def test_health_steps_with_integer_steps(self):
        """
        Test HealthStepsBase schema with integer steps values.
        """
        # Arrange & Act
        health_steps = health_steps_schema.HealthStepsBase(steps=5000)

        # Assert
        assert health_steps.steps == 5000
        assert isinstance(health_steps.steps, int)

    def test_health_steps_forbid_extra_fields(self):
        """
        Test that HealthStepsBase schema forbids extra fields.
        """
        # Arrange & Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            health_steps_schema.HealthStepsBase(steps=10000, extra_field="not allowed")

        assert "extra_field" in str(exc_info.value)

    def test_health_steps_from_attributes(self):
        """
        Test HealthStepsRead schema can be created from ORM model.
        """

        # Arrange
        class MockORMModel:
            """Mock ORM model for testing."""

            id = 1
            user_id = 1
            date = datetime_date(2024, 1, 15)
            steps = 10000
            source = "garmin"

        # Act
        health_steps = health_steps_schema.HealthStepsRead.model_validate(
            MockORMModel()
        )

        # Assert
        assert health_steps.id == 1
        assert health_steps.steps == 10000
        assert health_steps.source == "garmin"

    def test_health_steps_validate_assignment(self):
        """
        Test that validate_assignment works correctly.
        """
        # Arrange
        health_steps = health_steps_schema.HealthStepsBase(steps=10000)

        # Act
        health_steps.steps = 12000
        health_steps.date = datetime_date(2024, 1, 16)

        # Assert
        assert health_steps.steps == 12000
        assert health_steps.date == datetime_date(2024, 1, 16)

    def test_health_steps_date_validation(self):
        """
        Test date field validation.
        """
        # Arrange & Act
        health_steps = health_steps_schema.HealthStepsBase(
            date=datetime_date(2024, 12, 31)
        )

        # Assert
        assert health_steps.date == datetime_date(2024, 12, 31)

    def test_health_steps_zero_steps(self):
        """
        Test HealthStepsBase schema accepts zero steps.
        """
        # Arrange & Act
        health_steps = health_steps_schema.HealthStepsBase(steps=0)

        # Assert
        assert health_steps.steps == 0

    def test_health_steps_large_steps_value(self):
        """
        Test HealthStepsBase schema with large steps values.
        """
        # Arrange & Act
        health_steps = health_steps_schema.HealthStepsBase(steps=50000)

        # Assert
        assert health_steps.steps == 50000


class TestSourceEnum:
    """
    Test suite for Source enum.
    """

    def test_source_enum_garmin(self):
        """
        Test Source enum has GARMIN value.
        """
        # Arrange & Act
        source = health_steps_schema.Source.GARMIN

        # Assert
        assert source.value == "garmin"

    def test_source_enum_use_in_schema(self):
        """
        Test Source enum can be used in HealthStepsBase schema.
        """
        # Arrange & Act
        health_steps = health_steps_schema.HealthStepsBase(
            source=health_steps_schema.Source.GARMIN
        )

        # Assert
        assert health_steps.source == "garmin"

    def test_source_enum_string_value(self):
        """
        Test Source enum accepts string value directly.
        """
        # Arrange & Act
        health_steps = health_steps_schema.HealthStepsBase(source="garmin")

        # Assert
        assert health_steps.source == "garmin"

    def test_source_enum_invalid_value(self):
        """
        Test Source enum rejects invalid values.
        """
        # Arrange & Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            health_steps_schema.HealthStepsBase(source="invalid")

        assert "source" in str(exc_info.value)


class TestHealthStepsListResponse:
    """
    Test suite for HealthStepsListResponse schema.
    """

    def test_health_steps_list_response_valid(self):
        """
        Test HealthStepsListResponse with valid data.
        """
        # Arrange & Act
        health_steps1 = health_steps_schema.HealthStepsRead(
            id=1,
            user_id=1,
            date=datetime_date(2024, 1, 15),
            steps=10000,
        )
        health_steps2 = health_steps_schema.HealthStepsRead(
            id=2,
            user_id=1,
            date=datetime_date(2024, 1, 16),
            steps=12000,
        )

        response = health_steps_schema.HealthStepsListResponse(
            total=2, records=[health_steps1, health_steps2]
        )

        # Assert
        assert response.total == 2
        assert len(response.records) == 2
        assert response.records[0].steps == 10000
        assert response.records[1].steps == 12000

    def test_health_steps_list_response_empty(self):
        """
        Test HealthStepsListResponse with empty records.
        """
        # Arrange & Act
        response = health_steps_schema.HealthStepsListResponse(total=0, records=[])

        # Assert
        assert response.total == 0
        assert response.records == []

    def test_health_steps_list_response_forbid_extra(self):
        """
        Test that HealthStepsListResponse forbids extra fields.
        """
        # Arrange & Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            health_steps_schema.HealthStepsListResponse(
                total=1, records=[], extra="not allowed"
            )

        assert "extra" in str(exc_info.value)
