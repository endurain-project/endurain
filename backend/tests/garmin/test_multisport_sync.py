"""The Garmin Connect sync of a multisport activity: one parent with its legs, each leg on its own gear."""

from datetime import UTC, datetime
from pathlib import Path

import garminconnect
import pytest
from sqlalchemy import select

import core.exceptions as core_exceptions
import modules.activities.activity.constants as activity_constants
import modules.activities.activity.models as activity_models
import modules.garmin.activity_service as garmin_activity_service
import modules.garmin.gear_service as garmin_gear_service
import modules.gears.gear.models as gear_models
from tests._factories import garmin as garmin_factories

_START = datetime(2026, 1, 14, tzinfo=UTC)
_END = datetime(2026, 1, 16, tzinfo=UTC)
_TRIATHLON = (
    Path(__file__).parent.parent / "activities/activity_file_import/fixtures/triathlon/24846754341_ACTIVITY.fit"
)
_PARENT_ID = 24846754341
_CHILD_IDS = [24846754276, 24846754277, 24846754278, 24846754279, 24846754280]
_RIDE_ID = _CHILD_IDS[2]
_BIKE_UUID = "7a1d6c1e-52c1-4b4e-9c55-0d3a3d3f8a10"


def _sync(user, rate_limits):
    return garmin_activity_service.get_user_garminconnect_activities_by_dates(user.id, _START, _END, rate_limits)


def _rows(sessions, user):
    with sessions() as db:
        return list(db.scalars(select(activity_models.Activity).where(activity_models.Activity.user_id == user.id)))


def _triathlon(account, child_ids=None):
    archive = garmin_factories.zip_of({_TRIATHLON.name: _TRIATHLON.read_bytes()})
    account.add_multisport_activity(
        _PARENT_ID,
        archive,
        _CHILD_IDS if child_ids is None else child_ids,
        name="Triathlon",
        start=datetime(2026, 1, 15, 12, 4, 15, tzinfo=UTC),
    )


def _with_bike(account, user, rate_limits):
    account.gear = [garmin_factories.gear_payload(_BIKE_UUID, gearTypeName="Bike", displayName="Road bike")]
    account.activity_gear[_RIDE_ID] = [{"uuid": _BIKE_UUID}]
    assert garmin_gear_service.get_user_gear(user.id, rate_limits) is True


class TestSyncingAMultisportActivity:
    def test_stores_one_parent_with_its_legs_and_the_ride_leg_on_its_own_bike(
        self, account, linked, rate_limits, committed_sessions
    ):
        _with_bike(account, linked, rate_limits)
        _triathlon(account)

        _sync(linked, rate_limits)

        rows = _rows(committed_sessions, linked)
        [parent] = [row for row in rows if row.parent_activity_id is None]
        legs = sorted((row for row in rows if row.parent_activity_id is not None), key=lambda row: row.start_time)
        with committed_sessions() as db:
            bike = db.scalars(
                select(gear_models.Gear).where(gear_models.Gear.garminconnect_gear_id == _BIKE_UUID)
            ).one()
        assert (parent.garminconnect_activity_id, parent.name) == (_PARENT_ID, "Triathlon")
        assert parent.activity_type == activity_constants.ActivityType.MULTISPORT.stored
        assert (parent.gear_id, parent.garminconnect_gear_id) == (None, None)
        assert len(legs) == 5
        assert [leg.gear_id for leg in legs] == [None, None, bike.id, None, None]
        assert [leg.garminconnect_gear_id for leg in legs] == [None, None, _BIKE_UUID, None, None]
        assert account.called("get_activity") == [(_PARENT_ID,)]
        assert account.called("get_activity_gear") == [(_PARENT_ID,)] + [(child,) for child in _CHILD_IDS]

    def test_a_second_sync_stores_nothing_and_downloads_nothing(self, account, linked, rate_limits, committed_sessions):
        _triathlon(account)
        _sync(linked, rate_limits)
        account.calls.clear()

        assert _sync(linked, rate_limits) is None

        assert account.called("download_activity") == []
        assert account.called("get_activity") == []
        assert len(_rows(committed_sessions, linked)) == 6

    def test_another_count_of_children_than_legs_gives_no_leg_garmin_gear_and_logs_it(
        self, account, linked, rate_limits, committed_sessions, caplog
    ):
        _with_bike(account, linked, rate_limits)
        _triathlon(account, child_ids=_CHILD_IDS[:4])
        account.activity_gear[_RIDE_ID] = [{"uuid": _BIKE_UUID}]

        with caplog.at_level("WARNING"):
            _sync(linked, rate_limits)

        legs = [row for row in _rows(committed_sessions, linked) if row.parent_activity_id is not None]
        assert len(legs) == 5
        assert {leg.garminconnect_gear_id for leg in legs} == {None}
        [record] = [r for r in caplog.records if "leg gear" in r.getMessage()]
        assert (record.activity_id, record.leg_gear_count, record.leg_count) == (_PARENT_ID, 4, 5)


class TestAnActivityThatIsNotAParent:
    def test_makes_no_call_for_the_detail_of_the_activity(self, account, linked, rate_limits):
        account.add_activity(555)

        _sync(linked, rate_limits)

        assert account.called("get_activity") == []
        assert account.called("get_activity_gear") == [(555,)]


class TestRateLimitOnAChildsGear:
    def test_stops_the_window_like_a_rate_limited_gear_call(self, account, linked, rate_limits, committed_sessions):
        _triathlon(account)
        account.fail("get_activity_gear", garminconnect.GarminConnectTooManyRequestsError("429"), key=_RIDE_ID)

        with pytest.raises(core_exceptions.TooManyRequestsError):
            _sync(linked, rate_limits)

        assert rate_limits.rate_limited_until(linked.id) is not None
        assert account.called("download_activity") == []
        assert _rows(committed_sessions, linked) == []
