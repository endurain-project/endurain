"""Who reads an activity's streams and what each viewer gets of them, on the real database."""

import uuid
from datetime import date

import pytest

import core.exceptions as core_exceptions
import modules.activities.activity.constants as activity_constants
import modules.activities.activity_streams.constants as stream_constants
import modules.activities.activity_streams.service as streams_service
from tests._factories.activities import make_activity, make_samples, make_stream
from tests._factories.followers import make_follow
from tests._factories.server_settings import edit_server_settings
from tests._factories.users import make_user

_VISIBILITY = activity_constants.ActivityVisibility
_TYPE = stream_constants.ActivityStreamType
_OFFSETS = [0, 1000, 2000, 3000, 4000, 5000]
_HR = [100.0, 130.0, 150.0, 170.0, 190.0, 190.0]

#: Each stored channel, its values, and the parent flag that withholds it (``None``: no flag covers it).
_CHANNELS: dict[str, tuple[list[float], str | None]] = {
    "latitude": ([38.0, 38.5, 39.0, 39.5, 40.0, 40.5], "hide_map"),
    "longitude": ([-9.0, -9.5, -10.0, -10.5, -11.0, -11.5], "hide_map"),
    "elevation": ([40.0, 41.0, 42.0, 43.0, 44.0, 45.0], "hide_elevation"),
    "heart_rate": (_HR, "hide_hr"),
    "power": ([250.0, 251.0, 252.0, 253.0, 254.0, 255.0], "hide_power"),
    "cadence": ([85.0, 86.0, 87.0, 88.0, 89.0, 90.0], "hide_cadence"),
    "speed": ([4.0, 2.0, 0.0, 5.0, 8.0, 4.0], "hide_speed"),
    "temperature": ([21.5, 21.5, 21.5, 21.5, 21.5, 21.5], None),
}
_PACE = [0.25, 0.5, None, 0.2, 0.125, 0.25]
_ZONE_1 = {"percent": 20.0, "hr": "< 120", "time_seconds": 1}


@pytest.fixture
def owner(db):
    return make_user(db, max_heart_rate=200)


@pytest.fixture
def follower(db, owner):
    user = make_user(db)
    make_follow(db, user.id, owner.id, accepted=True)
    return user


def _shared(db, owner, visibility=_VISIBILITY.FOLLOWERS, **flags):
    activity = make_activity(db, owner.id, visibility=visibility, total_timer_time=100.0, **flags)
    make_samples(db, activity, _OFFSETS, **{name: values for name, (values, _) in _CHANNELS.items()})
    return activity


def _channels(streams) -> dict[str, list[float | None] | None]:
    """The channels of a response, by name."""
    return streams.model_dump(exclude={"offsets_ms", "heart_rate_zones"})


def _withheld(streams) -> set[str]:
    return {name for name, values in _channels(streams).items() if values is None}


class TestAuthenticated:
    def test_the_owner_reads_every_channel_whatever_the_flags_say(self, db, owner):
        flags = {flag: True for _, flag in _CHANNELS.values() if flag} | {"hide_pace": True, "hide_start_time": True}
        activity = _shared(db, owner, _VISIBILITY.PRIVATE, **flags)

        streams = streams_service.get_activity_streams(activity.id, owner.id, db)

        assert streams.offsets_ms == _OFFSETS
        assert _channels(streams) == {name: values for name, (values, _) in _CHANNELS.items()} | {"pace": _PACE}
        assert streams.heart_rate_zones is not None

    def test_pace_is_derived_from_speed_and_none_where_the_speed_is_not_above_zero(self, db, owner):
        activity = _shared(db, owner)

        assert streams_service.get_activity_streams(activity.id, owner.id, db).pace == _PACE

    @pytest.mark.parametrize(
        ("flag", "withheld"),
        [
            ("hide_map", {"latitude", "longitude"}),
            ("hide_elevation", {"elevation"}),
            ("hide_hr", {"heart_rate"}),
            ("hide_power", {"power"}),
            ("hide_cadence", {"cadence"}),
            ("hide_speed", {"speed"}),
            ("hide_pace", {"pace"}),
        ],
    )
    def test_a_flag_nulls_its_channels_for_a_follower_and_leaves_the_others(self, db, owner, follower, flag, withheld):
        activity = _shared(db, owner, **{flag: True})

        streams = streams_service.get_activity_streams(activity.id, follower.id, db)

        assert _withheld(streams) == withheld
        assert streams.offsets_ms == _OFFSETS

    def test_hiding_the_speed_keeps_the_pace_the_owner_did_not_hide(self, db, owner, follower):
        activity = _shared(db, owner, hide_speed=True)

        streams = streams_service.get_activity_streams(activity.id, follower.id, db)

        assert (streams.speed, streams.pace) == (None, _PACE)

    def test_a_follower_reads_every_channel_when_no_flag_is_set(self, db, owner, follower):
        activity = _shared(db, owner)

        assert _withheld(streams_service.get_activity_streams(activity.id, follower.id, db)) == set()

    def test_temperature_has_no_flag_of_its_own(self, db, owner, follower):
        flags = {flag: True for _, flag in _CHANNELS.values() if flag} | {"hide_pace": True}
        activity = _shared(db, owner, **flags)

        streams = streams_service.get_activity_streams(activity.id, follower.id, db)

        assert {name for name, values in _channels(streams).items() if values is not None} == {"temperature"}

    def test_every_served_channel_has_a_rule_and_an_unlisted_one_is_withheld(self):
        class Unflagged:
            hide_map = hide_elevation = hide_hr = hide_power = hide_cadence = hide_speed = hide_pace = False

        assert set(streams_service._SERVED_CHANNELS) == set(streams_service._CHANNEL_HIDE_FLAG)
        assert streams_service._is_channel_hidden(Unflagged(), "unlisted")
        assert not streams_service._is_channel_hidden(Unflagged(), "temperature")

    def test_hide_start_time_strips_nothing_because_the_offsets_count_from_the_start(self, db, owner, follower):
        activity = _shared(db, owner, hide_start_time=True)

        streams = streams_service.get_activity_streams(activity.id, follower.id, db)

        assert streams.offsets_ms == _OFFSETS
        assert streams.heart_rate == _HR

    def test_a_stranger_and_a_missing_activity_are_not_found_with_the_same_message(self, db, owner):
        activity = _shared(db, owner)
        stranger = make_user(db)

        with pytest.raises(core_exceptions.NotFoundError) as refused:
            streams_service.get_activity_streams(activity.id, stranger.id, db)
        with pytest.raises(core_exceptions.NotFoundError) as missing:
            streams_service.get_activity_streams(uuid.uuid4(), stranger.id, db)

        assert str(refused.value) == str(missing.value)

    def test_an_activity_without_samples_or_streams_has_an_empty_timeline_and_no_channels(self, db, owner):
        activity = make_activity(db, owner.id)

        streams = streams_service.get_activity_streams(activity.id, owner.id, db)

        assert streams.offsets_ms == []
        assert set(streams.model_dump(exclude={"offsets_ms"}).values()) == {None}


class TestDownsampling:
    def test_max_points_averages_the_samples_into_that_many_buckets(self, db, owner):
        activity = _shared(db, owner, _VISIBILITY.PRIVATE)

        streams = streams_service.get_activity_streams(activity.id, owner.id, db, max_points=2)

        # Span 0..5000 in two buckets of 2500 ms: samples 0-2 and 3-5.
        assert streams.offsets_ms == [1000, 4000]
        assert streams.heart_rate == [pytest.approx(126.6667, abs=1e-3), pytest.approx(183.3333, abs=1e-3)]
        assert streams.speed == [pytest.approx(2.0), pytest.approx(5.6667, abs=1e-3)]

    def test_the_pace_of_a_bucket_comes_from_its_mean_speed(self, db, owner):
        activity = _shared(db, owner, _VISIBILITY.PRIVATE)

        streams = streams_service.get_activity_streams(activity.id, owner.id, db, max_points=2)

        assert streams.pace == [pytest.approx(0.5), pytest.approx(1 / 5.6667, abs=1e-3)]

    def test_a_bound_of_at_least_the_sample_count_returns_every_sample(self, db, owner):
        activity = _shared(db, owner, _VISIBILITY.PRIVATE)

        assert streams_service.get_activity_streams(activity.id, owner.id, db, max_points=6).offsets_ms == _OFFSETS

    def test_the_zones_count_every_sample_whatever_the_bound(self, db, owner):
        activity = _shared(db, owner, _VISIBILITY.PRIVATE)

        whole = streams_service.get_activity_streams(activity.id, owner.id, db)
        reduced = streams_service.get_activity_streams(activity.id, owner.id, db, max_points=2)

        assert reduced.heart_rate_zones == whole.heart_rate_zones
        assert reduced.heart_rate_zones is not None
        assert reduced.heart_rate_zones["zone_1"] == _ZONE_1

    def test_a_hidden_channel_stays_null_when_downsampled(self, db, owner, follower):
        activity = _shared(db, owner, hide_map=True)

        streams = streams_service.get_activity_streams(activity.id, follower.id, db, max_points=2)

        assert (streams.latitude, streams.longitude) == (None, None)
        assert streams.heart_rate is not None


class TestHeartRateZones:
    def test_the_owner_gets_the_zone_breakdown_from_their_max_heart_rate(self, db, owner):
        activity = _shared(db, owner, _VISIBILITY.PRIVATE)

        streams = streams_service.get_activity_streams(activity.id, owner.id, db)

        assert streams.heart_rate_zones is not None
        assert streams.heart_rate_zones["zone_1"] == _ZONE_1

    def test_the_max_heart_rate_follows_the_birthdate_when_none_is_stored(self, db):
        user = make_user(db, max_heart_rate=None, birthdate=date(1990, 1, 1))
        activity = _shared(db, user, _VISIBILITY.PRIVATE)

        streams = streams_service.get_activity_streams(activity.id, user.id, db)

        assert streams.heart_rate_zones is not None
        assert streams.heart_rate_zones["zone_5"]["hr"].startswith(">= ")

    def test_an_owner_without_a_max_heart_rate_or_birthdate_gets_no_zones(self, db):
        user = make_user(db, max_heart_rate=None, birthdate=None)
        activity = _shared(db, user, _VISIBILITY.PRIVATE)

        assert streams_service.get_activity_streams(activity.id, user.id, db).heart_rate_zones is None

    def test_an_activity_without_a_heart_rate_has_no_zones(self, db, owner):
        activity = make_activity(db, owner.id)
        make_samples(db, activity, _OFFSETS, power=[1.0] * 6)

        assert streams_service.get_activity_streams(activity.id, owner.id, db).heart_rate_zones is None

    def test_a_follower_gets_the_zones_of_the_owners_max_heart_rate_when_the_start_time_is_hidden(
        self, db, owner, follower
    ):
        activity = _shared(db, owner, hide_start_time=True)

        streams = streams_service.get_activity_streams(activity.id, follower.id, db)

        assert streams.heart_rate_zones is not None
        assert streams.heart_rate_zones["zone_1"] == _ZONE_1

    def test_hiding_the_heart_rate_hides_its_zones_from_a_follower_and_not_from_the_owner(self, db, owner, follower):
        activity = _shared(db, owner, hide_hr=True)

        assert streams_service.get_activity_streams(activity.id, follower.id, db).heart_rate_zones is None
        assert streams_service.get_activity_streams(activity.id, owner.id, db).heart_rate_zones is not None


class TestStoredBeforeTheSamples:
    """An activity stored before v0.22 has only old waypoint streams until the reprocess converts it."""

    @staticmethod
    def _old_streams(db, activity):
        for stream_type, key, values in (
            (_TYPE.HEART_RATE, "hr", _HR),
            (_TYPE.SPEED, "vel", [4.0, 2.0, 0.0, 5.0, 8.0, 4.0]),
            (_TYPE.PACE, "pace", [0.25, 0.5, 0.2, 0.125, 0.25]),
        ):
            make_stream(
                db,
                activity,
                stream_type.stored,
                [{"time": f"2025-03-10T08:00:0{i}", key: value} for i, value in enumerate(values)],
            )
        make_stream(
            db,
            activity,
            _TYPE.MAP.stored,
            [{"time": f"2025-03-10T08:00:0{i}", "lat": 38.0 + i, "lon": -9.0 - i} for i in range(6)],
        )

    def test_the_old_streams_are_served_as_samples(self, db, owner):
        activity = make_activity(db, owner.id)
        self._old_streams(db, activity)

        streams = streams_service.get_activity_streams(activity.id, owner.id, db)

        assert streams.offsets_ms == _OFFSETS
        assert streams.heart_rate == _HR
        assert streams.speed == [4.0, 2.0, 0.0, 5.0, 8.0, 4.0]
        assert streams.pace == _PACE
        assert streams.latitude == [38.0, 39.0, 40.0, 41.0, 42.0, 43.0]
        assert streams.heart_rate_zones is not None

    def test_the_masking_applies_to_the_converted_streams(self, db, owner, follower):
        activity = make_activity(db, owner.id, visibility=_VISIBILITY.FOLLOWERS, hide_map=True, hide_hr=True)
        self._old_streams(db, activity)

        streams = streams_service.get_activity_streams(activity.id, follower.id, db)

        assert (streams.latitude, streams.longitude, streams.heart_rate) == (None, None, None)
        assert streams.speed is not None
        assert streams.heart_rate_zones is None

    def test_the_samples_win_over_the_old_streams(self, db, owner):
        activity = _shared(db, owner, _VISIBILITY.PRIVATE)
        make_stream(db, activity, _TYPE.POWER.stored, [{"time": "2025-03-10T08:00:00", "power": 999}])

        streams = streams_service.get_activity_streams(activity.id, owner.id, db)

        assert streams.power == _CHANNELS["power"][0]

    def test_nothing_is_persisted_by_serving_them(self, db, owner):
        import modules.activities.activity_streams.crud as streams_crud

        activity = make_activity(db, owner.id)
        self._old_streams(db, activity)

        streams_service.get_activity_streams(activity.id, owner.id, db)

        assert streams_crud.get_activity_samples(activity.id, db) is None


class TestPublic:
    @pytest.fixture(autouse=True)
    def _links_on(self, db):
        edit_server_settings(db, public_shareable_links=True)

    def test_a_public_activity_serves_the_channels_its_flags_leave_visible(self, db, owner):
        activity = _shared(db, owner, _VISIBILITY.PUBLIC, hide_map=True, hide_start_time=True)

        streams = streams_service.get_public_activity_streams(activity.id, db)

        assert streams.offsets_ms == _OFFSETS
        assert _withheld(streams) == {"latitude", "longitude"}

    def test_a_public_reader_gets_the_zones_when_the_start_time_is_hidden(self, db, owner):
        activity = _shared(db, owner, _VISIBILITY.PUBLIC, hide_start_time=True)

        streams = streams_service.get_public_activity_streams(activity.id, db)

        assert streams.heart_rate_zones is not None
        assert streams.heart_rate_zones["zone_1"] == _ZONE_1

    def test_a_public_reader_is_never_the_owner_whoever_the_activity_belongs_to(self, db, owner):
        activity = _shared(db, owner, _VISIBILITY.PUBLIC, hide_hr=True)

        streams = streams_service.get_public_activity_streams(activity.id, db, max_points=3)

        assert (streams.heart_rate, streams.heart_rate_zones) == (None, None)
        assert len(streams.offsets_ms) == 3

    @pytest.mark.parametrize("visibility", [_VISIBILITY.FOLLOWERS, _VISIBILITY.PRIVATE])
    def test_an_activity_that_is_not_public_is_not_found(self, db, owner, visibility):
        activity = _shared(db, owner, visibility)

        with pytest.raises(core_exceptions.NotFoundError):
            streams_service.get_public_activity_streams(activity.id, db)

    def test_an_unknown_activity_is_not_found(self, db):
        with pytest.raises(core_exceptions.NotFoundError):
            streams_service.get_public_activity_streams(uuid.uuid4(), db)

    def test_turning_public_links_off_serves_nothing(self, db, owner):
        activity = _shared(db, owner, _VISIBILITY.PUBLIC)
        edit_server_settings(db, public_shareable_links=False)

        with pytest.raises(core_exceptions.NotFoundError):
            streams_service.get_public_activity_streams(activity.id, db)
