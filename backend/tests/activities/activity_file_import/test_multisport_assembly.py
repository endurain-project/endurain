"""Tests that a multisport recording assembles into a parent activity over its legs."""

import dataclasses
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import modules.activities.activity.constants as activity_constants
import modules.activities.activity_file_import.assembly as assembly
import modules.activities.activity_file_import.fit_decoder as fit_decoder
import modules.activities.activity_file_import.recording as recording
from tests.activities.activity_file_import.assembled import assemble_file, make_recording, session

_FIXTURES = Path(__file__).parent / "fixtures"
_START = datetime(2026, 6, 20, 8, 0, 0, tzinfo=UTC)
_MULTISPORT = activity_constants.ActivityType.MULTISPORT


def _leg(sport: str, offset: int, elapsed: int, **summary) -> recording.Session:
    return session(
        sport=sport,
        start_time=_START + timedelta(seconds=offset),
        summary=recording.DeviceSummary(total_elapsed_time=elapsed, total_timer_time=elapsed, **summary),
    )


def _run() -> recording.Session:
    return _leg(
        "running",
        0,
        600,
        distance=2000,
        calories=200,
        avg_heart_rate=150,
        max_heart_rate=170,
        total_ascent=10,
        total_descent=5,
    )


def _ride() -> recording.Session:
    return _leg(
        "cycling",
        700,
        1200,
        distance=20000,
        calories=400,
        avg_heart_rate=130,
        max_heart_rate=160,
        avg_power=200,
        max_power=300,
        total_ascent=100,
        total_descent=80,
    )


def _multisport(*legs: recording.Session, **fields) -> recording.Recording:
    return make_recording(*legs, multisport=True, manufacturer="garmin", product="3990", **fields)


class TestParentTotals:
    def test_the_parent_spans_its_legs_and_names_the_multisport_type(self):
        parent = assemble_file(_multisport(_run(), _ride())).parent

        assert parent is not None
        activity = parent["activity"]
        assert activity.activity_type == _MULTISPORT
        assert activity.start_time == _START
        assert activity.end_time == _START + timedelta(seconds=1900)
        assert activity.total_elapsed_time == 1900

    def test_the_elapsed_time_is_never_below_the_timer_when_whole_second_starts_overlap_the_legs(self):
        # A FIT session starts on a whole second, so back-to-back legs overlap by a fraction of a second.
        run = _leg("running", 0, 600)
        run = dataclasses.replace(run, summary=dataclasses.replace(run.summary, total_elapsed_time=600.7))
        ride = _leg("cycling", 600, 1200)

        activity = assemble_file(_multisport(run, ride, timer_time=1800.7)).parent["activity"]

        assert activity.total_timer_time == 1800.7
        assert activity.total_elapsed_time == 1800.7

    def test_totals_are_the_sums_over_the_legs(self):
        result = assemble_file(_multisport(_run(), _ride()))

        activity = result.parent["activity"]
        legs = [leg["activity"] for leg in result.activities]
        assert activity.distance == sum(leg.distance for leg in legs) == 22000
        assert activity.calories == 600
        assert activity.elevation_gain == sum(leg.elevation_gain for leg in legs)
        assert activity.elevation_loss == sum(leg.elevation_loss for leg in legs)
        assert activity.total_timer_time == 1800

    def test_the_devices_whole_timer_wins_over_the_sum(self):
        activity = assemble_file(_multisport(_run(), _ride(), timer_time=1850.5)).parent["activity"]

        assert activity.total_timer_time == 1850.5

    def test_heart_rate_is_timer_weighted_and_the_maximum_is_the_largest(self):
        activity = assemble_file(_multisport(_run(), _ride())).parent["activity"]

        # (150 * 600 + 130 * 1200) / 1800
        assert activity.average_hr == 137
        assert activity.max_hr == 170

    def test_power_averages_over_the_legs_that_have_it(self):
        activity = assemble_file(_multisport(_run(), _ride())).parent["activity"]

        assert activity.average_power == 200
        assert activity.max_power == 300

    def test_a_total_no_leg_has_is_none(self):
        bare = [_leg("running", 0, 60), _leg("cycling", 60, 60)]

        activity = assemble_file(_multisport(*bare)).parent["activity"]

        assert activity.calories is None
        assert activity.average_hr is None
        assert activity.max_hr is None
        assert activity.average_power is None
        assert activity.max_power is None

    def test_what_a_leg_measures_alone_stays_empty_on_the_parent(self):
        activity = assemble_file(_multisport(_run(), _ride())).parent["activity"]

        assert activity.average_speed is None
        assert activity.max_speed is None
        assert activity.pace is None
        assert activity.average_cad is None
        assert activity.max_cad is None
        assert activity.normalized_power is None

    def test_timezone_and_tracker_come_from_the_first_leg_and_the_file(self):
        result = assemble_file(_multisport(_run(), _ride()), timezone="Europe/Lisbon")

        activity = result.parent["activity"]
        assert activity.timezone == result.activities[0]["activity"].timezone
        assert activity.tracker_manufacturer == "garmin"
        assert activity.tracker_model == "3990"

    def test_the_parent_has_no_samples_laps_sets_or_steps(self):
        parent = assemble_file(_multisport(_run(), _ride())).parent

        assert parent is not None
        assert parent["samples"] is None
        assert parent["laps"] == []
        assert "sets" not in parent
        assert "workout_steps" not in parent


class TestNames:
    def test_a_multisport_parent_defaults_to_the_multisport_workout_name_and_legs_to_their_sport(self):
        result = assemble_file(_multisport(_run(), _ride()))

        assert result.parent["activity"].name == "Multisport workout"
        assert [leg["activity"].name for leg in result.activities] == ["Run", "Ride"]

    def test_the_file_name_names_the_parent(self):
        parent = assemble_file(_multisport(_run(), _ride(), name="Sunday duathlon")).parent

        assert parent["activity"].name == "Sunday duathlon"

    def test_the_callers_name_wins_for_the_parent_and_the_legs_keep_their_sport_names(self):
        result = assemble_file(_multisport(_run(), _ride(), name="Sunday duathlon"), name="Race day")

        assert result.parent["activity"].name == "Race day"
        assert [leg["activity"].name for leg in result.activities] == ["Run", "Ride"]


class TestWhenThereIsNoParent:
    def test_a_one_session_multisport_file_has_no_parent_and_keeps_todays_name(self):
        result = assemble_file(_multisport(_run(), name="Morning"))

        assert result.parent is None
        assert [leg["activity"].name for leg in result.activities] == ["Morning"]

    def test_a_multi_session_file_that_is_not_multisport_has_no_parent_and_keeps_todays_names(self):
        result = assemble_file(make_recording(_run(), _ride(), name="Brick"))

        assert result.parent is None
        assert [leg["activity"].name for leg in result.activities] == ["Brick", "Brick"]


class TestTriathlonFile:
    def test_the_parent_carries_the_devices_own_totals(self):
        path = next((_FIXTURES / "triathlon").glob("*.fit"))
        rec = fit_decoder.decode_fit(str(path))

        result = assemble_file(rec, timezone="Europe/Lisbon")

        assert isinstance(result, assembly.AssembledFile)
        parent = result.parent["activity"]
        legs = [leg["activity"] for leg in result.activities]
        assert len(legs) == 5
        assert parent.total_timer_time == pytest.approx(2302.548)
        assert parent.distance == sum(leg.distance for leg in legs)
        assert parent.start_time == legs[0].start_time
        assert parent.end_time == legs[-1].end_time
        assert parent.name == "Multisport workout"
        assert [leg.name for leg in legs] == [
            "Open water swimming",
            "Transition",
            "Ride",
            "Transition",
            "Run",
        ]
