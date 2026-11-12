"""
Tests for users.users_default_gear.schema module.

This module tests Pydantic schemas for user default gear validation.
"""

import uuid

import pytest
from pydantic import ValidationError

import modules.users.users_default_gear.schema as user_default_gear_schema


class TestUserDefaultGearBase:
    """Test suite for UserDefaultGearBase schema."""

    def test_user_default_gear_base_all_fields(self):
        """Test schema accepts all valid fields."""
        # Act
        gear = user_default_gear_schema.UserDefaultGearBase(
            run_gear_id=1,
            ride_gear_id=2,
            trail_run_gear_id=3,
        )

        # Assert
        assert gear.run_gear_id == 1
        assert gear.ride_gear_id == 2
        assert gear.trail_run_gear_id == 3

    def test_user_default_gear_base_optional_fields(self):
        """Test all fields are optional."""
        # Act
        gear = user_default_gear_schema.UserDefaultGearBase()

        # Assert
        assert gear.run_gear_id is None
        assert gear.ride_gear_id is None

    def test_user_default_gear_base_invalid_value(self):
        """Test schema rejects invalid gear ID."""
        # Act & Assert
        with pytest.raises(ValidationError):
            user_default_gear_schema.UserDefaultGearBase(run_gear_id=0)


class TestUserDefaultGearRead:
    """Test suite for UserDefaultGearRead schema."""

    def test_user_default_gear_read_required_fields(self):
        """Test schema requires id and user_id."""
        record_id = uuid.uuid4()
        # Act
        gear = user_default_gear_schema.UserDefaultGearRead(
            id=record_id,
            user_id=2,
            run_gear_id=3,
        )

        # Assert
        assert gear.id == record_id
        assert gear.user_id == 2
        assert gear.run_gear_id == 3


class TestUserDefaultGearUpdate:
    """Test suite for UserDefaultGearUpdate schema."""

    def test_update_carries_only_the_gear_assignments(self):
        gear = user_default_gear_schema.UserDefaultGearUpdate(run_gear_id=3)

        assert gear.run_gear_id == 3
        assert not hasattr(gear, "user_id")

    @pytest.mark.parametrize("field", ["id", "user_id"])
    def test_update_refuses_identity_fields(self, field):
        with pytest.raises(ValidationError):
            user_default_gear_schema.UserDefaultGearUpdate(**{field: 1})


class TestDefaultGearIdsFitIntegerColumns:
    """A gear id above the int4 range would reach PostgreSQL and answer 500."""

    @pytest.mark.parametrize("field", list(user_default_gear_schema.UserDefaultGearBase.model_fields))
    def test_an_id_above_int32_is_rejected(self, field):
        with pytest.raises(ValidationError):
            user_default_gear_schema.UserDefaultGearBase(**{field: 2**31})
