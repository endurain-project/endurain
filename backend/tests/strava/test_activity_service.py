"""Strava activity sync: a window fetched from the fake Strava is stored, with its streams and laps, on the database."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select

import core.database as core_database
import core.exceptions as core_exceptions
import modules.activities.activity.constants as activity_constants
import modules.activities.activity.models as activity_models
import modules.activities.activity_laps.models as activity_laps_models
import modules.activities.activity_streams.constants as activity_streams_constants
import modules.activities.activity_streams.models as activity_streams_models
import modules.gears.gear.integration_service as gears_integration
import modules.strava.activity_service as strava_activity_service
import modules.strava.client_service as strava_client_service
import modules.users.users_integrations.integration_service as user_integrations_integration
import modules.users.users_privacy_settings.models as privacy_models
from tests._factories import strava as strava_factories
from tests._factories.gears import gear_payload
from tests._factories.users import make_user

_START = datetime(2025, 3, 1, tzinfo=UTC)
_END = datetime(2025, 3, 31, tzinfo=UTC)
_SAMPLES = {
    "time": [0, 10, 20, 30],
    "heartrate": [120, 130, 140, 150],
    "altitude": [100.0, 101.0, 103.0, 102.0],
    "cadence": [80, 82, 84, 86],
    "watts": [200, 210, 220, 230],
    "velocity_smooth": [2.0, 4.0, 0.0, 5.0],
}
_STREAM_TYPES = activity_streams_constants


def _linked(db, **link):
    user = make_user(db, timezone="Europe/Lisbon")
    strava_factories.link_strava(db, user.id, **link)
    db.flush()
    return user


def _reply(value, default):
    """Turn an arranged payload into a reply: a ``Reply`` as it is, a payload as a 200, ``None`` as the default."""
    if value is None:
        value = default
    return value if isinstance(value, strava_factories.Reply) else strava_factories.ok(value)


def _activity(strava, activity_id, *, detail=None, streams=None, laps=None):
    """Answer the three calls one listed activity takes: its detail, its streams and its laps."""
    strava.on("GET", f"/activities/{activity_id}", _reply(detail, strava_factories.detailed_activity(activity_id)))
    strava.on(
        "GET", f"/activities/{activity_id}/streams", _reply(streams, strava_factories.streams_payload(**_SAMPLES))
    )
    strava.on("GET", f"/activities/{activity_id}/laps", _reply(laps, [strava_factories.lap_payload()]))


def _list(strava, *activity_ids):
    strava.on(
        "GET",
        "/athlete/activities",
        strava_factories.ok([strava_factories.summary_activity(activity_id) for activity_id in activity_ids]),
    )


def _sync(user, rate_limits):
    return strava_activity_service.get_user_strava_activities_by_dates(user.id, _START, _END, rate_limits)


def _stored(user_id):
    with core_database.SessionLocal() as db:
        rows = db.scalars(
            select(activity_models.Activity)
            .where(activity_models.Activity.user_id == user_id)
            .order_by(activity_models.Activity.strava_activity_id)
        ).all()
        db.expunge_all()
        return list(rows)


def _streams_of(activity_id):
    with core_database.SessionLocal() as db:
        rows = db.scalars(
            select(activity_streams_models.ActivityStreams).where(
                activity_streams_models.ActivityStreams.activity_id == activity_id
            )
        ).all()
        return {row.stream_type: row.stream_waypoints for row in rows}


def _laps_of(activity_id):
    with core_database.SessionLocal() as db:
        rows = db.scalars(
            select(activity_laps_models.ActivityLaps)
            .where(activity_laps_models.ActivityLaps.activity_id == activity_id)
            .order_by(activity_laps_models.ActivityLaps.start_time)
        ).all()
        db.expunge_all()
        return list(rows)


class TestASyncedWindow:
    def test_a_listed_activity_is_stored_with_its_details_streams_and_laps(self, db, strava, rate_limits):
        user = _linked(db)
        _list(strava, 1001)
        _activity(
            strava,
            1001,
            detail=strava_factories.detailed_activity(
                1001, name="Lunch run", gear_id=None, start_latlng=[38.7, -9.1], average_cadence=80.0
            ),
            streams=strava_factories.streams_payload(**_SAMPLES, latlng=[[38.7, -9.1]] * 4),
        )

        stored = _sync(user, rate_limits)

        (activity,) = _stored(user.id)
        assert [a.id for a in stored] == [activity.id]
        assert (activity.name, activity.distance, activity.strava_activity_id) == ("Lunch run", 10000, 1001)
        assert activity.dedup_key == "strava:1001"
        assert activity.activity_type == activity_constants.ActivityType.RUN.stored
        assert (activity.average_hr, activity.max_hr, activity.calories) == (145, 175, 500)
        assert activity.elevation_gain == 50, "Strava's own total wins over the one computed from the stream"
        assert activity.timezone == "Europe/Lisbon"
        assert activity.start_time == datetime(2025, 3, 10, 8, 0, tzinfo=UTC)
        assert activity.end_time == activity.start_time + timedelta(seconds=3600)
        assert set(_streams_of(activity.id)) == {
            _STREAM_TYPES.STREAM_TYPE_HR,
            _STREAM_TYPES.STREAM_TYPE_POWER,
            _STREAM_TYPES.STREAM_TYPE_CADENCE,
            _STREAM_TYPES.STREAM_TYPE_ELEVATION,
            _STREAM_TYPES.STREAM_TYPE_SPEED,
            _STREAM_TYPES.STREAM_TYPE_PACE,
            _STREAM_TYPES.STREAM_TYPE_MAP,
        }
        (lap,) = _laps_of(activity.id)
        assert (lap.avg_heart_rate, lap.max_heart_rate) == (140, 150)

    def test_an_activity_that_is_already_stored_is_not_fetched_again(self, db, strava, rate_limits):
        user = _linked(db)
        _list(strava, 1001)
        _activity(strava, 1001)
        _sync(user, rate_limits)
        strava.calls.clear()

        stored = _sync(user, rate_limits)

        assert stored == []
        assert [call.path for call in strava.calls] == ["/athlete/activities"]
        assert len(_stored(user.id)) == 1

    def test_two_users_linked_to_the_same_athlete_each_store_the_activity(self, db, strava, rate_limits):
        first, second = _linked(db), _linked(db)
        _list(strava, 1001)
        _activity(strava, 1001)

        _sync(first, rate_limits)
        _sync(second, rate_limits)

        assert [a.strava_activity_id for a in _stored(first.id)] == [1001]
        assert [a.strava_activity_id for a in _stored(second.id)] == [1001]

    def test_a_window_with_no_activities_stores_nothing(self, db, strava, rate_limits):
        user = _linked(db)
        _list(strava)

        assert _sync(user, rate_limits) is None
        assert _stored(user.id) == []

    def test_a_user_who_is_not_linked_is_skipped_without_calling_strava(self, db, strava, rate_limits):
        user = make_user(db)

        assert _sync(user, rate_limits) is None
        assert strava.calls == []

    def test_a_user_without_privacy_settings_is_refused_before_any_activity_is_fetched(self, db, strava, rate_limits):
        user = _linked(db)
        db.execute(
            delete(privacy_models.UsersPrivacySettings).where(privacy_models.UsersPrivacySettings.user_id == user.id)
        )
        _list(strava, 1001)

        with pytest.raises(core_exceptions.NotFoundError):
            _sync(user, rate_limits)

        assert [call.path for call in strava.calls] == ["/athlete/activities"]

    def test_the_users_privacy_defaults_are_applied_to_what_is_stored(self, db, strava, rate_limits):
        user = _linked(db)
        db.execute(
            privacy_models.UsersPrivacySettings.__table__.update()
            .where(privacy_models.UsersPrivacySettings.user_id == user.id)
            .values(hide_activity_hr=True, hide_activity_map=True)
        )
        _list(strava, 1001)
        _activity(strava, 1001)

        _sync(user, rate_limits)

        (activity,) = _stored(user.id)
        assert (activity.hide_hr, activity.hide_map, activity.hide_power) == (True, True, False)


class TestAnActivityThatIsIncomplete:
    @pytest.fixture
    def user(self, db):
        return _linked(db)

    def test_an_activity_without_streams_is_stored_without_them(self, user, strava, rate_limits):
        _list(strava, 1001)
        _activity(strava, 1001, streams=strava_factories.refused(404))

        _sync(user, rate_limits)

        (activity,) = _stored(user.id)
        assert _streams_of(activity.id) == {}

    def test_an_activity_without_laps_is_stored_without_them(self, user, strava, rate_limits):
        _list(strava, 1001)
        _activity(strava, 1001, laps=strava_factories.refused(404))

        _sync(user, rate_limits)

        (activity,) = _stored(user.id)
        assert _laps_of(activity.id) == []

    def test_an_activity_without_speed_or_heart_rate_data_stores_none_of_them(self, user, strava, rate_limits):
        _list(strava, 1001)
        _activity(
            strava,
            1001,
            detail=strava_factories.detailed_activity(
                1001, average_speed=None, max_speed=None, average_heartrate=None, max_heartrate=None
            ),
        )

        _sync(user, rate_limits)

        (activity,) = _stored(user.id)
        assert (activity.average_speed, activity.max_speed, activity.pace) == (None, None, None)
        assert (activity.average_hr, activity.max_hr) == (None, None)

    def test_an_activity_without_a_name_is_stored_as_a_workout(self, user, strava, rate_limits):
        _list(strava, 1001)
        _activity(strava, 1001, detail=strava_factories.detailed_activity(1001, name=None))

        _sync(user, rate_limits)

        assert [a.name for a in _stored(user.id)] == [activity_constants.DEFAULT_ACTIVITY_NAME]

    @pytest.mark.parametrize("missing", ["start_date", "sport_type", "elapsed_time"])
    def test_an_activity_without_a_required_field_fails_the_window_after_the_others_are_stored(
        self, user, strava, rate_limits, missing
    ):
        _list(strava, 1001, 1002)
        _activity(strava, 1001, detail=strava_factories.detailed_activity(1001, **{missing: None}))
        _activity(strava, 1002)

        with pytest.raises(core_exceptions.DependencyFailedError):
            _sync(user, rate_limits)

        assert [a.strava_activity_id for a in _stored(user.id)] == [1002]

    def test_a_failing_activity_does_not_stop_the_others_but_fails_the_window(self, user, strava, rate_limits):
        _list(strava, 1001, 1002)
        _activity(strava, 1001, detail=strava_factories.refused(500))
        _activity(strava, 1002)

        with pytest.raises(core_exceptions.DependencyFailedError):
            _sync(user, rate_limits)

        assert [a.strava_activity_id for a in _stored(user.id)] == [1002]

    def test_a_listed_activity_without_an_id_fails_the_window(self, user, strava, rate_limits):
        strava.on("GET", "/athlete/activities", strava_factories.ok([strava_factories.summary_activity(1001, id=None)]))

        with pytest.raises(core_exceptions.DependencyFailedError):
            _sync(user, rate_limits)

        assert _stored(user.id) == []

    def test_cycling_cadence_stays_in_rpm_and_running_cadence_is_doubled(self, user, strava, rate_limits):
        _list(strava, 1001, 1002)
        _activity(
            strava, 1001, detail=strava_factories.detailed_activity(1001, sport_type="Ride", average_cadence=80.0)
        )
        _activity(strava, 1002, detail=strava_factories.detailed_activity(1002, sport_type="Run", average_cadence=80.0))

        _sync(user, rate_limits)

        ride, run = _stored(user.id)
        assert (ride.average_cad, ride.max_cad) == (80, 86)
        assert (run.average_cad, run.max_cad) == (160, 172)


class TestGearAndTimezone:
    def test_an_activity_gets_the_gear_the_user_synced_from_strava(self, db, strava, rate_limits):
        user = _linked(db, sync_gear=True)
        gears_integration.create_multiple_gears(
            [gear_payload("Strava bike", user_id=user.id, strava_gear_id="b1")], user.id, db
        )
        gear = gears_integration.get_gear_by_strava_id("b1", user.id, db)
        _list(strava, 1001)
        _activity(strava, 1001, detail=strava_factories.detailed_activity(1001, gear_id="b1"))

        _sync(user, rate_limits)

        (activity,) = _stored(user.id)
        assert (activity.gear_id, activity.strava_gear_id) == (gear.id, "b1")

    def test_an_activity_on_gear_the_user_does_not_have_is_stored_without_gear(self, db, strava, rate_limits):
        user = _linked(db, sync_gear=True)
        _list(strava, 1001)
        _activity(strava, 1001, detail=strava_factories.detailed_activity(1001, gear_id="unknown"))

        _sync(user, rate_limits)

        (activity,) = _stored(user.id)
        assert (activity.gear_id, activity.strava_gear_id) == (None, "unknown")

    def test_a_ride_with_a_gps_track_takes_the_timezone_of_where_it_was_ridden(self, db, strava, rate_limits):
        user = _linked(db)
        _list(strava, 1001)
        _activity(
            strava,
            1001,
            detail=strava_factories.detailed_activity(1001, sport_type="Ride", start_latlng=[40.7, -74.0]),
            streams=strava_factories.streams_payload(time=[0, 10], latlng=[[40.7, -74.0], [40.71, -74.0]]),
        )

        _sync(user, rate_limits)

        (activity,) = _stored(user.id)
        assert activity.timezone == "America/New_York"


class TestRefusalsEndTheWindow:
    @pytest.fixture
    def user(self, db):
        return _linked(db)

    def test_an_active_rate_limit_stops_the_window_before_strava_is_called(self, user, strava, rate_limits):
        until = rate_limits.mark_rate_limited(strava_factories.CLIENT_ID)

        with pytest.raises(core_exceptions.TooManyRequestsError) as raised:
            _sync(user, rate_limits)

        assert raised.value.retry_at == until
        assert strava.calls == []

    @pytest.mark.parametrize("endpoint", ["", "/streams", "/laps"])
    def test_a_429_from_strava_ends_the_window_and_says_when_to_try_again(self, user, strava, rate_limits, endpoint):
        _list(strava, 1001, 1002)
        _activity(strava, 1001)
        _activity(strava, 1002)
        strava.on("GET", f"/activities/1001{endpoint}", strava_factories.rate_limited())

        with pytest.raises(core_exceptions.TooManyRequestsError) as raised:
            _sync(user, rate_limits)

        assert raised.value.scope == core_exceptions.TooManyRequestsScope.PROVIDER
        assert raised.value.retry_at == rate_limits.rate_limited_until(strava_factories.CLIENT_ID)
        assert strava.made("GET", "/activities/1002") == [], "the window stopped at the limit"

    def test_a_429_on_the_listing_is_refused_the_same_way(self, user, strava, rate_limits):
        strava.on("GET", "/athlete/activities", strava_factories.rate_limited(daily=True))

        with pytest.raises(core_exceptions.TooManyRequestsError) as raised:
            _sync(user, rate_limits)

        assert (raised.value.retry_at.hour, raised.value.retry_at.minute) == (0, 0)

    def test_an_error_listing_the_window_is_a_failed_dependency(self, user, strava, rate_limits):
        strava.on("GET", "/athlete/activities", strava_factories.refused(500))

        with pytest.raises(core_exceptions.DependencyFailedError):
            _sync(user, rate_limits)

    @pytest.mark.parametrize(
        "endpoint", ["/athlete/activities", "/activities/1001", "/activities/1001/streams", "/activities/1001/laps"]
    )
    def test_a_token_strava_rejects_unlinks_the_account_and_stops_the_window(
        self, db, user, strava, rate_limits, endpoint
    ):
        _list(strava, 1001, 1002)
        _activity(strava, 1001)
        _activity(strava, 1002)
        strava.on("GET", endpoint, strava_factories.refused(401))
        strava.on("POST", "/oauth/token", strava_factories.refused(400, resource="RefreshToken"))

        with pytest.raises(strava_client_service.StravaTokenRejectedError):
            _sync(user, rate_limits)

        with core_database.SessionLocal() as session:
            stored = user_integrations_integration.require_user_integrations(user.id, session)
        assert (stored.strava_token, stored.strava_revoked_at is not None) == (None, True)
        assert strava.made("GET", "/activities/1002") == []
        assert _stored(user.id) == []


class TestStreamConversion:
    @pytest.fixture
    def context(self, db, strava, rate_limits):
        user = _linked(db)
        with core_database.SessionLocal() as session:
            integrations = user_integrations_integration.require_user_integrations(user.id, session)
        return user, integrations, strava_client_service.create_strava_client(integrations)

    def _streams(self, context, rate_limits, strava, **streams):
        user, integrations, client = context
        strava.on("GET", "/activities/1/streams", strava_factories.ok(strava_factories.streams_payload(**streams)))
        return strava_activity_service.fetch_and_process_activity_streams(client, 1, user.id, integrations, rate_limits)

    def test_a_stream_longer_than_the_time_stream_is_cut_instead_of_failing(self, context, strava, rate_limits):
        lat_lon, _, _, _, hr, is_hr, *_ = self._streams(
            context, rate_limits, strava, time=[0, 1], heartrate=[100, 110, 120], latlng=[[1.0, 2.0]]
        )

        assert hr == [{"time": 0, "hr": 100}, {"time": 1, "hr": 110}]
        assert is_hr is True
        assert lat_lon == [{"time": 0, "lat": 1.0, "lon": 2.0}]

    def test_pace_is_derived_from_velocity_and_has_no_point_at_a_standstill(self, context, strava, rate_limits):
        *_, pace = self._streams(context, rate_limits, strava, time=[0, 1, 2], velocity_smooth=[4.0, 0.0, 2.0])

        assert pace == [{"time": 0, "pace": 0.25}, {"time": 2, "pace": 0.5}]

    def test_a_heart_rate_of_zero_is_a_dropout_and_is_not_stored(self, context, strava, rate_limits):
        _, _, _, _, hr, is_hr, *_ = self._streams(context, rate_limits, strava, time=[0, 1, 2], heartrate=[100, 0, 120])

        assert hr == [{"time": 0, "hr": 100}, {"time": 2, "hr": 120}]
        assert is_hr is True

    def test_a_heart_rate_stream_of_only_zeros_is_not_set(self, context, strava, rate_limits):
        _, _, _, _, hr, is_hr, *_ = self._streams(context, rate_limits, strava, time=[0, 1], heartrate=[0, 0])

        assert (hr, is_hr) == ([], False)

    def test_the_elevation_stream_is_smoothed_over_time_and_keeps_its_shape(self, context, strava, rate_limits):
        noisy = [100.0 + (1.5 if second % 2 else -1.5) for second in range(60)]

        _, _, ele, *_ = self._streams(context, rate_limits, strava, time=list(range(60)), altitude=noisy)

        assert [point["time"] for point in ele] == list(range(60))
        assert all(set(point) == {"time", "ele"} for point in ele)
        assert all(abs(point["ele"] - 100.0) < 0.3 for point in ele)

    def test_streams_strava_did_not_send_are_reported_as_not_set(self, context, strava, rate_limits):
        lat_lon, is_lat_lon, ele, is_ele, _hr, is_hr, cad, is_cad, power, is_power, vel, is_vel, pace = self._streams(
            context, rate_limits, strava, time=[0, 1], heartrate=[100, 110]
        )

        assert (is_hr, is_lat_lon, is_ele, is_cad, is_power, is_vel) == (True, False, False, False, False, False)
        assert (lat_lon, ele, cad, power, vel, pace) == ([], [], [], [], [], [])

    def test_an_activity_with_no_streams_at_all_is_not_an_error(self, context, strava, rate_limits):
        user, integrations, client = context
        strava.on("GET", "/activities/1/streams", strava_factories.refused(404))

        streams = strava_activity_service.fetch_and_process_activity_streams(
            client, 1, user.id, integrations, rate_limits
        )

        assert not any(streams)

    def test_any_other_failure_fetching_streams_is_a_failed_dependency(self, context, strava, rate_limits):
        user, integrations, client = context
        strava.on("GET", "/activities/1/streams", strava_factories.refused(500))

        with pytest.raises(core_exceptions.DependencyFailedError):
            strava_activity_service.fetch_and_process_activity_streams(client, 1, user.id, integrations, rate_limits)


class TestLaps:
    @pytest.fixture
    def context(self, db, strava, rate_limits):
        user = _linked(db)
        with core_database.SessionLocal() as session:
            integrations = user_integrations_integration.require_user_integrations(user.id, session)
        return user, integrations, strava_client_service.create_strava_client(integrations)

    def _laps(self, context, rate_limits, strava, stream_data, *laps):
        user, integrations, client = context
        strava.on("GET", "/activities/1/laps", strava_factories.ok(list(laps)))
        return strava_activity_service.fetch_and_process_activity_laps(
            client, 1, user.id, stream_data, integrations, rate_limits
        )

    def test_a_lap_gets_the_metrics_of_its_slice_of_the_streams(self, context, strava, rate_limits):
        cadence = [{"time": i, "cad": 80 + i} for i in range(12)]
        power = [{"time": i, "power": 200 + 10 * i} for i in range(12)]
        elevation = [{"time": i, "ele": 100.0 + 10 * i} for i in range(12)]
        stream_data = [
            (True, _STREAM_TYPES.STREAM_TYPE_CADENCE, cadence),
            (True, _STREAM_TYPES.STREAM_TYPE_POWER, power),
            (True, _STREAM_TYPES.STREAM_TYPE_ELEVATION, elevation),
            (False, _STREAM_TYPES.STREAM_TYPE_HR, []),
        ]

        (lap,) = self._laps(context, rate_limits, strava, stream_data, strava_factories.lap_payload(end_index=11))

        assert (lap["avg_cadence"], lap["max_cadence"]) == (85, 91)
        assert (lap["avg_power"], lap["max_power"]) == (250, 310)
        assert lap["total_ascent"] > 0
        assert lap["total_descent"] == 0
        assert (lap["enhanced_avg_speed"], lap["enhanced_avg_pace"]) == (3.0, pytest.approx(1 / 3))

    def test_a_flat_altitude_stream_gives_a_genuine_zero(self, context, strava, rate_limits):
        flat = [(True, _STREAM_TYPES.STREAM_TYPE_ELEVATION, [{"time": i, "ele": 100.0} for i in range(4)])]

        (flat_lap,) = self._laps(context, rate_limits, strava, flat, strava_factories.lap_payload())

        assert (flat_lap["total_ascent"], flat_lap["total_descent"]) == (0, 0)

    def test_a_lap_without_a_start_time_is_left_out(self, context, strava, rate_limits):
        laps = self._laps(
            context,
            rate_limits,
            strava,
            [],
            strava_factories.lap_payload(1, start_date_local=None),
            strava_factories.lap_payload(2),
        )

        assert [lap["start_time"] for lap in laps] == ["2025-03-10T08:00:00"]

    def test_a_lap_without_stream_indexes_is_stored_without_stream_metrics(self, context, strava, rate_limits):
        cadence = [(True, _STREAM_TYPES.STREAM_TYPE_CADENCE, [{"time": 0, "cad": 80}])]

        (lap,) = self._laps(
            context,
            rate_limits,
            strava,
            cadence,
            strava_factories.lap_payload(start_index=None, end_index=None),
        )

        assert lap["avg_cadence"] is None

    def test_a_lap_with_zero_speed_has_no_pace(self, context, strava, rate_limits):
        (lap,) = self._laps(
            context, rate_limits, strava, [], strava_factories.lap_payload(average_speed=0.0, max_speed=0.0)
        )

        assert (lap["enhanced_avg_pace"], lap["enhanced_max_pace"]) == (None, None)

    def test_an_activity_without_laps_is_not_an_error(self, context, strava, rate_limits):
        user, integrations, client = context
        strava.on("GET", "/activities/1/laps", strava_factories.refused(404))

        assert (
            strava_activity_service.fetch_and_process_activity_laps(client, 1, user.id, [], integrations, rate_limits)
            is None
        )

    def test_a_429_is_recorded_against_this_application_and_refused(self, context, strava, rate_limits):
        user, integrations, client = context
        strava.on("GET", "/activities/1/laps", strava_factories.rate_limited())

        with pytest.raises(core_exceptions.TooManyRequestsError):
            strava_activity_service.fetch_and_process_activity_laps(client, 1, user.id, [], integrations, rate_limits)

        assert rate_limits.is_rate_limited(strava_factories.CLIENT_ID) is True
        assert rate_limits.is_rate_limited("another-application") is False

    def test_any_other_failure_is_a_failed_dependency_so_the_activity_is_retried(self, context, strava, rate_limits):
        user, integrations, client = context
        strava.on("GET", "/activities/1/laps", strava_factories.refused(500))

        with pytest.raises(core_exceptions.DependencyFailedError):
            strava_activity_service.fetch_and_process_activity_laps(client, 1, user.id, [], integrations, rate_limits)


def _on_off(seconds, on=400, off=100, period=30):
    return [on if (second // period) % 2 == 0 else off for second in range(seconds)]


def _reference_normalized_power(watts):
    """Return Coggan's NP of a 1 Hz power list in plain Python: 30-sample rolling mean, 4th-power mean, 4th root."""
    rolling = [sum(watts[i : i + 30]) / 30 for i in range(len(watts) - 29)]
    return (sum(w**4 for w in rolling) / len(rolling)) ** 0.25


def _climb_and_descent(climb=60, descent=60, start=100.0):
    """Return a 1 Hz altitude series that climbs 1 m a second, then descends 1 m a second."""
    up = [start + second for second in range(climb)]
    return up + [up[-1] - second for second in range(1, descent + 1)]


class TestStravaStreamsThroughTheSharedAnalysis:
    @pytest.fixture
    def user(self, db):
        return _linked(db)

    def _stored_one(self, user, strava, rate_limits, *, detail, streams, laps=None):
        _list(strava, 1001)
        _activity(strava, 1001, detail=detail, streams=streams, laps=laps)
        _sync(user, rate_limits)
        (activity,) = _stored(user.id)
        return activity

    def test_the_cadence_average_is_time_weighted_without_zeros_and_the_max_is_the_peak_sample(
        self, user, strava, rate_limits
    ):
        # Smart recording: 60 held 11 s, 90 held 11 s; the zeros are coasting and are left out of the average.
        streams = strava_factories.streams_payload(time=[0, 10, 11, 21, 22], cadence=[60, 0, 90, 0, 90])

        activity = self._stored_one(
            user,
            strava,
            rate_limits,
            detail=strava_factories.detailed_activity(1001, sport_type="Ride"),
            streams=streams,
        )

        assert (activity.average_cad, activity.max_cad) == (75, 90)

    def test_running_cadence_computed_here_is_doubled_to_steps_per_minute(self, user, strava, rate_limits):
        streams = strava_factories.streams_payload(time=[0, 10, 11, 21, 22], cadence=[60, 0, 90, 0, 90])

        activity = self._stored_one(
            user,
            strava,
            rate_limits,
            detail=strava_factories.detailed_activity(1001, sport_type="Run"),
            streams=streams,
        )

        assert (activity.average_cad, activity.max_cad) == (150, 180)

    def test_strava_own_average_cadence_wins_over_the_stream(self, user, strava, rate_limits):
        streams = strava_factories.streams_payload(time=[0, 10, 11, 21, 22], cadence=[60, 0, 90, 0, 90])

        activity = self._stored_one(
            user,
            strava,
            rate_limits,
            detail=strava_factories.detailed_activity(1001, sport_type="Ride", average_cadence=70.0),
            streams=streams,
        )

        assert (activity.average_cad, activity.max_cad) == (70, 90)

    def test_normalized_power_of_thirty_second_intervals_matches_the_reference(self, user, strava, rate_limits):
        watts = _on_off(600)
        streams = strava_factories.streams_payload(time=list(range(600)), watts=watts)

        activity = self._stored_one(
            user, strava, rate_limits, detail=strava_factories.detailed_activity(1001), streams=streams
        )

        assert activity.normalized_power == round(_reference_normalized_power(watts))
        assert activity.normalized_power == pytest.approx(287.6, abs=1.0)

    def test_strava_own_power_totals_win_over_the_stream(self, user, strava, rate_limits):
        streams = strava_factories.streams_payload(time=list(range(600)), watts=_on_off(600))

        activity = self._stored_one(
            user,
            strava,
            rate_limits,
            detail=strava_factories.detailed_activity(1001, average_watts=250.0, max_watts=900.0),
            streams=streams,
        )

        assert (activity.average_power, activity.max_power) == (250, 900)

    def test_a_noisy_flat_altitude_stream_gives_no_elevation_loss_or_gain(self, user, strava, rate_limits):
        noisy = [100.0 + (1.5 if second % 2 else -1.5) for second in range(600)]
        streams = strava_factories.streams_payload(time=list(range(600)), altitude=noisy)

        activity = self._stored_one(
            user,
            strava,
            rate_limits,
            detail=strava_factories.detailed_activity(1001, total_elevation_gain=None),
            streams=streams,
        )

        assert (activity.elevation_gain, activity.elevation_loss) == (None, None)

    def test_a_clean_climb_and_descent_gives_their_gain_and_loss_and_strava_gain_still_wins(
        self, user, strava, rate_limits
    ):
        altitude = _climb_and_descent()
        streams = strava_factories.streams_payload(time=list(range(len(altitude))), altitude=altitude)

        computed = self._stored_one(
            user,
            strava,
            rate_limits,
            detail=strava_factories.detailed_activity(1001, total_elevation_gain=None),
            streams=streams,
        )

        assert 50 <= computed.elevation_gain <= 60
        assert 50 <= computed.elevation_loss <= 60

    def test_strava_total_elevation_gain_wins_and_the_loss_is_still_computed(self, user, strava, rate_limits):
        altitude = _climb_and_descent()
        streams = strava_factories.streams_payload(time=list(range(len(altitude))), altitude=altitude)

        activity = self._stored_one(
            user,
            strava,
            rate_limits,
            detail=strava_factories.detailed_activity(1001, total_elevation_gain=77.0),
            streams=streams,
        )

        assert activity.elevation_gain == 77
        assert 50 <= activity.elevation_loss <= 60

    def test_lap_ascents_and_descents_add_up_to_the_activity(self, user, strava, rate_limits):
        altitude = _climb_and_descent(60, 60) + _climb_and_descent(60, 0, start=100.0)[1:]
        streams = strava_factories.streams_payload(time=list(range(len(altitude))), altitude=altitude)
        last = len(altitude) - 1
        laps = [
            strava_factories.lap_payload(1, start_index=0, end_index=40, start_date_local="2025-03-10T08:00:00Z"),
            strava_factories.lap_payload(2, start_index=40, end_index=90, start_date_local="2025-03-10T08:00:40Z"),
            strava_factories.lap_payload(3, start_index=90, end_index=last, start_date_local="2025-03-10T08:01:30Z"),
        ]

        activity = self._stored_one(
            user,
            strava,
            rate_limits,
            detail=strava_factories.detailed_activity(1001, total_elevation_gain=None),
            streams=streams,
            laps=laps,
        )

        stored_laps = _laps_of(activity.id)
        assert len(stored_laps) == 3
        # Each lap is rounded on its own, so the sums may differ from the whole by half a metre per lap.
        assert abs(sum(lap.total_ascent for lap in stored_laps) - activity.elevation_gain) <= 2
        assert abs(sum(lap.total_descent for lap in stored_laps) - activity.elevation_loss) <= 2
        assert sum(lap.total_ascent for lap in stored_laps) > 100


class TestLapsThroughTheSharedAnalysis:
    @pytest.fixture
    def context(self, db, strava, rate_limits):
        user = _linked(db)
        with core_database.SessionLocal() as session:
            integrations = user_integrations_integration.require_user_integrations(user.id, session)
        return user, integrations, strava_client_service.create_strava_client(integrations)

    def _lap(self, context, rate_limits, strava, stream_data, **lap):
        user, integrations, client = context
        strava.on("GET", "/activities/1/laps", strava_factories.ok([strava_factories.lap_payload(**lap)]))
        (processed,) = strava_activity_service.fetch_and_process_activity_laps(
            client, 1, user.id, stream_data, integrations, rate_limits
        )
        return processed

    def test_lap_cadence_is_time_weighted_without_zeros_and_power_is_time_weighted_with_them(
        self, context, strava, rate_limits
    ):
        times = [0, 1, 11, 12, 22]
        stream_data = [
            (
                True,
                _STREAM_TYPES.STREAM_TYPE_CADENCE,
                [{"time": t, "cad": c} for t, c in zip(times, [60, 0, 90, 0, 90], strict=True)],
            ),
            (
                True,
                _STREAM_TYPES.STREAM_TYPE_POWER,
                [{"time": t, "power": p} for t, p in zip(times, [100, 300, 100, 300, 100], strict=True)],
            ),
        ]

        lap = self._lap(context, rate_limits, strava, stream_data, start_index=0, end_index=4)

        # Cadence: 60 held 11 s then 90 held 11 s; power: 6200 W.s over 22 s.
        assert (lap["avg_cadence"], lap["max_cadence"]) == (75, 90)
        assert (lap["avg_power"], lap["max_power"]) == (282, 300)

    @pytest.mark.parametrize(
        ("first_end", "second_start"),
        [(1, 2), (2, 2)],
        ids=["adjacent indexes", "shared boundary index"],
    )
    def test_a_laps_last_sample_holds_its_time_whether_laps_share_the_boundary_index_or_not(
        self, context, strava, rate_limits, first_end, second_start
    ):
        times = [0, 10, 20, 30]
        stream_data = [
            (
                True,
                _STREAM_TYPES.STREAM_TYPE_CADENCE,
                [{"time": t, "cad": c} for t, c in zip(times, [60, 120, 80, 80], strict=True)],
            )
        ]
        user, integrations, client = context
        strava.on(
            "GET",
            "/activities/1/laps",
            strava_factories.ok(
                [
                    strava_factories.lap_payload(1, start_index=0, end_index=first_end),
                    strava_factories.lap_payload(2, start_index=second_start, end_index=3),
                ]
            ),
        )

        first, second = strava_activity_service.fetch_and_process_activity_laps(
            client, 1, user.id, stream_data, integrations, rate_limits
        )

        # 60 and 120 each hold 10 s before the next lap starts at 20 s.
        assert first["avg_cadence"] == 90
        assert first["max_cadence"] == 120
        assert second["avg_cadence"] == 80

    def test_lap_normalized_power_of_thirty_second_intervals_matches_the_reference(self, context, strava, rate_limits):
        watts = _on_off(600)
        stream_data = [(True, _STREAM_TYPES.STREAM_TYPE_POWER, [{"time": t, "power": w} for t, w in enumerate(watts)])]

        lap = self._lap(context, rate_limits, strava, stream_data, start_index=0, end_index=599)

        assert lap["normalized_power"] == round(_reference_normalized_power(watts))

    def test_a_lap_with_under_thirty_seconds_of_power_has_no_normalized_power(self, context, strava, rate_limits):
        stream_data = [(True, _STREAM_TYPES.STREAM_TYPE_POWER, [{"time": t, "power": 200} for t in range(20)])]

        lap = self._lap(context, rate_limits, strava, stream_data, start_index=0, end_index=19)

        assert lap["normalized_power"] is None
        assert lap["avg_power"] == 200

    def test_a_lap_counts_the_elevation_steps_after_its_start_index_up_to_its_end_index(
        self, context, strava, rate_limits
    ):
        altitude = _climb_and_descent(60, 60)
        smoothed = [{"time": t, "ele": a} for t, a in enumerate(altitude)]
        stream_data = [(True, _STREAM_TYPES.STREAM_TYPE_ELEVATION, smoothed)]
        user, integrations, client = context
        strava.on(
            "GET",
            "/activities/1/laps",
            strava_factories.ok(
                [
                    strava_factories.lap_payload(1, start_index=0, end_index=60),
                    strava_factories.lap_payload(2, start_index=60, end_index=120),
                ]
            ),
        )

        first, second = strava_activity_service.fetch_and_process_activity_laps(
            client, 1, user.id, stream_data, integrations, rate_limits
        )

        # The 3 m hysteresis confirms the climb up to 157 m (57 m) and the descent from there down to 100 m (57 m).
        assert (first["total_ascent"], first["total_descent"]) == (57, 0)
        assert (second["total_ascent"], second["total_descent"]) == (0, 57)
