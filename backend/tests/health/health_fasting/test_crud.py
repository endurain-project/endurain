"""The fasting records' persistence, on the real database."""

from datetime import UTC, date, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

import core.etag as core_etag
import core.exceptions as core_exceptions
import modules.health.health_fasting.crud as health_fasting_crud
import modules.health.health_fasting.models as health_fasting_models
import modules.health.health_fasting.schema as health_fasting_schema
import modules.health.models as health_models
from tests._factories.health import make_ended_health_fasting, make_health_fasting
from tests._factories.users import make_user

_T0 = datetime(2025, 3, 10, 8, 0, tzinfo=UTC)


def _hours(n: float) -> datetime:
    return _T0 + timedelta(hours=n)


def _stored(db, record_id):
    return db.get(health_fasting_models.HealthFasting, record_id)


@pytest.fixture
def user(db):
    return make_user(db)


@pytest.fixture
def other(db):
    return make_user(db)


class TestCreate:
    def test_the_record_is_stored_for_the_user_with_its_values_and_the_given_duration(self, db, user):
        created = health_fasting_crud.create_health_fasting(
            user.id,
            health_fasting_schema.HealthFastingImport(
                fast_start_time=_hours(0),
                fast_end_time=_hours(16),
                status="completed",
                fasting_type="16:8",
                target_duration_seconds=57600,
                notes="done",
            ),
            db,
            actual_duration_seconds=57600,
        )

        row = _stored(db, created.id)
        assert (row.user_id, row.fast_start_time, row.fast_end_time, row.status, row.actual_duration_seconds) == (
            user.id,
            _hours(0),
            _hours(16),
            "completed",
            57600,
        )
        assert (row.fasting_type, row.target_duration_seconds, row.notes, row.source, row.version) == (
            "16:8",
            57600,
            "done",
            "manual",
            1,
        )

    def test_a_user_cannot_have_two_running_fasts(self, db, user):
        make_health_fasting(db, user.id, fast_start_time=_hours(0), status="in_progress")

        with pytest.raises(core_exceptions.ConflictError, match="already has an active fasting session"):
            make_health_fasting(db, user.id, fast_start_time=_hours(5), status="in_progress")

    def test_the_database_allows_one_running_fast_per_user(self, db, user, other):
        make_health_fasting(db, user.id, status="in_progress")
        make_health_fasting(db, other.id, status="in_progress")

        with pytest.raises(IntegrityError, match="uq_health_fasting_one_in_progress_per_user"):
            db.add(
                health_fasting_models.HealthFasting(user_id=user.id, fast_start_time=_hours(3), status="in_progress")
            )
            db.flush()

    def test_a_running_fast_does_not_stop_other_fasts_being_recorded(self, db, user):
        make_health_fasting(db, user.id, fast_start_time=_hours(100), status="in_progress")
        make_ended_health_fasting(db, user.id, _hours(0), _hours(10))
        make_ended_health_fasting(db, user.id, _hours(20), _hours(30), status="cancelled")

        assert health_fasting_crud.get_health_fasting_number_by_user_id(user.id, db) == 3

    def test_deleting_the_user_deletes_their_records(self, db, user):
        record = make_health_fasting(db, user.id)

        db.execute(sa.text("DELETE FROM users WHERE id = :id"), {"id": user.id})

        assert _stored(db, record.id) is None


class TestRead:
    def test_a_record_is_found_by_id_only_for_its_owner(self, db, user, other):
        record = make_health_fasting(db, user.id)

        assert health_fasting_crud.get_health_fasting_by_id_and_user_id(record.id, user.id, db) == record
        assert health_fasting_crud.get_health_fasting_by_id_and_user_id(record.id, other.id, db) is None

    def test_the_active_fast_is_the_users_running_one(self, db, user, other):
        make_ended_health_fasting(db, user.id, _hours(0), _hours(10))
        running = make_health_fasting(db, user.id, fast_start_time=_hours(20), status="in_progress")
        make_health_fasting(db, other.id, status="in_progress")

        assert health_fasting_crud.get_active_fasting_by_user_id(user.id, db) == running

    def test_without_a_running_fast_there_is_no_active_one(self, db, user):
        make_ended_health_fasting(db, user.id, _hours(0), _hours(10))

        assert health_fasting_crud.get_active_fasting_by_user_id(user.id, db) is None

    def test_a_fast_is_known_by_its_exact_start_and_only_for_its_owner(self, db, user, other):
        make_health_fasting(db, user.id, fast_start_time=_hours(0))

        exists = health_fasting_crud.health_fasting_exists_at
        assert (exists(user.id, _hours(0), db), exists(user.id, _hours(1), db), exists(other.id, _hours(0), db)) == (
            True,
            False,
            False,
        )

    def test_the_list_is_newest_start_first_bounded_by_local_start_days_paged_and_only_the_users(self, db, user, other):
        for day in range(1, 6):
            start = datetime(2025, 3, day, 22, 0, tzinfo=UTC)
            make_ended_health_fasting(db, user.id, start, start + timedelta(hours=2))
        make_ended_health_fasting(db, other.id, _hours(0), _hours(1))
        get = health_fasting_crud.get_health_fasting_by_user_id
        count = health_fasting_crud.get_health_fasting_number_by_user_id

        assert [r.fast_start_time.day for r in get(user.id, db)] == [5, 4, 3, 2, 1]
        assert [r.fast_start_time.day for r in get(user.id, db, page_number=2, num_records=2)] == [3, 2]
        assert [r.fast_start_time.day for r in get(user.id, db, since=date(2025, 3, 2), until=date(2025, 3, 3))] == [
            3,
            2,
        ]
        assert (count(user.id, db), count(user.id, db, date(2025, 3, 2), date(2025, 3, 3))) == (5, 2)

    def test_the_bounds_are_the_start_days_in_the_users_zone(self, db, user):
        make_ended_health_fasting(db, user.id, datetime(2025, 3, 10, 22, 0, tzinfo=UTC), _hours(30))

        count = health_fasting_crud.get_health_fasting_number_by_user_id
        assert (
            count(user.id, db, date(2025, 3, 11), None, "UTC"),
            count(user.id, db, date(2025, 3, 11), None, "Asia/Tokyo"),
        ) == (0, 1)


class TestStatistics:
    def test_only_completed_fasts_are_counted_summed_and_averaged(self, db, user, other):
        make_ended_health_fasting(db, user.id, _hours(0), _hours(10))
        make_ended_health_fasting(db, user.id, _hours(24), _hours(38))
        make_ended_health_fasting(db, user.id, _hours(48), _hours(50), status="broken")
        make_ended_health_fasting(db, user.id, _hours(72), _hours(73), status="cancelled")
        make_ended_health_fasting(db, other.id, _hours(0), _hours(100))

        assert health_fasting_crud.get_completed_fasting_count(user.id, db) == 2
        assert health_fasting_crud.get_total_fasting_seconds(user.id, db) == 24 * 3600
        assert health_fasting_crud.get_avg_fasting_duration(user.id, db) == 12 * 3600

    def test_without_completed_fasts_the_totals_are_zero_and_the_average_is_none(self, db, user):
        make_health_fasting(db, user.id, status="in_progress")

        assert health_fasting_crud.get_completed_fasting_count(user.id, db) == 0
        assert health_fasting_crud.get_total_fasting_seconds(user.id, db) == 0
        assert health_fasting_crud.get_avg_fasting_duration(user.id, db) is None

    def test_the_completed_dates_are_the_distinct_local_start_days_ascending(self, db, user):
        make_ended_health_fasting(
            db, user.id, datetime(2025, 3, 12, 8, 0, tzinfo=UTC), datetime(2025, 3, 12, 9, 0, tzinfo=UTC)
        )
        make_ended_health_fasting(
            db, user.id, datetime(2025, 3, 10, 22, 0, tzinfo=UTC), datetime(2025, 3, 10, 23, 0, tzinfo=UTC)
        )
        make_ended_health_fasting(
            db, user.id, datetime(2025, 3, 10, 6, 0, tzinfo=UTC), datetime(2025, 3, 10, 7, 0, tzinfo=UTC)
        )
        make_ended_health_fasting(
            db,
            user.id,
            datetime(2025, 3, 14, 6, 0, tzinfo=UTC),
            datetime(2025, 3, 14, 7, 0, tzinfo=UTC),
            status="broken",
        )

        dates = health_fasting_crud.get_completed_fasting_dates_by_user_id
        assert dates(user.id, "UTC", db) == [date(2025, 3, 10), date(2025, 3, 12)]
        assert dates(user.id, "Asia/Tokyo", db) == [date(2025, 3, 10), date(2025, 3, 11), date(2025, 3, 12)]


class TestOverlap:
    def _overlaps(self, db, user, start, end, **kwargs):
        return health_fasting_crud.fasting_overlaps(user.id, start, end, db, **kwargs)

    @pytest.fixture
    def ended(self, db, user):
        return make_ended_health_fasting(db, user.id, _hours(0), _hours(10))

    @pytest.mark.usefixtures("ended")
    @pytest.mark.parametrize(
        ("start", "end", "expected"),
        [
            (5, 15, True),
            (2, 4, True),
            (-5, 20, True),
            (-5, 5, True),
            (10, 12, False),
            (-5, 0, False),
            (20, None, False),
        ],
        ids=["overlapping", "inside", "around", "head", "starts-at-its-end", "ends-at-its-start", "open-after"],
    )
    def test_a_span_overlaps_an_ended_fast_when_they_share_more_than_an_endpoint(self, db, user, start, end, expected):
        assert self._overlaps(db, user, _hours(start), None if end is None else _hours(end)) is expected

    def test_a_running_fast_lasts_indefinitely(self, db, user):
        make_health_fasting(db, user.id, fast_start_time=_hours(0), status="in_progress")

        assert self._overlaps(db, user, _hours(1000), _hours(1001)) is True
        assert self._overlaps(db, user, _hours(-10), _hours(0)) is False

    def test_a_cancelled_fast_without_an_end_has_no_extent(self, db, user):
        make_health_fasting(db, user.id, fast_start_time=_hours(0), status="cancelled")

        assert self._overlaps(db, user, _hours(1), _hours(2)) is False

    def test_the_fast_being_edited_does_not_overlap_itself(self, db, user, ended):
        assert self._overlaps(db, user, _hours(1), _hours(2), exclude_id=ended.id) is False

    def test_another_users_fast_is_not_an_overlap(self, db, user, other):
        make_ended_health_fasting(db, other.id, _hours(0), _hours(10))

        assert self._overlaps(db, user, _hours(1), _hours(2)) is False


class TestEdit:
    def _edit(self, db, user_id, record, *, if_match=None, duration=None, **changes):
        return health_fasting_crud.edit_health_fasting(
            user_id,
            record.id,
            health_fasting_schema.HealthFastingUpdate(**changes),
            db,
            actual_duration_seconds=duration,
            if_match=core_etag.format_etag(record.version) if if_match is None else if_match,
        )

    def test_only_the_fields_sent_change_and_the_version_moves_on(self, db, user):
        record = make_ended_health_fasting(db, user.id, _hours(0), _hours(10), notes="before", fasting_type="16:8")

        edited = self._edit(db, user.id, record, duration=36000, notes="after")

        row = _stored(db, record.id)
        assert (row.notes, row.fasting_type, row.fast_end_time, row.actual_duration_seconds) == (
            "after",
            "16:8",
            _hours(10),
            36000,
        )
        assert (record.version, edited.version, row.version) == (1, 2, 2)

    def test_a_stale_version_is_refused_and_nothing_changes(self, db, user):
        record = make_health_fasting(db, user.id, notes="one")
        self._edit(db, user.id, record, notes="two")

        with pytest.raises(core_exceptions.PreconditionFailedError):
            self._edit(db, user.id, record, notes="three")

        assert _stored(db, record.id).notes == "two"

    def test_another_users_record_is_not_found_and_stays_as_it_was(self, db, user, other):
        theirs = make_health_fasting(db, other.id, notes="theirs")

        with pytest.raises(core_exceptions.NotFoundError):
            self._edit(db, user.id, theirs, notes="mine")

        assert (_stored(db, theirs.id).notes, _stored(db, theirs.id).version) == ("theirs", 1)

    def test_a_change_that_would_leave_two_running_fasts_is_a_conflict(self, db, user):
        make_health_fasting(db, user.id, fast_start_time=_hours(0), status="in_progress")
        ended = make_ended_health_fasting(db, user.id, _hours(-30), _hours(-20), fasting_type="16:8")

        with pytest.raises(core_exceptions.ConflictError, match="already has an active fasting session"):
            self._edit(db, user.id, ended, status="in_progress", fast_end_time=None)


class TestEnd:
    def _end(self, db, user_id, record, *, status="completed", notes=None, if_match=None):
        return health_fasting_crud.end_health_fasting(
            user_id,
            record.id,
            _hours(16),
            status,
            57600,
            notes,
            db,
            if_match=core_etag.format_etag(record.version) if if_match is None else if_match,
        )

    def test_the_end_status_and_duration_are_stored_and_the_notes_kept_when_none_are_sent(self, db, user):
        record = make_health_fasting(db, user.id, fast_start_time=_hours(0), status="in_progress", notes="kept")

        ended = self._end(db, user.id, record)

        row = _stored(db, record.id)
        assert (row.fast_end_time, row.status, row.actual_duration_seconds, row.notes) == (
            _hours(16),
            "completed",
            57600,
            "kept",
        )
        assert ended.version == 2

    def test_notes_that_are_sent_replace_the_stored_ones(self, db, user):
        record = make_health_fasting(db, user.id, status="in_progress", notes="old")

        self._end(db, user.id, record, notes="new")

        assert _stored(db, record.id).notes == "new"

    def test_a_stale_version_is_refused_and_the_fast_keeps_running(self, db, user):
        record = make_health_fasting(db, user.id, status="in_progress")

        with pytest.raises(core_exceptions.PreconditionFailedError):
            self._end(db, user.id, record, if_match='"4"')

        assert _stored(db, record.id).status == "in_progress"

    def test_another_users_fast_is_not_found(self, db, user, other):
        theirs = make_health_fasting(db, other.id, status="in_progress")

        with pytest.raises(core_exceptions.NotFoundError):
            self._end(db, user.id, theirs)


class TestDelete:
    def test_the_record_is_removed_and_its_deletion_remembered_for_sync(self, db, user):
        record = make_health_fasting(db, user.id)

        health_fasting_crud.delete_health_fasting(
            user.id, record.id, db, if_match=core_etag.format_etag(record.version)
        )

        assert _stored(db, record.id) is None
        tombstones = db.scalars(sa.select(health_models.HealthRecordDeletion)).all()
        assert [(t.user_id, t.record_id, t.record_type) for t in tombstones] == [(user.id, record.id, "health_fasting")]

    def test_a_stale_version_is_refused_and_the_record_stays(self, db, user):
        record = make_health_fasting(db, user.id)

        with pytest.raises(core_exceptions.PreconditionFailedError):
            health_fasting_crud.delete_health_fasting(user.id, record.id, db, if_match='"2"')

        assert _stored(db, record.id) is not None

    def test_another_users_record_is_not_found_and_stays(self, db, user, other):
        theirs = make_health_fasting(db, other.id)

        with pytest.raises(core_exceptions.NotFoundError):
            health_fasting_crud.delete_health_fasting(user.id, theirs.id, db, if_match='"1"')

        assert _stored(db, theirs.id) is not None
        assert db.scalars(sa.select(health_models.HealthRecordDeletion)).all() == []


class TestChanged:
    def test_changed_records_are_the_users_only(self, db, user, other):
        mine = make_ended_health_fasting(db, user.id, _hours(0), _hours(1))
        make_health_fasting(db, other.id)

        changed = health_fasting_crud.list_changed(user.id, None, datetime.now(UTC) + timedelta(days=1), 10, db)

        assert [r.id for r in changed] == [mine.id]
