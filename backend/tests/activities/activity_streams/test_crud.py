"""Streams are stored as the parsers hand them over and read back unchanged, on the real database."""

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

import modules.activities.activity_streams.constants as stream_constants
import modules.activities.activity_streams.contracts as stream_contracts
import modules.activities.activity_streams.crud as streams_crud
from tests._factories.activities import make_activity, make_samples, make_stream
from tests._factories.users import make_user

_HR = stream_constants.STREAM_TYPE_HR
_MAP = stream_constants.STREAM_TYPE_MAP


@pytest.fixture
def activity(db):
    return make_activity(db, make_user(db).id)


class TestStoredBeforeTheSamples:
    def test_a_stream_keeps_its_samples_in_order_with_their_json_types(self, db, activity):
        waypoints = [{"time": "2025-03-10T08:00:01", "hr": 120, "x": None}, {"time": "2025-03-10T08:00:00", "hr": 0.5}]

        stored = make_stream(db, activity, _HR, waypoints)

        assert (stored.activity_id, stored.stream_type, stored.stream_waypoints) == (activity.id, _HR, waypoints)
        assert streams_crud.get_activity_streams(activity.id, db)[0].stream_waypoints == waypoints


class TestRead:
    def test_an_activitys_streams_are_read_and_another_activitys_are_not(self, db, activity):
        other = make_activity(db, make_user(db).id)
        make_stream(db, activity, _HR, [{"hr": 1}])
        make_stream(db, activity, _MAP, [{"lat": 1.0, "lon": 2.0}])
        make_stream(db, other, _HR, [{"hr": 9}])

        streams = streams_crud.get_activity_streams(activity.id, db)

        assert sorted(s.stream_type for s in streams) == [_HR, _MAP]
        assert all(s.activity_id == activity.id for s in streams)

    def test_the_streams_of_an_activity_are_deleted_and_no_other_activitys(self, db, activity):
        other = make_activity(db, make_user(db).id)
        make_stream(db, activity, _HR, [{"hr": 1}])
        make_stream(db, other, _HR, [{"hr": 2}])

        streams_crud.delete_activity_streams(activity.id, db)

        assert streams_crud.get_activity_streams(activity.id, db) == []
        assert len(streams_crud.get_activity_streams(other.id, db)) == 1


class TestSamples:
    def test_a_round_trip_keeps_null_channels_null_elements_and_signed_sub_second_offsets(self, db, activity):
        make_samples(
            db,
            activity,
            [-1500, 0, 250],
            heart_rate=[120.0, None, 130.0],
            latitude=[38.5, None, 38.6],
            longitude=[-9.1, None, -9.2],
        )
        db.expire_all()

        stored = streams_crud.get_activity_samples(activity.id, db)

        assert stored.offsets_ms == [-1500, 0, 250]
        assert stored.heart_rate == [120.0, None, 130.0]
        assert (stored.latitude, stored.longitude) == ([38.5, None, 38.6], [-9.1, None, -9.2])
        assert (stored.power, stored.speed, stored.elevation, stored.cadence, stored.temperature) == (None,) * 5

    def test_a_channel_mixing_whole_numbers_and_decimals_is_stored(self, db, activity):
        make_samples(db, activity, [0, 1000, 2000], heart_rate=[140, None, 141.5], cadence=[85, 86, 87])

        stored = streams_crud.get_activity_samples(activity.id, db)

        assert stored is not None
        assert (stored.heart_rate, stored.cadence) == ([140, None, 141.5], [85, 86, 87])

    def test_an_activity_without_samples_reads_none(self, db, activity):
        assert streams_crud.get_activity_samples(activity.id, db) is None

    def test_a_second_create_for_the_activity_is_refused_by_the_primary_key(self, db, activity):
        make_samples(db, activity, [0])

        with pytest.raises(IntegrityError, match="activity_samples_pkey"):
            make_samples(db, activity, [1])

    def test_the_batch_get_returns_the_samples_by_activity_in_one_query(self, db, activity):
        other = make_activity(db, activity.user_id)
        without = make_activity(db, activity.user_id)
        make_samples(db, activity, [0, 1], speed=[1.5, 2.5])
        make_samples(db, other, [5])

        found = streams_crud.get_activities_samples([activity.id, other.id, without.id], db)

        assert set(found) == {activity.id, other.id}
        assert found[activity.id].speed == [1.5, 2.5]
        assert streams_crud.get_activities_samples([], db) == {}

    def test_delete_removes_only_that_activitys_samples(self, db, activity):
        other = make_activity(db, activity.user_id)
        make_samples(db, activity, [0])
        make_samples(db, other, [0])

        streams_crud.delete_activity_samples(activity.id, db)

        assert streams_crud.get_activity_samples(activity.id, db) is None
        assert streams_crud.get_activity_samples(other.id, db) is not None

    def test_deleting_the_activity_cascades_to_its_samples(self, db, activity):
        make_samples(db, activity, [0])
        db.expire_all()

        db.execute(sa.text("DELETE FROM activities WHERE id = :id"), {"id": activity.id})

        assert db.scalar(sa.text("SELECT count(*) FROM activity_samples")) == 0

    def test_the_database_rejects_a_channel_of_another_length(self, db, activity):
        with pytest.raises(IntegrityError, match="ck_activity_samples_power_len"):
            db.execute(
                sa.text("INSERT INTO activity_samples (activity_id, offsets_ms, power) VALUES (:id, '{1,2}', '{1}')"),
                {"id": activity.id},
            )

    def test_the_database_rejects_a_lone_latitude(self, db, activity):
        with pytest.raises(IntegrityError, match="ck_activity_samples_lat_lon_together"):
            db.execute(
                sa.text(
                    "INSERT INTO activity_samples (activity_id, offsets_ms, latitude) VALUES (:id, '{1}', '{1.5}')"
                ),
                {"id": activity.id},
            )

    def test_every_array_column_is_stored_with_lz4(self, db):
        rows = db.execute(
            sa.text(
                "SELECT attname, attcompression FROM pg_attribute "
                "WHERE attrelid = 'activity_samples'::regclass AND attnum > 0 AND atttypid IN "
                "(SELECT oid FROM pg_type WHERE typcategory = 'A')"
            )
        ).all()

        assert len(rows) == 9
        assert {compression for _, compression in rows} == {"l"}


class TestParsedSamples:
    def test_a_channel_of_another_length_is_rejected(self):
        with pytest.raises(ValueError, match="heart_rate"):
            stream_contracts.ParsedSamples(offsets_ms=[0, 1], heart_rate=[1.0])

    def test_a_lone_longitude_is_rejected(self):
        with pytest.raises(ValueError, match="latitude and longitude"):
            stream_contracts.ParsedSamples(offsets_ms=[0], longitude=[1.0])
