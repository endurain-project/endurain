"""Tests for the core activity ingestion service (store_parsed_activity)."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException


def _parsed(**overrides):
    """Build a ParsedActivity with a mock activity and overridable children.

    The default activity carries no provider ids (an ``"upload"``), so
    ``_derive_dedup_key`` yields ``None`` and the idempotency no-op path stays
    inert unless a test opts in via ``source``/``activity`` overrides.
    """
    import modules.activities.activity.schema as schema

    data = {
        "activity": MagicMock(strava_activity_id=None, garminconnect_activity_id=None, user_id=3),
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
        mock_streams_crud.create_activity_streams = MagicMock()

        parsed = _parsed(streams=[schema.ParsedStream(stream_type=1, stream_waypoints=[{"hr": 100}])])

        result = ingestion_service.store_parsed_activity(parsed, MagicMock())

        assert result is created
        mock_crud.create_activity.assert_called_once()
        # The stream was converted to an ActivityStreamsCreate carrying the new id.
        mock_streams_crud.create_activity_streams.assert_called_once()
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
        mock_streams_crud.create_activity_streams = MagicMock()

        ingestion_service.store_parsed_activity(_parsed(), MagicMock())

        mock_streams_crud.create_activity_streams.assert_not_called()

    @patch("modules.activities.activity.ingestion_service.activity_event_publishers")
    @patch("modules.activities.activity.ingestion_service.activity_workout_steps_crud")
    @patch("modules.activities.activity.ingestion_service.activity_sets_crud")
    @patch("modules.activities.activity.ingestion_service.activity_laps_crud")
    @patch("modules.activities.activity.ingestion_service.activities_crud")
    def test_persists_laps_sets_and_steps(self, mock_crud, mock_laps, mock_sets, mock_steps, mock_pub):
        import modules.activities.activity.ingestion_service as ingestion_service

        mock_crud.create_activity = MagicMock(return_value=MagicMock(id=9, user_id=1))

        parsed = _parsed(laps=[{"a": 1}], sets=[{"b": 2}], workout_steps=[{"c": 3}])
        ingestion_service.store_parsed_activity(parsed, MagicMock())

        mock_laps.create_activity_laps.assert_called_once()
        mock_sets.create_activity_sets.assert_called_once()
        mock_steps.create_activity_workout_steps.assert_called_once()

    @patch("modules.activities.activity.ingestion_service.activities_crud")
    def test_raises_when_activity_none(self, mock_crud):
        import modules.activities.activity.ingestion_service as ingestion_service

        mock_crud.create_activity = MagicMock(return_value=None)

        with pytest.raises(HTTPException) as exc:
            ingestion_service.store_parsed_activity(_parsed(), MagicMock())
        assert exc.value.status_code == 500

    @patch("modules.activities.activity.ingestion_service.activities_crud")
    def test_raises_when_id_none(self, mock_crud):
        import modules.activities.activity.ingestion_service as ingestion_service

        mock_crud.create_activity = MagicMock(return_value=MagicMock(id=None))

        with pytest.raises(HTTPException) as exc:
            ingestion_service.store_parsed_activity(_parsed(), MagicMock())
        assert exc.value.status_code == 500

    @patch("modules.activities.activity.ingestion_service.activity_event_publishers")
    @patch("modules.activities.activity.ingestion_service.activity_streams_crud")
    @patch("modules.activities.activity.ingestion_service.activities_crud")
    def test_persists_children_and_activity_without_committing(self, mock_crud, mock_streams_crud, mock_pub):
        import modules.activities.activity.ingestion_service as ingestion_service
        import modules.activities.activity.schema as schema

        mock_crud.create_activity = MagicMock(return_value=MagicMock(id=7, user_id=3, is_hidden=False))
        db = MagicMock()

        parsed = _parsed(streams=[schema.ParsedStream(stream_type=1, stream_waypoints=[{"hr": 1}])])
        ingestion_service.store_parsed_activity(parsed, db)

        # Activity + children are staged with commit=False so they land in ONE
        # transaction; the publish seam owns the single commit (commit=db.commit).
        assert mock_crud.create_activity.call_args.kwargs["commit"] is False
        assert mock_streams_crud.create_activity_streams.call_args.kwargs["commit"] is False
        assert mock_pub.publish_activity_created.call_args.kwargs["commit"] is db.commit

    @patch("modules.activities.activity.ingestion_service.activity_event_publishers")
    @patch("modules.activities.activity.ingestion_service.activity_streams_crud")
    @patch("modules.activities.activity.ingestion_service.activities_crud")
    def test_rolls_back_and_raises_when_child_fails(self, mock_crud, mock_streams_crud, mock_pub):
        import modules.activities.activity.ingestion_service as ingestion_service
        import modules.activities.activity.schema as schema
        from sqlalchemy.exc import SQLAlchemyError

        mock_crud.create_activity = MagicMock(return_value=MagicMock(id=5, user_id=2, is_hidden=False))
        mock_streams_crud.create_activity_streams = MagicMock(side_effect=SQLAlchemyError("boom"))
        db = MagicMock()

        parsed = _parsed(streams=[schema.ParsedStream(stream_type=1, stream_waypoints=[{"hr": 100}])])

        with pytest.raises(HTTPException) as exc:
            ingestion_service.store_parsed_activity(parsed, db)
        assert exc.value.status_code == 500
        # The whole unit of work rolls back (no partial activity) and no event is
        # published for a store that never committed.
        db.rollback.assert_called_once()
        mock_pub.publish_activity_created.assert_not_called()

    @patch("modules.activities.activity.ingestion_service.activity_event_publishers")
    @patch("modules.activities.activity.ingestion_service.activity_streams_crud")
    @patch("modules.activities.activity.ingestion_service.activities_crud")
    def test_noop_when_dedup_key_already_ingested(self, mock_crud, mock_streams_crud, mock_pub):
        import modules.activities.activity.ingestion_service as ingestion_service
        import modules.activities.activity.schema as schema

        existing = MagicMock(id=42, user_id=3)
        mock_crud.get_activity_by_dedup_key = MagicMock(return_value=existing)
        mock_crud.create_activity = MagicMock()
        db = MagicMock()

        parsed = _parsed(
            streams=[schema.ParsedStream(stream_type=1, stream_waypoints=[{"hr": 1}])],
            source=schema.ImportSource(kind="strava", dedup_key="strava:123"),
        )

        result = ingestion_service.store_parsed_activity(parsed, db)

        # Re-import of an already-ingested dedup_key is a true no-op: the existing
        # activity is returned and nothing is created, staged, or published.
        assert result is existing
        mock_crud.get_activity_by_dedup_key.assert_called_once_with("strava:123", 3, db)
        mock_crud.create_activity.assert_not_called()
        mock_streams_crud.create_activity_streams.assert_not_called()
        mock_pub.publish_activity_created.assert_not_called()

    @patch("modules.activities.activity.ingestion_service.activity_event_publishers")
    @patch("modules.activities.activity.ingestion_service.activity_streams_crud")
    @patch("modules.activities.activity.ingestion_service.activities_crud")
    def test_derives_and_passes_strava_dedup_key(self, mock_crud, mock_streams_crud, mock_pub):
        import modules.activities.activity.ingestion_service as ingestion_service
        import modules.activities.activity.schema as schema

        mock_crud.get_activity_by_dedup_key = MagicMock(return_value=None)
        mock_crud.create_activity = MagicMock(return_value=MagicMock(id=7, user_id=3, is_hidden=False))

        activity = MagicMock(strava_activity_id=123, garminconnect_activity_id=None, user_id=3)
        parsed = _parsed(activity=activity, source=schema.ImportSource(kind="upload"))

        ingestion_service.store_parsed_activity(parsed, MagicMock())

        # The key is derived from the activity's Strava id (no explicit source key)
        # and forwarded to create_activity for persistence on the new row.
        mock_crud.get_activity_by_dedup_key.assert_called_once()
        assert mock_crud.get_activity_by_dedup_key.call_args.args[0] == "strava:123"
        assert mock_crud.create_activity.call_args.kwargs["dedup_key"] == "strava:123"

    @patch("modules.activities.activity.ingestion_service.activity_event_publishers")
    @patch("modules.activities.activity.ingestion_service.activity_streams_crud")
    @patch("modules.activities.activity.ingestion_service.activities_crud")
    def test_derives_garmin_dedup_key_when_no_strava(self, mock_crud, mock_streams_crud, mock_pub):
        import modules.activities.activity.ingestion_service as ingestion_service
        import modules.activities.activity.schema as schema

        mock_crud.get_activity_by_dedup_key = MagicMock(return_value=None)
        mock_crud.create_activity = MagicMock(return_value=MagicMock(id=8, user_id=3, is_hidden=False))

        activity = MagicMock(strava_activity_id=None, garminconnect_activity_id=456, user_id=3)
        parsed = _parsed(activity=activity, source=schema.ImportSource(kind="garmin"))

        ingestion_service.store_parsed_activity(parsed, MagicMock())

        assert mock_crud.create_activity.call_args.kwargs["dedup_key"] == "garmin:456"


class TestDeriveDedupKey:
    def test_prefers_strava_over_garmin(self):
        import modules.activities.activity.ingestion_service as ingestion_service

        activity = MagicMock(strava_activity_id=1, garminconnect_activity_id=2)
        assert ingestion_service._derive_dedup_key(activity) == "strava:1"

    def test_falls_back_to_garmin(self):
        import modules.activities.activity.ingestion_service as ingestion_service

        activity = MagicMock(strava_activity_id=None, garminconnect_activity_id=2)
        assert ingestion_service._derive_dedup_key(activity) == "garmin:2"

    def test_none_for_plain_upload(self):
        import modules.activities.activity.ingestion_service as ingestion_service

        activity = MagicMock(strava_activity_id=None, garminconnect_activity_id=None)
        assert ingestion_service._derive_dedup_key(activity) is None
