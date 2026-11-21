"""Who reads an activity's laps, and which of their fields each viewer gets, on the real database."""

from datetime import timedelta

import pytest

import modules.activities.activity.constants as activity_constants
import modules.activities.activity_laps.service as laps_service
from tests._factories.activities import DEFAULT_START, make_activity, make_laps
from tests._factories.followers import make_follow
from tests._factories.server_settings import edit_server_settings
from tests._factories.users import make_user

_VISIBILITY = activity_constants.ActivityVisibility

#: Every lap field a parent flag withholds, with one value each.
_FIELDS = {
    "start_position_lat": 38.7,
    "start_position_long": -9.1,
    "end_position_lat": 38.8,
    "end_position_long": -9.2,
    "avg_heart_rate": 150,
    "max_heart_rate": 170,
    "avg_power": 200,
    "max_power": 400,
    "normalized_power": 210,
    "total_work": 60000,
    "avg_cadence": 85,
    "max_cadence": 95,
    "avg_fractional_cadence": 0.5,
    "max_fractional_cadence": 0.5,
    "total_cycles": 420,
    "enhanced_avg_speed": 3.3,
    "enhanced_max_speed": 4.1,
    "enhanced_avg_pace": 0.3,
    "enhanced_max_pace": 0.24,
    "total_ascent": 12,
    "total_descent": 10,
    "enhanced_min_altitude": 40.0,
    "enhanced_max_altitude": 52.0,
}

_FLAG_FIELDS = {
    "hide_start_time": ["start_time"],
    "hide_map": ["start_position_lat", "start_position_long", "end_position_lat", "end_position_long"],
    "hide_hr": ["avg_heart_rate", "max_heart_rate"],
    "hide_power": ["avg_power", "max_power", "normalized_power", "total_work"],
    "hide_cadence": ["avg_cadence", "max_cadence", "avg_fractional_cadence", "max_fractional_cadence", "total_cycles"],
    "hide_speed": ["enhanced_avg_speed", "enhanced_max_speed"],
    "hide_pace": ["enhanced_avg_pace", "enhanced_max_pace"],
    "hide_elevation": ["total_ascent", "total_descent", "enhanced_min_altitude", "enhanced_max_altitude"],
}


@pytest.fixture
def owner(db):
    return make_user(db)


@pytest.fixture
def follower(db, owner):
    user = make_user(db)
    make_follow(db, user.id, owner.id, accepted=True)
    return user


def _shared(db, owner, visibility=_VISIBILITY.FOLLOWERS, **flags):
    activity = make_activity(db, owner.id, visibility=visibility, **flags)
    make_laps(db, activity, [{"start_time": DEFAULT_START, "total_distance": 1000.0, **_FIELDS}])
    return activity


class TestAuthenticatedRead:
    def test_the_owner_reads_every_field_of_a_lap_whatever_the_flags_say(self, db, owner):
        flags = dict.fromkeys(_FLAG_FIELDS, True) | {"hide_laps": True}
        activity = _shared(db, owner, _VISIBILITY.PRIVATE, **flags)

        page = laps_service.list_activity_laps(activity.id, owner.id, db)

        [lap] = page.items
        assert (lap.start_time, lap.avg_heart_rate, lap.start_position_lat) == (DEFAULT_START, 150, 38.7)
        assert page.total == 1

    @pytest.mark.parametrize("flag", list(_FLAG_FIELDS))
    def test_a_follower_gets_a_lap_without_what_the_flag_hides_and_with_the_rest(self, db, owner, follower, flag):
        activity = _shared(db, owner, **{flag: True})

        [lap] = laps_service.list_activity_laps(activity.id, follower.id, db).items

        cleared = _FLAG_FIELDS[flag]
        assert all(getattr(lap, field) is None for field in cleared)
        kept = {field for field in {*_FIELDS, "start_time", "total_distance"} if field not in cleared}
        assert all(getattr(lap, field) is not None for field in kept)

    def test_a_follower_gets_a_lap_whole_when_no_flag_is_set(self, db, owner, follower):
        activity = _shared(db, owner)

        [lap] = laps_service.list_activity_laps(activity.id, follower.id, db).items

        assert (lap.start_time, lap.avg_power, lap.start_position_long) == (DEFAULT_START, 200, -9.1)

    def test_hide_laps_gives_a_follower_an_empty_page(self, db, owner, follower):
        activity = _shared(db, owner, hide_laps=True)

        page = laps_service.list_activity_laps(activity.id, follower.id, db)

        assert (page.items, page.total) == ([], 0)

    def test_a_stranger_gets_the_page_of_an_activity_that_does_not_exist(self, db, owner):
        stranger = make_user(db)
        activity = _shared(db, owner)

        refused = laps_service.list_activity_laps(activity.id, stranger.id, db)

        assert refused.model_dump() == {"items": [], "total": 0, "page": 1, "num_records": 200, "next": None}

    def test_a_page_reports_the_total_of_every_lap_and_the_next_page(self, db, owner):
        activity = make_activity(db, owner.id)
        make_laps(db, activity, [{"start_time": DEFAULT_START + timedelta(minutes=m)} for m in range(5)])

        page = laps_service.list_activity_laps(activity.id, owner.id, db, page_number=1, num_records=2)

        assert (len(page.items), page.total, page.next) == (2, 5, 2)

    def test_the_laps_a_viewer_sees_with_the_activity_are_the_first_page_masked_for_them(self, db, owner, follower):
        activity = _shared(db, owner, hide_hr=True)

        as_follower = laps_service.list_for_activity(activity, follower.id, db)
        as_anonymous = laps_service.list_for_activity(activity, None, db)

        assert as_follower.items[0].avg_heart_rate is None
        assert as_anonymous.items[0].avg_heart_rate is None
        assert laps_service.list_for_activity(activity, owner.id, db).items[0].avg_heart_rate == 150


class TestPublicRead:
    @pytest.fixture(autouse=True)
    def _links_on(self, db):
        edit_server_settings(db, public_shareable_links=True)

    def test_the_laps_of_a_public_activity_are_served_masked_by_its_flags(self, db, owner):
        activity = _shared(db, owner, _VISIBILITY.PUBLIC, hide_power=True)

        [lap] = laps_service.list_public_activity_laps(activity.id, db).items

        assert (lap.avg_power, lap.total_work, lap.avg_heart_rate) == (None, None, 150)

    @pytest.mark.parametrize("visibility", [_VISIBILITY.FOLLOWERS, _VISIBILITY.PRIVATE])
    def test_an_activity_that_is_not_public_serves_no_laps(self, db, owner, visibility):
        activity = _shared(db, owner, visibility)

        assert laps_service.list_public_activity_laps(activity.id, db).items == []

    def test_a_hidden_public_activity_serves_no_laps(self, db, owner):
        activity = _shared(db, owner, _VISIBILITY.PUBLIC, is_hidden=True)

        assert laps_service.list_public_activity_laps(activity.id, db).items == []

    def test_hide_laps_serves_none(self, db, owner):
        activity = _shared(db, owner, _VISIBILITY.PUBLIC, hide_laps=True)

        assert laps_service.list_public_activity_laps(activity.id, db).total == 0

    def test_turning_public_links_off_serves_no_laps(self, db, owner):
        activity = _shared(db, owner, _VISIBILITY.PUBLIC)
        edit_server_settings(db, public_shareable_links=False)

        assert laps_service.list_public_activity_laps(activity.id, db).items == []

    def test_an_owner_who_is_no_longer_active_serves_no_laps(self, db):
        gone = make_user(db, active=False)
        activity = _shared(db, gone, _VISIBILITY.PUBLIC)

        assert laps_service.list_public_activity_laps(activity.id, db).items == []
