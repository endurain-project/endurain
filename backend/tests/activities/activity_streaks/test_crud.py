"""Tests for weekly streak database access."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import insert
from sqlalchemy.exc import SQLAlchemyError
from tests._helpers.db import create_sqlite_session

import activities.activity.models as activity_models
import activities.activity_streaks.crud as streak_crud
import users.users_streak_settings.schema as streak_settings_schema

# Wednesday 2026-10-14 12:00 UTC; the Monday-based week starts 2026-10-12.
NOW = datetime(2026, 10, 14, 12, tzinfo=UTC)


@pytest.fixture
def sqlite_session():
    """Provide a real in-memory database."""
    session = create_sqlite_session()
    try:
        yield session
    finally:
        session.close()
        session.bind.dispose()


def _activity(start: datetime, **overrides):
    values = {
        "user_id": 1,
        "distance": 1000,
        "activity_type": 1,
        "start_time": start,
        "end_time": start + timedelta(hours=1),
        "created_at": start,
        "timezone": "Europe/Zurich",
        "total_elapsed_time": Decimal("3600"),
        "total_timer_time": Decimal("3600"),
        "visibility": 0,
        "is_hidden": False,
        "hide_start_time": False,
        "hide_location": False,
        "hide_map": False,
        "hide_hr": False,
        "hide_power": False,
        "hide_cadence": False,
        "hide_elevation": False,
        "hide_speed": False,
        "hide_pace": False,
        "hide_laps": False,
        "hide_workout_sets_steps": False,
        "hide_gear": False,
    }
    values.update(overrides)
    return values


def _settings(**kwargs) -> streak_settings_schema.UsersStreakSettingsBase:
    return streak_settings_schema.UsersStreakSettingsBase(**kwargs)


class TestGetWeeklyStreak:
    def test_counts_weeks_and_filters(self, sqlite_session):
        rows = [
            # Current week (Mon 12 Oct)
            _activity(datetime(2026, 10, 13, 7, tzinfo=UTC)),
            # Last week: Sunday 23:30 UTC is Monday in Zurich -> current week
            _activity(datetime(2026, 10, 11, 22, 30, tzinfo=UTC)),
            # Last week proper
            _activity(datetime(2026, 10, 6, 7, tzinfo=UTC)),
            # Two weeks ago: only a walk (type 11) and a hidden run
            _activity(datetime(2026, 9, 29, 7, tzinfo=UTC), activity_type=11),
            _activity(datetime(2026, 9, 30, 7, tzinfo=UTC), is_hidden=True),
            # Another user
            _activity(datetime(2026, 9, 29, 7, tzinfo=UTC), user_id=2),
        ]
        sqlite_session.execute(insert(activity_models.Activity), rows)
        sqlite_session.commit()

        all_types = streak_crud.get_weekly_streak(
            db=sqlite_session,
            user_id=1,
            first_day_of_week="monday",
            settings=_settings(),
            now=NOW,
        )
        assert all_types.current_week_start == date(2026, 10, 12)
        assert all_types.current_week_count == 2
        assert all_types.current_streak == 3
        assert all_types.current_streak_start == date(2026, 9, 28)

        runs_only = streak_crud.get_weekly_streak(
            db=sqlite_session,
            user_id=1,
            first_day_of_week="monday",
            settings=_settings(activity_types=[1]),
            now=NOW,
        )
        assert runs_only.current_streak == 2
        assert runs_only.activity_types == [1]

        two_per_week = streak_crud.get_weekly_streak(
            db=sqlite_session,
            user_id=1,
            first_day_of_week="monday",
            settings=_settings(min_activities_per_week=2),
            now=NOW,
        )
        assert two_per_week.current_streak == 1
        assert two_per_week.current_week_met is True
        assert two_per_week.min_activities_per_week == 2

    def test_no_activities(self, sqlite_session):
        result = streak_crud.get_weekly_streak(
            db=sqlite_session,
            user_id=1,
            first_day_of_week="sunday",
            settings=_settings(),
            now=NOW,
        )
        assert result.current_streak == 0
        assert result.longest_streak == 0
        assert result.current_week_start == date(2026, 10, 11)
        assert len(result.recent_weeks) == 12

    def test_db_error(self, mock_db):
        mock_db.execute.side_effect = SQLAlchemyError("err")
        with pytest.raises(Exception):  # noqa: B017
            streak_crud.get_weekly_streak(
                db=mock_db,
                user_id=1,
                first_day_of_week="monday",
                settings=_settings(),
                now=NOW,
            )
