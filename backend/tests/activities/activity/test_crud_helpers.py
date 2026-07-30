"""Tests for the pure helpers in ``activities.activity.crud``.

Covers the LIKE-escaping and schema→ORM transformation helpers; the query
functions themselves live in ``test_crud.py``.
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch


class TestEscapeLike:
    def test_escape_percent(self):
        from modules.activities.activity.query import escape_like

        result = escape_like("100%")
        assert result == "100\\%"

    def test_escape_underscore(self):
        from modules.activities.activity.query import escape_like

        result = escape_like("test_name")
        assert result == "test\\_name"

    def test_escape_backslash(self):
        from modules.activities.activity.query import escape_like

        result = escape_like("foo\\bar")
        assert result == "foo\\\\bar"

    def test_no_escaping_needed(self):
        from modules.activities.activity.query import escape_like

        result = escape_like("hello")
        assert result == "hello"

    def test_escape_all(self):
        from modules.activities.activity.query import escape_like

        result = escape_like("a%b_c\\d")
        assert result == "a\\%b\\_c\\\\d"


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
