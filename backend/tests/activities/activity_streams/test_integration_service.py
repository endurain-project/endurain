"""What other modules do with streams: store parsed ones, export them for a profile archive, restore them, read GPS."""

import uuid

import pydantic
import pytest

import modules.activities.activity_streams.constants as stream_constants
import modules.activities.activity_streams.crud as streams_crud
import modules.activities.activity_streams.integration_service as streams_integration
from tests._factories.activities import make_activity, make_multisport, make_samples, make_stream
from tests._factories.users import make_user

_HR = stream_constants.STREAM_TYPE_HR
_MAP = stream_constants.STREAM_TYPE_MAP


@pytest.fixture
def activity(db):
    return make_activity(db, make_user(db).id)


def _old_map(db, activity, points):
    make_stream(
        db,
        activity,
        _MAP,
        [{"time": f"2025-03-10T08:00:{i:02d}", "lat": lat, "lon": lon} for i, (lat, lon) in enumerate(points)],
    )


class TestProfileArchive:
    def test_the_export_lists_the_samples_of_the_given_activities_only(self, db, activity):
        other = make_activity(db, make_user(db).id)
        make_samples(db, activity, [0, 1000], heart_rate=[100.0, 110.0])
        make_samples(db, other, [0], heart_rate=[2.0])

        exported = streams_integration.profile_contributor().export([activity.id], db)

        assert [(r.activity_id, r.offsets_ms, r.heart_rate, r.power) for r in exported] == [
            (activity.id, [0, 1000], [100.0, 110.0], None)
        ]

    def test_the_export_converts_the_old_streams_of_an_activity_the_reprocess_has_not_reached(self, db, activity):
        make_stream(
            db, activity, _HR, [{"time": "2025-03-10T08:00:00", "hr": 120}, {"time": "2025-03-10T08:00:03", "hr": 121}]
        )

        [exported] = streams_integration.profile_contributor().export([activity.id], db)

        assert (exported.offsets_ms, exported.heart_rate) == ([0, 3000], [120.0, 121.0])

    def test_an_activity_with_neither_samples_nor_streams_is_not_exported(self, db, activity):
        assert streams_integration.profile_contributor().export([activity.id], db) == []

    def test_restore_re_keys_the_archived_samples_and_skips_other_activities(self, db, activity):
        archived_id = uuid.uuid4()
        records = [
            {"activity_id": str(archived_id), "offsets_ms": [0, 500], "speed": [2.0, None]},
            {"activity_id": str(uuid.uuid4()), "offsets_ms": [0]},
        ]

        restored = streams_integration.profile_contributor().restore(records, archived_id, activity, db)

        stored = streams_crud.get_activity_samples(activity.id, db)
        assert restored == 1
        assert stored is not None
        assert (stored.offsets_ms, stored.speed) == ([0, 500], [2.0, None])

    def test_nothing_matching_is_restored_as_zero(self, db, activity):
        records = [{"activity_id": str(uuid.uuid4()), "offsets_ms": [0]}]

        assert streams_integration.profile_contributor().restore(records, uuid.uuid4(), activity, db) == 0
        assert streams_crud.get_activity_samples(activity.id, db) is None

    def test_an_archived_record_with_an_unknown_field_is_refused(self, db, activity):
        archived_id = uuid.uuid4()
        record = {"activity_id": str(archived_id), "offsets_ms": [0], "bogus": 1}

        with pytest.raises(pydantic.ValidationError):
            streams_integration.profile_contributor().restore([record], archived_id, activity, db)

    def test_an_old_archive_of_streams_restores_as_samples_and_stored_zones_are_dropped(self, db, activity):
        archived_id = uuid.uuid4()
        records = [
            {
                "id": str(uuid.uuid4()),
                "activity_id": str(archived_id),
                "stream_type": _HR,
                "stream_waypoints": [{"time": "2025-03-10T08:00:00", "hr": 1}],
                "strava_activity_stream_id": 9,
                "zone_percentages": {"hr": {}},
            },
            {"activity_id": str(uuid.uuid4()), "stream_type": _HR, "stream_waypoints": []},
        ]

        restored = streams_integration.legacy_profile_contributor().restore(records, archived_id, activity, db)

        stored = streams_crud.get_activity_samples(activity.id, db)
        assert restored == 1
        assert stored is not None
        assert (stored.offsets_ms, stored.heart_rate) == ([0], [1.0])
        assert streams_crud.get_activity_streams(activity.id, db) == []

    def test_an_old_archived_stream_with_an_unknown_field_is_refused(self, db, activity):
        archived_id = uuid.uuid4()
        record = {"activity_id": str(archived_id), "stream_type": _HR, "stream_waypoints": [], "bogus": 1}

        with pytest.raises(pydantic.ValidationError):
            streams_integration.legacy_profile_contributor().restore([record], archived_id, activity, db)


class TestRoutesFromOldStreams:
    def test_an_activity_with_samples_has_its_route_from_them(self, db, activity):
        make_samples(db, activity, [0, 1000], latitude=[1.0, 2.0], longitude=[3.0, 4.0])

        found = streams_integration.get_routes_for_reprocess([activity.id, uuid.uuid4()], db)

        assert found == {activity.id: [(1.0, 3.0), (2.0, 4.0)]}

    def test_an_activity_without_samples_has_its_route_from_its_old_map_stream(self, db, activity):
        _old_map(db, activity, [(1.0, 2.0), (1.5, 2.5)])

        assert streams_integration.get_routes_for_reprocess([activity.id], db) == {
            activity.id: [(1.0, 2.0), (1.5, 2.5)]
        }

    def test_the_route_before_and_after_a_reprocess_that_changes_nothing_is_the_same(self, db, activity):
        _old_map(db, activity, [(1.0, 2.0), (1.5, 2.5)])
        before = streams_integration.get_routes_for_reprocess([activity.id], db)
        make_samples(db, activity, [0, 1000], latitude=[1.0, 1.5], longitude=[2.0, 2.5])
        streams_crud.delete_activity_streams(activity.id, db)

        assert streams_integration.get_routes_for_reprocess([activity.id], db) == before

    def test_a_multisport_activity_has_its_legs_routes_old_and_new_in_start_order(self, db, activity):
        parent, legs = make_multisport(db, activity.user_id)
        _old_map(db, legs[0], [(1.0, 1.0), (1.5, 1.5)])
        make_samples(db, legs[2], [0], latitude=[3.0], longitude=[3.0])

        found = streams_integration.get_routes_for_reprocess([parent.id], db)

        assert found == {parent.id: [(1.0, 1.0), (1.5, 1.5), (3.0, 3.0)]}

    def test_no_activities_have_no_routes(self, db):
        assert streams_integration.get_routes_for_reprocess([], db) == {}


class TestRoutesFromSamples:
    def test_the_positioned_samples_of_several_activities_are_read_in_order_and_one_without_samples_is_absent(
        self, db, activity
    ):
        make_samples(db, activity, [0, 1000, 2000], latitude=[1.0, None, 2.0], longitude=[3.0, None, 4.0])

        found = streams_integration.get_routes_for_activities([activity.id, uuid.uuid4()], db)

        assert found == {activity.id: [(1.0, 3.0), (2.0, 4.0)]}

    def test_samples_without_a_position_have_no_route(self, db, activity):
        make_samples(db, activity, [0, 1000], heart_rate=[120.0, 121.0])

        assert streams_integration.get_routes_for_activities([activity.id], db) == {}

    def test_a_multisport_activity_has_its_legs_routes_in_start_order_and_a_leg_its_own(self, db, activity):
        parent, legs = make_multisport(db, activity.user_id)
        make_samples(db, legs[4], [0], latitude=[5.0], longitude=[5.0])
        make_samples(db, legs[0], [0, 1000], latitude=[1.0, 1.5], longitude=[1.0, 1.5])
        make_samples(db, legs[2], [0], latitude=[3.0], longitude=[3.0])

        found = streams_integration.get_routes_for_activities([parent.id, legs[4].id], db)

        assert found == {parent.id: [(1.0, 1.0), (1.5, 1.5), (3.0, 3.0), (5.0, 5.0)], legs[4].id: [(5.0, 5.0)]}

    def test_a_multisport_activity_whose_legs_have_no_position_has_no_route(self, db, activity):
        parent, _legs = make_multisport(db, activity.user_id)

        assert streams_integration.get_routes_for_activities([parent.id], db) == {}

    def test_no_activities_have_no_routes(self, db):
        assert streams_integration.get_routes_for_activities([], db) == {}
