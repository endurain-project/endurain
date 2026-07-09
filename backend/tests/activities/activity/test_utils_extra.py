"""Tests for uncovered utility functions in activities.activity.utils."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestTransformSchemaToModel:
    def _make_schema(self, **overrides):
        from activities.activity import schema as activities_schema

        defaults = dict(
            user_id=1,
            distance=10000,
            name="Morning Run",
            activity_type=1,
            start_time=datetime(2024, 1, 15, 8, 0, 0, tzinfo=UTC),
            end_time=datetime(2024, 1, 15, 9, 0, 0, tzinfo=UTC),
            visibility=0,
        )
        defaults.update(overrides)
        return activities_schema.Activity(**defaults)

    @patch("activities.activity.utils.activities_models.Activity")
    @patch("activities.activity.utils.core_sanitization")
    def test_transform_basic(self, mock_sanitization, mock_model):
        from activities.activity.utils import transform_schema_activity_to_model_activity

        mock_sanitization.sanitize_markdown.side_effect = lambda x: x
        mock_model.return_value = MagicMock()

        activity_schema = self._make_schema(
            description="test desc",
            private_notes="secret",
            timezone="Europe/Lisbon",
            total_elapsed_time=3600.0,
            total_timer_time=3500.0,
            city="Lisbon",
            town="Belem",
            country="Portugal",
            calories=500,
        )

        transform_schema_activity_to_model_activity(activity_schema)

        mock_model.assert_called_once()
        _, kwargs = mock_model.call_args
        assert kwargs["user_id"] == 1
        assert kwargs["distance"] == 10000
        assert kwargs["name"] == "Morning Run"
        assert kwargs["city"] == "Lisbon"
        assert kwargs["total_timer_time"] == 3500.0

    @patch("activities.activity.utils.activities_models.Activity")
    @patch("activities.activity.utils.core_sanitization")
    def test_transform_with_created_at(self, mock_sanitization, mock_model):
        from activities.activity.utils import transform_schema_activity_to_model_activity

        mock_sanitization.sanitize_markdown.side_effect = lambda x: x
        mock_model.return_value = MagicMock()

        created_at = datetime(2024, 1, 10, 12, 0, 0, tzinfo=UTC)
        activity_schema = self._make_schema(created_at=created_at)

        transform_schema_activity_to_model_activity(activity_schema)

        _, kwargs = mock_model.call_args
        assert kwargs["created_at"] == created_at

    @patch("activities.activity.utils.activities_models.Activity")
    @patch("activities.activity.utils.core_sanitization")
    def test_transform_total_timer_time_falls_back_to_elapsed(self, mock_sanitization, mock_model):
        from activities.activity.utils import transform_schema_activity_to_model_activity

        mock_sanitization.sanitize_markdown.side_effect = lambda x: x
        mock_model.return_value = MagicMock()

        activity_schema = self._make_schema(total_elapsed_time=4000.0, total_timer_time=None)

        transform_schema_activity_to_model_activity(activity_schema)

        _, kwargs = mock_model.call_args
        assert kwargs["total_timer_time"] == 4000.0

    @patch("activities.activity.utils.activities_models.Activity")
    @patch("activities.activity.utils.core_sanitization")
    def test_transform_sanitizes_markdown(self, mock_sanitization, mock_model):
        from activities.activity.utils import transform_schema_activity_to_model_activity

        mock_sanitization.sanitize_markdown.side_effect = lambda x: f"sanitized:{x}"
        mock_model.return_value = MagicMock()

        activity_schema = self._make_schema(
            description="<script>alert('xss')</script>",
            private_notes="<b>secret</b>",
        )

        transform_schema_activity_to_model_activity(activity_schema)

        _, kwargs = mock_model.call_args
        assert kwargs["description"] == "sanitized:<script>alert('xss')</script>"
        assert kwargs["private_notes"] == "sanitized:<b>secret</b>"


class TestSerializeActivity:
    @patch("activities.activity.utils.activities_schema.Activity")
    @patch("activities.activity.utils.core_timezone")
    def test_serialize_basic(self, mock_tz, mock_schema_cls):
        from activities.activity.utils import serialize_activity

        mock_tz.format_aware_datetime.side_effect = lambda dt, tz: (
            "2024-01-15T08:00:00" if tz is None else "2024-01-15T09:00:00"
        )
        mock_schema = MagicMock()
        mock_schema_cls.model_validate.return_value = mock_schema

        activity = MagicMock()
        activity.timezone = "Europe/Lisbon"
        activity.start_time = datetime(2024, 1, 15, 8, 0, 0, tzinfo=UTC)
        activity.end_time = datetime(2024, 1, 15, 9, 0, 0, tzinfo=UTC)
        activity.created_at = datetime(2024, 1, 15, 7, 0, 0, tzinfo=UTC)

        result = serialize_activity(activity)

        assert mock_tz.format_aware_datetime.call_count == 6
        assert result.start_time_tz_applied == "2024-01-15T09:00:00"
        assert result.start_time == "2024-01-15T08:00:00"
        mock_schema_cls.model_validate.assert_called_once_with(activity)


class TestHandleGzippedFile:
    @patch("activities.activity.utils.gzip.open")
    @patch("activities.activity.utils.NamedTemporaryFile")
    @patch("activities.activity.utils.move_file")
    @patch("activities.activity.utils.core_logger")
    @patch("activities.activity.utils.Path")
    def test_handle_decompresses_successfully(
        self, mock_path_cls, mock_logger, mock_move, mock_tempfile, mock_gzip_open
    ):
        from activities.activity.utils import handle_gzipped_file

        mock_path_cls.return_value.stem = "activity_123.fit"
        mock_path_cls.return_value.suffix = ".fit"
        mock_path_cls.return_value.name = "activity_123.fit.gz"
        mock_path = mock_path_cls.return_value

        mock_file = MagicMock()
        mock_file.name = "/safe/tmp/tmpabc123.fit"
        mock_tempfile.return_value.__enter__.return_value = mock_file

        mock_gz = MagicMock()
        mock_gzip_open.return_value.__enter__.return_value = mock_gz
        mock_gz.read.side_effect = [b"some data", b""]

        result_path, result_ext = handle_gzipped_file("/uploads/activity_123.fit.gz")

        assert result_path == "/safe/tmp/tmpabc123.fit"
        assert result_ext == ".fit"
        mock_gzip_open.assert_called_once_with(mock_path, "rb")

    @patch("activities.activity.utils.gzip.open")
    @patch("activities.activity.utils.NamedTemporaryFile")
    @patch("activities.activity.utils.move_file")
    @patch("activities.activity.utils.core_logger")
    @patch("activities.activity.utils.Path")
    def test_handle_invalid_gzip_raises_400(self, mock_path_cls, mock_logger, mock_move, mock_tempfile, mock_gzip_open):
        from fastapi import HTTPException

        from activities.activity.utils import handle_gzipped_file

        mock_path_cls.return_value.stem = "activity_123.fit"
        mock_path_cls.return_value.suffix = ".fit"
        mock_path_cls.return_value.name = "bad.gz"

        mock_file = MagicMock()
        mock_file.name = "/safe/tmp/tmpabc.fit"
        mock_tempfile.return_value.__enter__.return_value = mock_file

        mock_gzip_open.return_value.__enter__.side_effect = EOFError("Not a gzip file")

        with pytest.raises(HTTPException) as exc:
            handle_gzipped_file("/uploads/bad.gz")
        assert exc.value.status_code == 400

    @patch("activities.activity.utils.gzip.open")
    @patch("activities.activity.utils.NamedTemporaryFile")
    @patch("activities.activity.utils.move_file")
    @patch("activities.activity.utils.core_logger")
    @patch("activities.activity.utils.Path")
    def test_handle_exceeds_max_size_raises_413(
        self, mock_path_cls, mock_logger, mock_move, mock_tempfile, mock_gzip_open
    ):
        from fastapi import HTTPException

        import activities.activity.utils as utils
        from activities.activity.utils import handle_gzipped_file

        mock_path_cls.return_value.stem = "activity_123.fit"
        mock_path_cls.return_value.suffix = ".fit"
        mock_path_cls.return_value.name = "big.gz"

        mock_file = MagicMock()
        mock_file.name = "/safe/tmp/tmpabc.fit"
        mock_tempfile.return_value.__enter__.return_value = mock_file

        mock_gz = MagicMock()
        mock_gzip_open.return_value.__enter__.return_value = mock_gz
        chunk = b"x" * 1024 * 1024
        mock_gz.read.side_effect = [chunk, chunk, b""]

        orig_max = utils._MAX_DECOMPRESSED_ACTIVITY_BYTES
        utils._MAX_DECOMPRESSED_ACTIVITY_BYTES = 1

        with pytest.raises(HTTPException) as exc:
            handle_gzipped_file("/uploads/big.gz")
        utils._MAX_DECOMPRESSED_ACTIVITY_BYTES = orig_max
        assert exc.value.status_code == 413


class TestCleanupUploadArtifacts:
    @patch("activities.activity.utils.os")
    @patch("activities.activity.utils.core_logger")
    def test_removes_existing_files(self, mock_logger, mock_os):
        from activities.activity.utils import _cleanup_upload_artifacts

        mock_os.path.isfile.side_effect = lambda p: p in ["/safe/tmp/a", "/safe/tmp/b"]

        _cleanup_upload_artifacts(["/safe/tmp/a", "/safe/tmp/b", "/safe/tmp/c"])

        assert mock_os.remove.call_count == 2
        mock_os.remove.assert_any_call("/safe/tmp/a")
        mock_os.remove.assert_any_call("/safe/tmp/b")

    @patch("activities.activity.utils.os")
    @patch("activities.activity.utils.core_logger")
    def test_logs_warning_on_oserror(self, mock_logger, mock_os):
        from activities.activity.utils import _cleanup_upload_artifacts

        mock_os.path.isfile.return_value = True
        mock_os.remove.side_effect = OSError("Permission denied")

        _cleanup_upload_artifacts(["/safe/tmp/a"])

        mock_logger.print_to_log.assert_called_once()


class TestPrepareBulkImportActivity:
    def test_returns_activity_if_not_bulk_import(self):
        from activities.activity.utils import _prepare_bulk_import_activity

        activity = MagicMock()
        result = _prepare_bulk_import_activity(
            activity,
            is_bulk_import=False,
            created_activities_objects=[],
            strava_activities=None,
            activity_metadata_dict={},
        )

        assert result is activity

    @patch("activities.activity.utils.strava_bulk_import_utils")
    @patch("activities.activity.utils.core_logger")
    def test_skips_duplicate_in_multi_activity_fit(self, mock_logger, mock_strava):
        from activities.activity.utils import _prepare_bulk_import_activity

        mock_strava.does_activity_start_time_match_the_data_in_strava_activities_csv.return_value = False

        activity = MagicMock()
        result = _prepare_bulk_import_activity(
            activity,
            is_bulk_import=True,
            created_activities_objects=[MagicMock(), MagicMock()],
            strava_activities={"some": "data"},
            activity_metadata_dict={"metadata_found_in_csv": True},
        )

        assert result is None
        mock_strava.does_activity_start_time_match_the_data_in_strava_activities_csv.assert_called_once()

    @patch("activities.activity.utils.strava_bulk_import_utils")
    def test_appends_metadata_for_bulk_import(self, mock_strava):
        from activities.activity.utils import _prepare_bulk_import_activity

        mock_strava.does_activity_start_time_match_the_data_in_strava_activities_csv.return_value = True
        mock_strava.append_bulk_import_metadata_to_activity.side_effect = lambda a, m: a

        activity = MagicMock()
        result = _prepare_bulk_import_activity(
            activity,
            is_bulk_import=True,
            created_activities_objects=[MagicMock()],
            strava_activities={"some": "data"},
            activity_metadata_dict={"metadata_found_in_csv": True},
        )

        assert result is activity
        mock_strava.append_bulk_import_metadata_to_activity.assert_called_once()


class TestCalculateInstantSpeed:
    def test_returns_zero_when_prev_time_none(self):
        from activities.activity.utils import calculate_instant_speed

        t = datetime(2024, 1, 15, 8, 0, 5)
        result = calculate_instant_speed(
            prev_time=None,
            waypoint_time=t,
            latitude=38.0,
            longitude=-9.0,
            prev_latitude=38.001,
            prev_longitude=-9.001,
        )
        assert result == 0

    def test_returns_zero_when_prev_coords_none(self):
        from activities.activity.utils import calculate_instant_speed

        t = datetime(2024, 1, 15, 8, 0, 5)
        result = calculate_instant_speed(
            prev_time=datetime(2024, 1, 15, 8, 0, 0),
            waypoint_time=t,
            latitude=38.0,
            longitude=-9.0,
            prev_latitude=None,
            prev_longitude=None,
        )
        assert result == 0

    def test_returns_zero_when_time_delta_zero(self):
        from activities.activity.utils import calculate_instant_speed

        t = datetime(2024, 1, 15, 8, 0, 0)
        result = calculate_instant_speed(
            prev_time=t,
            waypoint_time=t,
            latitude=38.0,
            longitude=-9.0,
            prev_latitude=38.001,
            prev_longitude=-9.001,
        )
        assert result == 0

    def test_returns_positive_speed(self):
        from activities.activity.utils import calculate_instant_speed

        result = calculate_instant_speed(
            prev_time=datetime(2024, 1, 15, 8, 0, 0),
            waypoint_time=datetime(2024, 1, 15, 8, 1, 0),
            latitude=38.001,
            longitude=-9.001,
            prev_latitude=38.0,
            prev_longitude=-9.0,
        )
        assert result > 0


class TestComputeElevationGainAndLoss:
    def test_returns_zero_for_empty_list(self):
        from activities.activity.utils import compute_elevation_gain_and_loss

        assert compute_elevation_gain_and_loss([]) == (0.0, 0.0)

    def test_returns_zero_for_invalid_data(self):
        from activities.activity.utils import compute_elevation_gain_and_loss

        assert compute_elevation_gain_and_loss([{"no_ele": 100}]) == (0.0, 0.0)

    def test_flat_elevation_returns_zero(self):
        from activities.activity.utils import compute_elevation_gain_and_loss

        result = compute_elevation_gain_and_loss([{"ele": 100}, {"ele": 100}, {"ele": 100}])
        assert result == (0.0, 0.0)

    def test_computes_gain(self):
        from activities.activity.utils import compute_elevation_gain_and_loss

        gain, loss = compute_elevation_gain_and_loss(
            [{"ele": 100}, {"ele": 110}, {"ele": 120}],
            median_window=1,
            avg_window=1,
            threshold=0.1,
        )
        assert gain == 20.0
        assert loss == 0.0

    def test_computes_loss(self):
        from activities.activity.utils import compute_elevation_gain_and_loss

        gain, loss = compute_elevation_gain_and_loss(
            [{"ele": 120}, {"ele": 110}, {"ele": 100}],
            median_window=1,
            avg_window=1,
            threshold=0.1,
        )
        assert gain == 0.0
        assert loss == 20.0

    def test_computes_gain_and_loss_with_threshold(self):
        from activities.activity.utils import compute_elevation_gain_and_loss

        gain, loss = compute_elevation_gain_and_loss(
            [{"ele": 100}, {"ele": 100.05}, {"ele": 120}, {"ele": 100}],
            median_window=1,
            avg_window=1,
            threshold=0.1,
        )
        assert gain > 0
        assert loss > 0

    def test_median_window_large_handles_small_list(self):
        from activities.activity.utils import compute_elevation_gain_and_loss

        gain, loss = compute_elevation_gain_and_loss([{"ele": 100}], median_window=10, avg_window=10, threshold=0.1)
        assert gain == 0.0
        assert loss == 0.0


class TestCalculatePace:
    def test_returns_zero_when_distance_zero(self):
        from activities.activity.utils import calculate_pace

        t = datetime(2024, 1, 15, 8, 0, 0)
        result = calculate_pace(distance=0, first_waypoint_time=t, last_waypoint_time=t)
        assert result == 0

    def test_calculates_pace_correctly(self):
        from activities.activity.utils import calculate_pace

        result = calculate_pace(
            distance=10000,
            first_waypoint_time=datetime(2024, 1, 15, 8, 0, 0),
            last_waypoint_time=datetime(2024, 1, 15, 9, 0, 0),
        )
        assert result == 3600.0 / 10000

    def test_calculates_pace_with_fractional_distance(self):
        from activities.activity.utils import calculate_pace

        result = calculate_pace(
            distance=5000,
            first_waypoint_time=datetime(2024, 1, 15, 8, 0, 0),
            last_waypoint_time=datetime(2024, 1, 15, 8, 25, 0),
        )
        assert result == 1500.0 / 5000


class TestCalculateAvgAndMax:
    def test_returns_zero_for_empty_data(self):
        from activities.activity.utils import calculate_avg_and_max

        assert calculate_avg_and_max([], "hr") == (0.0, 0.0)

    def test_returns_zero_for_all_none_values(self):
        from activities.activity.utils import calculate_avg_and_max

        assert calculate_avg_and_max([{"hr": None}, {"hr": None}], "hr") == (0.0, 0.0)

    def test_returns_zero_for_missing_key(self):
        from activities.activity.utils import calculate_avg_and_max

        assert calculate_avg_and_max([{"other": 100}], "hr") == (0.0, 0.0)

    def test_computes_avg_and_max(self):
        from activities.activity.utils import calculate_avg_and_max

        avg, max_val = calculate_avg_and_max([{"hr": 140}, {"hr": 150}, {"hr": 160}], "hr")
        assert avg == 150.0
        assert max_val == 160.0

    def test_handles_mixed_none_and_values(self):
        from activities.activity.utils import calculate_avg_and_max

        avg, max_val = calculate_avg_and_max([{"hr": 140}, {"hr": None}, {"hr": 160}], "hr")
        assert avg == 150.0
        assert max_val == 160.0

    def test_single_value(self):
        from activities.activity.utils import calculate_avg_and_max

        avg, max_val = calculate_avg_and_max([{"hr": 145}], "hr")
        assert avg == 145.0
        assert max_val == 145.0

    def test_returns_zero_on_value_error(self):
        from activities.activity.utils import calculate_avg_and_max

        result = calculate_avg_and_max([{"hr": "not_a_number"}], "hr")
        assert result == (0.0, 0.0)

    def test_hr_zeros_are_excluded_from_avg_and_max(self):
        from activities.activity.utils import calculate_avg_and_max

        # Zero is a sensor-off sentinel; the filter must drop it so
        # only the real readings [150, 160] contribute.
        avg, max_val = calculate_avg_and_max(
            [{"hr": 0}, {"hr": 0}, {"hr": 150}, {"hr": 160}],
            "hr",
        )
        assert avg == 155.0
        assert max_val == 160.0

    def test_all_hr_zeros_returns_zero_pair(self):
        from activities.activity.utils import calculate_avg_and_max

        # After filtering all zeros the value list is empty → (0, 0).
        assert calculate_avg_and_max([{"hr": 0}, {"hr": 0}], "hr") == (0.0, 0.0)

    def test_exclude_zeros_flag_strips_zeros_for_non_hr_stream(self):
        from activities.activity.utils import calculate_avg_and_max

        avg, max_val = calculate_avg_and_max(
            [{"power": 0}, {"power": 200}, {"power": 300}],
            "power",
            exclude_zeros=True,
        )
        assert avg == 250.0
        assert max_val == 300.0


class TestCalculateNP:
    def test_returns_zero_for_empty_data(self):
        from activities.activity.utils import calculate_np

        assert calculate_np([]) == 0

    def test_returns_zero_for_missing_power_key(self):
        from activities.activity.utils import calculate_np

        assert calculate_np([{"hr": 140}]) == 0

    def test_returns_zero_for_none_power(self):
        from activities.activity.utils import calculate_np

        assert calculate_np([{"power": None}]) == 0

    def test_normalized_power_single_value(self):
        from activities.activity.utils import calculate_np

        assert calculate_np([{"power": 200}]) == 200.0

    def test_normalized_power_multiple_values(self):
        from activities.activity.utils import calculate_np

        data = [{"power": 200}, {"power": 150}, {"power": 250}]
        result = calculate_np(data)
        expected = (200**4 + 150**4 + 250**4) / 3
        expected = expected ** (1 / 4)
        assert result == expected

    def test_returns_zero_on_value_error(self):
        from activities.activity.utils import calculate_np

        result = calculate_np([{"power": "not_a_number"}])
        assert result == 0

    def test_returns_zero_on_key_error(self):
        from activities.activity.utils import calculate_np

        result = calculate_np([{"no_power": 200}])
        assert result == 0


class TestDefineActivityType:
    def test_known_type_returns_id(self):
        from activities.activity.utils import define_activity_type

        assert define_activity_type("Run") == 1
        assert define_activity_type("run") == 1
        assert define_activity_type("Ride") == 4
        assert define_activity_type("Walk") == 11

    def test_known_alias_returns_id(self):
        from activities.activity.utils import define_activity_type

        assert define_activity_type("Cycling") == 4
        assert define_activity_type("Swim") == 8
        assert define_activity_type("Trail") == 2

    def test_unknown_type_returns_default(self):
        from activities.activity.utils import define_activity_type

        assert define_activity_type("Skydiving") == 10

    def test_non_string_input_returns_default(self):
        from activities.activity.utils import define_activity_type

        assert define_activity_type(123) == 10
        assert define_activity_type(None) == 10


class TestSetActivityNameBasedOnActivityType:
    def test_known_type_returns_name_with_workout_suffix(self):
        from activities.activity.utils import set_activity_name_based_on_activity_type

        assert set_activity_name_based_on_activity_type(1) == "Run workout"
        assert set_activity_name_based_on_activity_type(4) == "Ride workout"

    def test_workout_type_returns_workout(self):
        from activities.activity.utils import set_activity_name_based_on_activity_type

        assert set_activity_name_based_on_activity_type(10) == "Workout"

    def test_unknown_type_returns_workout(self):
        from activities.activity.utils import set_activity_name_based_on_activity_type

        assert set_activity_name_based_on_activity_type(999) == "Workout"


class TestActivityNameToId:
    def test_contains_known_mappings(self):
        from activities.activity.utils import ACTIVITY_NAME_TO_ID

        assert ACTIVITY_NAME_TO_ID["running"] == 1
        assert ACTIVITY_NAME_TO_ID["cycling"] == 4
        assert ACTIVITY_NAME_TO_ID["swim"] == 8
        assert ACTIVITY_NAME_TO_ID["hike"] == 12
        assert ACTIVITY_NAME_TO_ID["yoga"] == 14
        assert ACTIVITY_NAME_TO_ID["strength_training"] == 19
        assert ACTIVITY_NAME_TO_ID["hiit"] == 46
        assert ACTIVITY_NAME_TO_ID["jump_rope"] == 47
        assert ACTIVITY_NAME_TO_ID["jumprope"] == 47
        assert ACTIVITY_NAME_TO_ID["indoor_running"] == 40

    def test_unknown_name_not_in_mapping(self):
        from activities.activity.utils import ACTIVITY_NAME_TO_ID

        assert "skydiving" not in ACTIVITY_NAME_TO_ID


class TestParseFile:
    @patch("activities.activity.utils.gpx_utils")
    @patch("activities.activity.utils.core_logger")
    def test_parse_gpx(self, mock_logger, mock_gpx):
        from activities.activity.utils import parse_file

        mock_gpx.parse_gpx_file.return_value = {"activity": "data"}
        result = parse_file(
            token_user_id=1,
            user_privacy_settings=MagicMock(),
            file_extension=".gpx",
            filename="/path/to/file.gpx",
            db=MagicMock(),
        )
        assert result == {"activity": "data"}

    @patch("activities.activity.utils.tcx_utils")
    @patch("activities.activity.utils.core_logger")
    def test_parse_tcx(self, mock_logger, mock_tcx):
        from activities.activity.utils import parse_file

        mock_tcx.parse_tcx_file.return_value = {"activity": "tcx_data"}
        result = parse_file(
            token_user_id=1,
            user_privacy_settings=MagicMock(),
            file_extension=".tcx",
            filename="/path/to/file.tcx",
            db=MagicMock(),
        )
        assert result == {"activity": "tcx_data"}

    @patch("activities.activity.utils.fit_utils")
    @patch("activities.activity.utils.core_logger")
    def test_parse_fit(self, mock_logger, mock_fit):
        from activities.activity.utils import parse_file

        mock_fit.parse_fit_file.return_value = {"activity": "fit_data"}
        result = parse_file(
            token_user_id=1,
            user_privacy_settings=MagicMock(),
            file_extension=".fit",
            filename="/path/to/file.fit",
            db=MagicMock(),
        )
        assert result == {"activity": "fit_data"}

    @patch("activities.activity.utils.core_logger")
    def test_raises_on_unsupported_extension(self, mock_logger):
        from fastapi import HTTPException

        from activities.activity.utils import parse_file

        with pytest.raises(HTTPException) as exc:
            parse_file(
                token_user_id=1,
                user_privacy_settings=MagicMock(),
                file_extension=".xyz",
                filename="/path/to/file.xyz",
                db=MagicMock(),
            )
        assert exc.value.status_code == 406

    @patch("activities.activity.utils.core_logger")
    def test_returns_none_for_bulk_import_init(self, mock_logger):
        from activities.activity.utils import parse_file

        result = parse_file(
            token_user_id=1,
            user_privacy_settings=MagicMock(),
            file_extension=".py",
            filename="bulk_import/__init__.py",
            db=MagicMock(),
        )
        assert result is None


class TestStoreActivity:
    @patch("activities.activity.utils.activities_crud")
    @patch("activities.activity.utils.parse_activity_streams_from_file")
    @patch("activities.activity.utils.activity_streams_crud")
    @patch("activities.activity.utils.core_logger")
    def test_store_basic(self, mock_logger, mock_streams_crud, mock_parse_streams, mock_crud):
        import asyncio

        from activities.activity.utils import store_activity

        mock_crud.create_activity = AsyncMock(return_value=MagicMock(id=1))
        mock_parse_streams.return_value = None

        parsed_info = {"activity": {"name": "test"}, "is_lat_lon_set": False}

        result = asyncio.run(store_activity(parsed_info, MagicMock(), MagicMock()))

        assert result.id == 1

    @patch("activities.activity.utils.activities_crud")
    @patch("activities.activity.utils.core_logger")
    def test_raises_when_activity_none(self, mock_logger, mock_crud):
        import asyncio

        from fastapi import HTTPException

        from activities.activity.utils import store_activity

        mock_crud.create_activity = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc:
            asyncio.run(store_activity({"activity": {"name": "test"}}, MagicMock(), MagicMock()))
        assert exc.value.status_code == 500

    @patch("activities.activity.utils.activities_crud")
    @patch("activities.activity.utils.core_logger")
    def test_raises_when_id_none(self, mock_logger, mock_crud):
        import asyncio

        from fastapi import HTTPException

        from activities.activity.utils import store_activity

        mock_crud.create_activity = AsyncMock(return_value=MagicMock(id=None))

        with pytest.raises(HTTPException) as exc:
            asyncio.run(store_activity({"activity": {"name": "test"}}, MagicMock(), MagicMock()))
        assert exc.value.status_code == 500


class TestHandleGzippedFileCleanup:
    """Cover lines 463-464: cleanup on EOFError during read (temp_file_path set)."""

    @patch("activities.activity.utils.gzip.open")
    @patch("activities.activity.utils.NamedTemporaryFile")
    @patch("activities.activity.utils.move_file")
    @patch("activities.activity.utils.core_logger")
    @patch("activities.activity.utils.Path")
    def test_cleanup_on_eof_during_read(self, mock_path_cls, mock_logger, mock_move, mock_tempfile, mock_gzip_open):
        from fastapi import HTTPException

        from activities.activity.utils import handle_gzipped_file

        mock_path_cls.return_value.stem = "activity.fit"
        mock_path_cls.return_value.suffix = ".fit"
        mock_path_cls.return_value.name = "bad.gz"

        mock_file = MagicMock()
        mock_file.name = "/safe/tmp/tmp.fit"
        mock_tempfile.return_value.__enter__.return_value = mock_file

        mock_gz = MagicMock()
        mock_gzip_open.return_value.__enter__.return_value = mock_gz
        mock_gz.read.side_effect = EOFError("corrupted read")

        with pytest.raises(HTTPException) as exc:
            handle_gzipped_file("/uploads/bad.gz")
        assert exc.value.status_code == 400


class TestParseFileError:
    """Cover lines 1085-1098: exception handler in parse_file."""

    @patch("activities.activity.utils.gpx_utils")
    @patch("activities.activity.utils.core_logger")
    def test_raises_500_on_parse_error(self, mock_logger, mock_gpx):
        from fastapi import HTTPException

        from activities.activity.utils import parse_file

        mock_gpx.parse_gpx_file.side_effect = ValueError("bad data")

        with pytest.raises(HTTPException) as exc:
            parse_file(
                token_user_id=1,
                user_privacy_settings=MagicMock(),
                file_extension=".gpx",
                filename="/path/to/file.gpx",
                db=MagicMock(),
            )
        assert exc.value.status_code == 500


class TestStoreActivityExtended:
    """Cover streams/laps/sets/workout_steps/thumbnail branches (lines 1130-1162)."""

    @patch("activities.activity.utils.activities_crud")
    @patch("activities.activity.utils.parse_activity_streams_from_file")
    @patch("activities.activity.utils.activity_streams_crud")
    @patch("activities.activity.utils.activity_laps_crud")
    @patch("activities.activity.utils.activity_sets_crud")
    @patch("activities.activity.utils.core_logger")
    def test_store_with_streams_laps_and_sets(
        self, mock_logger, mock_sets_crud, mock_laps_crud, mock_streams_crud, mock_parse_streams, mock_crud
    ):
        import asyncio

        from activities.activity.utils import store_activity

        mock_crud.create_activity = AsyncMock(return_value=MagicMock(id=1))
        mock_parse_streams.return_value = [MagicMock()]
        mock_streams_crud.create_activity_streams = AsyncMock()

        parsed_info = {
            "activity": {"name": "test"},
            "is_lat_lon_set": False,
            "laps": [{"lap": 1}],
            "sets": [{"set": 1}],
        }

        asyncio.run(store_activity(parsed_info, MagicMock(), MagicMock()))

        mock_streams_crud.create_activity_streams.assert_called_once()
        mock_laps_crud.create_activity_laps.assert_called_once()
        mock_sets_crud.create_activity_sets.assert_called_once()

    @patch("activities.activity.utils.activities_crud")
    @patch("activities.activity.utils.parse_activity_streams_from_file")
    @patch("activities.activity.utils.activity_workout_steps_crud")
    @patch("activities.activity.utils.core_logger")
    def test_store_with_workout_steps(self, mock_logger, mock_wsteps_crud, mock_parse_streams, mock_crud):
        import asyncio

        from activities.activity.utils import store_activity

        mock_crud.create_activity = AsyncMock(return_value=MagicMock(id=1))
        mock_parse_streams.return_value = None

        parsed_info = {
            "activity": {"name": "test"},
            "is_lat_lon_set": False,
            "workout_steps": [{"step": 1}],
        }

        asyncio.run(store_activity(parsed_info, MagicMock(), MagicMock()))

        mock_wsteps_crud.create_activity_workout_steps.assert_called_once()

    @patch("activities.activity.utils.activities_crud")
    @patch("activities.activity.utils.parse_activity_streams_from_file")
    @patch("activities.activity.utils.server_settings_crud")
    @patch("activities.activity.utils.activities_thumbnail")
    @patch("activities.activity.utils.core_cryptography")
    @patch("activities.activity.utils.core_logger")
    def test_store_with_thumbnail_and_api_key(
        self, mock_logger, mock_crypto, mock_thumbnail, mock_ss_crud, mock_parse_streams, mock_crud
    ):
        import asyncio

        from activities.activity.utils import store_activity

        mock_crud.create_activity = AsyncMock(return_value=MagicMock(id=1))
        mock_parse_streams.return_value = None

        server_settings = MagicMock()
        server_settings.tileserver_url = "https://tiles.example.com"
        server_settings.map_background_color = "#fff"
        server_settings.tileserver_api_key = "encrypted_key"
        mock_ss_crud.get_server_settings.return_value = server_settings
        mock_crypto.decrypt_token_fernet.return_value = "decrypted_key"
        mock_thumbnail.generate_activity_thumbnail.return_value = "/thumbnails/1.png"

        parsed_info = {
            "activity": {"name": "test"},
            "is_lat_lon_set": True,
            "lat_lon_waypoints": [{"lat": 38.0, "lon": -9.0}],
        }

        asyncio.run(store_activity(parsed_info, MagicMock(), MagicMock()))

        mock_thumbnail.generate_activity_thumbnail.assert_called_once()
        mock_crud.set_activity_thumbnail_path.assert_called_once()

    @patch("activities.activity.utils.activities_crud")
    @patch("activities.activity.utils.parse_activity_streams_from_file")
    @patch("activities.activity.utils.server_settings_crud")
    @patch("activities.activity.utils.activities_thumbnail")
    @patch("activities.activity.utils.core_logger")
    def test_store_with_thumbnail_no_server_settings(
        self, mock_logger, mock_thumbnail, mock_ss_crud, mock_parse_streams, mock_crud
    ):
        import asyncio

        from activities.activity.utils import store_activity

        mock_crud.create_activity = AsyncMock(return_value=MagicMock(id=1))
        mock_parse_streams.return_value = None
        mock_ss_crud.get_server_settings.return_value = None
        mock_thumbnail.generate_activity_thumbnail.return_value = "/thumbnails/1.png"

        parsed_info = {
            "activity": {"name": "test"},
            "is_lat_lon_set": True,
            "lat_lon_waypoints": [{"lat": 38.0, "lon": -9.0}],
        }

        asyncio.run(store_activity(parsed_info, MagicMock(), MagicMock()))

        mock_thumbnail.generate_activity_thumbnail.assert_called_once()
        mock_crud.set_activity_thumbnail_path.assert_called_once()


class TestCalculateActivityStatsExtended:
    """Cover lines 1252-1253: exception handler in calculate_activity_stats."""

    @patch("activities.activity.utils.core_logger")
    def test_error_handling_bad_activity_type(self, mock_logger):
        from activities.activity.utils import calculate_activity_stats

        bad_activity = MagicMock()
        type(bad_activity).activity_type = property(lambda self: (_ for _ in ()).throw(TypeError("bad type")))

        calculate_activity_stats([bad_activity])

        mock_logger.print_to_log.assert_called_once()


class TestLocationBasedOnCoordinatesFull:
    """Cover lines 1277-1362: all providers, rate limiting, error handling."""

    @patch("activities.activity.utils.core_config.settings.REVERSE_GEO_PROVIDER", "nominatim")
    @patch("activities.activity.utils.core_config.settings.NOMINATIM_API_USE_HTTPS", True)
    @patch("activities.activity.utils.core_config.settings.NOMINATIM_API_HOST", "nominatim.openstreetmap.org")
    @patch("activities.activity.utils.core_config.REVERSE_GEO_MIN_INTERVAL", 0)
    @patch("activities.activity.utils.core_config.API_VERSION", "1.0")
    @patch("activities.activity.utils.requests.get")
    def test_nominatim_success(self, mock_get):
        from activities.activity.utils import location_based_on_coordinates

        mock_response = MagicMock()
        mock_response.json.return_value = {"address": {"city": "Lisbon", "town": "Belem", "country": "Portugal"}}
        mock_get.return_value = mock_response

        result = location_based_on_coordinates(38.0, -9.0)

        assert result == {"city": "Lisbon", "town": "Belem", "country": "Portugal"}

    @patch("activities.activity.utils.core_config.settings.REVERSE_GEO_PROVIDER", "nominatim")
    @patch("activities.activity.utils.core_config.settings.NOMINATIM_API_USE_HTTPS", True)
    @patch("activities.activity.utils.core_config.settings.NOMINATIM_API_HOST", "nominatim.openstreetmap.org")
    @patch("activities.activity.utils.core_config.REVERSE_GEO_MIN_INTERVAL", 0)
    @patch("activities.activity.utils.core_config.API_VERSION", "1.0")
    @patch("activities.activity.utils.requests.get")
    def test_nominatim_empty_address_returns_none(self, mock_get):
        from activities.activity.utils import location_based_on_coordinates

        mock_response = MagicMock()
        mock_response.json.return_value = {"address": {}}
        mock_get.return_value = mock_response

        result = location_based_on_coordinates(38.0, -9.0)

        assert result is None

    @patch("activities.activity.utils.core_config.settings.REVERSE_GEO_PROVIDER", "nominatim")
    @patch("activities.activity.utils.core_config.settings.NOMINATIM_API_USE_HTTPS", False)
    @patch("activities.activity.utils.core_config.settings.NOMINATIM_API_HOST", "localhost")
    @patch("activities.activity.utils.core_config.REVERSE_GEO_MIN_INTERVAL", 0)
    @patch("activities.activity.utils.core_config.API_VERSION", "1.0")
    @patch("activities.activity.utils.requests.get")
    def test_nominatim_http_protocol(self, mock_get):
        from activities.activity.utils import location_based_on_coordinates

        mock_response = MagicMock()
        mock_response.json.return_value = {"address": {"city": "Lisbon", "country": "Portugal"}}
        mock_get.return_value = mock_response

        result = location_based_on_coordinates(38.0, -9.0)

        assert result == {"city": "Lisbon", "town": None, "country": "Portugal"}

    @patch("activities.activity.utils.core_config.settings.REVERSE_GEO_PROVIDER", "photon")
    @patch("activities.activity.utils.core_config.settings.PHOTON_API_USE_HTTPS", True)
    @patch("activities.activity.utils.core_config.settings.PHOTON_API_HOST", "photon.komoot.io")
    @patch("activities.activity.utils.core_config.REVERSE_GEO_MIN_INTERVAL", 0)
    @patch("activities.activity.utils.core_config.API_VERSION", "1.0")
    @patch("activities.activity.utils.requests.get")
    def test_photon_success(self, mock_get):
        from activities.activity.utils import location_based_on_coordinates

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "features": [{"properties": {"district": "Lisbon", "city": "Belem", "country": "Portugal"}}]
        }
        mock_get.return_value = mock_response

        result = location_based_on_coordinates(38.0, -9.0)

        assert result == {"city": "Lisbon", "town": "Belem", "country": "Portugal"}

    @patch("activities.activity.utils.core_config.settings.REVERSE_GEO_PROVIDER", "photon")
    @patch("activities.activity.utils.core_config.settings.PHOTON_API_USE_HTTPS", False)
    @patch("activities.activity.utils.core_config.settings.PHOTON_API_HOST", "localhost")
    @patch("activities.activity.utils.core_config.REVERSE_GEO_MIN_INTERVAL", 0)
    @patch("activities.activity.utils.core_config.API_VERSION", "1.0")
    @patch("activities.activity.utils.requests.get")
    def test_photon_http_protocol(self, mock_get):
        from activities.activity.utils import location_based_on_coordinates

        mock_response = MagicMock()
        mock_response.json.return_value = {"features": [{"properties": {"country": "Test"}}]}
        mock_get.return_value = mock_response

        result = location_based_on_coordinates(0.0, 0.0)

        assert result == {"city": None, "town": None, "country": "Test"}

    @patch("activities.activity.utils.core_config.settings.REVERSE_GEO_PROVIDER", "photon")
    @patch("activities.activity.utils.core_config.settings.PHOTON_API_USE_HTTPS", True)
    @patch("activities.activity.utils.core_config.settings.PHOTON_API_HOST", "photon.komoot.io")
    @patch("activities.activity.utils.core_config.REVERSE_GEO_MIN_INTERVAL", 0)
    @patch("activities.activity.utils.core_config.API_VERSION", "1.0")
    @patch("activities.activity.utils.requests.get")
    def test_photon_no_features_returns_none(self, mock_get):
        from activities.activity.utils import location_based_on_coordinates

        mock_response = MagicMock()
        mock_response.json.return_value = {"features": []}
        mock_get.return_value = mock_response

        result = location_based_on_coordinates(38.0, -9.0)

        assert result is None

    @patch("activities.activity.utils.core_config.settings.REVERSE_GEO_PROVIDER", "geocode")
    @patch("activities.activity.utils.core_config.settings.GEOCODES_MAPS_API", "valid_key")
    @patch("activities.activity.utils.core_config.REVERSE_GEO_MIN_INTERVAL", 0)
    @patch("activities.activity.utils.core_config.API_VERSION", "1.0")
    @patch("activities.activity.utils.requests.get")
    def test_geocode_success(self, mock_get):
        from activities.activity.utils import location_based_on_coordinates

        mock_response = MagicMock()
        mock_response.json.return_value = {"address": {"city": "Lisbon", "country": "Portugal"}}
        mock_get.return_value = mock_response

        result = location_based_on_coordinates(38.0, -9.0)

        assert result == {"city": "Lisbon", "town": None, "country": "Portugal"}

    @patch("activities.activity.utils.core_config.settings.REVERSE_GEO_PROVIDER", "nominatim")
    @patch("activities.activity.utils.core_config.settings.NOMINATIM_API_USE_HTTPS", True)
    @patch("activities.activity.utils.core_config.settings.NOMINATIM_API_HOST", "nominatim.openstreetmap.org")
    @patch("activities.activity.utils.core_config.REVERSE_GEO_MIN_INTERVAL", 0)
    @patch("activities.activity.utils.core_config.API_VERSION", "1.0")
    @patch("activities.activity.utils.requests.get")
    def test_nominatim_http_error_returns_none(self, mock_get):
        from activities.activity.utils import location_based_on_coordinates

        mock_get.side_effect = Exception("Connection error")

        result = location_based_on_coordinates(38.0, -9.0)

        assert result is None

    @patch("activities.activity.utils.core_config.settings.REVERSE_GEO_PROVIDER", "nominatim")
    @patch("activities.activity.utils.core_config.settings.NOMINATIM_API_USE_HTTPS", True)
    @patch("activities.activity.utils.core_config.settings.NOMINATIM_API_HOST", "nominatim.openstreetmap.org")
    @patch("activities.activity.utils.core_config.API_VERSION", "1.0")
    @patch("activities.activity.utils.core_config.REVERSE_GEO_LOCK")
    @patch("activities.activity.utils.requests.get")
    @patch("activities.activity.utils.time.sleep")
    @patch("activities.activity.utils.time.monotonic")
    def test_rate_limiting_applied(self, mock_monotonic, mock_sleep, mock_get, mock_lock):
        from activities.activity.utils import location_based_on_coordinates

        with (
            patch("activities.activity.utils.core_config.REVERSE_GEO_MIN_INTERVAL", 1),
            patch("activities.activity.utils.core_config.REVERSE_GEO_LAST_CALL", 0),
        ):
            mock_lock.__enter__.return_value = None
            mock_lock.__exit__.return_value = None
            mock_monotonic.side_effect = [0.5, 0.5]

            mock_response = MagicMock()
            mock_response.json.return_value = {"address": {"country": "Test"}}
            mock_get.return_value = mock_response

            result = location_based_on_coordinates(0.0, 0.0)

            assert result is not None
            mock_sleep.assert_called_once()


class TestDeleteAndRegenerateThumbnails:
    """Cover lines 1667-1696: delete and regenerate all activity thumbnails."""

    @patch("activities.activity.utils.core_database.SessionLocal")
    @patch("activities.activity.utils.activities_crud")
    @patch("activities.activity.utils.Path")
    @patch("activities.activity.utils.generate_missing_activity_thumbnails")
    @patch("activities.activity.utils.core_logger")
    def test_happy_path(self, mock_logger, mock_gen, mock_path_cls, mock_crud, mock_session):
        from activities.activity.utils import delete_and_regenerate_all_activity_thumbnails

        mock_db = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_db

        mock_thumb_dir = MagicMock()
        mock_path_cls.return_value = mock_thumb_dir
        mock_thumb_dir.is_dir.return_value = True
        mock_file1 = MagicMock()
        mock_file2 = MagicMock()
        mock_thumb_dir.glob.return_value = [mock_file1, mock_file2]

        delete_and_regenerate_all_activity_thumbnails()

        mock_crud.clear_all_activity_thumbnail_paths.assert_called_once_with(mock_db)
        mock_file1.unlink.assert_called_once()
        mock_file2.unlink.assert_called_once()
        mock_gen.assert_called_once()

    @patch("activities.activity.utils.core_database.SessionLocal")
    @patch("activities.activity.utils.activities_crud")
    @patch("activities.activity.utils.Path")
    @patch("activities.activity.utils.generate_missing_activity_thumbnails")
    @patch("activities.activity.utils.core_logger")
    def test_no_thumbnails_dir(self, mock_logger, mock_gen, mock_path_cls, mock_crud, mock_session):
        from activities.activity.utils import delete_and_regenerate_all_activity_thumbnails

        mock_db = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_db

        mock_thumb_dir = MagicMock()
        mock_path_cls.return_value = mock_thumb_dir
        mock_thumb_dir.is_dir.return_value = False

        delete_and_regenerate_all_activity_thumbnails()

        mock_thumb_dir.glob.assert_not_called()
        mock_gen.assert_called_once()

    @patch("activities.activity.utils.core_database.SessionLocal")
    @patch("activities.activity.utils.activities_crud")
    @patch("activities.activity.utils.Path")
    @patch("activities.activity.utils.generate_missing_activity_thumbnails")
    @patch("activities.activity.utils.core_logger")
    def test_logs_oserror_on_unlink(self, mock_logger, mock_gen, mock_path_cls, mock_crud, mock_session):
        from activities.activity.utils import delete_and_regenerate_all_activity_thumbnails

        mock_db = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_db

        mock_thumb_dir = MagicMock()
        mock_path_cls.return_value = mock_thumb_dir
        mock_thumb_dir.is_dir.return_value = True
        mock_file = MagicMock()
        mock_file.unlink.side_effect = OSError("Permission denied")
        mock_thumb_dir.glob.return_value = [mock_file]

        delete_and_regenerate_all_activity_thumbnails()

        mock_logger.print_to_log.assert_any_call(
            f"Thumbnail regeneration: could not delete {mock_file}: Permission denied",
            "warning",
        )
        mock_gen.assert_called_once()


class TestGenerateMissingThumbnails:
    """Cover lines 1714-1779: generate missing activity thumbnails."""

    @patch("activities.activity.utils.core_database.SessionLocal")
    @patch("activities.activity.utils.activities_crud")
    @patch("activities.activity.utils.core_logger")
    def test_no_activities_without_thumbnail(self, mock_logger, mock_crud, mock_session):
        from activities.activity.utils import generate_missing_activity_thumbnails

        mock_db = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_db
        mock_crud.get_activities_with_thumbnail.return_value = []
        mock_crud.get_activities_without_thumbnail.return_value = []

        generate_missing_activity_thumbnails()

        mock_logger.print_to_log.assert_any_call(
            "Thumbnail scheduler: no activities without thumbnail found",
            "debug",
        )

    @patch("activities.activity.utils.core_database.SessionLocal")
    @patch("activities.activity.utils.activities_crud")
    @patch("activities.activity.utils.Path")
    @patch("activities.activity.utils.core_logger")
    def test_clears_missing_thumbnail_file_reference(self, mock_logger, mock_path_cls, mock_crud, mock_session):
        from activities.activity.utils import generate_missing_activity_thumbnails

        mock_db = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_db

        activity = MagicMock()
        activity.id = 1
        activity.map_thumbnail_path = "/thumbnails/missing.png"
        mock_crud.get_activities_with_thumbnail.return_value = [activity]
        mock_crud.get_activities_without_thumbnail.return_value = []

        mock_path = MagicMock()
        mock_path.is_file.return_value = False
        mock_path_cls.return_value = mock_path

        generate_missing_activity_thumbnails()

        mock_crud.set_activity_thumbnail_path.assert_called_once_with(1, None, mock_db)

    @patch("activities.activity.utils.core_database.SessionLocal")
    @patch("activities.activity.utils.activities_crud")
    @patch("activities.activity.utils.server_settings_crud")
    @patch("activities.activity.utils.activities_thumbnail")
    @patch("activities.activity.utils.core_cryptography")
    @patch("activities.activity.utils.core_logger")
    def test_generates_thumbnails_with_api_key(
        self, mock_logger, mock_crypto, mock_thumbnail, mock_ss_crud, mock_crud, mock_session
    ):
        from activities.activity.utils import generate_missing_activity_thumbnails

        mock_db = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_db
        mock_crud.get_activities_with_thumbnail.return_value = []

        act = MagicMock()
        act.id = 1
        mock_crud.get_activities_without_thumbnail.return_value = [act]

        server_settings = MagicMock()
        server_settings.tileserver_url = "https://tiles.example.com"
        server_settings.map_background_color = "#fff"
        server_settings.tileserver_api_key = "encrypted_key"
        mock_ss_crud.get_server_settings.return_value = server_settings
        mock_crypto.decrypt_token_fernet.return_value = "decrypted_key"

        mock_stream = MagicMock()
        mock_stream.activity_id = 1
        mock_stream.stream_waypoints = [{"lat": 38.0, "lon": -9.0}]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_stream]
        mock_db.execute.return_value = mock_result

        mock_thumbnail.generate_activity_thumbnail.return_value = "/thumbnails/1.png"

        generate_missing_activity_thumbnails()

        mock_crypto.decrypt_token_fernet.assert_called_once_with("encrypted_key")
        mock_thumbnail.generate_activity_thumbnail.assert_called_once()
        mock_crud.set_activity_thumbnail_path.assert_called_once()

    @patch("activities.activity.utils.core_database.SessionLocal")
    @patch("activities.activity.utils.activities_crud")
    @patch("activities.activity.utils.server_settings_crud")
    @patch("activities.activity.utils.activities_thumbnail")
    @patch("activities.activity.utils.core_logger")
    def test_skips_activity_without_gps_stream(
        self, mock_logger, mock_thumbnail, mock_ss_crud, mock_crud, mock_session
    ):
        from activities.activity.utils import generate_missing_activity_thumbnails

        mock_db = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_db
        mock_crud.get_activities_with_thumbnail.return_value = []

        act1 = MagicMock()
        act1.id = 1
        act2 = MagicMock()
        act2.id = 2
        mock_crud.get_activities_without_thumbnail.return_value = [act1, act2]

        mock_ss_crud.get_server_settings.return_value = None

        mock_stream1 = MagicMock()
        mock_stream1.activity_id = 1
        mock_stream1.stream_waypoints = [{"lat": 38.0, "lon": -9.0}]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_stream1]
        mock_db.execute.return_value = mock_result

        mock_thumbnail.generate_activity_thumbnail.return_value = "/thumbnails/1.png"

        generate_missing_activity_thumbnails()

        mock_thumbnail.generate_activity_thumbnail.assert_called_once()
        mock_crud.set_activity_thumbnail_path.assert_called_once()
