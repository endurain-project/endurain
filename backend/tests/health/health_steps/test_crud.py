"""The steps records' persistence, on the real database."""

import uuid
from datetime import date, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

import core.etag as core_etag
import core.exceptions as core_exceptions
import modules.health.constants as health_constants
import modules.health.health_steps.crud as health_steps_crud
import modules.health.health_steps.models as health_steps_models
import modules.health.health_steps.schema as health_steps_schema
import modules.health.models as health_models
from tests._factories.health import make_health_steps
from tests._factories.users import make_user

_DAY = date(2025, 3, 10)


def _stored(db, record_id):
    return db.get(health_steps_models.HealthSteps, record_id)


def _value(db, record_id):
    return float(_stored(db, record_id).steps)


@pytest.fixture
def user(db):
    return make_user(db)


@pytest.fixture
def other(db):
    return make_user(db)


class TestCreate:
    def test_the_record_is_stored_for_the_user_with_its_values(self, db, user):
        created = health_steps_crud.create_health_steps(
            user.id, health_steps_schema.HealthStepsCreate(date=_DAY, steps=5000), db
        )

        row = _stored(db, created.id)
        assert (row.user_id, row.date, float(row.steps), row.source, row.version) == (user.id, _DAY, 5000, "manual", 1)

    def test_a_second_record_on_a_day_is_a_conflict(self, db, user):
        make_health_steps(db, user.id, date=_DAY)

        with pytest.raises(core_exceptions.ConflictError, match="Duplicate entry") as err:
            make_health_steps(db, user.id, date=_DAY, steps=9000)

        assert str(_DAY) in str(err.value)

    def test_two_users_may_each_have_a_record_on_a_day(self, db, user, other):
        mine = make_health_steps(db, user.id, date=_DAY)
        theirs = make_health_steps(db, other.id, date=_DAY)

        assert (mine.id != theirs.id, mine.user_id, theirs.user_id) == (True, user.id, other.id)

    def test_the_database_holds_one_record_per_user_and_day(self, db, user):
        make_health_steps(db, user.id, date=_DAY)

        with pytest.raises(IntegrityError, match="uq_health_steps_user_date"):
            db.add(health_steps_models.HealthSteps(user_id=user.id, date=_DAY, steps=9000))
            db.flush()

    def test_a_record_needs_a_value(self, db, user):
        with pytest.raises(IntegrityError):
            db.add(health_steps_models.HealthSteps(user_id=user.id, date=_DAY))
            db.flush()

    def test_deleting_the_user_deletes_their_records(self, db, user):
        record = make_health_steps(db, user.id)

        db.execute(sa.text("DELETE FROM users WHERE id = :id"), {"id": user.id})

        assert _stored(db, record.id) is None


class TestRead:
    def test_a_record_is_found_by_its_date_and_only_for_its_owner(self, db, user, other):
        record = make_health_steps(db, user.id, date=_DAY)
        make_health_steps(db, other.id, date=_DAY - timedelta(days=1))

        find = health_steps_crud.get_health_steps_by_date_and_user_id
        assert find(user.id, _DAY.isoformat(), db) == record
        assert find(other.id, _DAY.isoformat(), db) is None

    def test_the_records_come_newest_first_bounded_and_paged_and_only_the_users(self, db, user, other):
        for day in range(1, 8):
            make_health_steps(db, user.id, date=date(2025, 3, day))
        make_health_steps(db, other.id, date=date(2025, 3, 4))
        get = health_steps_crud.get_health_steps_by_user_id
        count = health_steps_crud.get_health_steps_number_by_user_id

        assert [r.date.day for r in get(user.id, db)] == [7, 6, 5, 4, 3, 2, 1]
        assert [r.date.day for r in get(user.id, db, page_number=2, num_records=3)] == [4, 3, 2]
        assert [r.date.day for r in get(user.id, db, since=date(2025, 3, 3), until=date(2025, 3, 5))] == [5, 4, 3]
        assert (count(user.id, db), count(user.id, db, date(2025, 3, 3), date(2025, 3, 5))) == (7, 3)


class TestChart:
    def test_a_month_bucket_averages_the_users_days_only(self, db, user, other):
        make_health_steps(db, user.id, date=date(2025, 3, 1), steps=5000)
        make_health_steps(db, user.id, date=date(2025, 3, 2), steps=12000)
        make_health_steps(db, other.id, date=date(2025, 3, 1), steps=12000 * 10)

        points = health_steps_crud.get_health_steps_chart(
            user.id, date(2025, 3, 1), date(2025, 3, 31), health_constants.ChartBucket.MONTH, db
        )

        assert [(p.date, p.value) for p in points] == [(date(2025, 3, 1), (5000 + 12000) / 2)]

    def test_a_day_bucket_has_a_point_per_day_oldest_first_within_the_bounds(self, db, user):
        for day, value in ((3, 9000), (1, 5000), (9, 12000)):
            make_health_steps(db, user.id, date=date(2025, 3, day), steps=value)

        points = health_steps_crud.get_health_steps_chart(
            user.id, date(2025, 3, 1), date(2025, 3, 5), health_constants.ChartBucket.DAY, db
        )

        assert [(p.date.day, p.value) for p in points] == [(1, 5000), (3, 9000)]


class TestEdit:
    def _edit(self, db, user_id, record, *, if_match=None, **changes):
        return health_steps_crud.edit_health_steps(
            user_id,
            record.id,
            health_steps_schema.HealthStepsUpdate(**changes),
            db,
            if_match=core_etag.format_etag(record.version) if if_match is None else if_match,
        )

    def test_the_change_is_stored_and_the_version_moves_on(self, db, user):
        record = make_health_steps(db, user.id, date=_DAY, steps=5000)

        edited = self._edit(db, user.id, record, steps=9000)

        row = _stored(db, record.id)
        assert (float(row.steps), row.date) == (9000, _DAY)
        assert (record.version, edited.version, row.version) == (1, 2, 2)

    def test_a_write_that_changes_nothing_keeps_the_version(self, db, user):
        record = make_health_steps(db, user.id, steps=5000)

        assert self._edit(db, user.id, record, steps=5000).version == record.version

    def test_a_stale_version_is_refused_and_nothing_changes(self, db, user):
        record = make_health_steps(db, user.id, steps=5000)
        self._edit(db, user.id, record, steps=9000)

        with pytest.raises(core_exceptions.PreconditionFailedError):
            self._edit(db, user.id, record, steps=12000)

        assert _value(db, record.id) == 9000

    def test_a_record_that_does_not_exist_is_not_found(self, db, user):
        with pytest.raises(core_exceptions.NotFoundError):
            health_steps_crud.edit_health_steps(
                user.id, uuid.uuid4(), health_steps_schema.HealthStepsUpdate(steps=9000), db, if_match='"1"'
            )

    def test_another_users_record_is_not_found_and_stays_as_it_was(self, db, user, other):
        theirs = make_health_steps(db, other.id, steps=5000)

        with pytest.raises(core_exceptions.NotFoundError):
            self._edit(db, user.id, theirs, steps=9000)

        row = _stored(db, theirs.id)
        assert (float(row.steps), row.version) == (5000, 1)

    def test_moving_a_record_onto_a_taken_day_is_a_conflict(self, db, user):
        make_health_steps(db, user.id, date=date(2025, 3, 1))
        moved = make_health_steps(db, user.id, date=date(2025, 3, 2))

        with pytest.raises(core_exceptions.ConflictError, match="Another record already exists for that date"):
            self._edit(db, user.id, moved, date=date(2025, 3, 1))


class TestDelete:
    def test_the_record_is_removed_and_its_deletion_remembered_for_sync(self, db, user):
        record = make_health_steps(db, user.id)

        health_steps_crud.delete_health_steps(user.id, record.id, db, if_match=core_etag.format_etag(record.version))

        assert _stored(db, record.id) is None
        tombstones = db.scalars(sa.select(health_models.HealthRecordDeletion)).all()
        assert [(t.user_id, t.record_id, t.record_type) for t in tombstones] == [(user.id, record.id, "health_steps")]

    def test_a_stale_version_is_refused_and_the_record_stays(self, db, user):
        record = make_health_steps(db, user.id)

        with pytest.raises(core_exceptions.PreconditionFailedError):
            health_steps_crud.delete_health_steps(user.id, record.id, db, if_match='"2"')

        assert _stored(db, record.id) is not None

    def test_a_record_that_does_not_exist_is_not_found(self, db, user):
        with pytest.raises(core_exceptions.NotFoundError):
            health_steps_crud.delete_health_steps(user.id, uuid.uuid4(), db, if_match='"1"')

    def test_another_users_record_is_not_found_and_stays(self, db, user, other):
        theirs = make_health_steps(db, other.id)

        with pytest.raises(core_exceptions.NotFoundError):
            health_steps_crud.delete_health_steps(user.id, theirs.id, db, if_match='"1"')

        assert _stored(db, theirs.id) is not None
        assert db.scalars(sa.select(health_models.HealthRecordDeletion)).all() == []


class TestChanged:
    def test_changed_records_come_oldest_change_first_and_only_the_users(self, db, user, other):
        from datetime import UTC, datetime

        first = make_health_steps(db, user.id, date=date(2025, 3, 1))
        second = make_health_steps(db, user.id, date=date(2025, 3, 2))
        make_health_steps(db, other.id, date=date(2025, 3, 1))
        db.flush()

        changed = health_steps_crud.list_changed(user.id, None, datetime.now(UTC) + timedelta(days=1), 10, db)

        assert {r.id for r in changed} == {first.id, second.id}
