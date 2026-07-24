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
        from modules.activities.activity.crud import _transform_schema_activity_to_model_activity

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

        _transform_schema_activity_to_model_activity(activity_schema)

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
        from modules.activities.activity.crud import _transform_schema_activity_to_model_activity

        mock_sanitization.sanitize_markdown.side_effect = lambda x: x
        mock_model.return_value = MagicMock()

        created_at = datetime(2024, 1, 10, 12, 0, 0, tzinfo=UTC)
        activity_schema = self._make_schema(created_at=created_at)

        _transform_schema_activity_to_model_activity(activity_schema)

        _, kwargs = mock_model.call_args
        assert kwargs["created_at"] == created_at

    @patch("modules.activities.activity.crud.activities_models.Activity")
    @patch("modules.activities.activity.crud.core_sanitization")
    def test_transform_total_timer_time_falls_back_to_elapsed(self, mock_sanitization, mock_model):
        from modules.activities.activity.crud import _transform_schema_activity_to_model_activity

        mock_sanitization.sanitize_markdown.side_effect = lambda x: x
        mock_model.return_value = MagicMock()

        activity_schema = self._make_schema(total_elapsed_time=4000.0, total_timer_time=None)

        _transform_schema_activity_to_model_activity(activity_schema)

        _, kwargs = mock_model.call_args
        assert kwargs["total_timer_time"] == 4000.0

    @patch("modules.activities.activity.crud.activities_models.Activity")
    @patch("modules.activities.activity.crud.core_sanitization")
    def test_transform_sanitizes_markdown(self, mock_sanitization, mock_model):
        from modules.activities.activity.crud import _transform_schema_activity_to_model_activity

        mock_sanitization.sanitize_markdown.side_effect = lambda x: f"sanitized:{x}"
        mock_model.return_value = MagicMock()

        activity_schema = self._make_schema(
            description="<script>alert('xss')</script>",
            private_notes="<b>secret</b>",
        )

        _transform_schema_activity_to_model_activity(activity_schema)

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
        mock_thumbnail.thumbnail_url.assert_called_once_with("1.webp", activity.id)
        mock_schema_cls.model_validate.assert_called_once_with(activity)


class TestCalculateActivityStatsExtended:
    """Cover lines 1252-1253: exception handler in calculate_activity_stats."""

    @patch("modules.activities.activity.stats.core_logger")
    def test_error_handling_bad_activity_type(self, mock_logger):
        from modules.activities.activity.stats import calculate_activity_stats

        bad_activity = MagicMock()
        type(bad_activity).activity_type = property(lambda self: (_ for _ in ()).throw(TypeError("bad type")))

        calculate_activity_stats([bad_activity])

        mock_logger.print_to_log.assert_called_once()
