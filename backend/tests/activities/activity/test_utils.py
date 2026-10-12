from unittest.mock import MagicMock, patch

import pytest


class TestEscapeLike:
    def test_escape_percent(self):
        from activities.activity.utils import escape_like

        result = escape_like("100%")
        assert result == "100\\%"

    def test_escape_underscore(self):
        from activities.activity.utils import escape_like

        result = escape_like("test_name")
        assert result == "test\\_name"

    def test_escape_backslash(self):
        from activities.activity.utils import escape_like

        result = escape_like("foo\\bar")
        assert result == "foo\\\\bar"

    def test_no_escaping_needed(self):
        from activities.activity.utils import escape_like

        result = escape_like("hello")
        assert result == "hello"

    def test_escape_all(self):
        from activities.activity.utils import escape_like

        result = escape_like("a%b_c\\d")
        assert result == "a\\%b\\_c\\\\d"


class TestApplyVisibilityMask:
    def test_owner_no_mask(self):
        from activities.activity.utils import apply_visibility_mask

        schema = MagicMock()
        schema.private_notes = "secret"
        schema.hide_start_time = True
        schema.hide_location = True
        schema.hide_gear = True

        result = apply_visibility_mask(schema, is_owner=True)

        assert result.private_notes == "secret"

    def test_non_owner_masks_private_notes(self):
        from activities.activity.utils import apply_visibility_mask

        schema = MagicMock()
        schema.private_notes = "secret"

        result = apply_visibility_mask(schema, is_owner=False)

        assert result.private_notes is None

    def test_non_owner_masks_hidden_fields(self):
        from activities.activity.utils import apply_visibility_mask

        schema = MagicMock()
        schema.hide_start_time = True
        schema.start_time = "2024-01-15T08:00:00"
        schema.end_time = "2024-01-15T09:00:00"
        schema.hide_location = True
        schema.city = "City"
        schema.town = "Town"
        schema.country = "Country"
        schema.hide_gear = True
        schema.gear_id = 1
        schema.strava_gear_id = "g1"
        schema.garminconnect_gear_id = "g2"
        schema.hide_hr = False

        result = apply_visibility_mask(schema, is_owner=False)

        assert result.start_time is None
        assert result.end_time is None
        assert result.city is None
        assert result.town is None
        assert result.country is None
        assert result.gear_id is None
        assert result.strava_gear_id is None
        assert result.garminconnect_gear_id is None

    def test_non_owner_does_not_mask_visible_fields(self):
        from activities.activity.utils import apply_visibility_mask

        schema = MagicMock()
        schema.hide_start_time = False
        schema.start_time = "2024-01-15T08:00:00"
        schema.hide_location = False
        schema.city = "City"
        schema.hide_gear = False
        schema.gear_id = 1

        result = apply_visibility_mask(schema, is_owner=False)

        assert result.start_time == "2024-01-15T08:00:00"
        assert result.city == "City"
        assert result.gear_id == 1

    def test_mask_private_notes_false_allows_notes(self):
        from activities.activity.utils import apply_visibility_mask

        schema = MagicMock()
        schema.private_notes = "visible"

        result = apply_visibility_mask(schema, is_owner=False, mask_private_notes=False)

        assert result.private_notes == "visible"


class TestCalculateActivityStats:
    def test_calculate_stats(self):
        from activities.activity.utils import calculate_activity_stats

        activity = MagicMock()
        activity.activity_type = 1
        activity.distance = 10000.0
        activity.total_timer_time = 3600.0
        activity.calories = 500

        result = calculate_activity_stats([activity])

        assert result.run.distance == 10000.0
        assert result.run.time == 3600.0
        assert result.run.calories == 500

    def test_calculate_stats_multiple_activities(self):
        from activities.activity.utils import calculate_activity_stats

        run = MagicMock()
        run.activity_type = 1
        run.distance = 5000.0
        run.total_timer_time = 1800.0
        run.calories = 250

        bike = MagicMock()
        bike.activity_type = 4
        bike.distance = 30000.0
        bike.total_timer_time = 5400.0
        bike.calories = 800

        result = calculate_activity_stats([run, bike])

        assert result.run.distance == 5000.0
        assert result.bike.distance == 30000.0

    def test_calculate_stats_none_activities(self):
        from activities.activity.utils import calculate_activity_stats

        result = calculate_activity_stats(None)

        assert result.run.distance == 0.0

    def test_calculate_stats_different_sports(self):
        from activities.activity.utils import calculate_activity_stats

        swim = MagicMock()
        swim.activity_type = 8
        swim.distance = 1500.0
        swim.total_timer_time = 1800.0
        swim.calories = 300

        walk = MagicMock()
        walk.activity_type = 11
        walk.distance = 3000.0
        walk.total_timer_time = 2400.0
        walk.calories = 150

        result = calculate_activity_stats([swim, walk])

        assert result.swim.distance == 1500.0
        assert result.walk.distance == 3000.0


class TestActivityIdToName:
    def test_mapping_contains_common_types(self):
        from activities.activity.utils import ACTIVITY_ID_TO_NAME

        assert ACTIVITY_ID_TO_NAME[1] == "Run"
        assert ACTIVITY_ID_TO_NAME[4] == "Ride"
        assert ACTIVITY_ID_TO_NAME[11] == "Walk"
        assert ACTIVITY_ID_TO_NAME[19] == "Strength training"
        assert ACTIVITY_ID_TO_NAME[47] == "Jump rope"

    def test_unknown_id(self):
        from activities.activity.utils import ACTIVITY_ID_TO_NAME

        assert 999 not in ACTIVITY_ID_TO_NAME


class TestAppendIfNotNone:
    def test_appends_when_value_not_none(self):
        from activities.activity.utils import append_if_not_none

        waypoints = []
        append_if_not_none(waypoints, waypoint_time="2024-01-15T08:00:00", value=145, key="hr")
        assert len(waypoints) == 1
        assert waypoints[0]["hr"] == 145

    def test_does_not_append_when_none(self):
        from activities.activity.utils import append_if_not_none

        waypoints = []
        append_if_not_none(waypoints, waypoint_time="2024-01-15T08:00:00", value=None, key="hr")
        assert len(waypoints) == 0


class TestParseActivityStreams:
    def test_parse_streams_hr_set(self):
        from activities.activity.utils import parse_activity_streams_from_file

        parsed_info = {
            "is_heart_rate_set": True,
            "hr_waypoints": [{"time": "2024-01-15T08:00:00", "hr": 145}],
            "is_power_set": False,
            "is_cadence_set": False,
            "is_elevation_set": False,
            "is_velocity_set": False,
            "is_lat_lon_set": False,
            "is_temperature_set": False,
        }

        result = parse_activity_streams_from_file(parsed_info, activity_id=1)

        assert len(result) == 1
        assert result[0].activity_id == 1
        assert result[0].stream_type == 1

    def test_parse_streams_multiple(self):
        from activities.activity.utils import parse_activity_streams_from_file

        parsed_info = {
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

        result = parse_activity_streams_from_file(parsed_info, activity_id=1)

        assert len(result) == 3

    def test_parse_streams_no_streams(self):
        from activities.activity.utils import parse_activity_streams_from_file

        parsed_info = {
            "is_heart_rate_set": False,
            "is_power_set": False,
            "is_cadence_set": False,
            "is_elevation_set": False,
            "is_velocity_set": False,
            "is_lat_lon_set": False,
            "is_temperature_set": False,
        }

        result = parse_activity_streams_from_file(parsed_info, activity_id=1)

        assert len(result) == 0


class TestLocationBasedOnCoordinates:
    @patch("activities.activity.utils.core_config.settings.REVERSE_GEO_PROVIDER", "geocode")
    @patch("activities.activity.utils.core_config")
    def test_location_missing_coords(self, mock_config):
        from activities.activity.utils import location_based_on_coordinates

        result = location_based_on_coordinates(None, None)

        assert result is None

    @patch("activities.activity.utils.core_config.settings.REVERSE_GEO_PROVIDER", "geocode")
    @patch("activities.activity.utils.core_config.settings.GEOCODES_MAPS_API", "changeme")
    @patch("activities.activity.utils.core_config")
    def test_location_geocode_api_key_changeme(self, mock_config):
        from activities.activity.utils import location_based_on_coordinates

        result = location_based_on_coordinates(38.0, -9.0)

        assert result is None

    @patch("activities.activity.utils.core_config.settings.REVERSE_GEO_PROVIDER", "unsupported")
    @patch("activities.activity.utils.core_config")
    def test_location_unsupported_provider(self, mock_config):
        from activities.activity.utils import location_based_on_coordinates

        result = location_based_on_coordinates(38.0, -9.0)

        assert result is None


@pytest.mark.skip(reason="HealthFasting mapper circular import issue in test env")
class TestTransformSchemaToModel:
    def test_transform_basic(self):
        pass

    def test_transform_with_created_at(self):
        pass


class TestMoveFile:
    @patch("activities.activity.utils.core_file_uploads.move_within")
    def test_move_file_calls_move_within(self, mock_move_within):
        from activities.activity.utils import move_file

        move_file(new_dir="/dest", new_filename="test.fit", file_path="/src/test.fit")

        mock_move_within.assert_called_once_with("/src/test.fit", "/dest", filename="test.fit")


class TestProcessAllFilesSync:
    @patch("activities.activity.utils.time.sleep")
    @patch("activities.activity.utils.core_database.get_db")
    def test_continues_after_file_error(self, mock_get_db, _mock_sleep):
        """A file that raises must not abort the rest of the batch (issue #775)."""
        from unittest.mock import AsyncMock

        from activities.activity.utils import process_all_files_sync

        mock_get_db.return_value = iter([MagicMock()])

        with patch(
            "activities.activity.utils.parse_and_store_activity_from_file",
            new_callable=AsyncMock,
            side_effect=[RuntimeError("boom"), None],
        ) as mock_parse:
            process_all_files_sync(
                user_id=1,
                file_paths=["a.tcx", "b.tcx"],
                websocket_manager=MagicMock(),
                import_initiated_time="2026-07-16T00:00:00",
            )

        assert mock_parse.call_count == 2


class TestBulkImportErrorFileMove:
    @patch("activities.activity.utils.os.makedirs")
    @patch("activities.activity.utils.move_file")
    def test_error_move_httpexception_is_swallowed(self, mock_move_file, _mock_makedirs):
        """HTTPException while moving a failed file to the errors dir must not escape (issue #775)."""
        import asyncio

        from fastapi import HTTPException

        from activities.activity.utils import parse_and_store_activity_from_file

        # Destination-exists collisions raise HTTPException (not OSError).
        mock_move_file.side_effect = HTTPException(status_code=400, detail="Destination file already exists")

        # Unsupported extension drives execution into the bulk-import error
        # handler without touching the filesystem.
        result = asyncio.run(
            parse_and_store_activity_from_file(
                1,
                "activity.xyz",
                MagicMock(),
                MagicMock(),
                is_bulk_import=True,
            )
        )

        assert result is None
        mock_move_file.assert_called_once()
