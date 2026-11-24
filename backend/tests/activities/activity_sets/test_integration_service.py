"""What other modules do with workout sets: store parsed ones, export them for a profile archive and restore them."""

import uuid

import pydantic
import pytest

import modules.activities.activity_sets.contracts as sets_contracts
import modules.activities.activity_sets.crud as sets_crud
import modules.activities.activity_sets.integration_service as sets_integration
from tests._factories.activities import DEFAULT_START, make_activity, make_sets
from tests._factories.users import make_user

_SET = {"start_time": DEFAULT_START.isoformat(), "duration": 30.0, "set_type": "active"}


@pytest.fixture
def activity(db):
    return make_activity(db, make_user(db).id)


class TestIngestion:
    def test_parsed_sets_are_stored_whether_they_are_schemas_or_raw_fit_rows(self, db, activity):
        schema = sets_contracts.ActivitySetsCreate(activity_id=activity.id, **_SET)
        raw = [45.0, 8, 20.0, "rest", DEFAULT_START.replace(minute=5), (7, "x"), None]

        sets_integration.ingestion_contributor().persist([schema, raw], activity, db)

        stored = sets_crud.get_activity_sets(activity.id, db)
        assert [(s.set_type, s.category) for s in stored] == [("active", None), ("rest", 7)]

    def test_sets_of_another_shape_are_refused_before_anything_is_stored(self, db, activity):
        with pytest.raises(pydantic.ValidationError):
            sets_integration.ingestion_contributor().persist([{"duration": 1.0}], activity, db)

        assert sets_crud.count_activity_sets(activity.id, db) == 0


class TestProfileArchive:
    def test_the_export_lists_the_sets_of_the_given_activities_only(self, db, activity):
        other = make_activity(db, make_user(db).id)
        make_sets(db, activity, [_SET])
        make_sets(db, other, [_SET])

        exported = sets_integration.profile_contributor().export([activity.id], db)

        assert [s.activity_id for s in exported] == [activity.id]

    def test_restore_re_keys_the_archived_sets_onto_the_new_activity_and_skips_other_activities(self, db, activity):
        archived_id = uuid.uuid4()
        records = [
            {"id": str(uuid.uuid4()), "activity_id": str(archived_id), **_SET, "repetitions": 12},
            {"activity_id": str(uuid.uuid4()), **_SET},
        ]

        restored = sets_integration.profile_contributor().restore(records, archived_id, activity, db)

        [stored] = sets_crud.get_activity_sets(activity.id, db)
        assert (restored, stored.repetitions) == (1, 12)

    def test_an_archived_set_missing_a_required_field_is_refused(self, db, activity):
        archived_id = uuid.uuid4()

        with pytest.raises(pydantic.ValidationError):
            sets_integration.profile_contributor().restore(
                [{"activity_id": str(archived_id), "set_type": "active"}], archived_id, activity, db
            )


def test_other_modules_read_the_first_page_of_sets_of_an_activity_they_may_see(db, activity):
    make_sets(db, activity, [_SET])

    page = sets_integration.list_for_activity(activity, activity.user_id, db)

    assert [s.set_type for s in page.items] == ["active"]
