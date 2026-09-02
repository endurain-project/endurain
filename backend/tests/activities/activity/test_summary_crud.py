from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import insert
from sqlalchemy.exc import SQLAlchemyError
from tests._helpers.db import create_sqlite_session, setup_mock_execute
from tests._helpers.models import mock_model


@pytest.fixture
def sqlite_session():
    """Provide a real in-memory database for period grouping tests."""
    session = create_sqlite_session()
    connection = session.connection().connection.driver_connection
    connection.create_function("timezone", 2, lambda _timezone, value: value)
    try:
        yield session
    finally:
        session.close()
        session.bind.dispose()


class TestGetWeeklySummary:
    def test_success(self, mock_db):
        from datetime import datetime

        import modules.activities.activity.models as am
        import modules.activities.activity.summary_crud as crud

        setup_mock_execute(mock_db, return_scalars_all=[mock_model(am.Activity, id=1, user_id=1)])
        r = crud.get_weekly_summary(
            user_id=1,
            target_date=datetime(2024, 1, 15),
            first_day_of_week="monday",
            db=mock_db,
        )
        assert r is not None

    def test_empty(self, mock_db):
        from datetime import datetime

        import modules.activities.activity.summary_crud as crud

        setup_mock_execute(mock_db, return_scalars_all=[])
        r = crud.get_weekly_summary(
            user_id=1,
            target_date=datetime(2024, 1, 15),
            first_day_of_week="monday",
            db=mock_db,
        )
        assert r is not None

    def test_postgresql(self, mock_db):
        from datetime import datetime

        import modules.activities.activity.summary_crud as crud

        engine_mock = MagicMock()
        engine_mock.dialect.name = "postgresql"
        mock_db.get_bind.return_value = engine_mock

        row = MagicMock()
        row.day_of_week = 3
        row.total_distance = 10000
        row.total_duration = 3600.0
        row.total_elevation_gain = 100
        row.total_calories = 500
        row.activity_count = 1
        mock_db.execute.return_value.all.side_effect = [
            [row],
            [],
        ]
        r = crud.get_weekly_summary(
            user_id=1,
            target_date=datetime(2024, 1, 15),
            first_day_of_week="monday",
            db=mock_db,
        )
        assert r.activity_count == 1

    def test_sunday_first_breakdown_order(self, mock_db):
        """Test weekly rows begin with the configured first day."""
        import modules.activities.activity.summary_crud as crud

        mock_db.execute.return_value.all.side_effect = [[], []]

        result = crud.get_weekly_summary(
            user_id=1,
            target_date=date(2024, 1, 15),
            first_day_of_week="sunday",
            db=mock_db,
        )

        assert [row.day_of_week for row in result.breakdown] == [6, 0, 1, 2, 3, 4, 5]

    def test_with_type_filter(self, mock_db):
        from datetime import datetime

        import modules.activities.activity.summary_crud as crud

        row = MagicMock()
        row.day_of_week = 1
        row.total_distance = 5000
        row.total_duration = 1800.0
        row.total_elevation_gain = 50
        row.total_calories = 250
        row.activity_count = 1
        mock_db.execute.return_value.all.side_effect = [
            [row],
            [],
        ]
        r = crud.get_weekly_summary(
            user_id=1,
            target_date=datetime(2024, 1, 15),
            first_day_of_week="monday",
            activity_type="running",
            db=mock_db,
        )
        assert r.activity_count == 1

    def test_db_error(self, mock_db):
        from datetime import datetime

        import modules.activities.activity.summary_crud as crud

        mock_db.execute.side_effect = SQLAlchemyError("err")
        with pytest.raises(SQLAlchemyError):
            crud.get_weekly_summary(
                user_id=1,
                target_date=datetime(2024, 1, 15),
                first_day_of_week="monday",
                db=mock_db,
            )


class TestGetMonthlySummary:
    def test_success(self, mock_db):
        from datetime import datetime

        import modules.activities.activity.summary_crud as crud

        row = MagicMock()
        row.week_number = 3
        row.total_distance = 20000
        row.total_duration = 7200.0
        row.total_elevation_gain = 200
        row.total_calories = 1000
        row.activity_count = 2
        mock_db.execute.return_value.all.side_effect = [
            [row],
            [],
        ]
        r = crud.get_monthly_summary(
            user_id=1,
            target_date=datetime(2024, 1, 15),
            first_day_of_week="monday",
            db=mock_db,
        )
        assert r.activity_count == 2

    def test_empty(self, mock_db):
        from datetime import datetime

        import modules.activities.activity.summary_crud as crud

        mock_db.execute.return_value.all.side_effect = [
            [],
            [],
        ]
        r = crud.get_monthly_summary(
            user_id=1,
            target_date=datetime(2024, 1, 15),
            first_day_of_week="monday",
            db=mock_db,
        )
        assert r.activity_count == 0

    def test_sunday_start_splits_monthly_buckets_on_sunday(self, sqlite_session):
        """Test monthly week buckets roll over on the configured day."""
        import modules.activities.activity.models as activity_models
        import modules.activities.activity.summary_crud as crud

        base_values = {
            "user_id": 1,
            "distance": 1000,
            "activity_type": 1,
            "end_time": datetime(2024, 1, 6, 9, tzinfo=UTC),
            "created_at": datetime(2024, 1, 6, 8, tzinfo=UTC),
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
        sqlite_session.execute(
            insert(activity_models.Activity),
            [
                {
                    **base_values,
                    "start_time": datetime(2024, 1, 6, 8, tzinfo=UTC),
                },
                {
                    **base_values,
                    "start_time": datetime(2024, 1, 7, 8, tzinfo=UTC),
                    "end_time": datetime(2024, 1, 7, 9, tzinfo=UTC),
                    "created_at": datetime(2024, 1, 7, 8, tzinfo=UTC),
                },
            ],
        )
        sqlite_session.commit()

        result = crud.get_monthly_summary(
            db=sqlite_session,
            user_id=1,
            target_date=date(2024, 1, 15),
            first_day_of_week="sunday",
        )

        assert [(row.week_number, row.activity_count) for row in result.breakdown] == [(1, 1), (2, 1)]

    def test_db_error(self, mock_db):
        from datetime import datetime

        import modules.activities.activity.summary_crud as crud

        mock_db.execute.side_effect = SQLAlchemyError("err")
        with pytest.raises(SQLAlchemyError):
            crud.get_monthly_summary(
                user_id=1,
                target_date=datetime(2024, 1, 15),
                first_day_of_week="monday",
                db=mock_db,
            )


class TestGetYearlySummary:
    def test_success(self, mock_db):
        import modules.activities.activity.summary_crud as crud

        row = MagicMock()
        row.month_number = 6
        row.total_distance = 50000
        row.total_duration = 18000.0
        row.total_elevation_gain = 500
        row.total_calories = 2500
        row.activity_count = 5
        mock_db.execute.return_value.all.side_effect = [
            [row],
            [],
        ]
        r = crud.get_yearly_summary(user_id=1, year=2024, db=mock_db)
        assert r.activity_count == 5
        assert len(r.breakdown) == 12

    def test_empty(self, mock_db):
        import modules.activities.activity.summary_crud as crud

        mock_db.execute.return_value.all.side_effect = [
            [],
            [],
        ]
        r = crud.get_yearly_summary(user_id=1, year=2024, db=mock_db)
        assert r.activity_count == 0

    def test_with_type_filter(self, mock_db):
        import modules.activities.activity.summary_crud as crud

        row = MagicMock()
        row.month_number = 1
        row.total_distance = 10000
        row.total_duration = 3600.0
        row.total_elevation_gain = 100
        row.total_calories = 500
        row.activity_count = 1
        mock_db.execute.return_value.all.side_effect = [
            [row],
            [],
        ]
        r = crud.get_yearly_summary(user_id=1, year=2024, activity_type="cycling", db=mock_db)
        assert r.activity_count == 1

    def test_db_error(self, mock_db):
        import modules.activities.activity.summary_crud as crud

        mock_db.execute.side_effect = SQLAlchemyError("err")
        with pytest.raises(SQLAlchemyError):
            crud.get_yearly_summary(user_id=1, year=2024, db=mock_db)


class TestGetLifetimeSummary:
    def test_success(self, mock_db):
        import modules.activities.activity.summary_crud as crud

        totals_row = MagicMock()
        totals_row.total_distance = 100000.0
        totals_row.total_duration = 36000.0
        totals_row.total_elevation_gain = 1000.0
        totals_row.total_calories = 5000.0
        totals_row.activity_count = 10

        yearly_row = MagicMock()
        yearly_row.year_number = 2024
        yearly_row.total_distance = 50000.0
        yearly_row.total_duration = 18000.0
        yearly_row.total_elevation_gain = 500.0
        yearly_row.total_calories = 2500.0
        yearly_row.activity_count = 5

        mock_db.execute.return_value.one_or_none.return_value = totals_row
        mock_db.execute.return_value.all.side_effect = [
            [yearly_row],
            [],
        ]
        r = crud.get_lifetime_summary(user_id=1, db=mock_db)
        assert r.activity_count == 10
        assert len(r.breakdown) == 1

    def test_no_totals(self, mock_db):
        import modules.activities.activity.summary_crud as crud

        mock_db.execute.return_value.one_or_none.return_value = None
        r = crud.get_lifetime_summary(user_id=1, db=mock_db)
        assert r.activity_count == 0
        assert r.total_distance == 0.0
        assert r.breakdown == []

    def test_with_type_filter(self, mock_db):
        import modules.activities.activity.summary_crud as crud

        totals_row = MagicMock()
        totals_row.total_distance = 50000.0
        totals_row.total_duration = 18000.0
        totals_row.total_elevation_gain = 500.0
        totals_row.total_calories = 2500.0
        totals_row.activity_count = 5

        yearly_row = MagicMock()
        yearly_row.year_number = 2024
        yearly_row.total_distance = 50000.0
        yearly_row.total_duration = 18000.0
        yearly_row.total_elevation_gain = 500.0
        yearly_row.total_calories = 2500.0
        yearly_row.activity_count = 5

        mock_db.execute.return_value.one_or_none.return_value = totals_row
        mock_db.execute.return_value.all.side_effect = [
            [yearly_row],
            [],
        ]
        r = crud.get_lifetime_summary(user_id=1, activity_type="running", db=mock_db)
        assert r.activity_count == 5

    def test_db_error(self, mock_db):
        import modules.activities.activity.summary_crud as crud

        mock_db.execute.side_effect = SQLAlchemyError("err")
        with pytest.raises(SQLAlchemyError):
            crud.get_lifetime_summary(user_id=1, db=mock_db)


class TestApplyActivityTypeFilter:
    @patch("modules.activities.activity.summary_crud.ACTIVITY_NAME_TO_ID", {"running": 1})
    def test_no_filter(self):
        import modules.activities.activity.summary_crud as crud

        stmt = MagicMock()
        _, type_id = crud._apply_activity_type_filter(stmt, None)
        assert type_id is None
        stmt.where.assert_not_called()

    @patch("modules.activities.activity.summary_crud.ACTIVITY_NAME_TO_ID", {"running": 1})
    def test_known_type(self):
        import modules.activities.activity.summary_crud as crud

        stmt = MagicMock()
        stmt.where.return_value = stmt
        _, type_id = crud._apply_activity_type_filter(stmt, "running")
        assert type_id == 1
        stmt.where.assert_called_once()

    @patch("modules.activities.activity.summary_crud.ACTIVITY_NAME_TO_ID", {"running": 1})
    def test_unknown_type(self):
        import modules.activities.activity.summary_crud as crud

        stmt = MagicMock()
        stmt.where.return_value = stmt
        _, type_id = crud._apply_activity_type_filter(stmt, "swimming")
        assert type_id is None
        stmt.where.assert_called_once()


class TestGetTypeBreakdown:
    def test_success(self, mock_db):
        import modules.activities.activity.summary_crud as crud

        row = MagicMock()
        row.activity_type = 1
        row.total_distance = 10000.0
        row.total_duration = 3600.0
        row.total_elevation_gain = 100.0
        row.total_calories = 500.0
        row.activity_count = 1
        mock_db.execute.return_value.all.return_value = [row]
        result = crud._get_type_breakdown(mock_db, 1, date.min, date.max)
        assert len(result) == 1
        assert result[0].activity_type_id == 1
        assert result[0].total_distance == 10000.0

    def test_empty(self, mock_db):
        import modules.activities.activity.summary_crud as crud

        mock_db.execute.return_value.all.return_value = []
        result = crud._get_type_breakdown(mock_db, 1, date.min, date.max)
        assert result == []

    def test_with_known_type_filter(self, mock_db):
        import modules.activities.activity.summary_crud as crud

        row = MagicMock()
        row.activity_type = 1
        row.total_distance = 5000.0
        row.total_duration = 1800.0
        row.total_elevation_gain = 50.0
        row.total_calories = 250.0
        row.activity_count = 1
        mock_db.execute.return_value.all.return_value = [row]
        result = crud._get_type_breakdown(mock_db, 1, date.min, date.max, activity_type="running")
        assert len(result) == 1

    def test_with_unknown_type_filter(self, mock_db):
        import modules.activities.activity.summary_crud as crud

        result = crud._get_type_breakdown(mock_db, 1, date.min, date.max, activity_type="unknown_sport")
        assert result == []


class TestLocalTimeBuckets:
    """Summary buckets follow the athlete's local calendar, not UTC's.

    A 07:00 ride in UTC+9 belongs to that local day; bucketing on the raw
    ``timestamptz`` put it on the previous UTC day (and, at month/year edges, in
    the wrong month or year entirely).
    """

    @staticmethod
    def _mock_db():
        db = MagicMock()
        row = MagicMock()
        row.day_of_week = 1
        row.week_number = 1
        row.month_number = 1
        row.year_number = 2024
        row.activity_type = 1
        row.total_distance = 0
        row.total_duration = 0.0
        row.total_elevation_gain = 0
        row.total_calories = 0
        row.activity_count = 0
        db.execute.return_value.all.return_value = [row]
        db.execute.return_value.one_or_none.return_value = row
        return db

    @staticmethod
    def _emitted_sql(db):
        from sqlalchemy.dialects import postgresql
        from tests._helpers.db import _import_all_models

        # Compiling a statement configures the mappers, which needs every
        # related model imported (Activity -> Gear, User, ...).
        _import_all_models()

        return " ".join(
            str(call.args[0].compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
            for call in db.execute.call_args_list
        )

    def test_weekly_summary_buckets_in_local_time(self):
        import modules.activities.activity.summary_crud as crud

        db = self._mock_db()
        crud.get_weekly_summary(
            db=db,
            user_id=1,
            target_date=date(2024, 1, 15),
            first_day_of_week="monday",
        )

        sql = self._emitted_sql(db)
        assert "coalesce(activities.timezone, 'UTC')" in sql
        assert "isodow" in sql

    def test_monthly_summary_buckets_in_local_time(self):
        import modules.activities.activity.summary_crud as crud

        db = self._mock_db()
        crud.get_monthly_summary(
            db=db,
            user_id=1,
            target_date=date(2024, 1, 1),
            first_day_of_week="monday",
        )

        assert "coalesce(activities.timezone, 'UTC')" in self._emitted_sql(db)

    def test_yearly_summary_buckets_in_local_time(self):
        import modules.activities.activity.summary_crud as crud

        db = self._mock_db()
        crud.get_yearly_summary(db=db, user_id=1, year=2024)

        assert "coalesce(activities.timezone, 'UTC')" in self._emitted_sql(db)

    def test_lifetime_summary_buckets_years_in_local_time(self):
        import modules.activities.activity.summary_crud as crud

        db = self._mock_db()
        crud.get_lifetime_summary(db=db, user_id=1)

        assert "coalesce(activities.timezone, 'UTC')" in self._emitted_sql(db)

    def test_lifetime_type_breakdown_stays_unbounded(self):
        """date.min/date.max must not be turned into date arithmetic that overflows."""
        import modules.activities.activity.summary_crud as crud

        db = self._mock_db()
        crud.get_lifetime_summary(db=db, user_id=1)

        assert "9999" not in self._emitted_sql(db)
