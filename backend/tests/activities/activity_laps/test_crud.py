"""Laps are stored from parsed dicts and read back in recorded order, page by page, on the real database."""

from datetime import timedelta

import pytest
from sqlalchemy.exc import IntegrityError

import modules.activities.activity_laps.crud as laps_crud
import modules.activities.activity_laps.models as laps_models
from tests._factories.activities import DEFAULT_START, make_activity, make_laps
from tests._factories.users import make_user


@pytest.fixture
def activity(db):
    return make_activity(db, make_user(db).id)


def _lap(minutes: int, **fields) -> dict[str, object]:
    return {"start_time": DEFAULT_START + timedelta(minutes=minutes), **fields}


class TestCreate:
    def test_a_lap_keeps_the_fields_it_was_given_and_stores_the_rest_as_null(self, db, activity):
        [stored] = make_laps(db, activity, [_lap(0, total_distance=1000.0, avg_heart_rate=150, lap_trigger="manual")])

        row = db.get(laps_models.ActivityLaps, stored.id)
        assert (row.activity_id, row.total_distance, row.avg_heart_rate, row.lap_trigger) == (
            activity.id,
            1000.0,
            150,
            "manual",
        )
        assert (row.avg_power, row.enhanced_avg_speed, row.start_position_lat) == (None, None, None)

    def test_no_laps_stores_nothing(self, db, activity):
        laps_crud.create_activity_laps([], activity.id, db)

        assert laps_crud.count_activity_laps(activity.id, db) == 0

    def test_a_lap_without_a_start_time_is_refused_by_the_database(self, db, activity):
        with pytest.raises(IntegrityError, match="start_time"):
            laps_crud.create_activity_laps([{"total_distance": 1.0}], activity.id, db)


class TestRead:
    def test_laps_come_in_start_order_whatever_order_they_were_stored_in(self, db, activity):
        make_laps(db, activity, [_lap(20), _lap(0), _lap(10)])

        starts = [lap.start_time for lap in laps_crud.get_activity_laps(activity.id, db)]

        assert starts == [DEFAULT_START + timedelta(minutes=m) for m in (0, 10, 20)]

    def test_a_page_holds_its_slice_and_the_count_covers_all_laps(self, db, activity):
        make_laps(db, activity, [_lap(m) for m in range(5)])

        page = laps_crud.get_activity_laps(activity.id, db, page_number=2, num_records=2)

        assert [lap.start_time for lap in page] == [DEFAULT_START + timedelta(minutes=m) for m in (2, 3)]
        assert laps_crud.count_activity_laps(activity.id, db) == 5

    def test_laps_of_laps_with_the_same_start_page_without_repeats(self, db, activity):
        make_laps(db, activity, [_lap(0, total_distance=float(n)) for n in range(4)])

        first = laps_crud.get_activity_laps(activity.id, db, page_number=1, num_records=2)
        second = laps_crud.get_activity_laps(activity.id, db, page_number=2, num_records=2)

        assert len({lap.id for lap in first + second}) == 4

    def test_another_activitys_laps_are_not_read_or_counted(self, db, activity):
        other = make_activity(db, make_user(db).id)
        make_laps(db, other, [_lap(0)])

        assert laps_crud.get_activity_laps(activity.id, db) == []
        assert laps_crud.count_activity_laps(activity.id, db) == 0

    def test_several_activities_are_read_at_once_and_none_reads_nothing(self, db, activity):
        other = make_activity(db, make_user(db).id)
        make_laps(db, activity, [_lap(0)])
        make_laps(db, other, [_lap(0), _lap(5)])

        rows = laps_crud.get_activities_laps([activity.id, other.id], db)

        assert sorted(lap.activity_id == activity.id for lap in rows) == [False, False, True]
        assert laps_crud.get_activities_laps([], db) == []
