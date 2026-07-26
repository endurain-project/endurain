"""Tests for uncovered utility functions in activities.activity.utils."""

from datetime import UTC, datetime
from types import SimpleNamespace
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

        # Only the three *_tz_applied display fields are formatted; the raw
        # datetimes keep the aware UTC values validated off the ORM row.
        assert mock_tz.format_aware_datetime.call_count == 3
        assert all(call.args[1] == "Europe/Lisbon" for call in mock_tz.format_aware_datetime.call_args_list)
        assert result.start_time_tz_applied == "2024-01-15T09:00:00"
        assert result.map_thumbnail_path == "/activity_thumbnails/1.webp"
        mock_thumbnail.thumbnail_url.assert_called_once_with("1.webp", activity.id)
        mock_schema_cls.model_validate.assert_called_once_with(activity)

    @patch("modules.activities.activity.serializers.activity_thumbnail_render")
    def test_raw_datetimes_stay_aware_utc(self, mock_thumbnail):
        """The API must emit a real instant, not a server-local wall clock."""
        from modules.activities.activity.serializers import serialize_activity

        mock_thumbnail.thumbnail_url.return_value = None
        activity = _activity_orm_stub()

        result = serialize_activity(activity)

        assert result.start_time == datetime(2024, 1, 15, 8, 0, 0, tzinfo=UTC)
        assert result.end_time == datetime(2024, 1, 15, 9, 0, 0, tzinfo=UTC)
        assert result.created_at == datetime(2024, 1, 15, 7, 0, 0, tzinfo=UTC)
        # ...while the display fields are localized to the activity's timezone
        # (Asia/Tokyo is UTC+9, so 08:00Z is 17:00 local).
        assert result.start_time_tz_applied == "2024-01-15T17:00:00"
        assert result.end_time_tz_applied == "2024-01-15T18:00:00"


def _activity_orm_stub():
    """An ORM-shaped object carrying only the attributes the serializer reads.

    A ``SimpleNamespace`` rather than a ``MagicMock`` so ``model_validate`` sees
    real values (a MagicMock hands back child mocks for every optional field and
    fails validation), and rather than a real ORM row so the test does not need
    the whole mapper registry configured.
    """
    return SimpleNamespace(
        id=1,
        user_id=1,
        distance=1000,
        name="Ride",
        activity_type=5,
        timezone="Asia/Tokyo",
        map_thumbnail_path=None,
        start_time=datetime(2024, 1, 15, 8, 0, 0, tzinfo=UTC),
        end_time=datetime(2024, 1, 15, 9, 0, 0, tzinfo=UTC),
        created_at=datetime(2024, 1, 15, 7, 0, 0, tzinfo=UTC),
    )


class TestApplyVisibilityMask:
    def test_hide_start_time_also_clears_localized_fields(self):
        """The *_tz_applied fields carry the same instant, so they must be masked too."""
        from modules.activities.activity.schema import Activity
        from modules.activities.activity.serializers import apply_visibility_mask

        schema = Activity(
            distance=1000,
            name="Ride",
            activity_type=5,
            start_time=datetime(2024, 1, 15, 8, 0, 0, tzinfo=UTC),
            start_time_tz_applied="2024-01-15T09:00:00",
            end_time=datetime(2024, 1, 15, 9, 0, 0, tzinfo=UTC),
            end_time_tz_applied="2024-01-15T10:00:00",
            hide_start_time=True,
        )

        apply_visibility_mask(schema, is_owner=False)

        assert schema.start_time is None
        assert schema.end_time is None
        assert schema.start_time_tz_applied is None
        assert schema.end_time_tz_applied is None

    def test_owner_keeps_everything(self):
        from modules.activities.activity.schema import Activity
        from modules.activities.activity.serializers import apply_visibility_mask

        schema = Activity(
            distance=1000,
            name="Ride",
            activity_type=5,
            start_time_tz_applied="2024-01-15T09:00:00",
            hide_start_time=True,
        )

        apply_visibility_mask(schema, is_owner=True)

        assert schema.start_time_tz_applied == "2024-01-15T09:00:00"


class TestCalculateActivityStatsExtended:
    """Cover lines 1252-1253: exception handler in calculate_activity_stats."""

    @patch("modules.activities.activity.stats.core_logger")
    def test_error_handling_bad_activity_type(self, mock_logger):
        from modules.activities.activity.stats import calculate_activity_stats

        bad_activity = MagicMock()
        type(bad_activity).activity_type = property(lambda self: (_ for _ in ()).throw(TypeError("bad type")))

        calculate_activity_stats([bad_activity])

        mock_logger.print_to_log.assert_called_once()
