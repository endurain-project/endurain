"""The bowel movement records' persistence, on the real database."""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
import sqlalchemy as sa

import core.etag as core_etag
import core.exceptions as core_exceptions
import modules.health.constants as health_constants
import modules.health.health_poop.crud as health_poop_crud
import modules.health.health_poop.models as health_poop_models
import modules.health.health_poop.schema as health_poop_schema
import modules.health.models as health_models
from tests._factories.health import make_health_poop
from tests._factories.users import make_user

_AT = datetime(2025, 3, 10, 12, 0, tzinfo=UTC)


def _stored(db, record_id):
    return db.get(health_poop_models.HealthPoop, record_id)


@pytest.fixture
def user(db):
    return make_user(db)


@pytest.fixture
def other(db):
    return make_user(db)


class TestCreate:
    def test_the_record_is_stored_for_the_user_with_its_values(self, db, user):
        created = health_poop_crud.create_health_poop(
            user.id,
            health_poop_schema.HealthPoopImport(date_time=_AT, bristol_type=4, color="brown", notes="fine"),
            db,
        )

        row = _stored(db, created.id)
        assert (row.user_id, row.date_time, row.bristol_type, row.color, row.notes, row.source, row.version) == (
            user.id,
            _AT,
            4,
            "brown",
            "fine",
            "manual",
            1,
        )

    def test_a_day_may_hold_several_records_even_at_the_same_instant(self, db, user):
        first = make_health_poop(db, user.id, date_time=_AT)
        second = make_health_poop(db, user.id, date_time=_AT)

        assert first.id != second.id

    def test_the_bristol_type_is_stored_as_its_scale_number_and_read_as_its_name(self, db, user):
        record = make_health_poop(db, user.id, bristol_type="type_6")

        assert (_stored(db, record.id).bristol_type, record.bristol_type) == (6, "type_6")

    def test_deleting_the_user_deletes_their_records(self, db, user):
        record = make_health_poop(db, user.id)

        db.execute(sa.text("DELETE FROM users WHERE id = :id"), {"id": user.id})

        assert _stored(db, record.id) is None


class TestExists:
    def test_a_record_at_the_exact_instant_is_found_only_for_its_owner(self, db, user, other):
        make_health_poop(db, user.id, date_time=_AT)

        assert health_poop_crud.health_poop_exists_at(user.id, _AT, db) is True
        assert health_poop_crud.health_poop_exists_at(user.id, _AT + timedelta(seconds=1), db) is False
        assert health_poop_crud.health_poop_exists_at(other.id, _AT, db) is False


class TestRead:
    def test_a_record_is_found_by_id_only_for_its_owner(self, db, user, other):
        record = make_health_poop(db, user.id)

        assert health_poop_crud.get_health_poop_by_id_and_user_id(record.id, user.id, db) == record
        assert health_poop_crud.get_health_poop_by_id_and_user_id(record.id, other.id, db) is None
        assert health_poop_crud.get_health_poop_by_id_and_user_id(uuid.uuid4(), user.id, db) is None

    def test_the_records_of_a_day_are_those_of_the_day_in_the_given_zone_newest_first(self, db, user, other):
        late = make_health_poop(db, user.id, date_time=datetime(2025, 3, 10, 23, 30, tzinfo=UTC))
        early = make_health_poop(db, user.id, date_time=datetime(2025, 3, 10, 1, 0, tzinfo=UTC))
        next_day = make_health_poop(db, user.id, date_time=datetime(2025, 3, 11, 1, 0, tzinfo=UTC))
        make_health_poop(db, other.id, date_time=datetime(2025, 3, 10, 12, 0, tzinfo=UTC))
        find = health_poop_crud.get_health_poop_by_date_and_user_id

        assert [r.id for r in find(user.id, "2025-03-10", "UTC", db)] == [late.id, early.id]
        # In Tokyo (UTC+9) the 23:30 instant is already the 11th and the 01:00 one the 10th.
        assert [r.id for r in find(user.id, "2025-03-11", "Asia/Tokyo", db)] == [next_day.id, late.id]
        assert [r.id for r in find(user.id, "2025-03-10", "Asia/Tokyo", db)] == [early.id]

    def test_the_list_is_newest_first_bounded_by_local_days_paged_and_only_the_users(self, db, user, other):
        for hour in (1, 13):
            for day in range(1, 5):
                make_health_poop(db, user.id, date_time=datetime(2025, 3, day, hour, 0, tzinfo=UTC))
        make_health_poop(db, other.id, date_time=datetime(2025, 3, 2, 1, 0, tzinfo=UTC))
        get = health_poop_crud.get_health_poop_by_user_id
        count = health_poop_crud.get_health_poop_number_by_user_id

        everything = get(user.id, db)
        assert [(r.date_time.day, r.date_time.hour) for r in everything][:3] == [(4, 13), (4, 1), (3, 13)]
        assert len(everything) == 8
        assert [r.date_time.day for r in get(user.id, db, page_number=2, num_records=3)] == [3, 2, 2]
        assert len(get(user.id, db, since=date(2025, 3, 2), until=date(2025, 3, 3))) == 4
        assert (count(user.id, db), count(user.id, db, date(2025, 3, 2), date(2025, 3, 3))) == (8, 4)

    def test_the_bounds_are_days_in_the_users_zone(self, db, user):
        make_health_poop(db, user.id, date_time=datetime(2025, 3, 10, 23, 30, tzinfo=UTC))

        in_utc = health_poop_crud.get_health_poop_number_by_user_id(user.id, db, date(2025, 3, 11), None, "UTC")
        in_tokyo = health_poop_crud.get_health_poop_number_by_user_id(
            user.id, db, date(2025, 3, 11), None, "Asia/Tokyo"
        )

        assert (in_utc, in_tokyo) == (0, 1)

    def test_the_first_day_is_the_earliest_local_day_of_the_user_or_none(self, db, user, other):
        make_health_poop(db, user.id, date_time=datetime(2025, 3, 10, 23, 30, tzinfo=UTC))
        make_health_poop(db, user.id, date_time=datetime(2025, 3, 12, 8, 0, tzinfo=UTC))

        first = health_poop_crud.get_health_poop_first_day
        assert first(user.id, "UTC", db) == date(2025, 3, 10)
        assert first(user.id, "Asia/Tokyo", db) == date(2025, 3, 11)
        assert first(other.id, "UTC", db) is None


class TestChart:
    def test_each_point_counts_the_movements_of_a_local_day_and_only_the_users(self, db, user, other):
        for hour in (6, 9, 22):
            make_health_poop(db, user.id, date_time=datetime(2025, 3, 1, hour, 0, tzinfo=UTC))
        make_health_poop(db, user.id, date_time=datetime(2025, 3, 3, 9, 0, tzinfo=UTC))
        make_health_poop(db, other.id, date_time=datetime(2025, 3, 1, 9, 0, tzinfo=UTC))

        points = health_poop_crud.get_health_poop_chart(
            user.id, date(2025, 3, 1), date(2025, 3, 31), health_constants.ChartBucket.DAY, "UTC", db
        )

        assert [(p.date, p.value) for p in points] == [(date(2025, 3, 1), 3.0), (date(2025, 3, 3), 1.0)]

    def test_a_movement_is_filed_under_the_day_it_happened_in_the_users_zone(self, db, user):
        make_health_poop(db, user.id, date_time=datetime(2025, 3, 1, 22, 0, tzinfo=UTC))

        points = health_poop_crud.get_health_poop_chart(
            user.id, date(2025, 3, 1), None, health_constants.ChartBucket.DAY, "Asia/Tokyo", db
        )

        assert [p.date for p in points] == [date(2025, 3, 2)]

    def test_a_month_bucket_counts_the_whole_month(self, db, user):
        for day in (1, 2, 20):
            make_health_poop(db, user.id, date_time=datetime(2025, 3, day, 9, 0, tzinfo=UTC))

        points = health_poop_crud.get_health_poop_chart(
            user.id, date(2025, 3, 1), date(2025, 3, 31), health_constants.ChartBucket.MONTH, "UTC", db
        )

        assert [(p.date, p.value) for p in points] == [(date(2025, 3, 1), 3.0)]


class TestEdit:
    def _edit(self, db, user_id, record, *, if_match=None, **changes):
        return health_poop_crud.edit_health_poop(
            user_id,
            record.id,
            health_poop_schema.HealthPoopUpdate(**changes),
            db,
            if_match=core_etag.format_etag(record.version) if if_match is None else if_match,
        )

    def test_only_the_fields_sent_change_and_the_version_moves_on(self, db, user):
        record = make_health_poop(db, user.id, notes="before", bristol_type=3)

        edited = self._edit(db, user.id, record, notes="after")

        row = _stored(db, record.id)
        assert (row.notes, row.bristol_type, row.date_time) == ("after", 3, datetime(2025, 1, 1, 12, 0, tzinfo=UTC))
        assert (record.version, edited.version, row.version) == (1, 2, 2)

    def test_an_optional_field_is_cleared_by_sending_null(self, db, user):
        record = make_health_poop(db, user.id, notes="note")

        self._edit(db, user.id, record, notes=None)

        assert _stored(db, record.id).notes is None

    def test_a_write_that_changes_nothing_keeps_the_version(self, db, user):
        record = make_health_poop(db, user.id, notes="same")

        assert self._edit(db, user.id, record, notes="same").version == record.version

    def test_a_stale_version_is_refused_and_nothing_changes(self, db, user):
        record = make_health_poop(db, user.id, notes="one")
        self._edit(db, user.id, record, notes="two")

        with pytest.raises(core_exceptions.PreconditionFailedError):
            self._edit(db, user.id, record, notes="three")

        assert _stored(db, record.id).notes == "two"

    def test_a_record_that_does_not_exist_is_not_found(self, db, user):
        with pytest.raises(core_exceptions.NotFoundError):
            health_poop_crud.edit_health_poop(
                user.id, uuid.uuid4(), health_poop_schema.HealthPoopUpdate(notes="x"), db, if_match='"1"'
            )

    def test_another_users_record_is_not_found_and_stays_as_it_was(self, db, user, other):
        theirs = make_health_poop(db, other.id, notes="theirs")

        with pytest.raises(core_exceptions.NotFoundError):
            self._edit(db, user.id, theirs, notes="mine")

        row = _stored(db, theirs.id)
        assert (row.notes, row.version) == ("theirs", 1)


class TestDelete:
    def test_the_record_is_removed_and_its_deletion_remembered_for_sync(self, db, user):
        record = make_health_poop(db, user.id)

        health_poop_crud.delete_health_poop(user.id, record.id, db, if_match=core_etag.format_etag(record.version))

        assert _stored(db, record.id) is None
        tombstones = db.scalars(sa.select(health_models.HealthRecordDeletion)).all()
        assert [(t.user_id, t.record_id, t.record_type) for t in tombstones] == [(user.id, record.id, "health_poop")]

    def test_a_stale_version_is_refused_and_the_record_stays(self, db, user):
        record = make_health_poop(db, user.id)

        with pytest.raises(core_exceptions.PreconditionFailedError):
            health_poop_crud.delete_health_poop(user.id, record.id, db, if_match='"2"')

        assert _stored(db, record.id) is not None

    def test_another_users_record_is_not_found_and_stays(self, db, user, other):
        theirs = make_health_poop(db, other.id)

        with pytest.raises(core_exceptions.NotFoundError):
            health_poop_crud.delete_health_poop(user.id, theirs.id, db, if_match='"1"')

        assert _stored(db, theirs.id) is not None
        assert db.scalars(sa.select(health_models.HealthRecordDeletion)).all() == []


class TestChanged:
    def test_changed_records_come_in_change_order_and_only_the_users(self, db, user, other):
        first = make_health_poop(db, user.id, date_time=_AT)
        second = make_health_poop(db, user.id, date_time=_AT + timedelta(hours=1))
        make_health_poop(db, other.id)

        changed = health_poop_crud.list_changed(user.id, None, datetime.now(UTC) + timedelta(days=1), 10, db)

        assert {r.id for r in changed} == {first.id, second.id}
