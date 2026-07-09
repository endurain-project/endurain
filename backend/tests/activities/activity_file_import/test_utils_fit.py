"""Tests for FIT activity file import utilities."""

from datetime import UTC, datetime
from types import SimpleNamespace

import activities.activity_file_import.utils_fit as utils_fit


class _MockFrame:
    """Minimal mock of a fitdecode.FitDataMessage for parse_frame_session tests."""

    def __init__(self, **values):
        self._values = values

    def get_value(self, key, default=None):
        return self._values.get(key, default)


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


def _session_record(manufacturer, product=None) -> dict:
    """
    Build a minimal FIT session record for create_activity_objects.

    Args:
        manufacturer: Value placed in file_id["manufacturer"].
        product: Value placed in file_id["product"].

    Returns:
        Session record dict with the keys the builder reads.
    """
    start = datetime(2026, 6, 20, 8, 20, 3, tzinfo=UTC)
    end = datetime(2026, 6, 20, 9, 43, 29, tzinfo=UTC)
    return {
        "activity_name": "Workout",
        "time_offset": None,
        "is_lat_lon_set": False,
        "is_power_set": False,
        "lat_lon_waypoints": [],
        "ele_waypoints": [],
        "power_waypoints": [],
        "hr_waypoints": [],
        "vel_waypoints": [],
        "pace_waypoints": [],
        "cad_waypoints": [],
        "temp_waypoints": [],
        "laps": [],
        "sets": [],
        "workout_steps": [],
        "split_summary": [],
        "lengths": [],
        "file_id": {"manufacturer": manufacturer, "product": product},
        "session": {
            "activity_type": None,
            "first_waypoint_time": start,
            "last_waypoint_time": end,
            "distance": None,
            "total_elapsed_time": 5006.0,
            "total_timer_time": 5006.0,
            "city": None,
            "town": None,
            "country": None,
            "ele_gain": None,
            "ele_loss": None,
            "avg_speed": None,
            "max_speed": None,
            "avg_power": None,
            "max_power": None,
            "np": None,
            "avg_hr": 145,
            "max_hr": 177,
            "avg_cadence": None,
            "max_cadence": None,
            "workout_feeling": None,
            "workout_rpe": None,
            "calories": 934,
            "total_cycles": None,
        },
    }


class TestUtilsFit:
    """Test suite for FIT parser helper functions."""

    def test_create_activity_objects_stringifies_numeric_manufacturer(self):
        """Numeric FIT manufacturer ids are coerced to strings."""
        # Some devices (e.g. Amazfit/Zepp) report an unmapped numeric
        # manufacturer id rather than a name; the schema expects a string.
        activities = utils_fit.create_activity_objects(
            [_session_record(339)],
            user_id=1,
            user_privacy_settings=_privacy_settings(),
        )

        assert len(activities) == 1
        assert activities[0]["activity"].tracker_manufacturer == "339"

    def test_create_activity_objects_keeps_none_manufacturer(self):
        """A missing manufacturer stays None instead of the string 'None'."""
        activities = utils_fit.create_activity_objects(
            [_session_record(None)],
            user_id=1,
            user_privacy_settings=_privacy_settings(),
        )

        assert activities[0]["activity"].tracker_manufacturer is None

    def test_create_activity_objects_stringifies_numeric_model(self):
        """Numeric FIT product ids are coerced to strings."""
        activities = utils_fit.create_activity_objects(
            [_session_record(None, product=4567)],
            user_id=1,
            user_privacy_settings=_privacy_settings(),
        )

        assert activities[0]["activity"].tracker_model == "4567"

    def test_create_activity_objects_keeps_none_model(self):
        """A missing product stays None instead of the string 'None'."""
        activities = utils_fit.create_activity_objects(
            [_session_record(None, product=None)],
            user_id=1,
            user_privacy_settings=_privacy_settings(),
        )

        assert activities[0]["activity"].tracker_model is None

    def test_create_activity_objects_recomputes_hr_from_waypoints(self):
        """HR avg/max are recomputed from hr_waypoints, dropping zeros."""
        record = _session_record(None)
        # Populate hr_waypoints: one sensor-off zero, then real readings.
        record["hr_waypoints"] = [
            {"time": "2026-06-20T08:20:03", "hr": 0},
            {"time": "2026-06-20T08:20:10", "hr": 150},
            {"time": "2026-06-20T08:20:20", "hr": 160},
        ]
        # Stale device values that included the zero reading.
        record["session"]["avg_hr"] = 103
        record["session"]["max_hr"] = 160

        activities_list = utils_fit.create_activity_objects(
            [record],
            user_id=1,
            user_privacy_settings=_privacy_settings(),
        )

        activity = activities_list[0]["activity"]
        # Zeros excluded: mean([150, 160]) = 155, max = 160.
        assert activity.average_hr == 155
        assert activity.max_hr == 160

    def test_create_activity_objects_computes_avg_speed_from_distance(self):
        """avg_speed falls back to distance/moving-time when omitted."""
        record = _session_record(None)
        # Device recorded distance and timer time but no session speed.
        record["session"]["distance"] = 10012.0
        record["session"]["total_timer_time"] = 5006.0
        record["session"]["avg_speed"] = None
        record["session"]["max_speed"] = None

        activities_list = utils_fit.create_activity_objects(
            [record],
            user_id=1,
            user_privacy_settings=_privacy_settings(),
        )

        activity = activities_list[0]["activity"]
        # 10012 m / 5006 s = 2.0 m/s.
        assert activity.average_speed == 2.0

    def test_create_activity_objects_computes_speed_from_vel_waypoints(self):
        """max_speed falls back to GPS velocity waypoints when omitted."""
        record = _session_record(None)
        # No distance (indoor-style record) so only GPS speed is usable.
        record["session"]["avg_speed"] = None
        record["session"]["max_speed"] = None
        record["vel_waypoints"] = [
            {"time": "2026-06-20T08:20:03", "vel": 2.0},
            {"time": "2026-06-20T08:20:10", "vel": 4.0},
        ]

        activities_list = utils_fit.create_activity_objects(
            [record],
            user_id=1,
            user_privacy_settings=_privacy_settings(),
        )

        activity = activities_list[0]["activity"]
        # mean([2, 4]) = 3.0, max = 4.0.
        assert activity.average_speed == 3.0
        assert activity.max_speed == 4.0

    def test_create_activity_objects_keeps_device_speed(self):
        """Device-provided session speed is used verbatim when present."""
        record = _session_record(None)
        record["session"]["distance"] = 10012.0
        record["session"]["avg_speed"] = 2.5
        record["session"]["max_speed"] = 6.0

        activities_list = utils_fit.create_activity_objects(
            [record],
            user_id=1,
            user_privacy_settings=_privacy_settings(),
        )

        activity = activities_list[0]["activity"]
        assert activity.average_speed == 2.5
        assert activity.max_speed == 6.0

    def test_create_activity_objects_computes_cadence_from_waypoints(self):
        """avg/max cadence fall back to cad_waypoints when omitted."""
        record = _session_record(None)
        record["session"]["avg_cadence"] = None
        record["session"]["max_cadence"] = None
        record["cad_waypoints"] = [
            {"time": "2026-06-20T08:20:03", "cad": 80},
            {"time": "2026-06-20T08:20:10", "cad": 90},
        ]

        activities_list = utils_fit.create_activity_objects(
            [record],
            user_id=1,
            user_privacy_settings=_privacy_settings(),
        )

        activity = activities_list[0]["activity"]
        # mean([80, 90]) = 85, max = 90.
        assert activity.average_cad == 85
        assert activity.max_cad == 90

    def test_create_activity_objects_keeps_device_cadence(self):
        """Device-provided session cadence is used verbatim when present."""
        record = _session_record(None)
        record["session"]["avg_cadence"] = 88
        record["session"]["max_cadence"] = 95
        record["cad_waypoints"] = [
            {"time": "2026-06-20T08:20:03", "cad": 80},
            {"time": "2026-06-20T08:20:10", "cad": 90},
        ]

        activities_list = utils_fit.create_activity_objects(
            [record],
            user_id=1,
            user_privacy_settings=_privacy_settings(),
        )

        activity = activities_list[0]["activity"]
        assert activity.average_cad == 88
        assert activity.max_cad == 95

    def test_create_activity_objects_computes_elevation_from_waypoints(self):
        """Elevation gain/loss fall back to ele_waypoints when omitted."""
        record = _session_record(None)
        record["session"]["ele_gain"] = None
        record["session"]["ele_loss"] = None
        # Rise 100 -> 130, then descend to 110 (net +30 gain / +20 loss),
        # with enough points for the smoothing filters to retain the trend.
        record["ele_waypoints"] = [
            {"time": "2026-06-20T08:20:00", "ele": 100},
            {"time": "2026-06-20T08:20:10", "ele": 100},
            {"time": "2026-06-20T08:20:20", "ele": 110},
            {"time": "2026-06-20T08:20:30", "ele": 120},
            {"time": "2026-06-20T08:20:40", "ele": 130},
            {"time": "2026-06-20T08:20:50", "ele": 130},
            {"time": "2026-06-20T08:21:00", "ele": 120},
            {"time": "2026-06-20T08:21:10", "ele": 110},
            {"time": "2026-06-20T08:21:20", "ele": 110},
        ]

        activities_list = utils_fit.create_activity_objects(
            [record],
            user_id=1,
            user_privacy_settings=_privacy_settings(),
        )

        activity = activities_list[0]["activity"]
        # Elevation increases overall then decreases, so both are set.
        assert activity.elevation_gain is not None
        assert activity.elevation_gain > 0
        assert activity.elevation_loss is not None
        assert activity.elevation_loss > 0

    def test_create_activity_objects_keeps_device_elevation(self):
        """Device-provided elevation gain/loss are used verbatim."""
        record = _session_record(None)
        record["session"]["ele_gain"] = 250
        record["session"]["ele_loss"] = 240
        record["ele_waypoints"] = [
            {"time": "2026-06-20T08:20:00", "ele": 100},
            {"time": "2026-06-20T08:20:10", "ele": 130},
        ]

        activities_list = utils_fit.create_activity_objects(
            [record],
            user_id=1,
            user_privacy_settings=_privacy_settings(),
        )

        activity = activities_list[0]["activity"]
        assert activity.elevation_gain == 250
        assert activity.elevation_loss == 240

    def test_create_activity_objects_leaves_distance_zero_without_data(self):
        """No session distance, no GPS track, no avg_speed → distance/pace stay 0."""
        # Category A: an HR-only recording has nothing to derive distance from.
        activities_list = utils_fit.create_activity_objects(
            [_session_record(None)],
            user_id=1,
            user_privacy_settings=_privacy_settings(),
        )

        activity = activities_list[0]["activity"]
        assert activity.distance == 0
        assert activity.pace == 0

    def test_create_activity_objects_derives_distance_from_avg_speed(self):
        """Missing session distance falls back to avg_speed * total_timer_time."""
        record = _session_record(None)
        record["session"]["distance"] = None
        record["session"]["avg_speed"] = 1.495
        record["session"]["total_timer_time"] = 1890.0

        activities_list = utils_fit.create_activity_objects(
            [record],
            user_id=1,
            user_privacy_settings=_privacy_settings(),
        )

        activity = activities_list[0]["activity"]
        assert activity.distance == round(1.495 * 1890.0)  # ~2826 m
        assert activity.pace > 0

    def test_create_activity_objects_derives_distance_from_gps_track(self):
        """Missing session distance falls back to geodesic sum over the GPS track."""
        record = _session_record(None)
        record["session"]["distance"] = None
        record["is_lat_lon_set"] = True
        record["lat_lon_waypoints"] = [
            {"time": datetime(2026, 6, 20, 8, 20, 3, tzinfo=UTC), "lat": 40.0, "lon": -3.0},
            {"time": datetime(2026, 6, 20, 8, 25, 3, tzinfo=UTC), "lat": 40.01, "lon": -3.0},
        ]

        activities_list = utils_fit.create_activity_objects(
            [record],
            user_id=1,
            user_privacy_settings=_privacy_settings(),
        )

        activity = activities_list[0]["activity"]
        # ~0.01 deg of latitude ≈ 1.1 km.
        assert 1000 < activity.distance < 1200
        assert activity.pace > 0

    def test_session_distance_takes_precedence_over_fallbacks(self):
        """A real session distance is used as-is, ignoring the fallbacks."""
        record = _session_record(None)
        record["session"]["distance"] = 5000.0
        record["session"]["avg_speed"] = 1.495
        record["session"]["total_timer_time"] = 1890.0

        activities_list = utils_fit.create_activity_objects(
            [record],
            user_id=1,
            user_privacy_settings=_privacy_settings(),
        )

        assert activities_list[0]["activity"].distance == 5000


class TestParseFrameSession:
    """Tests for parse_frame_session sub_sport → activity_type resolution."""

    def _frame(self, sport="running", sub_sport=None, **overrides):
        values = {
            "sport": sport,
            "sub_sport": sub_sport,
            "start_time": datetime(2026, 6, 20, 8, 0, 0, tzinfo=UTC),
            "total_elapsed_time": 3600.0,
            "total_timer_time": 3600.0,
        }
        values.update(overrides)
        return _MockFrame(**values)

    def _activity_type(self, **kwargs):
        """Call parse_frame_session and return only the activity_type (index 2)."""
        return utils_fit.parse_frame_session(self._frame(**kwargs))[2]

    # ── cycling sub_sports ──────────────────────────────────────────────

    def test_cycling_indoor_cycling_returns_indoor_cycling(self):
        """indoor_cycling sub_sport is NOT flattened — reaches ACTIVITY_NAME_TO_ID."""
        assert self._activity_type(sport="cycling", sub_sport="indoor_cycling") == "indoor_cycling"

    def test_cycling_virtual_activity_returns_virtual_ride(self):
        """virtual_activity is explicitly renamed to virtual_ride."""
        assert self._activity_type(sport="cycling", sub_sport="virtual_activity") == "virtual_ride"

    def test_cycling_commuting_returns_commuting_ride(self):
        """commuting is explicitly renamed to commuting_ride."""
        assert self._activity_type(sport="cycling", sub_sport="commuting") == "commuting_ride"

    def test_cycling_mixed_surface_returns_mixed_surface_ride(self):
        """mixed_surface is explicitly renamed to mixed_surface_ride."""
        assert self._activity_type(sport="cycling", sub_sport="mixed_surface") == "mixed_surface_ride"

    def test_cycling_generic_sub_sport_returns_cycling(self):
        """generic sub_sport is ignored — falls back to sport."""
        assert self._activity_type(sport="cycling", sub_sport="generic") == "cycling"

    def test_cycling_no_sub_sport_returns_cycling(self):
        """No sub_sport returns bare sport value."""
        assert self._activity_type(sport="cycling", sub_sport=None) == "cycling"

    # ── running sub_sports ──────────────────────────────────────────────

    def test_running_indoor_running_returns_indoor_running(self):
        """indoor_running sub_sport falls through to sub_sport assignment."""
        assert self._activity_type(sport="running", sub_sport="indoor_running") == "indoor_running"

    def test_running_generic_sub_sport_returns_running(self):
        """generic sub_sport is ignored — falls back to sport."""
        assert self._activity_type(sport="running", sub_sport="generic") == "running"

    def test_running_treadmill_returns_treadmill(self):
        """treadmill sub_sport falls through to sub_sport assignment."""
        assert self._activity_type(sport="running", sub_sport="treadmill") == "treadmill"

    # ── other sub_sports ────────────────────────────────────────────────

    def test_generic_with_breathing_returns_hiit(self):
        """generic sport + breathing sub_sport → hiit."""
        assert self._activity_type(sport="generic", sub_sport="breathing") == "hiit"

    def test_unknown_sub_sport_falls_through(self):
        """Unmapped sub_sport returns the sub_sport string."""
        assert self._activity_type(sport="running", sub_sport="ultramarathon") == "ultramarathon"
