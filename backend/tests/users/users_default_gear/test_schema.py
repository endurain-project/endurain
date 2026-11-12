"""
Tests for users.users_default_gear.schema module.

This module tests Pydantic schemas for user default gear validation.
"""

import uuid

import pytest
from pydantic import ValidationError

import modules.users.users_default_gear.schema as user_default_gear_schema

_GEAR_A = uuid.uuid4()
_GEAR_B = uuid.uuid4()
_GEAR_C = uuid.uuid4()


class TestUserDefaultGearBase:
    """Test suite for UserDefaultGearBase schema."""

    def test_user_default_gear_base_all_fields(self):
        """Test schema accepts all valid fields."""
        # Act
        gear = user_default_gear_schema.UserDefaultGearBase(
            run_gear_id=_GEAR_A,
            ride_gear_id=_GEAR_B,
            trail_run_gear_id=_GEAR_C,
        )

        # Assert
        assert gear.run_gear_id == _GEAR_A
        assert gear.ride_gear_id == _GEAR_B
        assert gear.trail_run_gear_id == _GEAR_C

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
            user_default_gear_schema.UserDefaultGearBase(run_gear_id="not-a-uuid")


class TestUserDefaultGearRead:
    """Test suite for UserDefaultGearRead schema."""

    def test_user_default_gear_read_required_fields(self):
        """Test schema requires id and user_id."""
        record_id = uuid.uuid4()
        # Act
        gear = user_default_gear_schema.UserDefaultGearRead(
            id=record_id,
            user_id=2,
            run_gear_id=_GEAR_C,
        )

        # Assert
        assert gear.id == record_id
        assert gear.user_id == 2
        assert gear.run_gear_id == _GEAR_C


class TestUserDefaultGearUpdate:
    """Test suite for UserDefaultGearUpdate schema."""

    def test_update_carries_only_the_gear_assignments(self):
        gear = user_default_gear_schema.UserDefaultGearUpdate(run_gear_id=_GEAR_C)

        assert gear.run_gear_id == _GEAR_C
        assert not hasattr(gear, "user_id")

    @pytest.mark.parametrize("field", ["id", "user_id"])
    def test_update_refuses_identity_fields(self, field):
        with pytest.raises(ValidationError):
            user_default_gear_schema.UserDefaultGearUpdate(**{field: 1})


class TestDefaultGearIdsAreUuids:
    """A gear id that is not a UUID is refused before it reaches PostgreSQL."""

    @pytest.mark.parametrize("field", list(user_default_gear_schema.UserDefaultGearBase.model_fields))
    @pytest.mark.parametrize("value", [1, "1", "not-a-uuid"])
    def test_a_non_uuid_id_is_rejected(self, field, value):
        with pytest.raises(ValidationError):
            user_default_gear_schema.UserDefaultGearBase(**{field: value})
