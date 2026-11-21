"""The water intake records' persistence, on the real database."""

import uuid
from datetime import date, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

import core.etag as core_etag
import core.exceptions as core_exceptions
import modules.health.constants as health_constants
import modules.health.health_water.crud as health_water_crud
import modules.health.health_water.models as health_water_models
import modules.health.health_water.schema as health_water_schema
import modules.health.models as health_models
from tests._factories.health import make_health_water
from tests._factories.users import make_user

_DAY = date(2025, 3, 10)


def _stored(db, record_id):
    return db.get(health_water_models.HealthWater, record_id)


def _value(db, record_id):
    return float(_stored(db, record_id).amount_ml)


@pytest.fixture
def user(db):
    return make_user(db)


@pytest.fixture
def other(db):
    return make_user(db)


class TestCreate:
    def test_the_record_is_stored_for_the_user_with_its_values(self, db, user):
        created = health_water_crud.create_health_water(
            user.id, health_water_schema.HealthWaterCreate(date=_DAY, amount_ml=500.0), db
        )

        row = _stored(db, created.id)
        assert (row.user_id, row.date, float(row.amount_ml), row.source, row.version) == (
            user.id,
            _DAY,
            500.0,
            "manual",
            1,
        )

    def test_a_second_record_on_a_day_is_a_conflict(self, db, user):
        make_health_water(db, user.id, date=_DAY)

        with pytest.raises(core_exceptions.ConflictError, match="Duplicate entry") as err:
            make_health_water(db, user.id, date=_DAY, amount_ml=900.0)

        assert str(_DAY) in str(err.value)

    def test_two_users_may_each_have_a_record_on_a_day(self, db, user, other):
        mine = make_health_water(db, user.id, date=_DAY)
        theirs = make_health_water(db, other.id, date=_DAY)

        assert (mine.id != theirs.id, mine.user_id, theirs.user_id) == (True, user.id, other.id)

    def test_the_database_holds_one_record_per_user_and_day(self, db, user):
        make_health_water(db, user.id, date=_DAY)

        with pytest.raises(IntegrityError, match="uq_health_water_user_date"):
            db.add(health_water_models.HealthWater(user_id=user.id, date=_DAY, amount_ml=900.0))
            db.flush()

    def test_a_record_needs_a_value(self, db, user):
        with pytest.raises(IntegrityError):
            db.add(health_water_models.HealthWater(user_id=user.id, date=_DAY))
            db.flush()

    def test_deleting_the_user_deletes_their_records(self, db, user):
        record = make_health_water(db, user.id)

        db.execute(sa.text("DELETE FROM users WHERE id = :id"), {"id": user.id})

        assert _stored(db, record.id) is None


class TestRead:
    def test_a_record_is_found_by_its_date_and_only_for_its_owner(self, db, user, other):
        record = make_health_water(db, user.id, date=_DAY)
        make_health_water(db, other.id, date=_DAY - timedelta(days=1))

        find = health_water_crud.get_health_water_by_date_and_user_id
        assert find(user.id, _DAY.isoformat(), db) == record
        assert find(other.id, _DAY.isoformat(), db) is None

    def test_the_records_come_newest_first_bounded_and_paged_and_only_the_users(self, db, user, other):
        for day in range(1, 8):
            make_health_water(db, user.id, date=date(2025, 3, day))
        make_health_water(db, other.id, date=date(2025, 3, 4))
        get = health_water_crud.get_health_water_by_user_id
        count = health_water_crud.get_health_water_number_by_user_id

        assert [r.date.day for r in get(user.id, db)] == [7, 6, 5, 4, 3, 2, 1]
        assert [r.date.day for r in get(user.id, db, page_number=2, num_records=3)] == [4, 3, 2]
        assert [r.date.day for r in get(user.id, db, since=date(2025, 3, 3), until=date(2025, 3, 5))] == [5, 4, 3]
        assert (count(user.id, db), count(user.id, db, date(2025, 3, 3), date(2025, 3, 5))) == (7, 3)


class TestChart:
    def test_a_month_bucket_averages_the_users_days_only(self, db, user, other):
        make_health_water(db, user.id, date=date(2025, 3, 1), amount_ml=500.0)
        make_health_water(db, user.id, date=date(2025, 3, 2), amount_ml=1200.0)
        make_health_water(db, other.id, date=date(2025, 3, 1), amount_ml=1200.0 * 10)

        points = health_water_crud.get_health_water_chart(
            user.id, date(2025, 3, 1), date(2025, 3, 31), health_constants.ChartBucket.MONTH, db
        )

        assert [(p.date, p.value) for p in points] == [(date(2025, 3, 1), (500.0 + 1200.0) / 2)]

    def test_a_day_bucket_has_a_point_per_day_oldest_first_within_the_bounds(self, db, user):
        for day, value in ((3, 900.0), (1, 500.0), (9, 1200.0)):
            make_health_water(db, user.id, date=date(2025, 3, day), amount_ml=value)

        points = health_water_crud.get_health_water_chart(
            user.id, date(2025, 3, 1), date(2025, 3, 5), health_constants.ChartBucket.DAY, db
        )

        assert [(p.date.day, p.value) for p in points] == [(1, 500.0), (3, 900.0)]


class TestEdit:
    def _edit(self, db, user_id, record, *, if_match=None, **changes):
        return health_water_crud.edit_health_water(
            user_id,
            record.id,
            health_water_schema.HealthWaterUpdate(**changes),
            db,
            if_match=core_etag.format_etag(record.version) if if_match is None else if_match,
        )

    def test_the_change_is_stored_and_the_version_moves_on(self, db, user):
        record = make_health_water(db, user.id, date=_DAY, amount_ml=500.0)

        edited = self._edit(db, user.id, record, amount_ml=900.0)

        row = _stored(db, record.id)
        assert (float(row.amount_ml), row.date) == (900.0, _DAY)
        assert (record.version, edited.version, row.version) == (1, 2, 2)

    def test_a_write_that_changes_nothing_keeps_the_version(self, db, user):
        record = make_health_water(db, user.id, amount_ml=500.0)

        assert self._edit(db, user.id, record, amount_ml=500.0).version == record.version

    def test_a_stale_version_is_refused_and_nothing_changes(self, db, user):
        record = make_health_water(db, user.id, amount_ml=500.0)
        self._edit(db, user.id, record, amount_ml=900.0)

        with pytest.raises(core_exceptions.PreconditionFailedError):
            self._edit(db, user.id, record, amount_ml=1200.0)

        assert _value(db, record.id) == 900.0

    def test_a_record_that_does_not_exist_is_not_found(self, db, user):
        with pytest.raises(core_exceptions.NotFoundError):
            health_water_crud.edit_health_water(
                user.id, uuid.uuid4(), health_water_schema.HealthWaterUpdate(amount_ml=900.0), db, if_match='"1"'
            )

    def test_another_users_record_is_not_found_and_stays_as_it_was(self, db, user, other):
        theirs = make_health_water(db, other.id, amount_ml=500.0)

        with pytest.raises(core_exceptions.NotFoundError):
            self._edit(db, user.id, theirs, amount_ml=900.0)

        row = _stored(db, theirs.id)
        assert (float(row.amount_ml), row.version) == (500.0, 1)

    def test_moving_a_record_onto_a_taken_day_is_a_conflict(self, db, user):
        make_health_water(db, user.id, date=date(2025, 3, 1))
        moved = make_health_water(db, user.id, date=date(2025, 3, 2))

        with pytest.raises(core_exceptions.ConflictError, match="Another record already exists for that date"):
            self._edit(db, user.id, moved, date=date(2025, 3, 1))


class TestDelete:
    def test_the_record_is_removed_and_its_deletion_remembered_for_sync(self, db, user):
        record = make_health_water(db, user.id)

        health_water_crud.delete_health_water(user.id, record.id, db, if_match=core_etag.format_etag(record.version))

        assert _stored(db, record.id) is None
        tombstones = db.scalars(sa.select(health_models.HealthRecordDeletion)).all()
        assert [(t.user_id, t.record_id, t.record_type) for t in tombstones] == [(user.id, record.id, "health_water")]

    def test_a_stale_version_is_refused_and_the_record_stays(self, db, user):
        record = make_health_water(db, user.id)

        with pytest.raises(core_exceptions.PreconditionFailedError):
            health_water_crud.delete_health_water(user.id, record.id, db, if_match='"2"')

        assert _stored(db, record.id) is not None

    def test_a_record_that_does_not_exist_is_not_found(self, db, user):
        with pytest.raises(core_exceptions.NotFoundError):
            health_water_crud.delete_health_water(user.id, uuid.uuid4(), db, if_match='"1"')

    def test_another_users_record_is_not_found_and_stays(self, db, user, other):
        theirs = make_health_water(db, other.id)

        with pytest.raises(core_exceptions.NotFoundError):
            health_water_crud.delete_health_water(user.id, theirs.id, db, if_match='"1"')

        assert _stored(db, theirs.id) is not None
        assert db.scalars(sa.select(health_models.HealthRecordDeletion)).all() == []


class TestChanged:
    def test_changed_records_come_oldest_change_first_and_only_the_users(self, db, user, other):
        from datetime import UTC, datetime

        first = make_health_water(db, user.id, date=date(2025, 3, 1))
        second = make_health_water(db, user.id, date=date(2025, 3, 2))
        make_health_water(db, other.id, date=date(2025, 3, 1))
        db.flush()

        changed = health_water_crud.list_changed(user.id, None, datetime.now(UTC) + timedelta(days=1), 10, db)

        assert {r.id for r in changed} == {first.id, second.id}
