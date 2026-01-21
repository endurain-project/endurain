"""Tests for user default gear database models."""

import pytest

import users.users_default_gear.models as user_default_gear_models


class TestUsersDefaultGearModel:
    """
    Test suite for UsersDefaultGear SQLAlchemy model.
    """

    def test_users_default_gear_model_table_name(self):
        """
        Test UsersDefaultGear model has correct table name.
        """
        # Assert
        assert (
            user_default_gear_models.UsersDefaultGear.__tablename__
            == "users_default_gear"
        )

    def test_users_default_gear_model_columns_exist(self):
        """
        Test UsersDefaultGear model has all expected columns.
        """
        # Assert
        model = user_default_gear_models.UsersDefaultGear
        assert hasattr(model, "id")
        assert hasattr(model, "user_id")
        assert hasattr(model, "run_gear_id")
        assert hasattr(model, "trail_run_gear_id")
        assert hasattr(model, "virtual_run_gear_id")
        assert hasattr(model, "ride_gear_id")
        assert hasattr(model, "gravel_ride_gear_id")
        assert hasattr(model, "mtb_ride_gear_id")
        assert hasattr(model, "virtual_ride_gear_id")
        assert hasattr(model, "ows_gear_id")
        assert hasattr(model, "walk_gear_id")
        assert hasattr(model, "hike_gear_id")
        assert hasattr(model, "tennis_gear_id")
        assert hasattr(model, "alpine_ski_gear_id")
        assert hasattr(model, "nordic_ski_gear_id")
        assert hasattr(model, "snowboard_gear_id")
        assert hasattr(model, "windsurf_gear_id")

    def test_users_default_gear_model_primary_key(self):
        """
        Test UsersDefaultGear model has correct primary key.
        """
        # Arrange
        id_column = user_default_gear_models.UsersDefaultGear.id

        # Assert
        assert id_column.primary_key is True
        assert id_column.autoincrement is True

    def test_users_default_gear_model_foreign_keys(self):
        """
        Test UsersDefaultGear model has correct foreign keys.
        """
        # Arrange
        user_id_column = user_default_gear_models.UsersDefaultGear.user_id

        # Assert - user_id is required and indexed
        assert user_id_column.nullable is False
        assert user_id_column.index is True

    def test_users_default_gear_model_nullable_gear_fields(self):
        """
        Test UsersDefaultGear model has nullable gear ID fields.
        """
        # Assert - all gear_id fields should be nullable
        model = user_default_gear_models.UsersDefaultGear
        assert model.run_gear_id.nullable is True
        assert model.trail_run_gear_id.nullable is True
        assert model.virtual_run_gear_id.nullable is True
        assert model.ride_gear_id.nullable is True
        assert model.gravel_ride_gear_id.nullable is True
        assert model.mtb_ride_gear_id.nullable is True
        assert model.virtual_ride_gear_id.nullable is True
        assert model.ows_gear_id.nullable is True
        assert model.walk_gear_id.nullable is True
        assert model.hike_gear_id.nullable is True
        assert model.tennis_gear_id.nullable is True
        assert model.alpine_ski_gear_id.nullable is True
        assert model.nordic_ski_gear_id.nullable is True
        assert model.snowboard_gear_id.nullable is True
        assert model.windsurf_gear_id.nullable is True

    def test_users_default_gear_model_required_fields(self):
        """
        Test UsersDefaultGear model has correct required fields.
        """
        # Arrange
        model = user_default_gear_models.UsersDefaultGear

        # Assert - only id and user_id are required
        assert model.id.nullable is False
        assert model.user_id.nullable is False

    def test_users_default_gear_model_has_relationships(self):
        """
        Test UsersDefaultGear model has relationship to User and Gear.
        """
        # Assert
        model = user_default_gear_models.UsersDefaultGear
        assert hasattr(model, "users")
        assert hasattr(model, "run_gear")
        assert hasattr(model, "trail_run_gear")
        assert hasattr(model, "virtual_run_gear")
        assert hasattr(model, "ride_gear")
        assert hasattr(model, "gravel_ride_gear")
        assert hasattr(model, "mtb_ride_gear")
        assert hasattr(model, "virtual_ride_gear")
        assert hasattr(model, "ows_gear")
        assert hasattr(model, "walk_gear")
        assert hasattr(model, "hike_gear")
        assert hasattr(model, "tennis_gear")
        assert hasattr(model, "alpine_ski_gear")
        assert hasattr(model, "nordic_ski_gear")
        assert hasattr(model, "snowboard_gear")
        assert hasattr(model, "windsurf_gear")

    def test_users_default_gear_model_gear_id_fields_indexed(self):
        """
        Test UsersDefaultGear model has indexed gear_id fields.
        """
        # Assert - all gear_id fields should be indexed
        model = user_default_gear_models.UsersDefaultGear
        assert model.run_gear_id.index is True
        assert model.trail_run_gear_id.index is True
        assert model.virtual_run_gear_id.index is True
        assert model.ride_gear_id.index is True
        assert model.gravel_ride_gear_id.index is True
        assert model.mtb_ride_gear_id.index is True
        assert model.virtual_ride_gear_id.index is True
        assert model.ows_gear_id.index is True
        assert model.walk_gear_id.index is True
        assert model.hike_gear_id.index is True
        assert model.tennis_gear_id.index is True
        assert model.alpine_ski_gear_id.index is True
        assert model.nordic_ski_gear_id.index is True
        assert model.snowboard_gear_id.index is True
        assert model.windsurf_gear_id.index is True
