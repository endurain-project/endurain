import pytest
from pydantic import ValidationError

import users.users_privacy_settings.schema as user_privacy_settings_schema


class TestActivityVisibilityEnum:
    """
    Test suite for ActivityVisibility enum.
    """

    def test_activity_visibility_public_value(self):
        """
        Test ActivityVisibility.PUBLIC has correct value.
        """
        # Assert
        assert user_privacy_settings_schema.ActivityVisibility.PUBLIC.value == "public"

    def test_activity_visibility_followers_value(self):
        """
        Test ActivityVisibility.FOLLOWERS has correct value.
        """
        # Assert
        assert (
            user_privacy_settings_schema.ActivityVisibility.FOLLOWERS.value
            == "followers"
        )

    def test_activity_visibility_private_value(self):
        """
        Test ActivityVisibility.PRIVATE has correct value.
        """
        # Assert
        assert (
            user_privacy_settings_schema.ActivityVisibility.PRIVATE.value == "private"
        )


class TestUsersPrivacySettingsBaseSchema:
    """
    Test suite for UsersPrivacySettingsBase Pydantic schema.
    """

    def test_base_schema_default_values(self):
        """
        Test UsersPrivacySettingsBase schema has correct defaults.
        """
        # Arrange & Act
        settings = user_privacy_settings_schema.UsersPrivacySettingsBase()

        # Assert - defaults remain as enum objects (not converted due to Pydantic behavior)
        assert (
            settings.default_activity_visibility
            == user_privacy_settings_schema.ActivityVisibility.PUBLIC
        )
        assert settings.hide_activity_start_time is False
        assert settings.hide_activity_location is False
        assert settings.hide_activity_map is False
        assert settings.hide_activity_hr is False
        assert settings.hide_activity_power is False
        assert settings.hide_activity_cadence is False
        assert settings.hide_activity_elevation is False
        assert settings.hide_activity_speed is False
        assert settings.hide_activity_pace is False
        assert settings.hide_activity_laps is False
        assert settings.hide_activity_workout_sets_steps is False
        assert settings.hide_activity_gear is False

    def test_base_schema_with_all_true(self):
        """
        Test UsersPrivacySettingsBase schema with all boolean fields True.
        """
        # Arrange & Act
        settings = user_privacy_settings_schema.UsersPrivacySettingsBase(
            default_activity_visibility=user_privacy_settings_schema.ActivityVisibility.PRIVATE,
            hide_activity_start_time=True,
            hide_activity_location=True,
            hide_activity_map=True,
            hide_activity_hr=True,
            hide_activity_power=True,
            hide_activity_cadence=True,
            hide_activity_elevation=True,
            hide_activity_speed=True,
            hide_activity_pace=True,
            hide_activity_laps=True,
            hide_activity_workout_sets_steps=True,
            hide_activity_gear=True,
        )

        # Assert
        assert (
            settings.default_activity_visibility
            == user_privacy_settings_schema.ActivityVisibility.PRIVATE.value
        )
        assert settings.hide_activity_start_time is True
        assert settings.hide_activity_location is True
        assert settings.hide_activity_map is True
        assert settings.hide_activity_hr is True
        assert settings.hide_activity_power is True
        assert settings.hide_activity_cadence is True
        assert settings.hide_activity_elevation is True
        assert settings.hide_activity_speed is True
        assert settings.hide_activity_pace is True
        assert settings.hide_activity_laps is True
        assert settings.hide_activity_workout_sets_steps is True
        assert settings.hide_activity_gear is True

    def test_base_schema_forbid_extra_fields(self):
        """
        Test that UsersPrivacySettingsBase schema forbids extra fields.
        """
        # Arrange & Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            user_privacy_settings_schema.UsersPrivacySettingsBase(
                extra_field="not allowed"
            )

        assert "extra_field" in str(exc_info.value)

    def test_base_schema_validate_assignment(self):
        """
        Test that validate_assignment works correctly.
        """
        # Arrange
        settings = user_privacy_settings_schema.UsersPrivacySettingsBase()

        # Act
        settings.hide_activity_map = True
        settings.default_activity_visibility = (
            user_privacy_settings_schema.ActivityVisibility.FOLLOWERS
        )

        # Assert
        assert settings.hide_activity_map is True
        assert (
            settings.default_activity_visibility
            == user_privacy_settings_schema.ActivityVisibility.FOLLOWERS.value
        )

    def test_base_schema_from_attributes(self):
        """
        Test UsersPrivacySettingsBase schema can be created from ORM.
        """

        # Arrange
        class MockORMModel:
            """Mock ORM model for testing."""

            default_activity_visibility = "followers"
            hide_activity_start_time = True
            hide_activity_location = False
            hide_activity_map = True
            hide_activity_hr = False
            hide_activity_power = False
            hide_activity_cadence = False
            hide_activity_elevation = False
            hide_activity_speed = False
            hide_activity_pace = False
            hide_activity_laps = False
            hide_activity_workout_sets_steps = False
            hide_activity_gear = False

        # Act
        settings = user_privacy_settings_schema.UsersPrivacySettingsBase.model_validate(
            MockORMModel()
        )

        # Assert
        assert (
            settings.default_activity_visibility
            == user_privacy_settings_schema.ActivityVisibility.FOLLOWERS.value
        )
        assert settings.hide_activity_start_time is True
        assert settings.hide_activity_map is True

    def test_base_schema_visibility_enum_values(self):
        """
        Test UsersPrivacySettingsBase accepts valid visibility values.
        """
        # Arrange & Act
        public = user_privacy_settings_schema.UsersPrivacySettingsBase(
            default_activity_visibility=user_privacy_settings_schema.ActivityVisibility.PUBLIC
        )
        followers = user_privacy_settings_schema.UsersPrivacySettingsBase(
            default_activity_visibility=user_privacy_settings_schema.ActivityVisibility.FOLLOWERS
        )
        private = user_privacy_settings_schema.UsersPrivacySettingsBase(
            default_activity_visibility=user_privacy_settings_schema.ActivityVisibility.PRIVATE
        )

        # Assert
        assert (
            public.default_activity_visibility
            == user_privacy_settings_schema.ActivityVisibility.PUBLIC.value
        )
        assert (
            followers.default_activity_visibility
            == user_privacy_settings_schema.ActivityVisibility.FOLLOWERS.value
        )
        assert (
            private.default_activity_visibility
            == user_privacy_settings_schema.ActivityVisibility.PRIVATE.value
        )

    def test_base_schema_invalid_visibility_value(self):
        """
        Test UsersPrivacySettingsBase rejects invalid visibility values.
        """
        # Arrange & Act & Assert
        with pytest.raises(ValidationError):
            user_privacy_settings_schema.UsersPrivacySettingsBase(
                default_activity_visibility=5
            )

    def test_base_schema_strict_bool_type(self):
        """
        Test UsersPrivacySettingsBase uses StrictBool (no coercion).
        """
        # Arrange & Act & Assert
        with pytest.raises(ValidationError):
            user_privacy_settings_schema.UsersPrivacySettingsBase(
                hide_activity_map="true"
            )


class TestUsersPrivacySettingsReadSchema:
    """
    Test suite for UsersPrivacySettingsRead Pydantic schema.
    """

    def test_read_schema_valid_full_data(self):
        """
        Test UsersPrivacySettingsRead schema with all valid fields.
        """
        # Arrange & Act
        settings = user_privacy_settings_schema.UsersPrivacySettingsRead(
            id=1,
            user_id=1,
            default_activity_visibility=user_privacy_settings_schema.ActivityVisibility.PUBLIC,
            hide_activity_start_time=False,
            hide_activity_location=False,
            hide_activity_map=False,
            hide_activity_hr=False,
            hide_activity_power=False,
            hide_activity_cadence=False,
            hide_activity_elevation=False,
            hide_activity_speed=False,
            hide_activity_pace=False,
            hide_activity_laps=False,
            hide_activity_workout_sets_steps=False,
            hide_activity_gear=False,
        )

        # Assert
        assert settings.id == 1
        assert settings.user_id == 1
        assert (
            settings.default_activity_visibility
            == user_privacy_settings_schema.ActivityVisibility.PUBLIC.value
        )

    def test_read_schema_requires_id(self):
        """
        Test UsersPrivacySettingsRead requires id field.
        """
        # Arrange & Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            user_privacy_settings_schema.UsersPrivacySettingsRead(user_id=1)

        assert "id" in str(exc_info.value)

    def test_read_schema_requires_user_id(self):
        """
        Test UsersPrivacySettingsRead requires user_id field.
        """
        # Arrange & Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            user_privacy_settings_schema.UsersPrivacySettingsRead(id=1)

        assert "user_id" in str(exc_info.value)

    def test_read_schema_from_orm_model(self):
        """
        Test UsersPrivacySettingsRead from ORM model.
        """

        # Arrange
        class MockORMModel:
            """Mock ORM model for testing."""

            id = 1
            user_id = 1
            default_activity_visibility = "private"
            hide_activity_start_time = True
            hide_activity_location = True
            hide_activity_map = False
            hide_activity_hr = False
            hide_activity_power = False
            hide_activity_cadence = False
            hide_activity_elevation = False
            hide_activity_speed = False
            hide_activity_pace = False
            hide_activity_laps = False
            hide_activity_workout_sets_steps = False
            hide_activity_gear = False

        # Act
        settings = user_privacy_settings_schema.UsersPrivacySettingsRead.model_validate(
            MockORMModel()
        )

        # Assert
        assert settings.id == 1
        assert settings.user_id == 1
        assert (
            settings.default_activity_visibility
            == user_privacy_settings_schema.ActivityVisibility.PRIVATE.value
        )
        assert settings.hide_activity_start_time is True


class TestUsersPrivacySettingsUpdateSchema:
    """
    Test suite for UsersPrivacySettingsUpdate Pydantic schema.
    """

    def test_update_schema_partial_update(self):
        """
        Test UsersPrivacySettingsUpdate allows partial updates.
        """
        # Arrange & Act
        settings = user_privacy_settings_schema.UsersPrivacySettingsUpdate(
            hide_activity_map=True
        )

        # Assert
        assert settings.hide_activity_map is True
        assert settings.hide_activity_hr is False

    def test_update_schema_visibility_only(self):
        """
        Test UsersPrivacySettingsUpdate with visibility only.
        """
        # Arrange & Act
        settings = user_privacy_settings_schema.UsersPrivacySettingsUpdate(
            default_activity_visibility=user_privacy_settings_schema.ActivityVisibility.PRIVATE
        )

        # Assert
        assert (
            settings.default_activity_visibility
            == user_privacy_settings_schema.ActivityVisibility.PRIVATE.value
        )

    def test_update_schema_all_fields(self):
        """
        Test UsersPrivacySettingsUpdate with all fields.
        """
        # Arrange & Act
        settings = user_privacy_settings_schema.UsersPrivacySettingsUpdate(
            default_activity_visibility=user_privacy_settings_schema.ActivityVisibility.FOLLOWERS,
            hide_activity_start_time=True,
            hide_activity_location=True,
            hide_activity_map=True,
            hide_activity_hr=True,
            hide_activity_power=True,
            hide_activity_cadence=True,
            hide_activity_elevation=True,
            hide_activity_speed=True,
            hide_activity_pace=True,
            hide_activity_laps=True,
            hide_activity_workout_sets_steps=True,
            hide_activity_gear=True,
        )

        # Assert
        assert (
            settings.default_activity_visibility
            == user_privacy_settings_schema.ActivityVisibility.FOLLOWERS.value
        )
        assert settings.hide_activity_start_time is True
        assert settings.hide_activity_gear is True


class TestUsersPrivacySettingsCreateSchema:
    """
    Test suite for UsersPrivacySettingsCreate Pydantic schema.
    """

    def test_create_schema_defaults(self):
        """
        Test UsersPrivacySettingsCreate has correct defaults.
        """
        # Arrange & Act
        settings = user_privacy_settings_schema.UsersPrivacySettingsCreate()

        # Assert - defaults remain as enum objects (not converted due to Pydantic behavior)
        assert (
            settings.default_activity_visibility
            == user_privacy_settings_schema.ActivityVisibility.PUBLIC
        )
        assert settings.hide_activity_start_time is False

    def test_create_schema_custom_values(self):
        """
        Test UsersPrivacySettingsCreate with custom values.
        """
        # Arrange & Act
        settings = user_privacy_settings_schema.UsersPrivacySettingsCreate(
            default_activity_visibility=user_privacy_settings_schema.ActivityVisibility.PRIVATE,
            hide_activity_map=True,
        )

        # Assert
        assert (
            settings.default_activity_visibility
            == user_privacy_settings_schema.ActivityVisibility.PRIVATE.value
        )
        assert settings.hide_activity_map is True
