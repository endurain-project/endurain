import pytest
from datetime import datetime
from pydantic import ValidationError

import health.health_intraday_heart_rate.schema as health_intraday_heart_rate_schema


class TestHealthIntradayHeartrateSchema:
    """
    Test suite for HealthIntradayHeartrate Pydantic schema.
    """

    def test_health_intraday_heart_rate_valid_full_data(self):
        """
        Test HealthIntradayHeartrateRead schema with all valid fields.
        """
        # Arrange & Act
        test_timestamp = datetime(2024, 1, 15, 10, 30, 0)
        health_intraday_heart_rate = health_intraday_heart_rate_schema.HealthIntradayHeartrateRead(
            id=1,
            user_id=1,
            timestamp=test_timestamp,
            heart_rate=72,
            source=health_intraday_heart_rate_schema.Source.GARMIN,
        )

        # Assert
        assert health_intraday_heart_rate.id == 1
        assert health_intraday_heart_rate.user_id == 1
        assert health_intraday_heart_rate.timestamp == test_timestamp
        assert health_intraday_heart_rate.heart_rate == 72
        assert health_intraday_heart_rate.source == "garmin"

    def test_health_intraday_heart_rate_minimal_data(self):
        """
        Test HealthIntradayHeartrateBase schema with minimal required fields.
        """
        # Arrange & Act
        health_intraday_heart_rate = health_intraday_heart_rate_schema.HealthIntradayHeartrateBase()

        # Assert
        assert health_intraday_heart_rate.timestamp is None
        assert health_intraday_heart_rate.heart_rate is None
        assert health_intraday_heart_rate.source is None

    def test_health_intraday_heart_rate_with_none_values(self):
        """
        Test HealthIntradayHeartrateRead schema allows None for optional fields.
        """
        # Arrange & Act
        test_timestamp = datetime(2024, 1, 15, 10, 30, 0)
        health_intraday_heart_rate = health_intraday_heart_rate_schema.HealthIntradayHeartrateRead(
            id=1,
            user_id=1,
            timestamp=test_timestamp,
            heart_rate=72,
            source=None,
        )

        # Assert
        assert health_intraday_heart_rate.id == 1
        assert health_intraday_heart_rate.heart_rate == 72
        assert health_intraday_heart_rate.source is None

    def test_health_intraday_heart_rate_with_integer_heart_rate(self):
        """
        Test HealthIntradayHeartrateBase schema with integer heart_rate values.
        """
        # Arrange & Act
        health_intraday_heart_rate = health_intraday_heart_rate_schema.HealthIntradayHeartrateBase(heart_rate=75)

        # Assert
        assert health_intraday_heart_rate.heart_rate == 75
        assert isinstance(health_intraday_heart_rate.heart_rate, int)

    def test_health_intraday_heart_rate_forbid_extra_fields(self):
        """
        Test that HealthIntradayHeartrateBase schema forbids extra fields.
        """
        # Arrange & Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            health_intraday_heart_rate_schema.HealthIntradayHeartrateBase(heart_rate=72, extra_field="not allowed")

        assert "extra_field" in str(exc_info.value)

    def test_health_intraday_heart_rate_from_attributes(self):
        """
        Test HealthIntradayHeartrateRead schema can be created from ORM model.
        """
        # Arrange
        test_timestamp = datetime(2024, 1, 15, 10, 30, 0)

        class MockORMModel:
            """Mock ORM model for testing."""

            id = 1
            user_id = 1
            timestamp = test_timestamp
            heart_rate = 72
            source = "garmin"

        # Act
        health_intraday_heart_rate = health_intraday_heart_rate_schema.HealthIntradayHeartrateRead.model_validate(
            MockORMModel()
        )

        # Assert
        assert health_intraday_heart_rate.id == 1
        assert health_intraday_heart_rate.heart_rate == 72
        assert health_intraday_heart_rate.source == "garmin"

    def test_health_intraday_heart_rate_validate_assignment(self):
        """
        Test that validate_assignment works correctly.
        """
        # Arrange
        test_timestamp = datetime(2024, 1, 15, 10, 30, 0)
        health_intraday_heart_rate = health_intraday_heart_rate_schema.HealthIntradayHeartrateBase(heart_rate=72)

        # Act
        health_intraday_heart_rate.heart_rate = 80
        health_intraday_heart_rate.timestamp = test_timestamp

        # Assert
        assert health_intraday_heart_rate.heart_rate == 80
        assert health_intraday_heart_rate.timestamp == test_timestamp

    def test_health_intraday_heart_rate_timestamp_validation(self):
        """
        Test timestamp field validation.
        """
        # Arrange & Act
        test_timestamp = datetime(2024, 12, 31, 23, 59, 59)
        health_intraday_heart_rate = health_intraday_heart_rate_schema.HealthIntradayHeartrateBase(
            timestamp=test_timestamp
        )

        # Assert
        assert health_intraday_heart_rate.timestamp == test_timestamp

    def test_health_intraday_heart_rate_zero_heart_rate(self):
        """
        Test HealthIntradayHeartrateBase schema accepts zero heart_rate.
        """
        # Arrange & Act
        health_intraday_heart_rate = health_intraday_heart_rate_schema.HealthIntradayHeartrateBase(heart_rate=0)

        # Assert
        assert health_intraday_heart_rate.heart_rate == 0

    def test_health_intraday_heart_rate_large_heart_rate_value(self):
        """
        Test HealthIntradayHeartrateBase schema with large heart_rate values.
        """
        # Arrange & Act
        health_intraday_heart_rate = health_intraday_heart_rate_schema.HealthIntradayHeartrateBase(heart_rate=200)

        # Assert
        assert health_intraday_heart_rate.heart_rate == 200

    def test_health_intraday_heart_rate_create_sets_default_timestamp(self):
        """
        Test HealthIntradayHeartrateCreate automatically sets timestamp if None.
        """
        # Arrange & Act
        health_intraday_heart_rate = health_intraday_heart_rate_schema.HealthIntradayHeartrateCreate(
            heart_rate=72
        )

        # Assert
        assert health_intraday_heart_rate.timestamp is not None
        assert isinstance(health_intraday_heart_rate.timestamp, datetime)


class TestSourceEnum:
    """
    Test suite for Source enum.
    """

    def test_source_enum_garmin(self):
        """
        Test Source enum has GARMIN value.
        """
        # Arrange & Act
        source = health_intraday_heart_rate_schema.Source.GARMIN

        # Assert
        assert source.value == "garmin"

    def test_source_enum_use_in_schema(self):
        """
        Test Source enum can be used in HealthIntradayHeartrateBase schema.
        """
        # Arrange & Act
        health_intraday_heart_rate = health_intraday_heart_rate_schema.HealthIntradayHeartrateBase(
            source=health_intraday_heart_rate_schema.Source.GARMIN
        )

        # Assert
        assert health_intraday_heart_rate.source == "garmin"

    def test_source_enum_string_value(self):
        """
        Test Source enum accepts string value directly.
        """
        # Arrange & Act
        health_intraday_heart_rate = health_intraday_heart_rate_schema.HealthIntradayHeartrateBase(source="garmin")

        # Assert
        assert health_intraday_heart_rate.source == "garmin"

    def test_source_enum_invalid_value(self):
        """
        Test Source enum rejects invalid values.
        """
        # Arrange & Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            health_intraday_heart_rate_schema.HealthIntradayHeartrateBase(source="invalid")

        assert "source" in str(exc_info.value)


class TestHealthIntradayHeartrateListResponse:
    """
    Test suite for HealthIntradayHeartrateListResponse schema.
    """

    def test_health_intraday_heart_rate_list_response_valid(self):
        """
        Test HealthIntradayHeartrateListResponse with valid data.
        """
        # Arrange & Act
        test_timestamp1 = datetime(2024, 1, 15, 10, 30, 0)
        test_timestamp2 = datetime(2024, 1, 15, 11, 30, 0)
        health_intraday_heart_rate1 = health_intraday_heart_rate_schema.HealthIntradayHeartrateRead(
            id=1,
            user_id=1,
            timestamp=test_timestamp1,
            heart_rate=72,
        )
        health_intraday_heart_rate2 = health_intraday_heart_rate_schema.HealthIntradayHeartrateRead(
            id=2,
            user_id=1,
            timestamp=test_timestamp2,
            heart_rate=75,
        )

        response = health_intraday_heart_rate_schema.HealthIntradayHeartrateListResponse(
            records=[health_intraday_heart_rate1, health_intraday_heart_rate2]
        )

        # Assert
        assert len(response.records) == 2
        assert response.records[0].heart_rate == 72
        assert response.records[1].heart_rate == 75

    def test_health_intraday_heart_rate_list_response_empty(self):
        """
        Test HealthIntradayHeartrateListResponse with empty records.
        """
        # Arrange & Act
        response = health_intraday_heart_rate_schema.HealthIntradayHeartrateListResponse(records=[])

        # Assert
        assert response.records == []

    def test_health_intraday_heart_rate_list_response_forbid_extra(self):
        """
        Test that HealthIntradayHeartrateListResponse forbids extra fields.
        """
        # Arrange & Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            health_intraday_heart_rate_schema.HealthIntradayHeartrateListResponse(
                records=[], extra="not allowed"
            )

        assert "extra" in str(exc_info.value)
