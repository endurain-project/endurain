"""The weight records' persistence, on the real database."""

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from tests._factories.health import make_health_weight
from tests._factories.users import make_user

import core.exceptions as core_exceptions
import modules.health.constants as health_constants
import modules.health.health_weight.crud as health_weight_crud
import modules.health.health_weight.models as health_weight_models
import modules.health.health_weight.schema as health_weight_schema
import modules.health.models as health_models

_DAY = date(2025, 3, 10)


def _stored(db, record_id):
    return db.get(health_weight_models.HealthWeight, record_id)


@pytest.fixture
def user(db):
    return make_user(db)


@pytest.fixture
def other(db):
    return make_user(db)


class TestCreate:
    def test_the_record_is_stored_for_the_user_with_its_values(self, db, user):
        created = health_weight_crud.create_health_weight(
            user.id,
            health_weight_schema.HealthWeightCreate(
                date=_DAY, weight_kg=71.25, body_fat_percent=18.5, physique_rating=4
            ),
            db,
        )

        row = _stored(db, created.id)
        assert (row.user_id, row.date, row.weight_kg, row.body_fat_percent, row.physique_rating) == (
            user.id,
            _DAY,
            Decimal("71.25"),
            Decimal("18.50"),
            4,
        )
        assert (row.source, row.version, row.bmi) == ("manual", 1, None)

    def test_a_second_record_on_a_day_is_a_conflict(self, db, user):
        make_health_weight(db, user.id, date=_DAY)

        with pytest.raises(core_exceptions.ConflictError, match="Duplicate entry") as err:
            make_health_weight(db, user.id, date=_DAY, weight_kg=80.0)

        assert str(_DAY) in str(err.value)

    def test_two_users_may_each_have_a_record_on_a_day(self, db, user, other):
        mine = make_health_weight(db, user.id, date=_DAY)
        theirs = make_health_weight(db, other.id, date=_DAY)

        assert mine.id != theirs.id
        assert (mine.user_id, theirs.user_id) == (user.id, other.id)

    def test_the_database_holds_one_record_per_user_and_day(self, db, user):
        make_health_weight(db, user.id, date=_DAY)

        with pytest.raises(IntegrityError, match="uq_health_weight_user_date"):
            db.add(health_weight_models.HealthWeight(user_id=user.id, date=_DAY, weight_kg=Decimal(80)))
            db.flush()

    def test_a_record_needs_a_weight(self, db, user):
        with pytest.raises(IntegrityError):
            db.add(health_weight_models.HealthWeight(user_id=user.id, date=_DAY))
            db.flush()

    def test_deleting_the_user_deletes_their_records(self, db, user):
        record = make_health_weight(db, user.id)

        db.execute(sa.text("DELETE FROM users WHERE id = :id"), {"id": user.id})

        assert _stored(db, record.id) is None


class TestRead:
    def test_a_record_is_found_by_its_date(self, db, user):
        record = make_health_weight(db, user.id, date=_DAY)
        make_health_weight(db, user.id, date=_DAY - timedelta(days=1))

        assert health_weight_crud.get_health_weight_by_date_and_user_id(user.id, _DAY.isoformat(), db) == record

    def test_a_date_without_a_record_has_none(self, db, user):
        assert health_weight_crud.get_health_weight_by_date_and_user_id(user.id, _DAY.isoformat(), db) is None

    def test_another_users_record_is_not_found_by_date(self, db, user, other):
        make_health_weight(db, other.id, date=_DAY)

        assert health_weight_crud.get_health_weight_by_date_and_user_id(user.id, _DAY.isoformat(), db) is None

    def test_the_latest_record_is_the_newest_on_or_before_the_day(self, db, user):
        make_health_weight(db, user.id, date=date(2025, 3, 1), weight_kg=70.0)
        newest = make_health_weight(db, user.id, date=date(2025, 3, 8), weight_kg=71.0)
        make_health_weight(db, user.id, date=date(2025, 3, 20), weight_kg=99.0)

        assert health_weight_crud.get_latest_weight_by_user_id(user.id, date(2025, 3, 10), db) == newest

    def test_a_record_on_the_day_itself_is_the_latest(self, db, user):
        on_the_day = make_health_weight(db, user.id, date=_DAY)

        assert health_weight_crud.get_latest_weight_by_user_id(user.id, _DAY, db) == on_the_day

    def test_there_is_no_latest_when_every_record_is_after_the_day(self, db, user):
        make_health_weight(db, user.id, date=date(2025, 3, 20))

        assert health_weight_crud.get_latest_weight_by_user_id(user.id, _DAY, db) is None

    def test_the_latest_never_belongs_to_another_user(self, db, user, other):
        make_health_weight(db, other.id, date=_DAY)

        assert health_weight_crud.get_latest_weight_by_user_id(user.id, _DAY, db) is None

    def test_all_records_come_newest_first_and_only_the_users(self, db, user, other):
        days = [date(2025, 3, 2), date(2025, 3, 9), date(2025, 3, 5)]
        for day in days:
            make_health_weight(db, user.id, date=day)
        make_health_weight(db, other.id, date=date(2025, 3, 7))

        records = health_weight_crud.get_all_health_weight_by_user_id(user.id, db)

        assert [r.date for r in records] == sorted(days, reverse=True)
        assert {r.user_id for r in records} == {user.id}


class TestList:
    @pytest.fixture
    def ten_days(self, db, user):
        for offset in range(10):
            make_health_weight(db, user.id, date=date(2025, 3, 1) + timedelta(days=offset))

    def _dates(self, db, user, **kwargs):
        return [r.date.day for r in health_weight_crud.get_health_weight_by_user_id(user.id, db, **kwargs)]

    @pytest.mark.usefixtures("ten_days")
    def test_without_paging_every_record_comes_newest_first(self, db, user):
        assert self._dates(db, user) == list(range(10, 0, -1))

    @pytest.mark.usefixtures("ten_days")
    @pytest.mark.parametrize(
        ("page_number", "expected"),
        [(1, [10, 9, 8, 7]), (2, [6, 5, 4, 3]), (3, [2, 1]), (4, [])],
    )
    def test_a_page_holds_its_slice_of_the_newest_first_list(self, db, user, page_number, expected):
        assert self._dates(db, user, page_number=page_number, num_records=4) == expected

    @pytest.mark.usefixtures("ten_days")
    def test_both_bounds_are_inclusive(self, db, user):
        assert self._dates(db, user, since=date(2025, 3, 3), until=date(2025, 3, 5)) == [5, 4, 3]

    @pytest.mark.usefixtures("ten_days")
    def test_one_bound_leaves_the_other_side_open(self, db, user):
        assert self._dates(db, user, since=date(2025, 3, 9)) == [10, 9]
        assert self._dates(db, user, until=date(2025, 3, 2)) == [2, 1]

    @pytest.mark.usefixtures("ten_days")
    def test_the_count_follows_the_same_bounds(self, db, user):
        count = health_weight_crud.get_health_weight_number_by_user_id

        assert count(user.id, db) == 10
        assert count(user.id, db, date(2025, 3, 3), date(2025, 3, 5)) == 3
        assert count(user.id, db, since=date(2025, 3, 9)) == 2

    @pytest.mark.usefixtures("ten_days")
    def test_another_user_sees_none_of_them(self, db, other):
        assert self._dates(db, other) == []
        assert health_weight_crud.get_health_weight_number_by_user_id(other.id, db) == 0


class TestChart:
    def test_a_day_with_several_values_is_one_averaged_point_and_only_the_users_count(self, db, user, other):
        make_health_weight(db, user.id, date=date(2025, 3, 1), weight_kg=70.0)
        make_health_weight(db, user.id, date=date(2025, 3, 2), weight_kg=72.0)
        make_health_weight(db, other.id, date=date(2025, 3, 1), weight_kg=120.0)

        points = health_weight_crud.get_health_weight_chart(
            user.id, date(2025, 3, 1), date(2025, 3, 31), health_constants.ChartBucket.MONTH, db
        )

        assert [(p.date, p.value) for p in points] == [(date(2025, 3, 1), 71.0)]

    def test_a_day_bucket_has_a_point_per_day_oldest_first_within_the_bounds(self, db, user):
        for day, kg in ((3, 72.0), (1, 70.0), (9, 90.0)):
            make_health_weight(db, user.id, date=date(2025, 3, day), weight_kg=kg)

        points = health_weight_crud.get_health_weight_chart(
            user.id, date(2025, 3, 1), date(2025, 3, 5), health_constants.ChartBucket.DAY, db
        )

        assert [(p.date.day, p.value) for p in points] == [(1, 70.0), (3, 72.0)]


class TestEdit:
    def _edit(self, db, user_id, record, *, if_match=None, **changes):
        return health_weight_crud.edit_health_weight(
            user_id,
            record.id,
            health_weight_schema.HealthWeightUpdate(**changes),
            db,
            if_match=str(record.version) if if_match is None else if_match,
        )

    def test_only_the_fields_sent_change_and_the_version_moves_on(self, db, user):
        record = make_health_weight(db, user.id, date=_DAY, weight_kg=70.0, body_fat_percent=20.0)

        edited = self._edit(db, user.id, record, weight_kg=68.5)

        row = _stored(db, record.id)
        assert (row.weight_kg, row.body_fat_percent, row.date) == (Decimal("68.50"), Decimal("20.00"), _DAY)
        assert (record.version, edited.version, row.version) == (1, 2, 2)

    def test_an_optional_field_is_cleared_by_sending_null(self, db, user):
        record = make_health_weight(db, user.id, body_fat_percent=20.0)

        self._edit(db, user.id, record, body_fat_percent=None)

        assert _stored(db, record.id).body_fat_percent is None

    def test_a_write_that_changes_nothing_keeps_the_version(self, db, user):
        record = make_health_weight(db, user.id, weight_kg=70.3)

        edited = self._edit(db, user.id, record, weight_kg=70.3)

        assert edited.version == record.version

    def test_a_stale_version_is_refused_and_nothing_changes(self, db, user):
        record = make_health_weight(db, user.id, weight_kg=70.0)
        self._edit(db, user.id, record, weight_kg=71.0)

        with pytest.raises(core_exceptions.PreconditionFailedError):
            self._edit(db, user.id, record, weight_kg=99.0)

        assert _stored(db, record.id).weight_kg == Decimal("71.00")

    def test_a_record_that_does_not_exist_is_not_found(self, db, user):
        record = make_health_weight(db, user.id)

        with pytest.raises(core_exceptions.NotFoundError):
            health_weight_crud.edit_health_weight(
                user.id, uuid.uuid4(), health_weight_schema.HealthWeightUpdate(weight_kg=1.0), db, if_match="1"
            )
        assert _stored(db, record.id).weight_kg == Decimal("75.00")

    def test_another_users_record_is_not_found_and_stays_as_it_was(self, db, user, other):
        theirs = make_health_weight(db, other.id, weight_kg=75.0)

        with pytest.raises(core_exceptions.NotFoundError):
            self._edit(db, user.id, theirs, weight_kg=1.0)

        row = _stored(db, theirs.id)
        assert (row.weight_kg, row.version) == (Decimal("75.00"), 1)

    def test_moving_a_record_onto_a_taken_day_is_a_conflict(self, db, user):
        make_health_weight(db, user.id, date=date(2025, 3, 1))
        moved = make_health_weight(db, user.id, date=date(2025, 3, 2))

        with pytest.raises(core_exceptions.ConflictError, match="Another record already exists for that date"):
            self._edit(db, user.id, moved, date=date(2025, 3, 1))


class TestDelete:
    def test_the_record_is_removed_and_its_deletion_remembered_for_sync(self, db, user):
        record = make_health_weight(db, user.id)

        health_weight_crud.delete_health_weight(user.id, record.id, db, if_match=str(record.version))

        assert _stored(db, record.id) is None
        tombstones = db.scalars(sa.select(health_models.HealthRecordDeletion)).all()
        assert [(t.user_id, t.record_id, t.record_type) for t in tombstones] == [(user.id, record.id, "health_weight")]

    def test_a_stale_version_is_refused_and_the_record_stays(self, db, user):
        record = make_health_weight(db, user.id)

        with pytest.raises(core_exceptions.PreconditionFailedError):
            health_weight_crud.delete_health_weight(user.id, record.id, db, if_match="2")

        assert _stored(db, record.id) is not None

    def test_a_record_that_does_not_exist_is_not_found(self, db, user):
        with pytest.raises(core_exceptions.NotFoundError):
            health_weight_crud.delete_health_weight(user.id, uuid.uuid4(), db, if_match="1")

    def test_another_users_record_is_not_found_and_stays(self, db, user, other):
        theirs = make_health_weight(db, other.id)

        with pytest.raises(core_exceptions.NotFoundError):
            health_weight_crud.delete_health_weight(user.id, theirs.id, db, if_match="1")

        assert _stored(db, theirs.id) is not None
        assert db.scalars(sa.select(health_models.HealthRecordDeletion)).all() == []
