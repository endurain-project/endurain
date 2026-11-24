"""What other modules do with streams: store parsed ones, export them for a profile archive, restore them, read GPS."""

import uuid

import pydantic
import pytest

import modules.activities.activity_streams.constants as stream_constants
import modules.activities.activity_streams.contracts as stream_contracts
import modules.activities.activity_streams.crud as streams_crud
import modules.activities.activity_streams.integration_service as streams_integration
from tests._factories.activities import make_activity, make_stream
from tests._factories.users import make_user

_HR = stream_constants.STREAM_TYPE_HR
_MAP = stream_constants.STREAM_TYPE_MAP


@pytest.fixture
def activity(db):
    return make_activity(db, make_user(db).id)


class TestIngestion:
    def test_parsed_streams_are_stored_for_the_new_activity_with_plain_dict_samples(self, db, activity):
        parsed = [stream_contracts.ParsedStream(stream_type=_HR, stream_waypoints=[{"time": "t", "hr": 120}])]

        streams_integration.ingestion_contributor().persist(parsed, activity, db)

        [stored] = streams_crud.get_activity_streams(activity.id, db)
        assert (stored.stream_type, stored.stream_waypoints, stored.strava_activity_stream_id) == (
            _HR,
            [{"time": "t", "hr": 120}],
            None,
        )

    def test_streams_of_another_shape_are_refused_before_anything_is_stored(self, db, activity):
        with pytest.raises(pydantic.ValidationError):
            streams_integration.ingestion_contributor().persist([{"stream_type": _HR}], activity, db)

        assert streams_crud.get_activity_streams(activity.id, db) == []


class TestProfileArchive:
    def test_the_export_lists_the_streams_of_the_given_activities_only(self, db, activity):
        other = make_activity(db, make_user(db).id)
        make_stream(db, activity, _HR, [{"hr": 1}])
        make_stream(db, other, _HR, [{"hr": 2}])

        exported = streams_integration.profile_contributor().export([activity.id], db)

        assert [s.activity_id for s in exported] == [activity.id]

    def test_restore_re_keys_the_archived_streams_and_drops_stored_zones_and_other_activities(self, db, activity):
        archived_id = uuid.uuid4()
        records = [
            {
                "id": str(uuid.uuid4()),
                "activity_id": str(archived_id),
                "stream_type": _HR,
                "stream_waypoints": [{"hr": 1}],
                "strava_activity_stream_id": 9,
                "zone_percentages": {"hr": {}},
            },
            {"activity_id": str(uuid.uuid4()), "stream_type": _HR, "stream_waypoints": []},
        ]

        restored = streams_integration.profile_contributor().restore(records, archived_id, activity, db)

        [stored] = streams_crud.get_activity_streams(activity.id, db)
        assert (restored, stored.strava_activity_stream_id, stored.stream_waypoints) == (1, 9, [{"hr": 1}])

    def test_nothing_matching_is_restored_as_zero(self, db, activity):
        records = [{"activity_id": str(uuid.uuid4()), "stream_type": _HR, "stream_waypoints": []}]

        assert streams_integration.profile_contributor().restore(records, uuid.uuid4(), activity, db) == 0
        assert streams_crud.get_activity_streams(activity.id, db) == []

    def test_an_archived_stream_with_an_unknown_field_is_refused(self, db, activity):
        archived_id = uuid.uuid4()
        record = {"activity_id": str(archived_id), "stream_type": _HR, "stream_waypoints": [], "bogus": 1}

        with pytest.raises(pydantic.ValidationError):
            streams_integration.profile_contributor().restore([record], archived_id, activity, db)


class TestDerivation:
    def test_one_stream_is_read_unmasked_for_a_derived_artifact(self, db, activity):
        make_stream(db, activity, _MAP, [{"lat": 1.0, "lon": 2.0}])

        stream = streams_integration.get_stream_for_derivation(activity.id, _MAP, db)

        assert stream.stream_waypoints == [{"lat": 1.0, "lon": 2.0}]
        assert streams_integration.get_stream_for_derivation(activity.id, _HR, db) is None

    def test_the_gps_samples_of_several_activities_are_read_in_one_call(self, db, activity):
        make_stream(db, activity, _MAP, [{"lat": 1.0, "lon": 2.0}])

        found = streams_integration.get_gps_waypoints_for_activities([activity.id, uuid.uuid4()], db)

        assert found == {activity.id: [{"lat": 1.0, "lon": 2.0}]}
