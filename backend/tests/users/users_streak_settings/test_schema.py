"""Tests for streak settings schemas."""

import pytest
from pydantic import ValidationError

import users.users_streak_settings.schema as streak_settings_schema


class TestUsersStreakSettingsUpdate:
    def test_defaults(self):
        """Applies defaults when no fields are given."""
        settings = streak_settings_schema.UsersStreakSettingsUpdate()
        assert settings.min_activities_per_week == 1
        assert settings.activity_types is None
        assert settings.show_on_profile is False

    def test_activity_types_normalised(self):
        """Sorts and de-duplicates activity type IDs."""
        settings = streak_settings_schema.UsersStreakSettingsUpdate(activity_types=[4, 1, 4])
        assert settings.activity_types == [1, 4]

    def test_empty_activity_types_means_all(self):
        """Treats an empty type list as all types."""
        settings = streak_settings_schema.UsersStreakSettingsUpdate(activity_types=[])
        assert settings.activity_types is None

    def test_unknown_activity_type_rejected(self):
        """Rejects unknown activity type IDs."""
        with pytest.raises(ValidationError):
            streak_settings_schema.UsersStreakSettingsUpdate(activity_types=[1, 9999])

    @pytest.mark.parametrize("value", [0, -1, streak_settings_schema.MIN_ACTIVITIES_PER_WEEK_LIMIT + 1])
    def test_min_activities_bounds(self, value):
        """Rejects weekly targets outside 1..limit."""
        with pytest.raises(ValidationError):
            streak_settings_schema.UsersStreakSettingsUpdate(min_activities_per_week=value)

    def test_extra_fields_forbidden(self):
        """Rejects unknown fields such as user_id."""
        with pytest.raises(ValidationError):
            streak_settings_schema.UsersStreakSettingsUpdate(user_id=3)
