"""The fasting rules, checked against a real session: times, overlap, derived duration and statistics."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker
from tests._helpers.db import create_sqlite_session, ensure_user

import core.exceptions as core_exceptions
import modules.health.health_fasting.crud as fasting_crud
import modules.health.health_fasting.schema as fasting_schema
import modules.health.health_fasting.service as fasting_service
import modules.users.users.integration_service as users_integration

_T0 = datetime(2024, 1, 15, 8, 0, tzinfo=UTC)


def _hours(n: float) -> datetime:
    return _T0 + timedelta(hours=n)


@pytest.fixture
def db():
    session = create_sqlite_session()
    ensure_user(sessionmaker(bind=session.get_bind()), 1)
    # SQLite ignores the index's PostgreSQL-only predicate and would allow one fast per user; the
    # one-running-fast rule is covered against PostgreSQL in tests/postgres.
    session.execute(text("DROP INDEX uq_health_fasting_one_in_progress_per_user"))
    yield session
    session.close()


def _fast(db, start, end=None, status="completed"):
    return fasting_service.create_health_fasting(
        1, fasting_schema.HealthFastingCreate(fast_start_time=start, fast_end_time=end, status=status), db
    )


class TestCreateTimes:
    def test_an_end_before_the_start_is_refused(self, db):
        with pytest.raises(core_exceptions.InvalidInputError):
            _fast(db, _hours(10), _hours(2))

    @pytest.mark.parametrize("status", ["completed", "broken"])
    def test_an_ended_status_needs_an_end_time(self, db, status):
        with pytest.raises(core_exceptions.InvalidInputError):
            _fast(db, _hours(0), None, status)

    def test_cancelled_and_in_progress_need_no_end_time(self, db):
        assert _fast(db, _hours(0), None, "cancelled").actual_duration_seconds is None
        assert _fast(db, _hours(2), None, "in_progress").actual_duration_seconds is None

    def test_an_in_progress_fast_with_an_end_time_is_refused(self, db):
        with pytest.raises(core_exceptions.InvalidInputError, match="in progress"):
            _fast(db, _hours(0), _hours(6), "in_progress")

    def test_the_duration_is_derived_from_the_times(self, db):
        created = _fast(db, _hours(0), _hours(6))

        assert created.actual_duration_seconds == 6 * 3600

    def test_the_schema_has_no_duration_to_write(self):
        assert "actual_duration_seconds" not in fasting_schema.HealthFastingCreate.model_fields
        assert "actual_duration_seconds" not in fasting_schema.HealthFastingUpdate.model_fields
        assert "actual_duration_seconds" in fasting_schema.HealthFastingRead.model_fields

    @pytest.mark.parametrize("schema", [fasting_schema.HealthFastingCreate, fasting_schema.HealthFastingUpdate])
    def test_a_client_duration_is_refused(self, schema):
        with pytest.raises(ValidationError):
            schema.model_validate({"fast_start_time": _hours(0), "actual_duration_seconds": 5})


class TestCreateOverlap:
    def test_an_overlapping_fast_is_a_conflict(self, db):
        _fast(db, _hours(0), _hours(10))

        with pytest.raises(core_exceptions.ConflictError):
            _fast(db, _hours(5), _hours(15))

    def test_a_fast_inside_another_is_a_conflict(self, db):
        _fast(db, _hours(0), _hours(10))

        with pytest.raises(core_exceptions.ConflictError):
            _fast(db, _hours(2), _hours(3))

    def test_a_fast_around_another_is_a_conflict(self, db):
        _fast(db, _hours(2), _hours(3))

        with pytest.raises(core_exceptions.ConflictError):
            _fast(db, _hours(0), _hours(10))

    def test_touching_endpoints_are_allowed(self, db):
        _fast(db, _hours(0), _hours(10))

        _fast(db, _hours(10), _hours(12))
        _fast(db, _hours(-4), _hours(0))

    def test_a_fast_after_a_running_one_started_is_a_conflict(self, db):
        _fast(db, _hours(0), None, "in_progress")

        with pytest.raises(core_exceptions.ConflictError):
            _fast(db, _hours(20), _hours(30))

    def test_a_running_fast_may_start_where_an_earlier_one_ended(self, db):
        _fast(db, _hours(0), _hours(10))

        _fast(db, _hours(10), None, "in_progress")

    def test_another_users_fast_is_not_an_overlap(self, db):
        ensure_user(sessionmaker(bind=db.get_bind()), 2)
        fasting_service.create_health_fasting(
            2,
            fasting_schema.HealthFastingCreate(fast_start_time=_hours(0), fast_end_time=_hours(10), status="completed"),
            db,
        )

        _fast(db, _hours(5), _hours(15))


class TestEdit:
    def _edit(self, db, record, **changes):
        return fasting_service.edit_health_fasting(
            1, record.id, fasting_schema.HealthFastingUpdate(**changes), db, if_match=str(record.version)
        )

    def test_the_end_is_checked_against_the_stored_start(self, db):
        record = _fast(db, _hours(10), _hours(20))

        with pytest.raises(core_exceptions.InvalidInputError):
            self._edit(db, record, fast_end_time=_hours(5))

    def test_the_start_is_checked_against_the_stored_end(self, db):
        record = _fast(db, _hours(10), _hours(20))

        with pytest.raises(core_exceptions.InvalidInputError):
            self._edit(db, record, fast_start_time=_hours(30))

    def test_the_duration_follows_an_edit_of_the_times(self, db):
        record = _fast(db, _hours(0), _hours(6))

        edited = self._edit(db, record, fast_end_time=_hours(12))
        assert edited.actual_duration_seconds == 12 * 3600
        edited = self._edit(db, edited, fast_start_time=_hours(6))
        assert edited.actual_duration_seconds == 6 * 3600
        assert edited.version == record.version + 2

    def test_an_edit_of_the_notes_keeps_the_duration(self, db):
        record = _fast(db, _hours(0), _hours(6))

        assert self._edit(db, record, notes="felt fine").actual_duration_seconds == 6 * 3600

    def test_clearing_the_end_clears_the_duration(self, db):
        record = _fast(db, _hours(0), _hours(6))

        edited = self._edit(db, record, fast_end_time=None, status="cancelled")

        assert edited.actual_duration_seconds is None

    def test_an_ended_status_without_an_end_time_is_refused(self, db):
        record = _fast(db, _hours(0), None, "in_progress")

        with pytest.raises(core_exceptions.InvalidInputError):
            self._edit(db, record, status="completed")

    def test_an_end_time_on_an_in_progress_fast_is_refused(self, db):
        record = _fast(db, _hours(0), None, "in_progress")

        with pytest.raises(core_exceptions.InvalidInputError, match="in progress"):
            self._edit(db, record, fast_end_time=_hours(6))

    def test_an_end_time_with_an_ended_status_is_accepted(self, db):
        record = _fast(db, _hours(0), None, "in_progress")

        edited = self._edit(db, record, fast_end_time=_hours(6), status="completed")

        assert (edited.status, edited.actual_duration_seconds) == ("completed", 6 * 3600)

    def test_an_edit_into_another_fast_is_a_conflict(self, db):
        _fast(db, _hours(0), _hours(10))
        later = _fast(db, _hours(20), _hours(30))

        with pytest.raises(core_exceptions.ConflictError):
            self._edit(db, later, fast_start_time=_hours(5))

    def test_a_fast_does_not_overlap_itself(self, db):
        record = _fast(db, _hours(0), _hours(10))

        assert self._edit(db, record, fast_end_time=_hours(11)).actual_duration_seconds == 11 * 3600

    def test_the_statistics_follow_an_edit(self, db):
        record = _fast(db, _hours(0), _hours(6))
        _fast(db, _hours(24), _hours(36))
        with (
            patch.object(users_integration, "local_today", return_value=_T0.date()),
            patch.object(users_integration, "resolve_timezone", return_value="UTC"),
            # The streak query buckets days with PostgreSQL's AT TIME ZONE, which SQLite lacks.
            patch.object(fasting_crud, "get_completed_fasting_dates_by_user_id", return_value=[]),
        ):
            before = fasting_service.get_fasting_stats(1, db)
            self._edit(db, record, fast_end_time=_hours(12))
            after = fasting_service.get_fasting_stats(1, db)

        assert before.total_fasting_seconds == 18 * 3600
        assert after.total_fasting_seconds == 24 * 3600
        assert after.avg_duration_seconds == 12 * 3600


class TestComplete:
    def test_the_duration_is_derived_the_same_way(self, db):
        record = _fast(db, _hours(0), None, "in_progress")

        ended = fasting_service.complete_health_fasting(
            1,
            record.id,
            fasting_schema.HealthFastingComplete(fast_end_time=_hours(16)),
            db,
            if_match=str(record.version),
        )

        assert ended.actual_duration_seconds == 16 * 3600


class TestImport:
    def _import(self, db, start, end, status="completed"):
        return fasting_service.stage_import_health_fasting(
            1,
            fasting_schema.HealthFastingCreate(fast_start_time=start, fast_end_time=end, status=status),
            db,
        )

    def test_a_session_is_staged_with_its_derived_duration(self, db):
        assert self._import(db, _hours(0), _hours(4)) is True

        stored = fasting_crud.get_health_fasting_by_user_id(1, db)
        assert [fast.actual_duration_seconds for fast in stored] == [4 * 3600]

    def test_an_overlapping_session_is_skipped(self, db):
        _fast(db, _hours(0), _hours(10))

        assert self._import(db, _hours(5), _hours(15)) is False
        assert len(fasting_crud.get_health_fasting_by_user_id(1, db)) == 1

    def test_a_session_ending_before_it_starts_is_skipped(self, db):
        assert self._import(db, _hours(10), _hours(2)) is False

    def test_an_in_progress_session_with_an_end_is_skipped(self, db):
        assert self._import(db, _hours(0), _hours(4), "in_progress") is False
        assert fasting_crud.get_health_fasting_by_user_id(1, db) == []

    def test_a_completed_session_without_an_end_is_skipped(self, db):
        assert self._import(db, _hours(0), None) is False

    def test_a_session_at_the_same_start_is_still_skipped(self, db):
        _fast(db, _hours(0), _hours(10))

        assert self._import(db, _hours(0), _hours(1)) is False
