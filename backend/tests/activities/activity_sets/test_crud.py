"""Workout sets are stored from schemas or raw FIT rows and read back in start order, on the real database."""

from datetime import timedelta

import pytest

import modules.activities.activity_sets.crud as sets_crud
import modules.activities.activity_sets.models as sets_models
from tests._factories.activities import DEFAULT_START, make_activity, make_sets
from tests._factories.users import make_user


@pytest.fixture
def activity(db):
    return make_activity(db, make_user(db).id)


def _set(minutes: int, **fields) -> dict[str, object]:
    start = (DEFAULT_START + timedelta(minutes=minutes)).isoformat()
    return {"start_time": start, "duration": 30.0, "set_type": "active", **fields}


class TestCreate:
    def test_a_set_keeps_the_fields_it_was_given(self, db, activity):
        [stored] = make_sets(db, activity, [_set(0, repetitions=10, weight=42.5, category=3, category_subtype=4)])

        row = db.get(sets_models.ActivitySets, stored.id)
        assert (row.activity_id, row.repetitions, float(row.weight), row.category, row.category_subtype) == (
            activity.id,
            10,
            42.5,
            3,
            4,
        )
        assert (float(row.duration), row.set_type, row.start_time) == (30.0, "active", DEFAULT_START)

    def test_the_raw_rows_of_the_fit_parser_are_stored_with_their_tuple_values_unwrapped(self, db, activity):
        raw = [45.0, 8, 20.0, "active", DEFAULT_START, (7, "extra"), (None, "ignored")]

        sets_crud.create_activity_sets([raw], activity.id, db)

        [stored] = sets_crud.get_activity_sets(activity.id, db)
        assert (stored.duration, stored.repetitions, stored.weight, stored.set_type) == (45.0, 8, 20.0, "active")
        assert (stored.category, stored.category_subtype, stored.start_time) == (7, None, DEFAULT_START)

    def test_a_raw_row_with_plain_category_values_stores_them_as_they_are(self, db, activity):
        sets_crud.create_activity_sets([[10.0, 5, 10.0, "active", DEFAULT_START, 3, 4]], activity.id, db)

        [stored] = sets_crud.get_activity_sets(activity.id, db)
        assert (stored.category, stored.category_subtype) == (3, 4)

    def test_a_raw_row_with_no_category_stores_null(self, db, activity):
        sets_crud.create_activity_sets([[10.0, None, None, "rest", DEFAULT_START, None, None]], activity.id, db)

        [stored] = sets_crud.get_activity_sets(activity.id, db)
        assert (stored.category, stored.category_subtype, stored.repetitions) == (None, None, None)

    def test_no_sets_stores_nothing(self, db, activity):
        sets_crud.create_activity_sets([], activity.id, db)

        assert sets_crud.count_activity_sets(activity.id, db) == 0


class TestRead:
    def test_sets_come_in_start_order_whatever_order_they_were_stored_in(self, db, activity):
        make_sets(db, activity, [_set(20), _set(0), _set(10)])

        starts = [s.start_time for s in sets_crud.get_activity_sets(activity.id, db)]

        assert starts == [DEFAULT_START + timedelta(minutes=m) for m in (0, 10, 20)]

    def test_a_page_holds_its_slice_and_the_count_covers_all_sets(self, db, activity):
        make_sets(db, activity, [_set(m) for m in range(5)])

        page = sets_crud.get_activity_sets(activity.id, db, page_number=3, num_records=2)

        assert [s.start_time for s in page] == [DEFAULT_START + timedelta(minutes=4)]
        assert sets_crud.count_activity_sets(activity.id, db) == 5

    def test_another_activitys_sets_are_not_read_or_counted(self, db, activity):
        make_sets(db, make_activity(db, make_user(db).id), [_set(0)])

        assert sets_crud.get_activity_sets(activity.id, db) == []
        assert sets_crud.count_activity_sets(activity.id, db) == 0

    def test_several_activities_are_read_at_once_and_none_reads_nothing(self, db, activity):
        other = make_activity(db, make_user(db).id)
        make_sets(db, activity, [_set(0)])
        make_sets(db, other, [_set(0), _set(5)])

        rows = sets_crud.get_activities_sets([activity.id, other.id], db)

        assert sorted(s.activity_id == activity.id for s in rows) == [False, False, True]
        assert sets_crud.get_activities_sets([], db) == []
