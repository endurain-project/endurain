"""Tests for streak settings CRUD."""

import pytest

import modules.users.users_streak_settings.crud as streak_settings_crud
import modules.users.users_streak_settings.schema as streak_settings_schema
from tests._helpers.db import create_sqlite_session


@pytest.fixture
def sqlite_session():
    """Provide a real in-memory database."""
    session = create_sqlite_session()
    try:
        yield session
    finally:
        session.close()
        session.bind.dispose()


class TestStreakSettingsCrud:
    def test_defaults_when_missing(self, sqlite_session):
        """Returns defaults without creating a row when nothing is stored."""
        settings = streak_settings_crud.get_streak_settings_by_user_id(1, sqlite_session)
        assert settings.user_id == 1
        assert settings.min_activities_per_week == 1
        assert settings.activity_types is None
        assert settings.show_on_profile is False

    def test_upsert_creates_then_updates(self, sqlite_session):
        """Creates the row on first save and replaces it on the next."""
        created = streak_settings_crud.upsert_streak_settings(
            1,
            streak_settings_schema.UsersStreakSettingsUpdate(
                min_activities_per_week=3, activity_types=[1, 2], show_on_profile=True
            ),
            sqlite_session,
        )
        assert created.min_activities_per_week == 3
        assert created.activity_types == [1, 2]
        assert created.show_on_profile is True

        updated = streak_settings_crud.upsert_streak_settings(
            1,
            streak_settings_schema.UsersStreakSettingsUpdate(min_activities_per_week=2),
            sqlite_session,
        )
        assert updated.min_activities_per_week == 2
        assert updated.activity_types is None
        assert updated.show_on_profile is False

        stored = streak_settings_crud.get_streak_settings_by_user_id(1, sqlite_session)
        assert stored == updated
        # Other users keep defaults
        assert streak_settings_crud.get_streak_settings_by_user_id(2, sqlite_session).min_activities_per_week == 1
