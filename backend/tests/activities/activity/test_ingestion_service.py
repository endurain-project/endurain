"""Tests for the core activity ingestion service (store_parsed_activity)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


def _parsed(**overrides):
    """Build a ParsedActivity with a mock activity and overridable children."""
    import modules.activities.activity.schema as schema

    data = {
        "activity": MagicMock(),
        "streams": [],
        "laps": None,
        "sets": None,
        "workout_steps": None,
        "source": schema.ImportSource(kind="upload"),
    }
    data.update(overrides)
    return schema.ParsedActivity(**data)


class TestStoreParsedActivity:
    @patch("modules.activities.activity.ingestion_service.activity_event_publishers")
    @patch("modules.activities.activity.ingestion_service.activity_streams_crud")
    @patch("modules.activities.activity.ingestion_service.activities_crud")
    def test_stores_activity_and_streams(self, mock_crud, mock_streams_crud, mock_pub):
        import modules.activities.activity.ingestion_service as ingestion_service
        import modules.activities.activity.schema as schema

        created = MagicMock(id=7, user_id=3)
        mock_crud.create_activity = MagicMock(return_value=created)
        mock_streams_crud.create_activity_streams = AsyncMock()

        parsed = _parsed(streams=[schema.ParsedStream(stream_type=1, stream_waypoints=[{"hr": 100}])])

        result = asyncio.run(ingestion_service.store_parsed_activity(parsed, MagicMock()))

        assert result is created
        mock_crud.create_activity.assert_called_once()
        # The stream was converted to an ActivityStreamsCreate carrying the new id.
        mock_streams_crud.create_activity_streams.assert_awaited_once()
        built_streams = mock_streams_crud.create_activity_streams.call_args.args[0]
        assert built_streams[0].activity_id == 7
        assert built_streams[0].stream_type == 1
        mock_pub.publish_activity_created.assert_called_once()
        assert mock_pub.publish_activity_created.call_args.args[:2] == (7, 3)

    @patch("modules.activities.activity.ingestion_service.activity_event_publishers")
    @patch("modules.activities.activity.ingestion_service.activity_streams_crud")
    @patch("modules.activities.activity.ingestion_service.activities_crud")
    def test_no_streams_skips_stream_creation(self, mock_crud, mock_streams_crud, mock_pub):
        import modules.activities.activity.ingestion_service as ingestion_service

        mock_crud.create_activity = MagicMock(return_value=MagicMock(id=1, user_id=1))
        mock_streams_crud.create_activity_streams = AsyncMock()

        asyncio.run(ingestion_service.store_parsed_activity(_parsed(), MagicMock()))

        mock_streams_crud.create_activity_streams.assert_not_awaited()

    @patch("modules.activities.activity.ingestion_service.activity_event_publishers")
    @patch("modules.activities.activity.ingestion_service.activity_workout_steps_crud")
    @patch("modules.activities.activity.ingestion_service.activity_sets_crud")
    @patch("modules.activities.activity.ingestion_service.activity_laps_crud")
    @patch("modules.activities.activity.ingestion_service.activities_crud")
    def test_persists_laps_sets_and_steps(self, mock_crud, mock_laps, mock_sets, mock_steps, mock_pub):
        import modules.activities.activity.ingestion_service as ingestion_service

        mock_crud.create_activity = MagicMock(return_value=MagicMock(id=9, user_id=1))

        parsed = _parsed(laps=[{"a": 1}], sets=[{"b": 2}], workout_steps=[{"c": 3}])
        asyncio.run(ingestion_service.store_parsed_activity(parsed, MagicMock()))

        mock_laps.create_activity_laps.assert_called_once()
        mock_sets.create_activity_sets.assert_called_once()
        mock_steps.create_activity_workout_steps.assert_called_once()

    @patch("modules.activities.activity.ingestion_service.activities_crud")
    def test_raises_when_activity_none(self, mock_crud):
        import modules.activities.activity.ingestion_service as ingestion_service

        mock_crud.create_activity = MagicMock(return_value=None)

        with pytest.raises(HTTPException) as exc:
            asyncio.run(ingestion_service.store_parsed_activity(_parsed(), MagicMock()))
        assert exc.value.status_code == 500

    @patch("modules.activities.activity.ingestion_service.activities_crud")
    def test_raises_when_id_none(self, mock_crud):
        import modules.activities.activity.ingestion_service as ingestion_service

        mock_crud.create_activity = MagicMock(return_value=MagicMock(id=None))

        with pytest.raises(HTTPException) as exc:
            asyncio.run(ingestion_service.store_parsed_activity(_parsed(), MagicMock()))
        assert exc.value.status_code == 500
