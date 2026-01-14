"""
Tests for users.user_default_gear.schema module.

This module tests Pydantic schemas for user default gear validation.
"""

import pytest
from pydantic import ValidationError

import users.user_default_gear.schema as user_default_gear_schema


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
        # Act
        gear = user_default_gear_schema.UserDefaultGearRead(
            id=1,
            user_id=2,
            run_gear_id=3,
        )

        # Assert
        assert gear.id == 1
        assert gear.user_id == 2
        assert gear.run_gear_id == 3


class TestUserDefaultGearUpdate:
    """Test suite for UserDefaultGearUpdate schema."""

    def test_user_default_gear_update_inherits_from_read(self):
        """Test Update schema inherits from Read."""
        # Act
        gear = user_default_gear_schema.UserDefaultGearUpdate(
            id=1,
            user_id=2,
            run_gear_id=3,
        )

        # Assert
        assert gear.id == 1
        assert gear.user_id == 2
        assert gear.run_gear_id == 3
