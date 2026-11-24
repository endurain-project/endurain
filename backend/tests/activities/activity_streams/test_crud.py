"""Streams are stored as the parsers hand them over and read back unchanged, on the real database."""

import pytest

import modules.activities.activity_streams.constants as stream_constants
import modules.activities.activity_streams.contracts as stream_contracts
import modules.activities.activity_streams.crud as streams_crud
from tests._factories.activities import make_activity, make_stream
from tests._factories.users import make_user

_HR = stream_constants.STREAM_TYPE_HR
_MAP = stream_constants.STREAM_TYPE_MAP


@pytest.fixture
def activity(db):
    return make_activity(db, make_user(db).id)


class TestCreate:
    def test_a_stream_keeps_its_samples_in_order_with_their_json_types(self, db, activity):
        waypoints = [{"time": "2025-03-10T08:00:01", "hr": 120, "x": None}, {"time": "2025-03-10T08:00:00", "hr": 0.5}]

        stored = make_stream(db, activity, _HR, waypoints)

        assert (stored.activity_id, stored.stream_type, stored.stream_waypoints) == (activity.id, _HR, waypoints)
        assert streams_crud.get_activity_streams(activity.id, db)[0].stream_waypoints == waypoints

    def test_the_strava_stream_id_is_kept(self, db, activity):
        streams_crud.create_activity_streams(
            [
                stream_contracts.ActivityStreamsCreate(
                    activity_id=activity.id, stream_type=_HR, stream_waypoints=[], strava_activity_stream_id=77
                )
            ],
            activity,
            db,
        )

        assert streams_crud.get_activity_stream_by_type(activity.id, _HR, db).strava_activity_stream_id == 77

    def test_no_streams_store_nothing(self, db, activity):
        streams_crud.create_activity_streams([], activity, db)

        assert streams_crud.get_activity_streams(activity.id, db) == []

    def test_streams_of_an_activity_without_an_owner_are_not_stored(self, db, activity):
        orphan = activity.model_copy(update={"user_id": None})

        streams_crud.create_activity_streams(
            [stream_contracts.ActivityStreamsCreate(activity_id=activity.id, stream_type=_HR, stream_waypoints=[])],
            orphan,
            db,
        )

        assert streams_crud.get_activity_streams(activity.id, db) == []


class TestRead:
    def test_an_activitys_streams_are_read_and_another_activitys_are_not(self, db, activity):
        other = make_activity(db, make_user(db).id)
        make_stream(db, activity, _HR, [{"hr": 1}])
        make_stream(db, activity, _MAP, [{"lat": 1.0, "lon": 2.0}])
        make_stream(db, other, _HR, [{"hr": 9}])

        streams = streams_crud.get_activity_streams(activity.id, db)

        assert sorted(s.stream_type for s in streams) == [_HR, _MAP]
        assert all(s.activity_id == activity.id for s in streams)

    def test_one_type_is_read_and_a_missing_type_is_none(self, db, activity):
        make_stream(db, activity, _HR, [{"hr": 1}])

        assert streams_crud.get_activity_stream_by_type(activity.id, _HR, db).stream_waypoints == [{"hr": 1}]
        assert streams_crud.get_activity_stream_by_type(activity.id, _MAP, db) is None

    def test_several_activities_are_read_at_once_and_none_reads_nothing(self, db, activity):
        other = make_activity(db, make_user(db).id)
        make_stream(db, activity, _HR, [{"hr": 1}])
        make_stream(db, other, _HR, [{"hr": 2}])

        streams = streams_crud.get_activities_streams([activity.id, other.id], db)

        assert sorted(s.activity_id == activity.id for s in streams) == [False, True]
        assert streams_crud.get_activities_streams([], db) == []
        assert streams_crud.get_activities_streams([make_activity(db, make_user(db).id).id], db) == []

    def test_gps_samples_are_read_per_activity_and_only_for_map_streams(self, db, activity):
        gps = [{"lat": 1.0, "lon": 2.0}, {"lat": 1.1, "lon": 2.1}]
        no_gps = make_activity(db, make_user(db).id)
        empty_gps = make_activity(db, make_user(db).id)
        make_stream(db, activity, _MAP, gps)
        make_stream(db, activity, _HR, [{"hr": 1}])
        make_stream(db, no_gps, _HR, [{"hr": 1}])
        make_stream(db, empty_gps, _MAP, [])

        found = streams_crud.get_gps_stream_waypoints_for_activities([activity.id, no_gps.id, empty_gps.id], db)

        assert found == {activity.id: gps, empty_gps.id: []}
        assert streams_crud.get_gps_stream_waypoints_for_activities([], db) == {}
