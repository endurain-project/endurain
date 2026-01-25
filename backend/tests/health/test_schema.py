import pytest
from datetime import datetime
from pydantic import ValidationError

import health.schema as health_schema
import health.health_intraday_steps.schema as health_intraday_steps_schema
import health.health_intraday_heart_rate.schema as health_intraday_heart_rate_schema


class TestHealthImportResponse:
    """
    Test suite for HealthImportResponse Pydantic schema.
    """

    def test_health_import_response_valid_data(self):
        """
        Test HealthImportResponse schema with valid data.
        """
        # Arrange
        test_timestamp = datetime(2024, 1, 15, 10, 30, 0)
        mock_steps = health_intraday_steps_schema.HealthIntradayStepsRead(
            id=1,
            user_id=1,
            timestamp=test_timestamp,
            steps=1000,
            source="garmin",
        )
        mock_heart_rate = health_intraday_heart_rate_schema.HealthIntradayHeartrateRead(
            id=1,
            user_id=1,
            timestamp=test_timestamp,
            heart_rate=75,
            source="garmin",
        )

        # Act
        response = health_schema.HealthImportResponse(
            created_intraday_step_records=[mock_steps],
            created_intraday_heart_rate_records=[mock_heart_rate],
        )

        # Assert
        assert len(response.created_intraday_step_records) == 1
        assert len(response.created_intraday_heart_rate_records) == 1
        assert response.created_intraday_step_records[0].id == 1
        assert response.created_intraday_heart_rate_records[0].id == 1

    def test_health_import_response_empty_lists(self):
        """
        Test HealthImportResponse schema with empty lists.
        """
        # Act
        response = health_schema.HealthImportResponse(
            created_intraday_step_records=[],
            created_intraday_heart_rate_records=[],
        )

        # Assert
        assert len(response.created_intraday_step_records) == 0
        assert len(response.created_intraday_heart_rate_records) == 0

    def test_health_import_response_multiple_records(self):
        """
        Test HealthImportResponse schema with multiple records.
        """
        # Arrange
        test_timestamp1 = datetime(2024, 1, 15, 10, 30, 0)
        test_timestamp2 = datetime(2024, 1, 15, 11, 30, 0)
        mock_steps1 = health_intraday_steps_schema.HealthIntradayStepsRead(
            id=1,
            user_id=1,
            timestamp=test_timestamp1,
            steps=1000,
            source="garmin",
        )
        mock_steps2 = health_intraday_steps_schema.HealthIntradayStepsRead(
            id=2,
            user_id=1,
            timestamp=test_timestamp2,
            steps=1200,
            source="garmin",
        )
        mock_heart_rate1 = health_intraday_heart_rate_schema.HealthIntradayHeartrateRead(
            id=1,
            user_id=1,
            timestamp=test_timestamp1,
            heart_rate=75,
            source="garmin",
        )
        mock_heart_rate2 = health_intraday_heart_rate_schema.HealthIntradayHeartrateRead(
            id=2,
            user_id=1,
            timestamp=test_timestamp2,
            heart_rate=80,
            source="garmin",
        )

        # Act
        response = health_schema.HealthImportResponse(
            created_intraday_step_records=[mock_steps1, mock_steps2],
            created_intraday_heart_rate_records=[mock_heart_rate1, mock_heart_rate2],
        )

        # Assert
        assert len(response.created_intraday_step_records) == 2
        assert len(response.created_intraday_heart_rate_records) == 2

    def test_health_import_response_forbid_extra_fields(self):
        """
        Test that HealthImportResponse schema forbids extra fields.
        """
        # Arrange
        test_timestamp = datetime(2024, 1, 15, 10, 30, 0)
        mock_steps = health_intraday_steps_schema.HealthIntradayStepsRead(
            id=1,
            user_id=1,
            timestamp=test_timestamp,
            steps=1000,
            source="garmin",
        )
        mock_heart_rate = health_intraday_heart_rate_schema.HealthIntradayHeartrateRead(
            id=1,
            user_id=1,
            timestamp=test_timestamp,
            heart_rate=75,
            source="garmin",
        )

        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            health_schema.HealthImportResponse(
                created_intraday_step_records=[mock_steps],
                created_intraday_heart_rate_records=[mock_heart_rate],
                extra_field="not allowed",
            )

        assert "extra_field" in str(exc_info.value)

    def test_health_import_response_missing_required_fields(self):
        """
        Test that HealthImportResponse schema requires all fields.
        """
        # Arrange
        test_timestamp = datetime(2024, 1, 15, 10, 30, 0)
        mock_steps = health_intraday_steps_schema.HealthIntradayStepsRead(
            id=1,
            user_id=1,
            timestamp=test_timestamp,
            steps=1000,
            source="garmin",
        )

        # Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            health_schema.HealthImportResponse(
                created_intraday_step_records=[mock_steps],
            )

        assert "created_intraday_heart_rate_records" in str(exc_info.value)

    def test_health_import_response_from_attributes(self):
        """
        Test HealthImportResponse schema can be created from ORM model.
        """
        # Arrange
        class MockORMModel:
            """Mock ORM model for testing."""

            created_intraday_step_records = []
            created_intraday_heart_rate_records = []

        # Act
        response = health_schema.HealthImportResponse.model_validate(
            MockORMModel()
        )

        # Assert
        assert isinstance(response, health_schema.HealthImportResponse)
        assert response.created_intraday_step_records == []
        assert response.created_intraday_heart_rate_records == []

    def test_health_import_response_validate_assignment(self):
        """
        Test that validate_assignment works correctly.
        """
        # Arrange
        test_timestamp = datetime(2024, 1, 15, 10, 30, 0)
        mock_steps1 = health_intraday_steps_schema.HealthIntradayStepsRead(
            id=1,
            user_id=1,
            timestamp=test_timestamp,
            steps=1000,
            source="garmin",
        )
        mock_steps2 = health_intraday_steps_schema.HealthIntradayStepsRead(
            id=2,
            user_id=1,
            timestamp=test_timestamp,
            steps=1200,
            source="garmin",
        )
        mock_heart_rate = health_intraday_heart_rate_schema.HealthIntradayHeartrateRead(
            id=1,
            user_id=1,
            timestamp=test_timestamp,
            heart_rate=75,
            source="garmin",
        )

        response = health_schema.HealthImportResponse(
            created_intraday_step_records=[mock_steps1],
            created_intraday_heart_rate_records=[mock_heart_rate],
        )

        # Act
        response.created_intraday_step_records = [mock_steps1, mock_steps2]

        # Assert
        assert len(response.created_intraday_step_records) == 2
        assert len(response.created_intraday_heart_rate_records) == 1
