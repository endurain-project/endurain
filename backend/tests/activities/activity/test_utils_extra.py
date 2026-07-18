"""Tests for uncovered utility functions in activities.activity.utils."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch


class TestTransformSchemaToModel:
    def _make_schema(self, **overrides):
        from modules.activities.activity import schema as activities_schema

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

    @patch("modules.activities.activity.crud.activities_models.Activity")
    @patch("modules.activities.activity.crud.core_sanitization")
    def test_transform_basic(self, mock_sanitization, mock_model):
        from modules.activities.activity.crud import transform_schema_activity_to_model_activity

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

    @patch("modules.activities.activity.crud.activities_models.Activity")
    @patch("modules.activities.activity.crud.core_sanitization")
    def test_transform_with_created_at(self, mock_sanitization, mock_model):
        from modules.activities.activity.crud import transform_schema_activity_to_model_activity

        mock_sanitization.sanitize_markdown.side_effect = lambda x: x
        mock_model.return_value = MagicMock()

        created_at = datetime(2024, 1, 10, 12, 0, 0, tzinfo=UTC)
        activity_schema = self._make_schema(created_at=created_at)

        transform_schema_activity_to_model_activity(activity_schema)

        _, kwargs = mock_model.call_args
        assert kwargs["created_at"] == created_at

    @patch("modules.activities.activity.crud.activities_models.Activity")
    @patch("modules.activities.activity.crud.core_sanitization")
    def test_transform_total_timer_time_falls_back_to_elapsed(self, mock_sanitization, mock_model):
        from modules.activities.activity.crud import transform_schema_activity_to_model_activity

        mock_sanitization.sanitize_markdown.side_effect = lambda x: x
        mock_model.return_value = MagicMock()

        activity_schema = self._make_schema(total_elapsed_time=4000.0, total_timer_time=None)

        transform_schema_activity_to_model_activity(activity_schema)

        _, kwargs = mock_model.call_args
        assert kwargs["total_timer_time"] == 4000.0

    @patch("modules.activities.activity.crud.activities_models.Activity")
    @patch("modules.activities.activity.crud.core_sanitization")
    def test_transform_sanitizes_markdown(self, mock_sanitization, mock_model):
        from modules.activities.activity.crud import transform_schema_activity_to_model_activity

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
    @patch("modules.activities.activity.serializers.activity_thumbnail_render")
    @patch("modules.activities.activity.serializers.activities_schema.Activity")
    @patch("modules.activities.activity.serializers.core_timezone")
    def test_serialize_basic(self, mock_tz, mock_schema_cls, mock_thumbnail):
        from modules.activities.activity.serializers import serialize_activity

        mock_tz.format_aware_datetime.side_effect = lambda dt, tz: (
            "2024-01-15T08:00:00" if tz is None else "2024-01-15T09:00:00"
        )
        mock_schema = MagicMock()
        mock_schema_cls.model_validate.return_value = mock_schema
        mock_thumbnail.thumbnail_url.return_value = "/activity_thumbnails/1.webp"

        activity = MagicMock()
        activity.timezone = "Europe/Lisbon"
        activity.map_thumbnail_path = "1.webp"
        activity.start_time = datetime(2024, 1, 15, 8, 0, 0, tzinfo=UTC)
        activity.end_time = datetime(2024, 1, 15, 9, 0, 0, tzinfo=UTC)
        activity.created_at = datetime(2024, 1, 15, 7, 0, 0, tzinfo=UTC)

        result = serialize_activity(activity)

        assert mock_tz.format_aware_datetime.call_count == 6
        assert result.start_time_tz_applied == "2024-01-15T09:00:00"
        assert result.start_time == "2024-01-15T08:00:00"
        assert result.map_thumbnail_path == "/activity_thumbnails/1.webp"
        mock_thumbnail.thumbnail_url.assert_called_once_with("1.webp")
        mock_schema_cls.model_validate.assert_called_once_with(activity)


class TestCalculateInstantSpeed:
    def test_returns_zero_when_prev_time_none(self):
        from modules.activities.activity.utils import calculate_instant_speed

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
        from modules.activities.activity.utils import calculate_instant_speed

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
        from modules.activities.activity.utils import calculate_instant_speed

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
        from modules.activities.activity.utils import calculate_instant_speed

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
        from modules.activities.activity.utils import compute_elevation_gain_and_loss

        assert compute_elevation_gain_and_loss([]) == (0.0, 0.0)

    def test_returns_zero_for_invalid_data(self):
        from modules.activities.activity.utils import compute_elevation_gain_and_loss

        assert compute_elevation_gain_and_loss([{"no_ele": 100}]) == (0.0, 0.0)

    def test_flat_elevation_returns_zero(self):
        from modules.activities.activity.utils import compute_elevation_gain_and_loss

        result = compute_elevation_gain_and_loss([{"ele": 100}, {"ele": 100}, {"ele": 100}])
        assert result == (0.0, 0.0)

    def test_computes_gain(self):
        from modules.activities.activity.utils import compute_elevation_gain_and_loss

        gain, loss = compute_elevation_gain_and_loss(
            [{"ele": 100}, {"ele": 110}, {"ele": 120}],
            median_window=1,
            avg_window=1,
            threshold=0.1,
        )
        assert gain == 20.0
        assert loss == 0.0

    def test_computes_loss(self):
        from modules.activities.activity.utils import compute_elevation_gain_and_loss

        gain, loss = compute_elevation_gain_and_loss(
            [{"ele": 120}, {"ele": 110}, {"ele": 100}],
            median_window=1,
            avg_window=1,
            threshold=0.1,
        )
        assert gain == 0.0
        assert loss == 20.0

    def test_computes_gain_and_loss_with_threshold(self):
        from modules.activities.activity.utils import compute_elevation_gain_and_loss

        gain, loss = compute_elevation_gain_and_loss(
            [{"ele": 100}, {"ele": 100.05}, {"ele": 120}, {"ele": 100}],
            median_window=1,
            avg_window=1,
            threshold=0.1,
        )
        assert gain > 0
        assert loss > 0

    def test_median_window_large_handles_small_list(self):
        from modules.activities.activity.utils import compute_elevation_gain_and_loss

        gain, loss = compute_elevation_gain_and_loss([{"ele": 100}], median_window=10, avg_window=10, threshold=0.1)
        assert gain == 0.0
        assert loss == 0.0


class TestCalculatePace:
    def test_returns_zero_when_distance_zero(self):
        from modules.activities.activity.utils import calculate_pace

        t = datetime(2024, 1, 15, 8, 0, 0)
        result = calculate_pace(distance=0, first_waypoint_time=t, last_waypoint_time=t)
        assert result == 0

    def test_calculates_pace_correctly(self):
        from modules.activities.activity.utils import calculate_pace

        result = calculate_pace(
            distance=10000,
            first_waypoint_time=datetime(2024, 1, 15, 8, 0, 0),
            last_waypoint_time=datetime(2024, 1, 15, 9, 0, 0),
        )
        assert result == 3600.0 / 10000

    def test_calculates_pace_with_fractional_distance(self):
        from modules.activities.activity.utils import calculate_pace

        result = calculate_pace(
            distance=5000,
            first_waypoint_time=datetime(2024, 1, 15, 8, 0, 0),
            last_waypoint_time=datetime(2024, 1, 15, 8, 25, 0),
        )
        assert result == 1500.0 / 5000


class TestCalculateAvgAndMax:
    def test_returns_zero_for_empty_data(self):
        from modules.activities.activity.utils import calculate_avg_and_max

        assert calculate_avg_and_max([], "hr") == (0.0, 0.0)

    def test_returns_zero_for_all_none_values(self):
        from modules.activities.activity.utils import calculate_avg_and_max

        assert calculate_avg_and_max([{"hr": None}, {"hr": None}], "hr") == (0.0, 0.0)

    def test_returns_zero_for_missing_key(self):
        from modules.activities.activity.utils import calculate_avg_and_max

        assert calculate_avg_and_max([{"other": 100}], "hr") == (0.0, 0.0)

    def test_computes_avg_and_max(self):
        from modules.activities.activity.utils import calculate_avg_and_max

        avg, max_val = calculate_avg_and_max([{"hr": 140}, {"hr": 150}, {"hr": 160}], "hr")
        assert avg == 150.0
        assert max_val == 160.0

    def test_handles_mixed_none_and_values(self):
        from modules.activities.activity.utils import calculate_avg_and_max

        avg, max_val = calculate_avg_and_max([{"hr": 140}, {"hr": None}, {"hr": 160}], "hr")
        assert avg == 150.0
        assert max_val == 160.0

    def test_single_value(self):
        from modules.activities.activity.utils import calculate_avg_and_max

        avg, max_val = calculate_avg_and_max([{"hr": 145}], "hr")
        assert avg == 145.0
        assert max_val == 145.0

    def test_returns_zero_on_value_error(self):
        from modules.activities.activity.utils import calculate_avg_and_max

        result = calculate_avg_and_max([{"hr": "not_a_number"}], "hr")
        assert result == (0.0, 0.0)

    def test_hr_zeros_are_excluded_from_avg_and_max(self):
        from modules.activities.activity.utils import calculate_avg_and_max

        # Zero is a sensor-off sentinel; the filter must drop it so
        # only the real readings [150, 160] contribute.
        avg, max_val = calculate_avg_and_max(
            [{"hr": 0}, {"hr": 0}, {"hr": 150}, {"hr": 160}],
            "hr",
        )
        assert avg == 155.0
        assert max_val == 160.0

    def test_all_hr_zeros_returns_zero_pair(self):
        from modules.activities.activity.utils import calculate_avg_and_max

        # After filtering all zeros the value list is empty → (0, 0).
        assert calculate_avg_and_max([{"hr": 0}, {"hr": 0}], "hr") == (0.0, 0.0)

    def test_exclude_zeros_flag_strips_zeros_for_non_hr_stream(self):
        from modules.activities.activity.utils import calculate_avg_and_max

        avg, max_val = calculate_avg_and_max(
            [{"power": 0}, {"power": 200}, {"power": 300}],
            "power",
            exclude_zeros=True,
        )
        assert avg == 250.0
        assert max_val == 300.0


class TestCalculateNP:
    def test_returns_zero_for_empty_data(self):
        from modules.activities.activity.utils import calculate_np

        assert calculate_np([]) == 0

    def test_returns_zero_for_missing_power_key(self):
        from modules.activities.activity.utils import calculate_np

        assert calculate_np([{"hr": 140}]) == 0

    def test_returns_zero_for_none_power(self):
        from modules.activities.activity.utils import calculate_np

        assert calculate_np([{"power": None}]) == 0

    def test_normalized_power_single_value(self):
        from modules.activities.activity.utils import calculate_np

        assert calculate_np([{"power": 200}]) == 200.0

    def test_normalized_power_multiple_values(self):
        from modules.activities.activity.utils import calculate_np

        data = [{"power": 200}, {"power": 150}, {"power": 250}]
        result = calculate_np(data)
        expected = (200**4 + 150**4 + 250**4) / 3
        expected = expected ** (1 / 4)
        assert result == expected

    def test_returns_zero_on_value_error(self):
        from modules.activities.activity.utils import calculate_np

        result = calculate_np([{"power": "not_a_number"}])
        assert result == 0

    def test_returns_zero_on_key_error(self):
        from modules.activities.activity.utils import calculate_np

        result = calculate_np([{"no_power": 200}])
        assert result == 0


class TestDefineActivityType:
    def test_known_type_returns_id(self):
        from modules.activities.activity.utils import define_activity_type

        assert define_activity_type("Run") == 1
        assert define_activity_type("run") == 1
        assert define_activity_type("Ride") == 4
        assert define_activity_type("Walk") == 11

    def test_known_alias_returns_id(self):
        from modules.activities.activity.utils import define_activity_type

        assert define_activity_type("Cycling") == 4
        assert define_activity_type("Swim") == 8
        assert define_activity_type("Trail") == 2

    def test_unknown_type_returns_default(self):
        from modules.activities.activity.utils import define_activity_type

        assert define_activity_type("Skydiving") == 10

    def test_non_string_input_returns_default(self):
        from modules.activities.activity.utils import define_activity_type

        assert define_activity_type(123) == 10
        assert define_activity_type(None) == 10


class TestSetActivityNameBasedOnActivityType:
    def test_known_type_returns_name_with_workout_suffix(self):
        from modules.activities.activity.utils import set_activity_name_based_on_activity_type

        assert set_activity_name_based_on_activity_type(1) == "Run workout"
        assert set_activity_name_based_on_activity_type(4) == "Ride workout"

    def test_workout_type_returns_workout(self):
        from modules.activities.activity.utils import set_activity_name_based_on_activity_type

        assert set_activity_name_based_on_activity_type(10) == "Workout"

    def test_unknown_type_returns_workout(self):
        from modules.activities.activity.utils import set_activity_name_based_on_activity_type

        assert set_activity_name_based_on_activity_type(999) == "Workout"


class TestActivityNameToId:
    def test_contains_known_mappings(self):
        from modules.activities.activity.constants import ACTIVITY_NAME_TO_ID

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
        from modules.activities.activity.utils import ACTIVITY_NAME_TO_ID

        assert "skydiving" not in ACTIVITY_NAME_TO_ID


class TestCalculateActivityStatsExtended:
    """Cover lines 1252-1253: exception handler in calculate_activity_stats."""

    @patch("modules.activities.activity.stats.core_logger")
    def test_error_handling_bad_activity_type(self, mock_logger):
        from modules.activities.activity.stats import calculate_activity_stats

        bad_activity = MagicMock()
        type(bad_activity).activity_type = property(lambda self: (_ for _ in ()).throw(TypeError("bad type")))

        calculate_activity_stats([bad_activity])

        mock_logger.print_to_log.assert_called_once()
