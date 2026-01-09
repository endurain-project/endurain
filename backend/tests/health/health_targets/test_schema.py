import pytest
from pydantic import ValidationError

import health.health_targets.schema as health_targets_schema


class TestHealthTargetsSchema:
    """
    Test suite for HealthTargets Pydantic schema.
    """

    def test_health_targets_valid_full_data(self):
        """
        Test HealthTargetsRead schema with all valid fields.
        """
        # Arrange & Act
        health_targets = health_targets_schema.HealthTargetsRead(
            id=1,
            user_id=1,
            weight=75.5,
            steps=10000,
            sleep=28800,
        )

        # Assert
        assert health_targets.id == 1
        assert health_targets.user_id == 1
        assert health_targets.weight == 75.5
        assert health_targets.steps == 10000
        assert health_targets.sleep == 28800

    def test_health_targets_minimal_data(self):
        """
        Test HealthTargetsBase schema with minimal required fields.
        """
        # Arrange & Act
        health_targets = health_targets_schema.HealthTargetsBase()

        # Assert
        assert health_targets.weight is None
        assert health_targets.steps is None
        assert health_targets.sleep is None

    def test_health_targets_with_none_values(self):
        """
        Test HealthTargetsRead schema allows None for optional fields.
        """
        # Arrange & Act
        health_targets = health_targets_schema.HealthTargetsRead(
            id=1,
            user_id=1,
            weight=None,
            steps=None,
            sleep=None,
        )

        # Assert
        assert health_targets.id == 1
        assert health_targets.user_id == 1
        assert health_targets.weight is None
        assert health_targets.steps is None
        assert health_targets.sleep is None

    def test_health_targets_with_float_weight(self):
        """
        Test HealthTargetsBase schema with float weight values.
        """
        # Arrange & Act
        health_targets = health_targets_schema.HealthTargetsBase(weight=75.567)

        # Assert
        assert health_targets.weight == 75.567

    def test_health_targets_with_integer_weight(self):
        """
        Test HealthTargetsBase schema with integer weight values.
        """
        # Arrange & Act
        health_targets = health_targets_schema.HealthTargetsBase(weight=75.0)

        # Assert
        assert health_targets.weight == 75.0

    def test_health_targets_with_integer_steps(self):
        """
        Test HealthTargetsBase schema with integer steps values.
        """
        # Arrange & Act
        health_targets = health_targets_schema.HealthTargetsBase(steps=10000)

        # Assert
        assert health_targets.steps == 10000
        assert isinstance(health_targets.steps, int)

    def test_health_targets_with_integer_sleep(self):
        """
        Test HealthTargetsBase schema with integer sleep values.
        """
        # Arrange & Act
        health_targets = health_targets_schema.HealthTargetsBase(sleep=28800)

        # Assert
        assert health_targets.sleep == 28800
        assert isinstance(health_targets.sleep, int)

    def test_health_targets_forbid_extra_fields(self):
        """
        Test that HealthTargetsBase schema forbids extra fields.
        """
        # Arrange & Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            health_targets_schema.HealthTargetsBase(
                weight=75.5, extra_field="not allowed"
            )

        assert "extra_field" in str(exc_info.value)

    def test_health_targets_from_attributes(self):
        """
        Test HealthTargetsRead schema can be created from ORM model.
        """

        # Arrange
        class MockORMModel:
            """Mock ORM model for testing."""

            id = 1
            user_id = 1
            weight = 75.5
            steps = 10000
            sleep = 28800

        # Act
        health_targets = health_targets_schema.HealthTargetsRead.model_validate(
            MockORMModel()
        )

        # Assert
        assert health_targets.id == 1
        assert health_targets.weight == 75.5
        assert health_targets.steps == 10000

    def test_health_targets_validate_assignment(self):
        """
        Test that validate_assignment works correctly.
        """
        # Arrange
        health_targets = health_targets_schema.HealthTargetsBase(weight=75.5)

        # Act
        health_targets.weight = 80.0
        health_targets.steps = 12000

        # Assert
        assert health_targets.weight == 80.0
        assert health_targets.steps == 12000

    def test_health_targets_zero_steps(self):
        """
        Test HealthTargetsBase schema accepts zero steps.
        """
        # Arrange & Act
        health_targets = health_targets_schema.HealthTargetsBase(steps=0)

        # Assert
        assert health_targets.steps == 0

    def test_health_targets_zero_sleep(self):
        """
        Test HealthTargetsBase schema accepts zero sleep.
        """
        # Arrange & Act
        health_targets = health_targets_schema.HealthTargetsBase(sleep=0)

        # Assert
        assert health_targets.sleep == 0

    def test_health_targets_large_values(self):
        """
        Test HealthTargetsBase schema with large values.
        """
        # Arrange & Act
        health_targets = health_targets_schema.HealthTargetsBase(
            weight=200.5, steps=50000, sleep=86400
        )

        # Assert
        assert health_targets.weight == 200.5
        assert health_targets.steps == 50000
        assert health_targets.sleep == 86400

    def test_health_targets_partial_data(self):
        """
        Test HealthTargetsRead schema with partial data.
        """
        # Arrange & Act
        health_targets = health_targets_schema.HealthTargetsRead(
            id=1,
            user_id=1,
            steps=10000,
        )

        # Assert
        assert health_targets.id == 1
        assert health_targets.user_id == 1
        assert health_targets.steps == 10000
        assert health_targets.weight is None
        assert health_targets.sleep is None
