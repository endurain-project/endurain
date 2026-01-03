import pytest
from datetime import date as datetime_date
from pydantic import ValidationError

import health.health_weight.schema as health_weight_schema


class TestHealthWeightSchema:
    """
    Test suite for HealthWeight Pydantic schema.
    """

    def test_health_weight_valid_full_data(self):
        """
        Test HealthWeight schema with all valid fields.
        """
        # Arrange & Act
        health_weight = health_weight_schema.HealthWeight(
            id=1,
            user_id=1,
            date=datetime_date(2024, 1, 15),
            weight=75.5,
            bmi=24.5,
            body_fat=18.5,
            body_water=60.0,
            bone_mass=3.5,
            muscle_mass=62.0,
            physique_rating=7,
            visceral_fat=5.0,
            metabolic_age=25,
            source=health_weight_schema.Source.GARMIN,
        )

        # Assert
        assert health_weight.id == 1
        assert health_weight.user_id == 1
        assert health_weight.date == datetime_date(2024, 1, 15)
        assert health_weight.weight == 75.5
        assert health_weight.bmi == 24.5
        assert health_weight.body_fat == 18.5
        assert health_weight.body_water == 60.0
        assert health_weight.bone_mass == 3.5
        assert health_weight.muscle_mass == 62.0
        assert health_weight.physique_rating == 7
        assert health_weight.visceral_fat == 5.0
        assert health_weight.metabolic_age == 25
        assert health_weight.source == "garmin"

    def test_health_weight_minimal_data(self):
        """
        Test HealthWeight schema with minimal required fields.
        """
        # Arrange & Act
        health_weight = health_weight_schema.HealthWeight()

        # Assert
        assert health_weight.id is None
        assert health_weight.user_id is None
        assert health_weight.date is None
        assert health_weight.weight is None
        assert health_weight.bmi is None

    def test_health_weight_with_none_values(self):
        """
        Test HealthWeight schema allows None for optional fields.
        """
        # Arrange & Act
        health_weight = health_weight_schema.HealthWeight(
            id=1,
            user_id=1,
            date=datetime_date(2024, 1, 15),
            weight=75.5,
            bmi=None,
            body_fat=None,
            body_water=None,
            bone_mass=None,
            muscle_mass=None,
            physique_rating=None,
            visceral_fat=None,
            metabolic_age=None,
            source=None,
        )

        # Assert
        assert health_weight.id == 1
        assert health_weight.bmi is None
        assert health_weight.body_fat is None

    def test_health_weight_with_float_values(self):
        """
        Test HealthWeight schema with various float values.
        """
        # Arrange & Act
        health_weight = health_weight_schema.HealthWeight(
            weight=75.567, bmi=24.523, body_fat=18.234
        )

        # Assert
        assert health_weight.weight == 75.567
        assert health_weight.bmi == 24.523
        assert health_weight.body_fat == 18.234

    def test_health_weight_with_integer_values(self):
        """
        Test HealthWeight schema with integer values for float fields.
        """
        # Arrange & Act
        health_weight = health_weight_schema.HealthWeight(
            weight=75, bmi=24, body_fat=18
        )

        # Assert
        assert health_weight.weight == 75
        assert health_weight.bmi == 24
        assert health_weight.body_fat == 18

    def test_health_weight_forbid_extra_fields(self):
        """
        Test that HealthWeight schema forbids extra fields.
        """
        # Arrange & Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            health_weight_schema.HealthWeight(weight=75.5, extra_field="not allowed")

        assert "extra_field" in str(exc_info.value)

    def test_health_weight_from_attributes(self):
        """
        Test HealthWeight schema can be created from ORM model.
        """

        # Arrange
        class MockORMModel:
            """Mock ORM model for testing."""

            id = 1
            user_id = 1
            date = datetime_date(2024, 1, 15)
            weight = 75.5
            bmi = 24.5
            body_fat = 18.5
            body_water = 60.0
            bone_mass = 3.5
            muscle_mass = 62.0
            physique_rating = 7
            visceral_fat = 5.0
            metabolic_age = 25
            source = "garmin"

        # Act
        health_weight = health_weight_schema.HealthWeight.model_validate(MockORMModel())

        # Assert
        assert health_weight.id == 1
        assert health_weight.weight == 75.5
        assert health_weight.source == "garmin"

    def test_health_weight_validate_assignment(self):
        """
        Test that validate_assignment works correctly.
        """
        # Arrange
        health_weight = health_weight_schema.HealthWeight(weight=75.5)

        # Act
        health_weight.weight = 80.0
        health_weight.bmi = 25.5

        # Assert
        assert health_weight.weight == 80.0
        assert health_weight.bmi == 25.5

    def test_health_weight_date_validation(self):
        """
        Test date field validation.
        """
        # Arrange & Act
        health_weight = health_weight_schema.HealthWeight(
            date=datetime_date(2024, 12, 31)
        )

        # Assert
        assert health_weight.date == datetime_date(2024, 12, 31)

    def test_health_weight_physique_rating_integer(self):
        """
        Test physique_rating accepts integer values.
        """
        # Arrange & Act
        health_weight = health_weight_schema.HealthWeight(physique_rating=8)

        # Assert
        assert health_weight.physique_rating == 8
        assert isinstance(health_weight.physique_rating, int)

    def test_health_weight_metabolic_age_integer(self):
        """
        Test metabolic_age accepts integer values.
        """
        # Arrange & Act
        health_weight = health_weight_schema.HealthWeight(metabolic_age=30)

        # Assert
        assert health_weight.metabolic_age == 30
        assert isinstance(health_weight.metabolic_age, int)


class TestSourceEnum:
    """
    Test suite for Source enum.
    """

    def test_source_enum_garmin(self):
        """
        Test Source enum has GARMIN value.
        """
        # Arrange & Act
        source = health_weight_schema.Source.GARMIN

        # Assert
        assert source.value == "garmin"

    def test_source_enum_use_in_schema(self):
        """
        Test Source enum can be used in HealthWeight schema.
        """
        # Arrange & Act
        health_weight = health_weight_schema.HealthWeight(
            source=health_weight_schema.Source.GARMIN
        )

        # Assert
        assert health_weight.source == "garmin"

    def test_source_enum_string_value(self):
        """
        Test Source enum accepts string value directly.
        """
        # Arrange & Act
        health_weight = health_weight_schema.HealthWeight(source="garmin")

        # Assert
        assert health_weight.source == "garmin"

    def test_source_enum_invalid_value(self):
        """
        Test Source enum rejects invalid values.
        """
        # Arrange & Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            health_weight_schema.HealthWeight(source="invalid")

        assert "source" in str(exc_info.value)
