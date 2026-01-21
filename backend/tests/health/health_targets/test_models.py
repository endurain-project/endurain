import pytest

import health.health_targets.models as health_targets_models


class TestHealthTargetsModel:
    """
    Test suite for HealthTargets SQLAlchemy model.
    """

    def test_health_targets_model_table_name(self):
        """
        Test HealthTargets model has correct table name.
        """
        # Assert
        assert health_targets_models.HealthTargets.__tablename__ == "health_targets"

    def test_health_targets_model_columns_exist(self):
        """
        Test HealthTargets model has all expected columns.
        """
        # Assert
        assert hasattr(health_targets_models.HealthTargets, "id")
        assert hasattr(health_targets_models.HealthTargets, "user_id")
        assert hasattr(health_targets_models.HealthTargets, "weight")
        assert hasattr(health_targets_models.HealthTargets, "steps")
        assert hasattr(health_targets_models.HealthTargets, "sleep")

    def test_health_targets_model_primary_key(self):
        """
        Test HealthTargets model has correct primary key.
        """
        # Arrange
        id_column = health_targets_models.HealthTargets.id

        # Assert
        assert id_column.primary_key is True
        assert id_column.autoincrement is True

    def test_health_targets_model_foreign_key(self):
        """
        Test HealthTargets model has correct foreign key.
        """
        # Arrange
        user_id_column = health_targets_models.HealthTargets.user_id

        # Assert
        assert user_id_column.nullable is False
        assert user_id_column.index is True
        assert user_id_column.unique is True

    def test_health_targets_model_nullable_fields(self):
        """
        Test HealthTargets model nullable fields.
        """
        # Assert
        assert health_targets_models.HealthTargets.weight.nullable is True
        assert health_targets_models.HealthTargets.steps.nullable is True
        assert health_targets_models.HealthTargets.sleep.nullable is True

    def test_health_targets_model_required_fields(self):
        """
        Test HealthTargets model required fields.
        """
        # Assert
        assert health_targets_models.HealthTargets.user_id.nullable is False

    def test_health_targets_model_column_types(self):
        """
        Test HealthTargets model column types.
        """
        # Assert
        assert health_targets_models.HealthTargets.id.type.python_type == int
        assert health_targets_models.HealthTargets.user_id.type.python_type == int
        assert health_targets_models.HealthTargets.steps.type.python_type == int
        assert health_targets_models.HealthTargets.sleep.type.python_type == int

    def test_health_targets_model_relationship(self):
        """
        Test HealthTargets model has relationship to User.
        """
        # Assert
        assert hasattr(health_targets_models.HealthTargets, "users")

    def test_health_targets_model_weight_precision(self):
        """
        Test HealthTargets model weight field has correct precision.
        """
        # Arrange
        weight_column = health_targets_models.HealthTargets.weight

        # Assert
        assert weight_column.type.precision == 10
        assert weight_column.type.scale == 2
