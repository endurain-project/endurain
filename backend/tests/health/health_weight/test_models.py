import pytest
from datetime import date as datetime_date
from decimal import Decimal

import health.health_weight.models as health_weight_models


class TestHealthWeightModel:
    """
    Test suite for HealthWeight SQLAlchemy model.
    """

    def test_health_weight_model_table_name(self):
        """
        Test HealthWeight model has correct table name.
        """
        # Assert
        assert health_weight_models.HealthWeight.__tablename__ == "health_weight"

    def test_health_weight_model_columns_exist(self):
        """
        Test HealthWeight model has all expected columns.
        """
        # Assert
        assert hasattr(health_weight_models.HealthWeight, "id")
        assert hasattr(health_weight_models.HealthWeight, "user_id")
        assert hasattr(health_weight_models.HealthWeight, "date")
        assert hasattr(health_weight_models.HealthWeight, "weight")
        assert hasattr(health_weight_models.HealthWeight, "bmi")
        assert hasattr(health_weight_models.HealthWeight, "body_fat")
        assert hasattr(health_weight_models.HealthWeight, "body_water")
        assert hasattr(health_weight_models.HealthWeight, "bone_mass")
        assert hasattr(health_weight_models.HealthWeight, "muscle_mass")
        assert hasattr(health_weight_models.HealthWeight, "physique_rating")
        assert hasattr(health_weight_models.HealthWeight, "visceral_fat")
        assert hasattr(health_weight_models.HealthWeight, "metabolic_age")
        assert hasattr(health_weight_models.HealthWeight, "source")

    def test_health_weight_model_primary_key(self):
        """
        Test HealthWeight model has correct primary key.
        """
        # Arrange
        id_column = health_weight_models.HealthWeight.id

        # Assert
        assert id_column.primary_key is True
        assert id_column.autoincrement is True

    def test_health_weight_model_foreign_key(self):
        """
        Test HealthWeight model has correct foreign key.
        """
        # Arrange
        user_id_column = health_weight_models.HealthWeight.user_id

        # Assert
        assert user_id_column.nullable is False
        assert user_id_column.index is True

    def test_health_weight_model_nullable_fields(self):
        """
        Test HealthWeight model nullable fields.
        """
        # Assert
        assert health_weight_models.HealthWeight.bmi.nullable is True
        assert health_weight_models.HealthWeight.body_fat.nullable is True
        assert health_weight_models.HealthWeight.body_water.nullable is True
        assert health_weight_models.HealthWeight.bone_mass.nullable is True
        assert health_weight_models.HealthWeight.muscle_mass.nullable is True
        assert health_weight_models.HealthWeight.physique_rating.nullable is True
        assert health_weight_models.HealthWeight.visceral_fat.nullable is True
        assert health_weight_models.HealthWeight.metabolic_age.nullable is True
        assert health_weight_models.HealthWeight.source.nullable is True

    def test_health_weight_model_required_fields(self):
        """
        Test HealthWeight model required fields.
        """
        # Assert
        assert health_weight_models.HealthWeight.user_id.nullable is False
        assert health_weight_models.HealthWeight.date.nullable is False
        assert health_weight_models.HealthWeight.weight.nullable is False

    def test_health_weight_model_column_types(self):
        """
        Test HealthWeight model column types.
        """
        # Assert
        assert health_weight_models.HealthWeight.id.type.python_type == int
        assert health_weight_models.HealthWeight.user_id.type.python_type == int
        assert health_weight_models.HealthWeight.date.type.python_type == datetime_date
        assert health_weight_models.HealthWeight.physique_rating.type.python_type == int
        assert health_weight_models.HealthWeight.metabolic_age.type.python_type == int
        assert health_weight_models.HealthWeight.source.type.python_type == str

    def test_health_weight_model_decimal_precision(self):
        """
        Test HealthWeight model decimal fields precision.
        """
        # Assert
        assert health_weight_models.HealthWeight.weight.type.precision == 10
        assert health_weight_models.HealthWeight.weight.type.scale == 2
        assert health_weight_models.HealthWeight.bmi.type.precision == 10
        assert health_weight_models.HealthWeight.bmi.type.scale == 2
        assert health_weight_models.HealthWeight.body_fat.type.precision == 10
        assert health_weight_models.HealthWeight.body_fat.type.scale == 2

    def test_health_weight_model_has_user_relationship(self):
        """
        Test HealthWeight model has user relationship.
        """
        # Assert
        assert hasattr(health_weight_models.HealthWeight, "users")

    def test_health_weight_model_docstring(self):
        """
        Test HealthWeight model has docstring.
        """
        # Assert
        assert health_weight_models.HealthWeight.__doc__ is not None
        assert "health weight" in health_weight_models.HealthWeight.__doc__.lower()
