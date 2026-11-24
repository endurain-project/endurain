"""The fasting records' application rules, on the real database: times, overlap, duration, statistics."""

import uuid
from datetime import UTC, date, datetime, timedelta

import jasil.runtime as platform_runtime
import pytest
import sqlalchemy as sa

import core.date_range as core_date_range
import core.etag as core_etag
import core.exceptions as core_exceptions
import core.types as core_types
import modules.health.constants as health_constants
import modules.health.health_fasting.crud as health_fasting_crud
import modules.health.health_fasting.models as health_fasting_models
import modules.health.health_fasting.schema as health_fasting_schema
import modules.health.health_fasting.service as health_fasting_service
from tests._factories.health import make_ended_health_fasting, make_health_fasting
from tests._factories.users import make_user

_NOW = datetime(2025, 3, 20, 12, 0, tzinfo=UTC)
_T0 = datetime(2025, 3, 10, 8, 0, tzinfo=UTC)


def _hours(n: float) -> datetime:
    return _T0 + timedelta(hours=n)


@pytest.fixture(autouse=True)
def now():
    """Stand the platform clock at :data:`_NOW`, after every fast the tests record."""
    platform_runtime.get_active_platform().clock.moment = _NOW


def _stored(db, record_id):
    return db.get(health_fasting_models.HealthFasting, record_id)


def _fast(db, user, start, end=None, status="completed", **fields):
    return health_fasting_service.create_health_fasting(
        user.id,
        health_fasting_schema.HealthFastingCreate(fast_start_time=start, fast_end_time=end, status=status, **fields),
        db,
    )


def _edit(db, user, record, **changes):
    return health_fasting_service.edit_health_fasting(
        user.id,
        record.id,
        health_fasting_schema.HealthFastingUpdate(**changes),
        db,
        if_match=core_etag.format_etag(record.version),
    )


def _complete(db, user, record, end, **fields):
    return health_fasting_service.complete_health_fasting(
        user.id,
        record.id,
        health_fasting_schema.HealthFastingComplete(fast_end_time=end, **fields),
        db,
        if_match=core_etag.format_etag(record.version),
    )


def _import(db, user, start, end, status="completed", **fields):
    return health_fasting_service.stage_import_health_fasting(
        user.id,
        health_fasting_schema.HealthFastingImport(fast_start_time=start, fast_end_time=end, status=status, **fields),
        db,
    )


@pytest.fixture
def user(db):
    return make_user(db, timezone="UTC")


@pytest.fixture
def other(db):
    return make_user(db, timezone="UTC")


class TestCreate:
    def test_the_fast_is_stored_committed_and_marked_manual_with_its_derived_duration(self, db, user):
        created = _fast(db, user, _hours(0), _hours(16))

        assert health_fasting_service.get_health_fasting(user.id, created.id, db) == created
        assert (created.source, created.actual_duration_seconds, created.version) == ("manual", 16 * 3600, 1)

    def test_a_fast_without_a_status_is_in_progress_with_no_duration(self, db, user):
        created = health_fasting_service.create_health_fasting(
            user.id, health_fasting_schema.HealthFastingCreate(fast_start_time=_hours(0)), db
        )

        assert (created.status, created.actual_duration_seconds) == ("in_progress", None)

    def test_an_end_before_the_start_is_refused(self, db, user):
        with pytest.raises(core_exceptions.InvalidInputError, match="cannot end before it started"):
            _fast(db, user, _hours(10), _hours(2))

        assert health_fasting_crud.get_health_fasting_number_by_user_id(user.id, db) == 0

    @pytest.mark.parametrize("status", ["completed", "broken"])
    def test_an_ended_status_needs_an_end_time(self, db, user, status):
        with pytest.raises(core_exceptions.InvalidInputError, match="needs an end time"):
            _fast(db, user, _hours(0), None, status)

    def test_cancelled_and_in_progress_need_no_end_time(self, db, user):
        _fast(db, user, _hours(0), None, "cancelled")
        _fast(db, user, _hours(100), None, "in_progress")

        assert health_fasting_crud.get_health_fasting_number_by_user_id(user.id, db) == 2

    def test_an_in_progress_fast_with_an_end_time_is_refused(self, db, user):
        with pytest.raises(core_exceptions.InvalidInputError, match="in progress cannot have an end time"):
            _fast(db, user, _hours(0), _hours(2), "in_progress")

    def test_a_span_longer_than_the_duration_column_holds_is_refused(self, db, user):
        start = datetime(1950, 1, 1, tzinfo=UTC)
        end = start + timedelta(seconds=core_types.INT32_MAX + 1)

        with pytest.raises(core_exceptions.InvalidInputError, match="too long"):
            _fast(db, user, start, end)

    def test_a_start_or_an_end_after_the_users_today_is_refused(self, db, user):
        with pytest.raises(core_exceptions.InvalidInputError, match="cannot be dated in the future"):
            _fast(db, user, _NOW + timedelta(days=2), None, "in_progress")
        with pytest.raises(core_exceptions.InvalidInputError, match="cannot be dated in the future"):
            _fast(db, user, _hours(0), _NOW + timedelta(days=2))

        assert health_fasting_crud.get_health_fasting_number_by_user_id(user.id, db) == 0

    def test_a_second_running_fast_is_a_conflict_and_the_first_keeps_running(self, db, user):
        first = _fast(db, user, _hours(0), None, "in_progress")

        with pytest.raises(core_exceptions.ConflictError, match="already has an active fasting session"):
            _fast(db, user, _hours(5), None, "in_progress")

        assert health_fasting_service.get_active_fasting(user.id, db) == first

    def test_another_user_may_run_a_fast_at_the_same_time(self, db, user, other):
        _fast(db, user, _hours(0), None, "in_progress")

        assert _fast(db, other, _hours(0), None, "in_progress").user_id == other.id


class TestOverlap:
    @pytest.fixture
    def existing(self, db, user):
        return _fast(db, user, _hours(0), _hours(10))

    @pytest.mark.usefixtures("existing")
    @pytest.mark.parametrize(("start", "end"), [(5, 15), (2, 4), (-5, 20)], ids=["overlapping", "inside", "around"])
    def test_a_fast_that_shares_time_with_another_is_a_conflict(self, db, user, start, end):
        with pytest.raises(core_exceptions.ConflictError, match="overlaps"):
            _fast(db, user, _hours(start), _hours(end))

    @pytest.mark.usefixtures("existing")
    def test_touching_endpoints_are_allowed(self, db, user):
        _fast(db, user, _hours(10), _hours(12))
        _fast(db, user, _hours(-5), _hours(0))

    def test_another_users_fast_is_not_an_overlap(self, db, user, other):
        _fast(db, other, _hours(0), _hours(10))

        _fast(db, user, _hours(2), _hours(4))


class TestGet:
    def test_a_record_the_user_does_not_have_is_not_found(self, db, user):
        with pytest.raises(core_exceptions.NotFoundError, match="Fasting record not found"):
            health_fasting_service.get_health_fasting(user.id, uuid.uuid4(), db)

    def test_another_users_record_is_not_found(self, db, user, other):
        theirs = make_health_fasting(db, other.id)

        with pytest.raises(core_exceptions.NotFoundError):
            health_fasting_service.get_health_fasting(user.id, theirs.id, db)

    def test_the_active_fast_is_the_users_running_one_or_none(self, db, user):
        assert health_fasting_service.get_active_fasting(user.id, db) is None

        running = _fast(db, user, _hours(0), None, "in_progress")

        assert health_fasting_service.get_active_fasting(user.id, db) == running


class TestEdit:
    def test_the_change_is_stored_and_the_version_moves_on(self, db, user):
        record = _fast(db, user, _hours(0), _hours(10), notes="before")

        edited = _edit(db, user, record, notes="after")

        assert (edited.notes, edited.version) == ("after", record.version + 1)
        assert _stored(db, record.id).notes == "after"

    def test_a_stale_version_is_refused_and_the_record_keeps_the_newer_value(self, db, user):
        record = _fast(db, user, _hours(0), _hours(10), notes="one")
        _edit(db, user, record, notes="two")

        with pytest.raises(core_exceptions.PreconditionFailedError):
            _edit(db, user, record, notes="three")

        assert _stored(db, record.id).notes == "two"

    def test_the_end_is_checked_against_the_stored_start_and_the_start_against_the_stored_end(self, db, user):
        record = _fast(db, user, _hours(10), _hours(20))

        with pytest.raises(core_exceptions.InvalidInputError, match="cannot end before it started"):
            _edit(db, user, record, fast_end_time=_hours(5))
        with pytest.raises(core_exceptions.InvalidInputError, match="cannot end before it started"):
            _edit(db, user, record, fast_start_time=_hours(30))

        assert _stored(db, record.id).fast_end_time == _hours(20)

    def test_the_duration_follows_an_edit_of_the_times_and_an_edit_of_the_notes_keeps_it(self, db, user):
        record = _fast(db, user, _hours(10), _hours(20))

        moved = _edit(db, user, record, fast_end_time=_hours(11))
        noted = _edit(db, user, moved, notes="x")

        assert (moved.actual_duration_seconds, noted.actual_duration_seconds) == (3600, 3600)

    def test_clearing_the_end_of_a_cancelled_fast_clears_the_duration(self, db, user):
        record = _fast(db, user, _hours(0), _hours(5), "cancelled")

        assert _edit(db, user, record, fast_end_time=None).actual_duration_seconds is None

    def test_a_status_that_does_not_fit_the_times_is_refused_and_nothing_changes(self, db, user):
        ended = _fast(db, user, _hours(0), _hours(5))
        running = _fast(db, user, _hours(100), None, "in_progress")

        with pytest.raises(core_exceptions.InvalidInputError, match="needs an end time"):
            _edit(db, user, ended, fast_end_time=None)
        with pytest.raises(core_exceptions.InvalidInputError, match="in progress cannot have an end time"):
            _edit(db, user, running, fast_end_time=_hours(101))

        assert (_stored(db, ended.id).fast_end_time, _stored(db, running.id).fast_end_time) == (_hours(5), None)

    def test_an_end_time_with_an_ended_status_is_accepted(self, db, user):
        running = _fast(db, user, _hours(0), None, "in_progress")

        edited = _edit(db, user, running, fast_end_time=_hours(4), status="completed")

        assert (edited.status, edited.actual_duration_seconds) == ("completed", 4 * 3600)

    def test_an_edit_into_another_fast_is_a_conflict_and_a_fast_does_not_overlap_itself(self, db, user):
        _fast(db, user, _hours(0), _hours(10))
        later = _fast(db, user, _hours(20), _hours(30))

        with pytest.raises(core_exceptions.ConflictError, match="overlaps"):
            _edit(db, user, later, fast_start_time=_hours(5))

        assert _edit(db, user, later, fast_end_time=_hours(31)).fast_end_time == _hours(31)

    def test_a_start_or_an_end_after_the_users_today_is_refused(self, db, user):
        record = _fast(db, user, _hours(0), _hours(5))

        with pytest.raises(core_exceptions.InvalidInputError, match="cannot be dated in the future"):
            _edit(db, user, record, fast_end_time=_NOW + timedelta(days=2))

    def test_another_users_record_is_not_found_and_unchanged(self, db, user, other):
        theirs = make_health_fasting(db, other.id, notes="theirs")

        with pytest.raises(core_exceptions.NotFoundError):
            _edit(db, user, theirs, notes="mine")

        assert _stored(db, theirs.id).notes == "theirs"


class TestComplete:
    def test_the_fast_ends_with_the_derived_duration_and_the_status_and_notes_sent(self, db, user):
        record = _fast(db, user, _hours(0), None, "in_progress")

        ended = _complete(db, user, record, _hours(16), status="broken", notes="gave in")

        row = _stored(db, record.id)
        assert (row.status, row.fast_end_time, row.actual_duration_seconds, row.notes, row.version) == (
            "broken",
            _hours(16),
            16 * 3600,
            "gave in",
            2,
        )
        assert ended.actual_duration_seconds == 16 * 3600

    def test_a_fast_that_is_not_in_progress_cannot_be_completed(self, db, user):
        record = _fast(db, user, _hours(0), _hours(5))

        with pytest.raises(core_exceptions.ConflictError, match="not in progress"):
            _complete(db, user, record, _hours(6))

    def test_an_end_before_the_start_is_refused_and_the_fast_keeps_running(self, db, user):
        record = _fast(db, user, _hours(10), None, "in_progress")

        with pytest.raises(core_exceptions.InvalidInputError, match="cannot end before it started"):
            _complete(db, user, record, _hours(2))

        assert _stored(db, record.id).status == "in_progress"

    def test_a_span_longer_than_the_duration_column_holds_is_refused(self, db, user):
        start = datetime(1950, 1, 1, tzinfo=UTC)
        record = _fast(db, user, start, None, "in_progress")

        with pytest.raises(core_exceptions.InvalidInputError, match="too long"):
            _complete(db, user, record, start + timedelta(seconds=core_types.INT32_MAX + 1))

    def test_an_end_after_the_users_today_is_refused(self, db, user):
        record = _fast(db, user, _hours(0), None, "in_progress")

        with pytest.raises(core_exceptions.InvalidInputError, match="cannot be dated in the future"):
            _complete(db, user, record, _NOW + timedelta(days=2))

    def test_a_stale_version_is_refused(self, db, user):
        record = _fast(db, user, _hours(0), None, "in_progress")

        with pytest.raises(core_exceptions.PreconditionFailedError):
            health_fasting_service.complete_health_fasting(
                user.id,
                record.id,
                health_fasting_schema.HealthFastingComplete(fast_end_time=_hours(3)),
                db,
                if_match='"9"',
            )

        assert _stored(db, record.id).status == "in_progress"

    def test_another_users_fast_is_not_found(self, db, user, other):
        theirs = make_health_fasting(db, other.id, status="in_progress")

        with pytest.raises(core_exceptions.NotFoundError):
            _complete(db, user, theirs, _hours(3))


class TestDelete:
    def test_the_record_is_gone_afterwards(self, db, user):
        record = _fast(db, user, _hours(0), _hours(5))

        health_fasting_service.delete_health_fasting(
            user.id, record.id, db, if_match=core_etag.format_etag(record.version)
        )

        with pytest.raises(core_exceptions.NotFoundError):
            health_fasting_service.get_health_fasting(user.id, record.id, db)

    def test_a_stale_version_is_refused_and_the_record_stays(self, db, user):
        record = _fast(db, user, _hours(0), _hours(5))

        with pytest.raises(core_exceptions.PreconditionFailedError):
            health_fasting_service.delete_health_fasting(user.id, record.id, db, if_match='"7"')

        assert _stored(db, record.id) is not None

    def test_another_users_record_is_not_found_and_stays(self, db, user, other):
        theirs = make_health_fasting(db, other.id)

        with pytest.raises(core_exceptions.NotFoundError):
            health_fasting_service.delete_health_fasting(user.id, theirs.id, db, if_match='"1"')

        assert _stored(db, theirs.id) is not None


class TestList:
    @pytest.fixture
    def records(self, db, user):
        for days in (0, 3, 20, 400):
            start = _NOW - timedelta(days=days)
            make_ended_health_fasting(db, user.id, start, start + timedelta(hours=1))

    @pytest.mark.usefixtures("records")
    @pytest.mark.parametrize(
        ("interval", "kept"),
        [
            (health_constants.Interval.LAST_7_DAYS, (0, 3)),
            (health_constants.Interval.LAST_30_DAYS, (0, 3, 20)),
            (health_constants.Interval.ALL_TIME, (0, 3, 20, 400)),
        ],
    )
    def test_an_interval_keeps_the_fasts_looking_back_from_the_users_today(self, db, user, interval, kept):
        page = health_fasting_service.list_health_fasting(user.id, db, interval=interval)

        assert [r.fast_start_time for r in page.items] == [_NOW - timedelta(days=d) for d in kept]
        assert (page.total, page.next) == (len(kept), None)

    @pytest.mark.usefixtures("records")
    def test_a_date_range_replaces_the_interval_and_a_page_holds_its_slice(self, db, user):
        window = core_date_range.DateRange(date(2024, 1, 1), date(2025, 3, 17))

        page = health_fasting_service.list_health_fasting(
            user.id, db, interval=health_constants.Interval.LAST_7_DAYS, date_range=window, num_records=2
        )

        assert [r.fast_start_time for r in page.items] == [_NOW - timedelta(days=d) for d in (3, 20)]
        assert (page.total, page.next) == (3, 2)

    def test_the_days_are_the_start_days_in_the_users_zone(self, db):
        tokyo = make_user(db, timezone="Asia/Tokyo")
        start = datetime(2025, 3, 10, 22, 0, tzinfo=UTC)
        make_ended_health_fasting(db, tokyo.id, start, start + timedelta(hours=2))

        page = health_fasting_service.list_health_fasting(
            tokyo.id, db, date_range=core_date_range.DateRange(date(2025, 3, 11), date(2025, 3, 11))
        )

        assert page.total == 1

    def test_another_users_fasts_are_not_listed(self, db, user, other):
        make_health_fasting(db, other.id)

        assert health_fasting_service.list_health_fasting(user.id, db).total == 0


class TestStats:
    def test_without_fasts_everything_is_zero(self, db, user):
        stats = health_fasting_service.get_fasting_stats(user.id, db)

        assert (stats.total_fasts, stats.current_streak, stats.longest_streak, stats.total_fasting_seconds) == (
            0,
            0,
            0,
            0,
        )
        assert (stats.avg_duration_seconds, stats.completion_rate) == (None, 0.0)

    def test_the_statistics_cover_completed_fasts_streaks_and_the_completion_rate(self, db, user):
        today_start = datetime(2025, 3, 20, 6, 0, tzinfo=UTC)
        for days_ago, status in ((0, "completed"), (1, "completed"), (2, "completed"), (6, "completed"), (8, "broken")):
            start = today_start - timedelta(days=days_ago)
            make_ended_health_fasting(db, user.id, start, start + timedelta(hours=10), status=status)

        stats = health_fasting_service.get_fasting_stats(user.id, db)

        assert (stats.total_fasts, stats.current_streak, stats.longest_streak) == (4, 3, 3)
        assert (stats.total_fasting_seconds, stats.avg_duration_seconds, stats.completion_rate) == (
            40 * 3600,
            10 * 3600,
            80.0,
        )

    def test_the_statistics_follow_an_edit_of_a_fast(self, db, user):
        record = _fast(db, user, _hours(0), _hours(6))
        _fast(db, user, _hours(24), _hours(36))

        before = health_fasting_service.get_fasting_stats(user.id, db)
        _edit(db, user, record, fast_end_time=_hours(12))
        after = health_fasting_service.get_fasting_stats(user.id, db)

        assert (before.total_fasting_seconds, after.total_fasting_seconds) == (18 * 3600, 24 * 3600)
        assert after.avg_duration_seconds == 12 * 3600

    def test_a_streak_is_counted_in_the_users_zone(self, db):
        # 23:00 UTC on the 17th and 18th are the 18th and 19th in Tokyo, where today is the 20th:
        # a run that ended yesterday is current there, and in UTC it ended two days ago.
        tokyo = make_user(db, timezone="Asia/Tokyo")
        for day in (17, 18):
            start = datetime(2025, 3, day, 23, 0, tzinfo=UTC)
            make_ended_health_fasting(db, tokyo.id, start, start + timedelta(hours=1))

        assert health_fasting_service.get_fasting_stats(tokyo.id, db).current_streak == 2


class TestImport:
    def test_a_session_is_staged_with_its_derived_duration(self, db, user):
        assert _import(db, user, _hours(0), _hours(4), source="garmin") is True

        (stored,) = health_fasting_crud.get_health_fasting_by_user_id(user.id, db)
        assert (stored.actual_duration_seconds, stored.source) == (4 * 3600, "garmin")

    def test_an_overlapping_session_is_skipped(self, db, user):
        _fast(db, user, _hours(0), _hours(10))

        assert _import(db, user, _hours(5), _hours(15)) is False
        assert health_fasting_crud.get_health_fasting_number_by_user_id(user.id, db) == 1

    def test_a_session_that_started_at_the_same_time_is_skipped(self, db, user):
        _fast(db, user, _hours(0), _hours(10))

        assert _import(db, user, _hours(0), _hours(1)) is False

    @pytest.mark.parametrize(
        ("start", "end", "status"),
        [(10, 2, "completed"), (0, 4, "in_progress"), (0, None, "completed")],
        ids=["ends-before-start", "in-progress-with-an-end", "completed-without-an-end"],
    )
    def test_a_session_with_times_that_cannot_be_one_fast_is_skipped(self, db, user, start, end, status):
        assert _import(db, user, _hours(start), None if end is None else _hours(end), status) is False
        assert health_fasting_crud.get_health_fasting_number_by_user_id(user.id, db) == 0

    def test_a_running_fast_blocks_a_later_session_but_not_an_earlier_one(self, db, user):
        _fast(db, user, _hours(20), None, "in_progress")

        assert _import(db, user, _hours(30), _hours(32)) is False
        assert _import(db, user, _hours(12), _hours(14)) is True

    def test_a_second_running_fast_is_skipped(self, db, user):
        _fast(db, user, _hours(0), None, "in_progress")

        assert _import(db, user, _hours(50), None, "in_progress") is False


class TestRestoreProfileRecords:
    def _restore(self, db, user, records):
        return health_fasting_service.restore_profile_records(records, user.id, {}, db)

    def test_the_archived_records_are_stored_for_the_importing_user_with_the_duration_derived_not_copied(
        self, db, user
    ):
        archived_id = uuid.uuid4()
        record = {
            "id": str(archived_id),
            "user_id": str(uuid.uuid4()),
            "version": 9,
            "updated_at": "2020-01-01T00:00:00Z",
            "fast_start_time": "2025-03-01T08:00:00Z",
            "fast_end_time": "2025-03-01T18:00:00Z",
            "status": "completed",
            "actual_duration_seconds": 1,
            "source": "garmin",
        }

        assert self._restore(db, user, [record]) == 1

        (stored,) = health_fasting_crud.get_health_fasting_by_user_id(user.id, db)
        assert (stored.user_id, stored.actual_duration_seconds, stored.source, stored.version) == (
            user.id,
            10 * 3600,
            "garmin",
            1,
        )
        assert stored.id != archived_id

    def test_a_record_that_is_invalid_or_overlaps_is_skipped_and_the_rest_are_stored(self, db, user):
        records = [
            {"fast_start_time": "nonsense"},
            {"fast_start_time": "2025-03-01T08:00:00Z", "fast_end_time": "2025-03-01T18:00:00Z", "status": "completed"},
            {"fast_start_time": "2025-03-01T10:00:00Z", "fast_end_time": "2025-03-01T12:00:00Z", "status": "completed"},
            {"fast_start_time": "2025-03-05T08:00:00Z", "fast_end_time": "2025-03-05T10:00:00Z", "status": "cancelled"},
        ]

        assert self._restore(db, user, records) == 2

        assert health_fasting_crud.get_health_fasting_number_by_user_id(user.id, db) == 2

    def test_an_empty_archive_stores_nothing(self, db, user):
        assert self._restore(db, user, []) == 0
        assert db.scalar(sa.select(sa.func.count()).select_from(health_fasting_models.HealthFasting)) == 0
