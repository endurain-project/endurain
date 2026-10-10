"""Tests for the activity_file_import adapter (parser dict -> ParsedActivity).

Moved from ``tests/activities/activity/test_utils.py`` when ``parse_activity_streams_from_file``
was replaced by :func:`~modules.activities.activity_file_import.adapter.parsed_info_to_parsed_activity`.
The adapter builds ``ParsedStream`` objects (without an ``activity_id`` — that is assigned
later by ``ingestion_service.store_parsed_activity``).
"""

import modules.activities.activity.schema as activities_schema


def _activity() -> activities_schema.Activity:
    """A minimal valid Activity (the ingestion contract's activity type)."""
    return activities_schema.Activity(distance=0, name="test", activity_type=1)


class TestParsedInfoToParsedActivity:
    def test_stream_mapping_uses_every_canonical_stream_type(self):
        import modules.activities.activity_file_import.adapter as adapter
        import modules.activities.activity_streams.constants as stream_constants

        assert set(adapter._STREAM_MAPPING) == {
            stream_constants.STREAM_TYPE_HR,
            stream_constants.STREAM_TYPE_POWER,
            stream_constants.STREAM_TYPE_CADENCE,
            stream_constants.STREAM_TYPE_ELEVATION,
            stream_constants.STREAM_TYPE_SPEED,
            stream_constants.STREAM_TYPE_PACE,
            stream_constants.STREAM_TYPE_MAP,
            stream_constants.STREAM_TYPE_TEMPERATURE,
        }

    def test_parse_streams_hr_set(self):
        from modules.activities.activity_file_import.adapter import parsed_info_to_parsed_activity

        parsed_info = {
            "activity": _activity(),
            "is_heart_rate_set": True,
            "hr_waypoints": [{"time": "2024-01-15T08:00:00", "hr": 145}],
            "is_power_set": False,
            "is_cadence_set": False,
            "is_elevation_set": False,
            "is_velocity_set": False,
            "is_lat_lon_set": False,
            "is_temperature_set": False,
        }

        result = parsed_info_to_parsed_activity(parsed_info).components["streams"]

        assert len(result) == 1
        assert result[0].stream_type == 1
        assert result[0].stream_waypoints == [{"time": "2024-01-15T08:00:00", "hr": 145}]

    def test_parse_streams_multiple(self):
        from modules.activities.activity_file_import.adapter import parsed_info_to_parsed_activity

        parsed_info = {
            "activity": _activity(),
            "is_heart_rate_set": True,
            "hr_waypoints": [{"hr": 145}],
            "is_power_set": True,
            "power_waypoints": [{"power": 200}],
            "is_cadence_set": False,
            "is_elevation_set": False,
            "is_velocity_set": False,
            "is_lat_lon_set": True,
            "lat_lon_waypoints": [{"lat": 38.0, "lon": -9.0}],
            "is_temperature_set": False,
        }

        result = parsed_info_to_parsed_activity(parsed_info).components["streams"]

        assert len(result) == 3

    def test_parse_streams_no_streams(self):
        from modules.activities.activity_file_import.adapter import parsed_info_to_parsed_activity

        parsed_info = {
            "activity": _activity(),
            "is_heart_rate_set": False,
            "is_power_set": False,
            "is_cadence_set": False,
            "is_elevation_set": False,
            "is_velocity_set": False,
            "is_lat_lon_set": False,
            "is_temperature_set": False,
        }

        result = parsed_info_to_parsed_activity(parsed_info).components["streams"]

        assert len(result) == 0

    def test_carries_activity_and_children(self):
        from modules.activities.activity_file_import.adapter import parsed_info_to_parsed_activity

        activity = _activity()
        parsed_info = {
            "activity": activity,
            "laps": [{"lap": 1}],
            "sets": [{"set": 1}],
            "workout_steps": [{"step": 1}],
        }

        result = parsed_info_to_parsed_activity(parsed_info)

        assert result.activity is activity
        assert result.components == {
            "streams": [],
            "laps": [{"lap": 1}],
            "sets": [{"set": 1}],
            "workout_steps": [{"step": 1}],
        }
