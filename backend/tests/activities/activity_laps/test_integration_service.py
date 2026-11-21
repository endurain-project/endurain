"""What other modules do with laps: store parsed ones, export them for a profile archive and restore them from one."""

import uuid
from datetime import timedelta

import pydantic
import pytest

import modules.activities.activity_laps.crud as laps_crud
import modules.activities.activity_laps.integration_service as laps_integration
from tests._factories.activities import DEFAULT_START, make_activity, make_laps
from tests._factories.users import make_user


@pytest.fixture
def activity(db):
    return make_activity(db, make_user(db).id)


class TestIngestion:
    def test_parsed_laps_are_stored_for_the_new_activity(self, db, activity):
        contributor = laps_integration.ingestion_contributor()

        contributor.persist([{"start_time": DEFAULT_START, "total_distance": 500.0}], activity, db)

        [lap] = laps_crud.get_activity_laps(activity.id, db)
        assert (lap.start_time, lap.total_distance) == (DEFAULT_START, 500.0)

    def test_laps_of_another_shape_are_refused_before_anything_is_stored(self, db, activity):
        contributor = laps_integration.ingestion_contributor()

        with pytest.raises(pydantic.ValidationError):
            contributor.persist("not laps", activity, db)

        assert laps_crud.count_activity_laps(activity.id, db) == 0


class TestProfileArchive:
    def test_the_export_lists_the_laps_of_the_given_activities_only(self, db, activity):
        other = make_activity(db, make_user(db).id)
        make_laps(db, activity, [{"start_time": DEFAULT_START}])
        make_laps(db, other, [{"start_time": DEFAULT_START}])

        exported = laps_integration.profile_contributor().export([activity.id], db)

        assert [lap.activity_id for lap in exported] == [activity.id]

    def test_restore_re_keys_the_archived_laps_onto_the_new_activity_and_skips_other_activities(self, db, activity):
        archived_id = uuid.uuid4()
        records = [
            {"id": str(uuid.uuid4()), "activity_id": str(archived_id), "start_time": DEFAULT_START.isoformat()},
            {
                "activity_id": str(archived_id),
                "start_time": (DEFAULT_START + timedelta(minutes=5)).isoformat(),
                "total_distance": 800.0,
            },
            {"activity_id": str(uuid.uuid4()), "start_time": DEFAULT_START.isoformat()},
        ]

        restored = laps_integration.profile_contributor().restore(records, archived_id, activity, db)

        stored = laps_crud.get_activity_laps(activity.id, db)
        assert (restored, len(stored), stored[1].total_distance) == (2, 2, 800.0)

    def test_an_archived_lap_with_an_unknown_field_is_refused(self, db, activity):
        archived_id = uuid.uuid4()
        record = {"activity_id": str(archived_id), "start_time": DEFAULT_START.isoformat(), "bogus": 1}

        with pytest.raises(pydantic.ValidationError):
            laps_integration.profile_contributor().restore([record], archived_id, activity, db)


def test_other_modules_read_the_first_page_of_laps_of_an_activity_they_may_see(db, activity):
    make_laps(db, activity, [{"start_time": DEFAULT_START, "total_distance": 500.0}])

    page = laps_integration.list_for_activity(activity, activity.user_id, db)

    assert [lap.total_distance for lap in page.items] == [500.0]
