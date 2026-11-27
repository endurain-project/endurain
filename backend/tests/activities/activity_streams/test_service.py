"""Who reads an activity's streams and what each viewer gets of them, on the real database."""

from datetime import date

import pytest

import core.exceptions as core_exceptions
import modules.activities.activity.constants as activity_constants
import modules.activities.activity_streams.constants as stream_constants
import modules.activities.activity_streams.service as streams_service
from tests._factories.activities import make_activity, make_stream
from tests._factories.followers import make_follow
from tests._factories.server_settings import edit_server_settings
from tests._factories.users import make_user

_VISIBILITY = activity_constants.ActivityVisibility
_HR_SAMPLES = (100, 130, 150, 170, 190, 190)
_TYPE = stream_constants.ActivityStreamType
_TIME = "2025-03-10T08:00:00"

#: Each stream type, a sample of it, and the parent flag that withholds it (``None``: no flag covers it).
_STREAMS = {
    _TYPE.HEART_RATE: ({"time": _TIME, "hr": 150}, "hide_hr"),
    _TYPE.POWER: ({"time": _TIME, "power": 250.5}, "hide_power"),
    _TYPE.CADENCE: ({"time": _TIME, "cad": 85}, "hide_cadence"),
    _TYPE.ELEVATION: ({"time": _TIME, "ele": 40.0}, "hide_elevation"),
    _TYPE.SPEED: ({"time": _TIME, "vel": 3.5}, "hide_speed"),
    _TYPE.PACE: ({"time": _TIME, "pace": 0.28}, "hide_pace"),
    _TYPE.MAP: ({"time": _TIME, "lat": 38.7, "lon": -9.1}, "hide_map"),
    _TYPE.TEMPERATURE: ({"time": _TIME, "temp": 21.5}, None),
}


@pytest.fixture
def owner(db):
    return make_user(db, max_heart_rate=200)


@pytest.fixture
def follower(db, owner):
    user = make_user(db)
    make_follow(db, user.id, owner.id, accepted=True)
    return user


def _shared(db, owner, visibility=_VISIBILITY.FOLLOWERS, **flags):
    activity = make_activity(db, owner.id, visibility=visibility, **flags)
    for stream_type, (sample, _) in _STREAMS.items():
        make_stream(db, activity, stream_type.stored, [sample])
    return activity


def _types(page) -> set[int]:
    return {stream.stream_type for stream in page.items}


class TestAuthenticatedList:
    def test_the_owner_reads_every_stream_whatever_the_flags_say(self, db, owner):
        flags = {flag: True for _, flag in _STREAMS.values() if flag} | {"hide_start_time": True}
        activity = _shared(db, owner, _VISIBILITY.PRIVATE, **flags)

        page = streams_service.list_activity_streams(activity.id, owner.id, db)

        assert (_types(page), page.total) == ({t.stored for t in _TYPE}, 8)
        assert all("time" in stream.stream_waypoints[0] for stream in page.items)

    @pytest.mark.parametrize(
        ("stream_type", "flag"),
        [(stream_type, flag) for stream_type, (_, flag) in _STREAMS.items() if flag],
    )
    def test_a_flag_withholds_its_stream_type_from_a_follower_and_the_total_follows(
        self, db, owner, follower, stream_type, flag
    ):
        activity = _shared(db, owner, **{flag: True})

        page = streams_service.list_activity_streams(activity.id, follower.id, db)

        assert _types(page) == {t.stored for t in _TYPE} - {stream_type.stored}
        assert page.total == 7

    def test_a_follower_reads_every_stream_when_no_flag_is_set(self, db, owner, follower):
        activity = _shared(db, owner)

        assert streams_service.list_activity_streams(activity.id, follower.id, db).total == 8

    def test_a_stream_of_a_type_no_rule_covers_stays_with_the_owner(self, db, owner, follower):
        activity = make_activity(db, owner.id, visibility=_VISIBILITY.FOLLOWERS)
        make_stream(db, activity, 99, [{"time": _TIME}])

        as_follower = streams_service.list_activity_streams(activity.id, follower.id, db)
        as_owner = streams_service.list_activity_streams(activity.id, owner.id, db)

        assert (as_follower.total, as_owner.total) == (0, 1)

    def test_temperature_has_no_flag_of_its_own(self, db, owner, follower):
        every_flag = {flag: True for _, flag in _STREAMS.values() if flag}
        activity = _shared(db, owner, **every_flag)

        page = streams_service.list_activity_streams(activity.id, follower.id, db)

        assert _types(page) == {_TYPE.TEMPERATURE.stored}

    def test_hide_start_time_takes_the_sample_times_off_a_followers_streams_and_keeps_the_values(
        self, db, owner, follower
    ):
        activity = _shared(db, owner, hide_start_time=True)

        page = streams_service.list_activity_streams(activity.id, follower.id, db)

        by_type = {stream.stream_type: stream.stream_waypoints for stream in page.items}
        assert by_type[_TYPE.POWER.stored] == [{"power": 250.5}]
        assert by_type[_TYPE.MAP.stored] == [{"lat": 38.7, "lon": -9.1}]

    def test_a_stranger_gets_the_page_of_an_activity_that_does_not_exist(self, db, owner):
        activity = _shared(db, owner)

        refused = streams_service.list_activity_streams(activity.id, make_user(db).id, db)

        assert (refused.items, refused.total, refused.next) == ([], 0, None)

    def test_the_streams_are_cut_into_pages_after_the_masking(self, db, owner, follower):
        activity = _shared(db, owner, hide_hr=True)

        first = streams_service.list_activity_streams(activity.id, follower.id, db, page_number=1, num_records=3)
        last = streams_service.list_activity_streams(activity.id, follower.id, db, page_number=3, num_records=3)

        assert (len(first.items), first.total, first.next) == (3, 7, 2)
        assert (len(last.items), last.next) == (1, None)


class TestAuthenticatedStream:
    def test_a_follower_reads_one_stream_of_a_followers_only_activity(self, db, owner, follower):
        activity = _shared(db, owner)

        stream = streams_service.get_activity_stream(activity.id, _TYPE.POWER.stored, follower.id, db)

        assert stream.stream_waypoints == [_STREAMS[_TYPE.POWER][0]]

    def test_a_hidden_stream_is_not_found_for_a_follower_and_read_by_the_owner(self, db, owner, follower):
        activity = _shared(db, owner, hide_power=True)

        with pytest.raises(core_exceptions.NotFoundError):
            streams_service.get_activity_stream(activity.id, _TYPE.POWER.stored, follower.id, db)
        assert streams_service.get_activity_stream(activity.id, _TYPE.POWER.stored, owner.id, db).stream_type == 2

    def test_a_stream_the_activity_does_not_have_is_not_found(self, db, owner):
        activity = make_activity(db, owner.id)

        with pytest.raises(core_exceptions.NotFoundError):
            streams_service.get_activity_stream(activity.id, _TYPE.POWER.stored, owner.id, db)

    def test_a_stranger_is_told_the_same_as_for_a_stream_that_does_not_exist(self, db, owner):
        activity = _shared(db, owner)

        with pytest.raises(core_exceptions.NotFoundError, match="Activity stream not found"):
            streams_service.get_activity_stream(activity.id, _TYPE.POWER.stored, make_user(db).id, db)

    def test_hide_start_time_takes_the_sample_times_off_the_stream_for_a_follower(self, db, owner, follower):
        activity = _shared(db, owner, hide_start_time=True)

        stream = streams_service.get_activity_stream(activity.id, _TYPE.SPEED.stored, follower.id, db)

        assert stream.stream_waypoints == [{"vel": 3.5}]


def _hr_stream_of(db, user, **activity_fields):
    activity = make_activity(db, user.id, total_timer_time=100.0, **activity_fields)
    samples = [{"time": f"2025-03-10T08:00:{second:02d}", "hr": hr} for second, hr in enumerate(_HR_SAMPLES)]
    make_stream(db, activity, _TYPE.HEART_RATE.stored, samples)
    return activity


class TestHeartRateZones:
    def test_the_owner_gets_the_zone_breakdown_from_their_max_heart_rate(self, db, owner):
        activity = _hr_stream_of(db, owner)

        stream = streams_service.get_activity_stream(activity.id, _TYPE.HEART_RATE.stored, owner.id, db)

        assert stream.zone_percentages is not None
        assert stream.zone_percentages.hr["zone_1"] == {"percent": 20.0, "hr": "< 120", "time_seconds": 1}

    def test_the_max_heart_rate_follows_the_birthdate_when_none_is_stored(self, db):
        user = make_user(db, max_heart_rate=None, birthdate=date(1990, 1, 1))
        activity = _hr_stream_of(db, user)

        stream = streams_service.get_activity_stream(activity.id, _TYPE.HEART_RATE.stored, user.id, db)

        assert stream.zone_percentages is not None
        assert stream.zone_percentages.hr["zone_5"]["hr"].startswith(">= ")

    def test_an_owner_without_a_max_heart_rate_or_birthdate_gets_no_zones(self, db):
        user = make_user(db, max_heart_rate=None, birthdate=None)
        activity = _hr_stream_of(db, user)

        stream = streams_service.get_activity_stream(activity.id, _TYPE.HEART_RATE.stored, user.id, db)

        assert stream.zone_percentages is None

    def test_a_heart_rate_stream_without_heart_rate_samples_gets_no_zones(self, db, owner):
        activity = make_activity(db, owner.id)
        make_stream(db, activity, _TYPE.HEART_RATE.stored, [{"time": _TIME}])

        page = streams_service.list_activity_streams(activity.id, owner.id, db)

        assert page.items[0].zone_percentages is None

    def test_other_stream_types_carry_no_zones(self, db, owner):
        activity = _hr_stream_of(db, owner)
        for stream_type, (sample, _) in _STREAMS.items():
            if stream_type is not _TYPE.HEART_RATE:
                make_stream(db, activity, stream_type.stored, [sample])

        page = streams_service.list_activity_streams(activity.id, owner.id, db)

        zoned = {s.stream_type for s in page.items if s.zone_percentages is not None}
        assert zoned == {_TYPE.HEART_RATE.stored}

    def test_a_follower_gets_the_zones_of_the_owners_max_heart_rate(self, db, owner, follower):
        activity = _hr_stream_of(db, owner, visibility=_VISIBILITY.FOLLOWERS)

        stream = streams_service.get_activity_stream(activity.id, _TYPE.HEART_RATE.stored, follower.id, db)

        assert stream.zone_percentages is not None
        assert stream.zone_percentages.hr["zone_1"]["hr"] == "< 120"

    def test_a_follower_gets_the_zones_when_the_start_time_is_hidden(self, db, owner, follower):
        activity = _hr_stream_of(db, owner, visibility=_VISIBILITY.FOLLOWERS, hide_start_time=True)

        stream = streams_service.get_activity_stream(activity.id, _TYPE.HEART_RATE.stored, follower.id, db)
        [listed] = streams_service.list_activity_streams(activity.id, follower.id, db).items

        for read in (stream, listed):
            assert "time" not in read.stream_waypoints[0]
            assert read.zone_percentages is not None
            assert read.zone_percentages.hr["zone_1"] == {"percent": 20.0, "hr": "< 120", "time_seconds": 1}

    def test_a_public_reader_gets_the_zones_when_the_start_time_is_hidden(self, db, owner):
        edit_server_settings(db, public_shareable_links=True)
        activity = _hr_stream_of(db, owner, visibility=_VISIBILITY.PUBLIC, hide_start_time=True)

        stream = streams_service.get_public_activity_stream(activity.id, _TYPE.HEART_RATE.stored, db)
        [listed] = streams_service.list_public_activity_streams(activity.id, db).items

        for read in (stream, listed):
            assert "time" not in read.stream_waypoints[0]
            assert read.zone_percentages is not None
            assert read.zone_percentages.hr["zone_1"] == {"percent": 20.0, "hr": "< 120", "time_seconds": 1}


class TestPublic:
    @pytest.fixture(autouse=True)
    def _links_on(self, db):
        edit_server_settings(db, public_shareable_links=True)

    def test_a_public_activity_serves_the_streams_its_flags_leave_visible_without_times_when_hidden(self, db, owner):
        activity = _shared(db, owner, _VISIBILITY.PUBLIC, hide_map=True, hide_start_time=True)

        page = streams_service.list_public_activity_streams(activity.id, db)

        assert _types(page) == {t.stored for t in _TYPE} - {_TYPE.MAP.stored}
        assert all("time" not in stream.stream_waypoints[0] for stream in page.items)

    def test_a_public_activity_serves_one_stream_with_its_zones(self, db, owner):
        activity = make_activity(db, owner.id, visibility=_VISIBILITY.PUBLIC, total_timer_time=100.0)
        make_stream(
            db,
            activity,
            _TYPE.HEART_RATE.stored,
            [
                {"time": _TIME, "hr": 100},
                {"time": "2025-03-10T08:00:01", "hr": 190},
                {"time": "2025-03-10T08:00:02", "hr": 190},
            ],
        )

        stream = streams_service.get_public_activity_stream(activity.id, _TYPE.HEART_RATE.stored, db)

        assert stream.zone_percentages is not None

    @pytest.mark.parametrize("visibility", [_VISIBILITY.FOLLOWERS, _VISIBILITY.PRIVATE])
    def test_an_activity_that_is_not_public_serves_no_streams(self, db, owner, visibility):
        activity = _shared(db, owner, visibility)

        assert streams_service.list_public_activity_streams(activity.id, db).items == []
        with pytest.raises(core_exceptions.NotFoundError):
            streams_service.get_public_activity_stream(activity.id, _TYPE.POWER.stored, db)

    def test_a_hidden_stream_and_a_missing_stream_are_not_found(self, db, owner):
        activity = _shared(db, owner, _VISIBILITY.PUBLIC, hide_power=True)
        bare = make_activity(
            db,
            owner.id,
            visibility=_VISIBILITY.PUBLIC,
            start_time=activity.start_time.replace(day=12),
            end_time=activity.end_time.replace(day=12),
        )

        with pytest.raises(core_exceptions.NotFoundError):
            streams_service.get_public_activity_stream(activity.id, _TYPE.POWER.stored, db)
        with pytest.raises(core_exceptions.NotFoundError):
            streams_service.get_public_activity_stream(bare.id, _TYPE.POWER.stored, db)

    def test_turning_public_links_off_serves_no_streams(self, db, owner):
        activity = _shared(db, owner, _VISIBILITY.PUBLIC)
        edit_server_settings(db, public_shareable_links=False)

        assert streams_service.list_public_activity_streams(activity.id, db).total == 0
        with pytest.raises(core_exceptions.NotFoundError):
            streams_service.get_public_activity_stream(activity.id, _TYPE.POWER.stored, db)
