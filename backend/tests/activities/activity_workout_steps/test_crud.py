"""Workout steps are stored from parsed schemas and read back in message-index order, on the real database."""

import pytest

import modules.activities.activity_workout_steps.crud as steps_crud
import modules.activities.activity_workout_steps.models as steps_models
from tests._factories.activities import make_activity, make_workout_steps
from tests._factories.users import make_user


@pytest.fixture
def activity(db):
    return make_activity(db, make_user(db).id)


def _step(index: int, **fields) -> dict[str, object]:
    return {"message_index": index, "duration_type": "time", **fields}


class TestCreate:
    def test_a_step_keeps_every_field_it_was_given(self, db, activity):
        [stored] = make_workout_steps(
            db,
            activity,
            [
                _step(
                    0,
                    duration_value=300.0,
                    target_type="heart_rate",
                    target_value=150,
                    intensity="active",
                    notes="easy",
                    exercise_category=2,
                    exercise_name=5,
                    exercise_weight=12.5,
                    weight_display_unit="kilogram",
                    secondary_target_value="zone 2",
                )
            ],
        )

        row = steps_models.ActivityWorkoutSteps
        read = db.get(row, stored.id)
        assert (read.activity_id, read.message_index, read.duration_type) == (activity.id, 0, "time")
        assert (float(read.duration_value), read.target_type, read.target_value) == (300.0, "heart_rate", 150)
        assert (read.intensity, read.notes, read.exercise_category, read.exercise_name) == ("active", "easy", 2, 5)
        assert (float(read.exercise_weight), read.weight_display_unit, read.secondary_target_value) == (
            12.5,
            "kilogram",
            "zone 2",
        )

    def test_a_step_with_only_the_required_fields_stores_the_rest_as_null(self, db, activity):
        [stored] = make_workout_steps(db, activity, [_step(3)])

        assert (stored.duration_value, stored.target_type, stored.notes, stored.exercise_weight) == (
            None,
            None,
            None,
            None,
        )

    def test_no_steps_stores_nothing(self, db, activity):
        steps_crud.create_activity_workout_steps([], activity.id, db)

        assert steps_crud.count_activity_workout_steps(activity.id, db) == 0


class TestRead:
    def test_steps_come_in_message_index_order_whatever_order_they_were_stored_in(self, db, activity):
        make_workout_steps(db, activity, [_step(2), _step(0), _step(1)])

        indexes = [s.message_index for s in steps_crud.get_activity_workout_steps(activity.id, db)]

        assert indexes == [0, 1, 2]

    def test_a_page_holds_its_slice_and_the_count_covers_all_steps(self, db, activity):
        make_workout_steps(db, activity, [_step(i) for i in range(5)])

        page = steps_crud.get_activity_workout_steps(activity.id, db, page_number=2, num_records=2)

        assert [s.message_index for s in page] == [2, 3]
        assert steps_crud.count_activity_workout_steps(activity.id, db) == 5

    def test_another_activitys_steps_are_not_read_or_counted(self, db, activity):
        make_workout_steps(db, make_activity(db, make_user(db).id), [_step(0)])

        assert steps_crud.get_activity_workout_steps(activity.id, db) == []
        assert steps_crud.count_activity_workout_steps(activity.id, db) == 0

    def test_several_activities_are_read_at_once_and_none_reads_nothing(self, db, activity):
        other = make_activity(db, make_user(db).id)
        make_workout_steps(db, activity, [_step(0)])
        make_workout_steps(db, other, [_step(0), _step(1)])

        rows = steps_crud.get_activities_workout_steps([activity.id, other.id], db)

        assert sorted(s.activity_id == activity.id for s in rows) == [False, False, True]
        assert steps_crud.get_activities_workout_steps([], db) == []
