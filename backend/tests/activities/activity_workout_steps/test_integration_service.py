"""What other modules do with workout steps: store parsed ones, export them for a profile archive and restore them."""

import uuid

import pydantic
import pytest

import modules.activities.activity_workout_steps.contracts as steps_contracts
import modules.activities.activity_workout_steps.crud as steps_crud
import modules.activities.activity_workout_steps.integration_service as steps_integration
from tests._factories.activities import make_activity, make_workout_steps
from tests._factories.users import make_user

_STEP = {"message_index": 0, "duration_type": "time"}


@pytest.fixture
def activity(db):
    return make_activity(db, make_user(db).id)


class TestIngestion:
    def test_parsed_steps_are_stored_for_the_new_activity(self, db, activity):
        parsed = [steps_contracts.ActivityWorkoutStepsCreate(**_STEP, notes="go")]

        steps_integration.ingestion_contributor().persist(parsed, activity, db)

        assert [s.notes for s in steps_crud.get_activity_workout_steps(activity.id, db)] == ["go"]

    def test_steps_of_another_shape_are_refused_before_anything_is_stored(self, db, activity):
        with pytest.raises(pydantic.ValidationError):
            steps_integration.ingestion_contributor().persist([_STEP], activity, db)

        assert steps_crud.count_activity_workout_steps(activity.id, db) == 0


class TestProfileArchive:
    def test_the_export_lists_the_steps_of_the_given_activities_only(self, db, activity):
        other = make_activity(db, make_user(db).id)
        make_workout_steps(db, activity, [_STEP])
        make_workout_steps(db, other, [_STEP])

        exported = steps_integration.profile_contributor().export([activity.id], db)

        assert [s.activity_id for s in exported] == [activity.id]

    def test_restore_re_keys_the_archived_steps_onto_the_new_activity_and_skips_other_activities(self, db, activity):
        archived_id = uuid.uuid4()
        records = [
            {"id": str(uuid.uuid4()), "activity_id": str(archived_id), **_STEP, "notes": "kept"},
            {"activity_id": str(uuid.uuid4()), **_STEP},
        ]

        restored = steps_integration.profile_contributor().restore(records, archived_id, activity, db)

        [stored] = steps_crud.get_activity_workout_steps(activity.id, db)
        assert (restored, stored.notes) == (1, "kept")

    def test_an_archived_step_with_an_unknown_field_is_refused(self, db, activity):
        archived_id = uuid.uuid4()

        with pytest.raises(pydantic.ValidationError):
            steps_integration.profile_contributor().restore(
                [{"activity_id": str(archived_id), **_STEP, "bogus": 1}], archived_id, activity, db
            )


def test_other_modules_read_the_first_page_of_steps_of_an_activity_they_may_see(db, activity):
    make_workout_steps(db, activity, [_STEP])

    page = steps_integration.list_for_activity(activity, activity.user_id, db)

    assert page.total == 1
