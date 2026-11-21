"""The water intake records' application rules, on the real database."""

import uuid
from datetime import date, timedelta

import pytest
import sqlalchemy as sa

import core.date_range as core_date_range
import core.etag as core_etag
import core.exceptions as core_exceptions
import core.timezone as core_timezone
import modules.health.constants as health_constants
import modules.health.health_water.crud as health_water_crud
import modules.health.health_water.models as health_water_models
import modules.health.health_water.schema as health_water_schema
import modules.health.health_water.service as health_water_service
from tests._factories.health import make_health_water
from tests._factories.users import make_user

_DAY = date(2025, 3, 10)


def _today() -> date:
    """The user's today: the tests' users are on UTC, and the code reads the day from the platform clock."""
    return core_timezone.today_in("UTC")


def _stored(db, record_id):
    return db.get(health_water_models.HealthWater, record_id)


def _create(db, user, **fields):
    return health_water_service.create_health_water(
        user.id, health_water_schema.HealthWaterCreate(**{"date": _DAY, "amount_ml": 500.0, **fields}), db
    )


def _edit(db, user, record, *, if_match=None, **changes):
    return health_water_service.edit_health_water(
        user.id,
        record.id,
        health_water_schema.HealthWaterUpdate(**changes),
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
    def test_the_record_is_stored_and_committed(self, db, user):
        created = _create(db, user, amount_ml=900.0)

        assert health_water_service.get_health_water(user.id, created.id, db) == created
        assert (created.user_id, created.date, created.amount_ml, created.source) == (user.id, _DAY, 900.0, "manual")

    def test_without_a_date_the_record_is_for_the_users_today(self, db, user):
        assert _create(db, user, date=None).date == _today()

    def test_a_date_after_the_users_today_is_refused_and_nothing_is_stored(self, db, user):
        with pytest.raises(core_exceptions.InvalidInputError, match="cannot be dated in the future"):
            _create(db, user, date=_today() + timedelta(days=1))

        assert health_water_crud.get_health_water_number_by_user_id(user.id, db) == 0

    def test_the_users_today_is_accepted(self, db, user):
        assert _create(db, user, date=_today()).date == _today()

    def test_a_day_that_has_a_record_is_a_conflict_and_the_record_is_unchanged(self, committed_sessions):
        with committed_sessions() as db:
            user = make_user(db, timezone="UTC")
            first = make_health_water(db, user.id, date=_DAY, amount_ml=500.0)
            db.commit()

        with committed_sessions() as db, pytest.raises(core_exceptions.ConflictError):
            _create(db, user, amount_ml=1200.0)

        with committed_sessions() as db:
            assert float(_stored(db, first.id).amount_ml) == 500.0
            assert health_water_crud.get_health_water_number_by_user_id(user.id, db) == 1


class TestGet:
    def test_a_record_the_user_does_not_have_is_not_found(self, db, user):
        with pytest.raises(core_exceptions.NotFoundError):
            health_water_service.get_health_water(user.id, uuid.uuid4(), db)

    def test_another_users_record_is_not_found(self, db, user, other):
        theirs = make_health_water(db, other.id)

        with pytest.raises(core_exceptions.NotFoundError):
            health_water_service.get_health_water(user.id, theirs.id, db)


class TestEdit:
    def test_the_change_is_stored_and_the_version_moves_on(self, db, user):
        record = _create(db, user, amount_ml=500.0)

        edited = _edit(db, user, record, amount_ml=900.0)

        assert (edited.amount_ml, edited.version) == (900.0, record.version + 1)
        assert float(_stored(db, record.id).amount_ml) == 900.0

    def test_a_stale_version_is_refused_and_the_record_keeps_the_newer_value(self, db, user):
        record = _create(db, user, amount_ml=500.0)
        _edit(db, user, record, amount_ml=900.0)

        with pytest.raises(core_exceptions.PreconditionFailedError):
            _edit(db, user, record, amount_ml=1200.0)

        assert float(_stored(db, record.id).amount_ml) == 900.0

    def test_a_date_after_the_users_today_is_refused_and_the_record_keeps_its_date(self, db, user):
        record = _create(db, user)

        with pytest.raises(core_exceptions.InvalidInputError, match="cannot be dated in the future"):
            _edit(db, user, record, date=_today() + timedelta(days=1))

        assert _stored(db, record.id).date == _DAY

    def test_moving_to_a_taken_day_is_a_conflict_and_the_record_keeps_its_day(self, committed_sessions):
        with committed_sessions() as db:
            user = make_user(db, timezone="UTC")
            make_health_water(db, user.id, date=date(2025, 3, 1))
            moved = make_health_water(db, user.id, date=date(2025, 3, 2))
            db.commit()

        with committed_sessions() as db, pytest.raises(core_exceptions.ConflictError):
            _edit(db, user, moved, date=date(2025, 3, 1))

        with committed_sessions() as db:
            row = _stored(db, moved.id)
            assert (row.date, row.version) == (date(2025, 3, 2), 1)

    def test_another_users_record_is_not_found_and_unchanged(self, db, user, other):
        theirs = make_health_water(db, other.id, amount_ml=500.0)

        with pytest.raises(core_exceptions.NotFoundError):
            _edit(db, user, theirs, amount_ml=900.0)

        assert (float(_stored(db, theirs.id).amount_ml), _stored(db, theirs.id).version) == (500.0, 1)


class TestDelete:
    def test_the_record_is_gone_afterwards(self, db, user):
        record = _create(db, user)

        health_water_service.delete_health_water(user.id, record.id, db, if_match=core_etag.format_etag(record.version))

        with pytest.raises(core_exceptions.NotFoundError):
            health_water_service.get_health_water(user.id, record.id, db)

    def test_a_stale_version_is_refused_and_the_record_stays(self, db, user):
        record = _create(db, user)

        with pytest.raises(core_exceptions.PreconditionFailedError):
            health_water_service.delete_health_water(user.id, record.id, db, if_match='"7"')

        assert _stored(db, record.id) is not None

    def test_another_users_record_is_not_found_and_stays(self, db, user, other):
        theirs = make_health_water(db, other.id)

        with pytest.raises(core_exceptions.NotFoundError):
            health_water_service.delete_health_water(user.id, theirs.id, db, if_match='"1"')

        assert _stored(db, theirs.id) is not None


class TestList:
    @pytest.fixture
    def records(self, db, user):
        return {
            offset: make_health_water(db, user.id, date=_today() - timedelta(days=offset)) for offset in (0, 3, 20, 400)
        }

    @pytest.mark.usefixtures("records")
    @pytest.mark.parametrize(
        ("interval", "kept_offsets"),
        [
            (health_constants.Interval.LAST_7_DAYS, (0, 3)),
            (health_constants.Interval.LAST_30_DAYS, (0, 3, 20)),
            (health_constants.Interval.ALL_TIME, (0, 3, 20, 400)),
        ],
    )
    def test_an_interval_keeps_the_records_looking_back_from_the_users_today(self, db, user, interval, kept_offsets):
        page = health_water_service.list_health_water(user.id, db, interval=interval)

        assert [r.date for r in page.items] == [_today() - timedelta(days=d) for d in kept_offsets]
        assert (page.total, page.page, page.num_records, page.next) == (len(kept_offsets), 1, 25, None)

    @pytest.mark.usefixtures("records")
    def test_a_date_range_replaces_the_interval_and_a_page_holds_its_slice(self, db, user):
        window = core_date_range.DateRange(_today() - timedelta(days=400), _today() - timedelta(days=3))

        page = health_water_service.list_health_water(
            user.id, db, interval=health_constants.Interval.LAST_7_DAYS, date_range=window, num_records=2
        )

        assert [r.date for r in page.items] == [_today() - timedelta(days=d) for d in (3, 20)]
        assert (page.total, page.next) == (3, 2)

    def test_another_users_records_are_not_listed(self, db, user, other):
        make_health_water(db, other.id, date=_today())

        page = health_water_service.list_health_water(user.id, db)

        assert (page.items, page.total) == ([], 0)


class TestChart:
    def test_a_window_is_one_averaged_point_per_day_with_a_value(self, db, user):
        make_health_water(db, user.id, date=_today(), amount_ml=500.0)
        make_health_water(db, user.id, date=_today() - timedelta(days=2), amount_ml=900.0)
        make_health_water(db, user.id, date=_today() - timedelta(days=30), amount_ml=1200.0)

        series = health_water_service.get_health_water_chart(user.id, health_constants.Interval.LAST_7_DAYS, db)

        assert series.bucket == health_constants.ChartBucket.DAY
        assert [(p.date, p.value) for p in series.points] == [(_today() - timedelta(days=2), 900.0), (_today(), 500.0)]

    def test_a_date_range_replaces_the_interval(self, db, user):
        make_health_water(db, user.id, date=date(2025, 3, 1), amount_ml=500.0)

        series = health_water_service.get_health_water_chart(
            user.id,
            health_constants.Interval.LAST_7_DAYS,
            db,
            date_range=core_date_range.DateRange(date(2025, 3, 1), date(2025, 3, 2)),
        )

        assert [(p.date, p.value) for p in series.points] == [(date(2025, 3, 1), 500.0)]


class TestRestoreProfileRecords:
    def _restore(self, db, user, records):
        return health_water_service.restore_profile_records(records, user.id, {}, db)

    def test_the_archived_records_are_stored_for_the_importing_user_not_the_exporter(self, db, user):
        archived_id = uuid.uuid4()
        record = {
            "id": str(archived_id),
            "user_id": str(uuid.uuid4()),
            "version": 9,
            "updated_at": "2020-01-01T00:00:00Z",
            "date": "2025-03-01",
            "amount_ml": 500.0,
            "source": "garmin",
        }

        assert self._restore(db, user, [record]) == 1

        stored = health_water_crud.get_health_water_by_user_id(user.id, db)
        assert [(r.user_id, r.date, r.amount_ml, r.source, r.version) for r in stored] == [
            (user.id, date(2025, 3, 1), 500.0, "garmin", 1)
        ]
        assert stored[0].id != archived_id

    def test_a_record_that_is_invalid_is_skipped_and_the_rest_are_stored(self, db, user):
        records = [
            {"date": "2025-03-01", "amount_ml": "not a number"},
            {"date": "2025-03-02", "amount_ml": -1},
            {"date": "2025-03-03", "amount_ml": 500.0},
        ]

        assert self._restore(db, user, records) == 1

        assert [r.date for r in health_water_crud.get_health_water_by_user_id(user.id, db)] == [date(2025, 3, 3)]

    def test_a_record_for_a_day_the_user_has_updates_it(self, db, user):
        existing = make_health_water(db, user.id, date=date(2025, 3, 1), amount_ml=500.0)

        self._restore(db, user, [{"date": "2025-03-01", "amount_ml": 900.0}])

        stored = health_water_crud.get_health_water_by_user_id(user.id, db)
        assert [(r.id, r.amount_ml) for r in stored] == [(existing.id, 900.0)]

    def test_an_empty_archive_stores_nothing(self, db, user):
        assert self._restore(db, user, []) == 0
        assert db.scalar(sa.select(sa.func.count()).select_from(health_water_models.HealthWater)) == 0


class TestUpsert:
    def _upsert(self, db, user, **fields):
        record = health_water_schema.HealthWaterImport(**{"date": _DAY, "amount_ml": 500.0, **fields})
        return health_water_service.stage_upsert_health_water(user.id, record, db)

    def test_a_new_day_is_created_with_the_source_it_came_from(self, db, user):
        staged = self._upsert(db, user, source="garmin")

        assert (staged.source, staged.version) == ("garmin", 1)

    def test_a_day_that_has_a_record_is_updated_instead_of_conflicting(self, db, user):
        first = self._upsert(db, user, amount_ml=500.0, source="garmin")

        second = self._upsert(db, user, amount_ml=900.0, source="garmin")

        assert (second.id, second.amount_ml) == (first.id, 900.0)
        assert health_water_crud.get_health_water_number_by_user_id(user.id, db) == 1

    def test_without_a_date_the_record_is_for_the_users_today(self, db, user):
        assert self._upsert(db, user, date=None).date == _today()

    def test_another_users_record_of_the_day_is_left_alone(self, db, user, other):
        theirs = make_health_water(db, other.id, date=_DAY, amount_ml=1200.0)

        mine = self._upsert(db, user, amount_ml=500.0)

        assert mine.id != theirs.id
        assert float(_stored(db, theirs.id).amount_ml) == 1200.0
