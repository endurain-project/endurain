"""Tests for TCX activity file import utilities."""

import sys
from datetime import UTC, datetime, timedelta, timezone
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

safeuploads_stub = ModuleType("safeuploads")
safeuploads_exceptions_stub = ModuleType("safeuploads.exceptions")


class _FileValidationError(Exception):
    """Test stub for safeuploads file validation errors."""


safeuploads_stub.FileValidator = MagicMock
safeuploads_exceptions_stub.FileValidationError = _FileValidationError
sys.modules.setdefault("safeuploads", safeuploads_stub)
sys.modules.setdefault("safeuploads.exceptions", safeuploads_exceptions_stub)

import activities.activity_file_import.utils_tcx as utils_tcx


def _privacy_settings() -> SimpleNamespace:
    """
    Build privacy settings for parser tests.

    Returns:
        Object with the attributes expected by privacy kwarg builder.
    """
    return SimpleNamespace(
        default_activity_visibility="public",
        hide_activity_start_time=False,
        hide_activity_location=False,
        hide_activity_map=False,
        hide_activity_hr=False,
        hide_activity_power=False,
        hide_activity_cadence=False,
        hide_activity_elevation=False,
        hide_activity_speed=False,
        hide_activity_pace=False,
        hide_activity_laps=False,
        hide_activity_workout_sets_steps=False,
        hide_activity_gear=False,
    )


class TestUtilsTcx:
    """Test suite for TCX parser helper functions."""

    def test_extract_waypoints_skips_entries_without_time(self):
        """Test waypoints ignore trackpoints that have no timestamp."""
        dt = datetime(2026, 4, 1, 10, 0, 0, tzinfo=timezone.utc)

        trackpoints = [
            {
                "time": None,
                "latitude": 10.0,
                "longitude": 20.0,
                "hr_value": 150,
                "cadence": 85,
                "elevation": 100,
            },
            {
                "time": dt,
                "latitude": 10.001,
                "longitude": 20.001,
                "hr_value": 152,
                "cadence": 88,
                "elevation": 101,
            },
        ]

        tcx_file = SimpleNamespace(
            trackpoints=[
                SimpleNamespace(
                    time=None,
                    tpx_ext={"Watts": 220, "RunCadence": 90},
                ),
                SimpleNamespace(
                    time=dt,
                    tpx_ext={"Watts": 230, "RunCadence": 92},
                ),
            ]
        )

        waypoints = utils_tcx._extract_waypoints(trackpoints, tcx_file)

        assert len(waypoints["lat_lon_waypoints"]) == 1
        assert len(waypoints["hr_waypoints"]) == 1
        assert len(waypoints["cad_waypoints"]) == 1
        assert len(waypoints["ele_waypoints"]) == 1
        assert len(waypoints["power_waypoints"]) == 1
        assert all(wp["time"] == "2026-04-01T10:00:00" for wp in waypoints["lat_lon_waypoints"])

    def test_build_activity_handles_missing_start_and_end_time(self):
        """Test activity schema accepts missing start/end timestamps."""
        tcx_file = SimpleNamespace(
            start_time=None,
            end_time=None,
            ascent=None,
            descent=None,
            hr_avg=None,
            hr_max=None,
            cadence_avg=None,
            cadence_max=None,
            calories=None,
        )

        activity = utils_tcx._build_activity(
            tcx_file=tcx_file,
            user_id=1,
            activity_name="Indoor Session",
            activity_type=1,
            distance=0,
            timezone="UTC",
            pace=None,
            city=None,
            town=None,
            country=None,
            avg_power=None,
            max_power=None,
            norm_power=None,
            gear_id=None,
            user_privacy_settings=_privacy_settings(),
        )

        assert activity.start_time is None
        assert activity.end_time is None
        assert activity.total_elapsed_time is None
        assert activity.total_timer_time is None


def test_extract_waypoints_normalizes_offset_times_to_utc(self):
    """Test TCX waypoint times are normalized before serialization."""
    dt = datetime(2026, 3, 28, 8, 19, 19, tzinfo=timezone(timedelta(hours=-7)))

    trackpoints = [
        {
            "time": dt,
            "latitude": 10.0,
            "longitude": 20.0,
            "hr_value": 150,
            "cadence": 85,
            "elevation": 100,
        },
    ]

    tcx_file = SimpleNamespace(
        trackpoints=[
            SimpleNamespace(
                time=dt,
                tpx_ext={"Watts": 220, "RunCadence": 90},
            ),
        ]
    )

    waypoints = utils_tcx._extract_waypoints(trackpoints, tcx_file)

    assert waypoints["lat_lon_waypoints"][0]["time"] == "2026-03-28T15:19:19"
    assert waypoints["power_waypoints"][0]["time"] == "2026-03-28T15:19:19"
