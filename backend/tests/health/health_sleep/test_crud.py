"""The sleep records' persistence, on the real database."""

from datetime import UTC, date, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

import core.exceptions as core_exceptions
import modules.health.constants as health_constants
import modules.health.health_sleep.crud as health_sleep_crud
import modules.health.health_sleep.models as health_sleep_models
import modules.health.health_sleep.schema as health_sleep_schema
from tests._factories.health import make_health_sleep
from tests._factories.users import make_user

_DAY = date(2025, 3, 10)


def _stored(db, record_id):
    return db.get(health_sleep_models.HealthSleep, record_id)


@pytest.fixture
def user(db):
    return make_user(db)


@pytest.fixture
def other(db):
    return make_user(db)


class TestCreate:
    def test_the_record_is_stored_for_the_user_with_its_values(self, db, user):
        created = make_health_sleep(
            db, user.id, date=_DAY, total_sleep_seconds=27000, resting_heart_rate=48, avg_skin_temp_deviation=0.25
        )

        row = _stored(db, created.id)
        assert (row.user_id, row.date, row.total_sleep_seconds, row.resting_heart_rate, row.version) == (
            user.id,
            _DAY,
            27000,
            48,
            1,
        )
        assert (row.avg_skin_temp_deviation, row.source) == (0.25, "manual")

    def test_a_second_record_on_a_day_is_a_conflict(self, db, user):
        make_health_sleep(db, user.id, date=_DAY)

        with pytest.raises(core_exceptions.ConflictError, match="Duplicate entry"):
            make_health_sleep(db, user.id, date=_DAY)

    def test_the_database_holds_one_record_per_user_and_day(self, db, user):
        make_health_sleep(db, user.id, date=_DAY)

        with pytest.raises(IntegrityError, match="uq_health_sleep_user_date"):
            db.add(health_sleep_models.HealthSleep(user_id=user.id, date=_DAY))
            db.flush()

    def test_two_users_may_each_have_a_record_on_a_day(self, db, user, other):
        mine = make_health_sleep(db, user.id, date=_DAY)
        theirs = make_health_sleep(db, other.id, date=_DAY)

        assert mine.id != theirs.id

    def test_the_stages_are_stored_with_their_times(self, db, user):
        start = datetime(2025, 3, 9, 22, 0, tzinfo=UTC)
        stage = health_sleep_schema.HealthSleepStageWrite(
            stage_type=health_sleep_schema.SleepStageType.DEEP,
            start_time_gmt=start,
            end_time_gmt=start + timedelta(hours=1),
            duration_seconds=3600,
        )

        created = make_health_sleep(db, user.id, date=_DAY, sleep_stages=[stage])

        stages = health_sleep_crud.get_health_sleep_by_id(user.id, created.id, db).sleep_stages
        assert [(s.stage_type, s.start_time_gmt, s.duration_seconds) for s in stages] == [("deep", start, 3600)]

    def test_deleting_the_user_deletes_their_records(self, db, user):
        record = make_health_sleep(db, user.id)

        db.execute(sa.text("DELETE FROM users WHERE id = :id"), {"id": user.id})

        assert _stored(db, record.id) is None


class TestRead:
    def test_a_record_is_found_by_id_and_by_date(self, db, user):
        record = make_health_sleep(db, user.id, date=_DAY)

        assert health_sleep_crud.get_health_sleep_by_id(user.id, record.id, db).id == record.id
        assert health_sleep_crud.get_health_sleep_by_date_and_user_id(user.id, _DAY.isoformat(), db).id == record.id

    def test_another_users_record_is_not_found(self, db, user, other):
        theirs = make_health_sleep(db, other.id, date=_DAY)

        with pytest.raises(core_exceptions.NotFoundError, match="Health sleep not found"):
            health_sleep_crud.get_health_sleep_by_id(user.id, theirs.id, db)
        assert health_sleep_crud.get_health_sleep_by_date_and_user_id(user.id, _DAY.isoformat(), db) is None

    def test_the_count_and_the_list_cover_the_users_records_newest_first(self, db, user, other):
        days = [date(2025, 3, 2), date(2025, 3, 9), date(2025, 3, 5)]
        for day in days:
            make_health_sleep(db, user.id, date=day)
        make_health_sleep(db, other.id, date=date(2025, 3, 7))

        records = health_sleep_crud.get_health_sleep_by_user_id(user.id, db)

        assert [r.date for r in records] == sorted(days, reverse=True)
        assert health_sleep_crud.get_health_sleep_number_by_user_id(user.id, db) == 3

    def test_the_list_pages_and_the_bounds_are_inclusive(self, db, user):
        for day in range(1, 8):
            make_health_sleep(db, user.id, date=date(2025, 3, day))

        page = health_sleep_crud.get_health_sleep_by_user_id(user.id, db, 2, 2)
        bounded = health_sleep_crud.get_health_sleep_by_user_id(
            user.id, db, None, None, date(2025, 3, 3), date(2025, 3, 5)
        )

        assert [r.date for r in page] == [date(2025, 3, 5), date(2025, 3, 4)]
        assert [r.date for r in bounded] == [date(2025, 3, 5), date(2025, 3, 4), date(2025, 3, 3)]
        assert (
            health_sleep_crud.get_health_sleep_number_by_user_id(user.id, db, date(2025, 3, 3), date(2025, 3, 5)) == 3
        )

    def test_the_resting_heart_rate_filter_keeps_the_count_and_the_page_in_step(self, db, user):
        make_health_sleep(db, user.id, date=date(2025, 3, 1), resting_heart_rate=50)
        make_health_sleep(db, user.id, date=date(2025, 3, 2))
        make_health_sleep(db, user.id, date=date(2025, 3, 3), resting_heart_rate=52)

        with_rate = health_sleep_crud.get_health_sleep_list_items_by_user_id(user.id, db, has_resting_heart_rate=True)
        without = health_sleep_crud.get_health_sleep_list_items_by_user_id(user.id, db, has_resting_heart_rate=False)

        assert [i.date for i in with_rate] == [date(2025, 3, 3), date(2025, 3, 1)]
        assert [i.date for i in without] == [date(2025, 3, 2)]
        assert health_sleep_crud.get_health_sleep_number_by_user_id(user.id, db, has_resting_heart_rate=True) == 2
        assert health_sleep_crud.get_health_sleep_number_by_user_id(user.id, db, has_resting_heart_rate=False) == 1
        assert health_sleep_crud.get_health_sleep_number_by_user_id(user.id, db) == 3

    def test_a_list_item_flags_the_stages_without_carrying_them(self, db, user):
        start = datetime(2025, 3, 9, 22, 0, tzinfo=UTC)
        stage = health_sleep_schema.HealthSleepStageWrite(
            stage_type=health_sleep_schema.SleepStageType.REM,
            start_time_gmt=start,
            end_time_gmt=start + timedelta(hours=1),
            duration_seconds=3600,
        )
        make_health_sleep(db, user.id, date=date(2025, 3, 1), sleep_stages=[stage])
        make_health_sleep(db, user.id, date=date(2025, 3, 2))

        items = health_sleep_crud.get_health_sleep_list_items_by_user_id(user.id, db)

        assert [(i.date, i.has_sleep_stages) for i in items] == [(date(2025, 3, 2), False), (date(2025, 3, 1), True)]
        assert not hasattr(items[0], "sleep_stages")


class TestEditAndDelete:
    def test_the_given_fields_are_stored_the_others_kept_and_the_version_moves_on(self, db, user):
        record = make_health_sleep(db, user.id, date=_DAY, total_sleep_seconds=25200, resting_heart_rate=50)

        health_sleep_crud.edit_health_sleep(
            user.id, record.id, health_sleep_schema.HealthSleepUpdate(resting_heart_rate=47), db, if_match='"1"'
        )

        row = _stored(db, record.id)
        assert (row.resting_heart_rate, row.total_sleep_seconds, row.version) == (47, 25200, 2)

    def test_a_field_given_as_null_is_cleared(self, db, user):
        record = make_health_sleep(db, user.id, resting_heart_rate=50)

        health_sleep_crud.edit_health_sleep(
            user.id, record.id, health_sleep_schema.HealthSleepUpdate(resting_heart_rate=None), db, if_match='"1"'
        )

        assert _stored(db, record.id).resting_heart_rate is None

    def test_a_stale_version_is_refused_and_the_record_is_unchanged(self, db, user):
        record = make_health_sleep(db, user.id, resting_heart_rate=50)

        with pytest.raises(core_exceptions.PreconditionFailedError):
            health_sleep_crud.edit_health_sleep(
                user.id, record.id, health_sleep_schema.HealthSleepUpdate(resting_heart_rate=40), db, if_match='"4"'
            )

        assert (_stored(db, record.id).resting_heart_rate, _stored(db, record.id).version) == (50, 1)

    def test_another_users_record_is_not_found_and_unchanged(self, db, user, other):
        theirs = make_health_sleep(db, other.id, resting_heart_rate=50)

        with pytest.raises(core_exceptions.NotFoundError):
            health_sleep_crud.edit_health_sleep(
                user.id, theirs.id, health_sleep_schema.HealthSleepUpdate(resting_heart_rate=40), db, if_match='"1"'
            )
        with pytest.raises(core_exceptions.NotFoundError):
            health_sleep_crud.delete_health_sleep(user.id, theirs.id, db, if_match='"1"')

        assert _stored(db, theirs.id).resting_heart_rate == 50

    def test_the_record_is_deleted_with_the_current_version(self, db, user):
        record = make_health_sleep(db, user.id)

        health_sleep_crud.delete_health_sleep(user.id, record.id, db, if_match='"1"')

        assert _stored(db, record.id) is None

    def test_a_delete_with_a_stale_version_is_refused_and_the_record_stays(self, db, user):
        record = make_health_sleep(db, user.id)

        with pytest.raises(core_exceptions.PreconditionFailedError):
            health_sleep_crud.delete_health_sleep(user.id, record.id, db, if_match='"3"')

        assert _stored(db, record.id) is not None


class TestChart:
    def test_the_total_and_the_resting_heart_rate_are_averaged_per_day_and_empty_values_left_out(self, db, user, other):
        make_health_sleep(db, user.id, date=date(2025, 3, 1), total_sleep_seconds=20000, resting_heart_rate=50)
        make_health_sleep(db, user.id, date=date(2025, 3, 2), total_sleep_seconds=30000)
        make_health_sleep(db, other.id, date=date(2025, 3, 1), total_sleep_seconds=1, resting_heart_rate=99)

        day = health_constants.ChartBucket.DAY
        total = health_sleep_crud.get_health_sleep_chart(user.id, date(2025, 3, 1), date(2025, 3, 7), day, db)
        rate = health_sleep_crud.get_health_sleep_resting_heart_rate_chart(
            user.id, date(2025, 3, 1), date(2025, 3, 7), day, db
        )

        assert [(p.date, p.value) for p in total] == [(date(2025, 3, 1), 20000.0), (date(2025, 3, 2), 30000.0)]
        assert [(p.date, p.value) for p in rate] == [(date(2025, 3, 1), 50.0)]
