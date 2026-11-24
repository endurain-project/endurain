"""The bowel movement records' application rules, on the real database."""

import uuid
from datetime import UTC, date, datetime, timedelta

import jasil.runtime as platform_runtime
import pytest
import sqlalchemy as sa

import core.date_range as core_date_range
import core.etag as core_etag
import core.exceptions as core_exceptions
import modules.health.constants as health_constants
import modules.health.health_poop.crud as health_poop_crud
import modules.health.health_poop.models as health_poop_models
import modules.health.health_poop.schema as health_poop_schema
import modules.health.health_poop.service as health_poop_service
from tests._factories.health import make_health_poop
from tests._factories.users import make_user

_NOW = datetime(2025, 3, 10, 12, 0, tzinfo=UTC)
_EARLIER = datetime(2025, 3, 1, 9, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def now():
    """Stand the platform clock at :data:`_NOW`, which is the 10th in UTC and already the 10th in Tokyo."""
    platform_runtime.get_active_platform().clock.moment = _NOW


def _stored(db, record_id):
    return db.get(health_poop_models.HealthPoop, record_id)


def _create(db, user, **fields):
    return health_poop_service.create_health_poop(
        user.id, health_poop_schema.HealthPoopCreate(**{"date_time": _EARLIER, **fields}), db
    )


def _edit(db, user, record, *, if_match=None, **changes):
    return health_poop_service.edit_health_poop(
        user.id,
        record.id,
        health_poop_schema.HealthPoopUpdate(**changes),
        db,
        if_match=core_etag.format_etag(record.version) if if_match is None else if_match,
    )


@pytest.fixture
def user(db):
    return make_user(db, timezone="UTC")


@pytest.fixture
def other(db):
    return make_user(db, timezone="UTC")


class TestCreate:
    def test_the_record_is_stored_committed_and_marked_manual(self, db, user):
        created = _create(db, user, bristol_type="type_4", notes="fine")

        assert health_poop_service.get_health_poop(user.id, created.id, db) == created
        assert (created.user_id, created.date_time, created.bristol_type, created.source) == (
            user.id,
            _EARLIER,
            "type_4",
            "manual",
        )

    def test_a_moment_after_the_users_today_is_refused_and_nothing_is_stored(self, db, user):
        with pytest.raises(core_exceptions.InvalidInputError, match="cannot be dated in the future"):
            _create(db, user, date_time=_NOW + timedelta(days=1))

        assert health_poop_crud.get_health_poop_number_by_user_id(user.id, db) == 0

    def test_a_moment_is_judged_by_the_day_it_falls_on_in_the_users_zone(self, db):
        # 2025-03-10 23:00 UTC is already the 11th in Tokyo, which is after the 10th there, but not in Los Angeles.
        moment = datetime(2025, 3, 10, 23, 0, tzinfo=UTC)
        tokyo = make_user(db, timezone="Asia/Tokyo")
        los_angeles = make_user(db, timezone="America/Los_Angeles")

        with pytest.raises(core_exceptions.InvalidInputError):
            _create(db, tokyo, date_time=moment)

        assert _create(db, los_angeles, date_time=moment).date_time == moment

    def test_a_second_record_at_the_same_instant_is_allowed(self, db, user):
        _create(db, user)
        _create(db, user)

        assert health_poop_crud.get_health_poop_number_by_user_id(user.id, db) == 2


class TestImport:
    def test_a_record_is_staged_once_per_instant_and_the_repeat_reports_it_was_there(self, db, user):
        record = health_poop_schema.HealthPoopImport(date_time=_EARLIER, notes="a")

        first = health_poop_service.stage_import_health_poop(user.id, record, db)
        second = health_poop_service.stage_import_health_poop(user.id, record, db)

        assert (first, second) == (True, False)
        assert health_poop_crud.get_health_poop_number_by_user_id(user.id, db) == 1

    def test_another_users_record_at_the_instant_does_not_block_the_import(self, db, user, other):
        make_health_poop(db, other.id, date_time=_EARLIER)

        record = health_poop_schema.HealthPoopImport(date_time=_EARLIER)

        assert health_poop_service.stage_import_health_poop(user.id, record, db) is True


class TestGet:
    def test_a_record_the_user_does_not_have_is_not_found(self, db, user):
        with pytest.raises(core_exceptions.NotFoundError, match="Poop record not found"):
            health_poop_service.get_health_poop(user.id, uuid.uuid4(), db)

    def test_another_users_record_is_not_found(self, db, user, other):
        theirs = make_health_poop(db, other.id)

        with pytest.raises(core_exceptions.NotFoundError):
            health_poop_service.get_health_poop(user.id, theirs.id, db)

    def test_the_records_of_a_day_are_those_of_the_users_local_day(self, db):
        tokyo = make_user(db, timezone="Asia/Tokyo")
        record = make_health_poop(db, tokyo.id, date_time=datetime(2025, 3, 10, 23, 0, tzinfo=UTC))

        assert [r.id for r in health_poop_service.list_health_poop_by_date(tokyo.id, "2025-03-11", db)] == [record.id]
        assert health_poop_service.list_health_poop_by_date(tokyo.id, "2025-03-10", db) == []


class TestEdit:
    def test_the_change_is_stored_and_the_version_moves_on(self, db, user):
        record = _create(db, user, notes="before")

        edited = _edit(db, user, record, notes="after")

        assert (edited.notes, edited.version) == ("after", record.version + 1)
        assert _stored(db, record.id).notes == "after"

    def test_a_stale_version_is_refused_and_the_record_keeps_the_newer_value(self, db, user):
        record = _create(db, user, notes="one")
        _edit(db, user, record, notes="two")

        with pytest.raises(core_exceptions.PreconditionFailedError):
            _edit(db, user, record, notes="three")

        assert _stored(db, record.id).notes == "two"

    def test_a_moment_after_the_users_today_is_refused_and_the_record_keeps_its_time(self, db, user):
        record = _create(db, user)

        with pytest.raises(core_exceptions.InvalidInputError, match="cannot be dated in the future"):
            _edit(db, user, record, date_time=_NOW + timedelta(days=1))

        assert _stored(db, record.id).date_time == _EARLIER

    def test_another_users_record_is_not_found_and_unchanged(self, db, user, other):
        theirs = make_health_poop(db, other.id, notes="theirs")

        with pytest.raises(core_exceptions.NotFoundError):
            _edit(db, user, theirs, notes="mine")

        assert (_stored(db, theirs.id).notes, _stored(db, theirs.id).version) == ("theirs", 1)


class TestDelete:
    def test_the_record_is_gone_afterwards(self, db, user):
        record = _create(db, user)

        health_poop_service.delete_health_poop(user.id, record.id, db, if_match=core_etag.format_etag(record.version))

        with pytest.raises(core_exceptions.NotFoundError):
            health_poop_service.get_health_poop(user.id, record.id, db)

    def test_a_stale_version_is_refused_and_the_record_stays(self, db, user):
        record = _create(db, user)

        with pytest.raises(core_exceptions.PreconditionFailedError):
            health_poop_service.delete_health_poop(user.id, record.id, db, if_match='"7"')

        assert _stored(db, record.id) is not None

    def test_another_users_record_is_not_found_and_stays(self, db, user, other):
        theirs = make_health_poop(db, other.id)

        with pytest.raises(core_exceptions.NotFoundError):
            health_poop_service.delete_health_poop(user.id, theirs.id, db, if_match='"1"')

        assert _stored(db, theirs.id) is not None


class TestList:
    @pytest.fixture
    def records(self, db, user):
        return {days: make_health_poop(db, user.id, date_time=_NOW - timedelta(days=days)) for days in (0, 3, 20, 400)}

    @pytest.mark.usefixtures("records")
    @pytest.mark.parametrize(
        ("interval", "kept"),
        [
            (health_constants.Interval.LAST_7_DAYS, (0, 3)),
            (health_constants.Interval.LAST_30_DAYS, (0, 3, 20)),
            (health_constants.Interval.ALL_TIME, (0, 3, 20, 400)),
        ],
    )
    def test_an_interval_keeps_the_records_looking_back_from_the_users_today(self, db, user, interval, kept):
        page = health_poop_service.list_health_poop(user.id, db, interval=interval)

        assert [r.date_time for r in page.items] == [_NOW - timedelta(days=d) for d in kept]
        assert (page.total, page.page, page.num_records, page.next) == (len(kept), 1, 25, None)

    @pytest.mark.usefixtures("records")
    def test_a_date_range_replaces_the_interval_and_a_page_holds_its_slice(self, db, user):
        window = core_date_range.DateRange(date(2024, 1, 1), date(2025, 3, 7))

        page = health_poop_service.list_health_poop(
            user.id, db, interval=health_constants.Interval.LAST_7_DAYS, date_range=window, num_records=2
        )

        assert [r.date_time for r in page.items] == [_NOW - timedelta(days=d) for d in (3, 20)]
        assert (page.total, page.next) == (3, 2)

    def test_the_days_are_the_users_local_days(self, db):
        tokyo = make_user(db, timezone="Asia/Tokyo")
        make_health_poop(db, tokyo.id, date_time=datetime(2025, 3, 10, 23, 0, tzinfo=UTC))
        window = core_date_range.DateRange(date(2025, 3, 11), date(2025, 3, 11))

        assert health_poop_service.list_health_poop(tokyo.id, db, date_range=window).total == 1

    def test_another_users_records_are_not_listed(self, db, user, other):
        make_health_poop(db, other.id, date_time=_NOW)

        page = health_poop_service.list_health_poop(user.id, db)

        assert (page.items, page.total) == ([], 0)


class TestChart:
    def test_a_window_is_one_count_per_day_with_a_movement(self, db, user):
        for moment in (_NOW, _NOW - timedelta(hours=2), _NOW - timedelta(days=2), _NOW - timedelta(days=30)):
            make_health_poop(db, user.id, date_time=moment)

        series = health_poop_service.get_health_poop_chart(user.id, health_constants.Interval.LAST_7_DAYS, db)

        assert series.bucket == health_constants.ChartBucket.DAY
        assert [(p.date, p.value) for p in series.points] == [(date(2025, 3, 8), 1.0), (date(2025, 3, 10), 2.0)]

    @pytest.fixture
    def a_movement_every_day_for_a_year_and_a_day(self, db, user):
        first = date(2024, 3, 1)
        for offset in range(367):
            day = first + timedelta(days=offset)
            make_health_poop(db, user.id, date_time=datetime(day.year, day.month, day.day, 9, 0, tzinfo=UTC))

    def _weekly_series(self, db, user):
        return health_poop_service.get_health_poop_chart(
            user.id,
            health_constants.Interval.LAST_7_DAYS,
            db,
            date_range=core_date_range.DateRange(date(2024, 3, 1), date(2025, 3, 31)),
        )

    @pytest.mark.usefixtures("a_movement_every_day_for_a_year_and_a_day")
    def test_a_window_of_more_than_a_year_of_days_is_weekly_and_each_value_is_movements_per_day(self, db, user):
        series = self._weekly_series(db, user)

        assert series.bucket == health_constants.ChartBucket.WEEK
        assert series.points[0].date == date(2024, 3, 1)
        assert {p.value for p in series.points[1:]} == {1.0}

    @pytest.mark.usefixtures("a_movement_every_day_for_a_year_and_a_day")
    def test_the_week_the_window_opens_in_counts_only_the_days_it_spans(self, db, user):
        """The window opens on a Friday, so its first week spans three days, each with a movement: 1 a day."""
        assert self._weekly_series(db, user).points[0].value == 1.0

    def test_all_time_opens_at_the_first_movement_so_the_first_bucket_is_not_diluted(self, db, user):
        make_health_poop(db, user.id, date_time=datetime(2025, 3, 8, 12, 0, tzinfo=UTC))
        make_health_poop(db, user.id, date_time=datetime(2025, 3, 9, 12, 0, tzinfo=UTC))

        series = health_poop_service.get_health_poop_chart(user.id, health_constants.Interval.ALL_TIME, db)

        assert [(p.date, p.value) for p in series.points] == [(date(2025, 3, 8), 1.0), (date(2025, 3, 9), 1.0)]

    def test_another_users_movements_are_not_charted(self, db, user, other):
        make_health_poop(db, other.id, date_time=_NOW)

        assert (
            health_poop_service.get_health_poop_chart(user.id, health_constants.Interval.LAST_7_DAYS, db).points == []
        )


class TestRestoreProfileRecords:
    def _restore(self, db, user, records):
        return health_poop_service.restore_profile_records(records, user.id, {}, db)

    def test_the_archived_records_are_stored_for_the_importing_user_not_the_exporter(self, db, user):
        archived_id = uuid.uuid4()
        record = {
            "id": str(archived_id),
            "user_id": str(uuid.uuid4()),
            "version": 9,
            "updated_at": "2020-01-01T00:00:00Z",
            "date_time": "2025-03-01T08:00:00Z",
            "bristol_type": 4,
            "color": "brown",
            "notes": "archived",
        }

        assert self._restore(db, user, [record]) == 1

        (stored,) = health_poop_crud.get_health_poop_by_user_id(user.id, db)
        assert (stored.user_id, stored.date_time, stored.bristol_type, stored.color, stored.version) == (
            user.id,
            datetime(2025, 3, 1, 8, 0, tzinfo=UTC),
            "type_4",
            "brown",
            1,
        )
        assert stored.id != archived_id

    def test_a_record_already_stored_at_that_instant_is_not_duplicated(self, db, user):
        make_health_poop(db, user.id, date_time=datetime(2025, 3, 1, 8, 0, tzinfo=UTC))

        assert self._restore(db, user, [{"date_time": "2025-03-01T08:00:00Z"}]) == 0
        assert health_poop_crud.get_health_poop_number_by_user_id(user.id, db) == 1

    def test_a_record_that_is_invalid_is_skipped_and_the_rest_are_stored(self, db, user):
        records = [
            {"date_time": "not a time"},
            {"date_time": "2025-03-02T08:00:00Z", "bristol_type": 99},
            {"date_time": "2025-03-03T08:00:00Z"},
        ]

        assert self._restore(db, user, records) == 1

        assert [r.date_time.day for r in health_poop_crud.get_health_poop_by_user_id(user.id, db)] == [3]

    def test_an_empty_archive_stores_nothing(self, db, user):
        assert self._restore(db, user, []) == 0
        assert db.scalar(sa.select(sa.func.count()).select_from(health_poop_models.HealthPoop)) == 0
