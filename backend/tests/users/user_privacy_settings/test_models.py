import pytest

import users.user_privacy_settings.models as user_privacy_settings_models


class TestUsersPrivacySettingsModel:
    """
    Test suite for UsersPrivacySettings SQLAlchemy model.
    """

    def test_users_privacy_settings_model_table_name(self):
        """
        Test UsersPrivacySettings model has correct table name.
        """
        # Assert
        assert (
            user_privacy_settings_models.UsersPrivacySettings.__tablename__
            == "users_privacy_settings"
        )

    def test_users_privacy_settings_model_columns_exist(self):
        """
        Test UsersPrivacySettings model has all expected columns.
        """
        # Assert
        model = user_privacy_settings_models.UsersPrivacySettings
        assert hasattr(model, "id")
        assert hasattr(model, "user_id")
        assert hasattr(model, "default_activity_visibility")
        assert hasattr(model, "hide_activity_start_time")
        assert hasattr(model, "hide_activity_location")
        assert hasattr(model, "hide_activity_map")
        assert hasattr(model, "hide_activity_hr")
        assert hasattr(model, "hide_activity_power")
        assert hasattr(model, "hide_activity_cadence")
        assert hasattr(model, "hide_activity_elevation")
        assert hasattr(model, "hide_activity_speed")
        assert hasattr(model, "hide_activity_pace")
        assert hasattr(model, "hide_activity_laps")
        assert hasattr(model, "hide_activity_workout_sets_steps")
        assert hasattr(model, "hide_activity_gear")

    def test_users_privacy_settings_model_primary_key(self):
        """
        Test UsersPrivacySettings model has correct primary key.
        """
        # Arrange
        id_column = user_privacy_settings_models.UsersPrivacySettings.id

        # Assert
        assert id_column.primary_key is True
        assert id_column.autoincrement is True

    def test_users_privacy_settings_model_foreign_key(self):
        """
        Test UsersPrivacySettings model has correct foreign key.
        """
        # Arrange
        user_id_column = user_privacy_settings_models.UsersPrivacySettings.user_id

        # Assert
        assert user_id_column.nullable is False
        assert user_id_column.index is True
        assert user_id_column.unique is True

    def test_users_privacy_settings_model_required_fields(self):
        """
        Test UsersPrivacySettings model required fields.
        """
        # Arrange
        model = user_privacy_settings_models.UsersPrivacySettings

        # Assert
        assert model.user_id.nullable is False
        assert model.default_activity_visibility.nullable is False
        assert model.hide_activity_start_time.nullable is False
        assert model.hide_activity_location.nullable is False
        assert model.hide_activity_map.nullable is False
        assert model.hide_activity_hr.nullable is False
        assert model.hide_activity_power.nullable is False
        assert model.hide_activity_cadence.nullable is False
        assert model.hide_activity_elevation.nullable is False
        assert model.hide_activity_speed.nullable is False
        assert model.hide_activity_pace.nullable is False
        assert model.hide_activity_laps.nullable is False
        assert model.hide_activity_workout_sets_steps.nullable is False
        assert model.hide_activity_gear.nullable is False

    def test_users_privacy_settings_model_column_types(self):
        """
        Test UsersPrivacySettings model column types.
        """
        # Arrange
        model = user_privacy_settings_models.UsersPrivacySettings

        # Assert
        assert model.id.type.python_type == int
        # user_id has ForeignKey, skip type check
        assert model.default_activity_visibility.type.python_type == int
        assert model.hide_activity_start_time.type.python_type == bool
        assert model.hide_activity_location.type.python_type == bool
        assert model.hide_activity_map.type.python_type == bool
        assert model.hide_activity_hr.type.python_type == bool
        assert model.hide_activity_power.type.python_type == bool
        assert model.hide_activity_cadence.type.python_type == bool
        assert model.hide_activity_elevation.type.python_type == bool
        assert model.hide_activity_speed.type.python_type == bool
        assert model.hide_activity_pace.type.python_type == bool
        assert model.hide_activity_laps.type.python_type == bool
        assert model.hide_activity_workout_sets_steps.type.python_type == bool
        assert model.hide_activity_gear.type.python_type == bool

    def test_users_privacy_settings_model_relationship(self):
        """
        Test UsersPrivacySettings model has relationship to User.
        """
        # Assert
        assert hasattr(user_privacy_settings_models.UsersPrivacySettings, "user")

    def test_users_privacy_settings_model_default_visibility(self):
        """
        Test UsersPrivacySettings model has correct default visibility.
        """
        # Arrange
        visibility_column = (
            user_privacy_settings_models.UsersPrivacySettings.default_activity_visibility
        )

        # Assert
        assert visibility_column.default.arg == 0

    def test_users_privacy_settings_model_boolean_defaults(self):
        """
        Test UsersPrivacySettings model boolean fields default to False.
        """
        # Arrange
        model = user_privacy_settings_models.UsersPrivacySettings

        # Assert
        assert model.hide_activity_start_time.default.arg is False
        assert model.hide_activity_location.default.arg is False
        assert model.hide_activity_map.default.arg is False
        assert model.hide_activity_hr.default.arg is False
        assert model.hide_activity_power.default.arg is False
        assert model.hide_activity_cadence.default.arg is False
        assert model.hide_activity_elevation.default.arg is False
        assert model.hide_activity_speed.default.arg is False
        assert model.hide_activity_pace.default.arg is False
        assert model.hide_activity_laps.default.arg is False
        assert model.hide_activity_workout_sets_steps.default.arg is False
        assert model.hide_activity_gear.default.arg is False
