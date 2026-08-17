from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError
from tests._helpers.db import setup_mock_execute
from tests._helpers.models import mock_model

import core.exceptions as core_exceptions


class TestCreateActivityStreams:
    @patch("modules.activities.activity_streams.crud.activity_streams_models.ActivityStreams")
    def test_success(self, mock_streams_model, mock_db):
        import modules.activities.activity_streams.crud as crud
        from modules.activities.activity_streams.schema import ActivityStreamsCreate

        mock_activity = MagicMock(user_id=1, id=1)
        mock_streams_model.return_value = MagicMock()
        s = [
            ActivityStreamsCreate(
                activity_id=1, stream_type=1, stream_waypoints=[{"hr": 145}], strava_activity_stream_id=None
            )
        ]
        crud.create_activity_streams(s, mock_activity, mock_db)
        mock_db.add_all.assert_called_once()
        mock_db.commit.assert_called_once()

    def test_empty(self, mock_db):
        import modules.activities.activity_streams.crud as crud

        mock_activity = MagicMock(user_id=1, id=1)
        crud.create_activity_streams([], mock_activity, mock_db)
        mock_db.add_all.assert_not_called()

    @patch("modules.activities.activity_streams.crud.activity_streams_models.ActivityStreams")
    def test_persists_without_zone_percentages(self, mock_streams_model, mock_db):
        # HR-zone computation is decoupled to the activity.created subscriber, so
        # streams are persisted with zone_percentages=None (scored later).
        import modules.activities.activity_streams.crud as crud
        from modules.activities.activity_streams.schema import ActivityStreamsCreate

        mock_activity = MagicMock(user_id=1, id=1)
        mock_streams_model.return_value = MagicMock()
        s = [
            ActivityStreamsCreate(
                activity_id=1, stream_type=1, stream_waypoints=[{"hr": 100}], strava_activity_stream_id=None
            )
        ]
        crud.create_activity_streams(s, mock_activity, mock_db)

        assert mock_streams_model.call_args.kwargs["zone_percentages"] is None

    @patch("modules.activities.activity_streams.crud.activity_streams_models.ActivityStreams")
    def test_db_error(self, mock_streams_model, mock_db):
        import modules.activities.activity_streams.crud as crud
        from modules.activities.activity_streams.schema import ActivityStreamsCreate

        mock_activity = MagicMock(user_id=1, id=1)
        mock_streams_model.return_value = MagicMock()
        mock_db.commit.side_effect = SQLAlchemyError("err")
        s = [ActivityStreamsCreate(activity_id=1, stream_type=1, stream_waypoints=[], strava_activity_stream_id=None)]
        with pytest.raises(core_exceptions.ProcessingError) as e:
            crud.create_activity_streams(s, mock_activity, mock_db)
        assert e.value.status_code == 500


class TestGetActivityStreams:
    """Persistence only — access and per-type masking live in ``activity_streams.service``."""

    @patch("modules.activities.activity_streams.crud.activity_streams_utils.transform_activity_streams")
    def test_success(self, mock_transform, mock_db):
        import modules.activities.activity_streams.crud as crud
        import modules.activities.activity_streams.models as m
        from modules.activities.activity_streams.schema import ActivityStreamsRead

        mock_transform.return_value = [
            ActivityStreamsRead(id=1, activity_id=1, stream_type=1, stream_waypoints=[], strava_activity_stream_id=None)
        ]
        setup_mock_execute(
            mock_db, return_scalars_all=[mock_model(m.ActivityStreams, id=1, activity_id=1, stream_type=1)]
        )
        assert len(crud.get_activity_streams(activity_id=1, db=mock_db)) == 1

    @patch("modules.activities.activity_streams.crud.activity_streams_schema.ActivityStreamsRead.model_validate")
    def test_by_type(self, mock_validate, mock_db):
        import modules.activities.activity_streams.crud as crud
        import modules.activities.activity_streams.models as m
        from modules.activities.activity_streams.schema import ActivityStreamsRead

        mock_validate.return_value = ActivityStreamsRead(
            id=1, activity_id=1, stream_type=1, stream_waypoints=[], strava_activity_stream_id=None
        )
        setup_mock_execute(
            mock_db, return_one_or_none=mock_model(m.ActivityStreams, id=1, activity_id=1, stream_type=1)
        )
        assert crud.get_activity_stream_by_type(activity_id=1, stream_type=1, db=mock_db) is not None

    def test_by_type_missing(self, mock_db):
        import modules.activities.activity_streams.crud as crud

        mock_db.scalars.return_value.first.return_value = None
        assert crud.get_activity_stream_by_type(activity_id=1, stream_type=1, db=mock_db) is None

    @patch("modules.activities.activity_streams.crud.activity_streams_utils.transform_activity_streams")
    def test_empty(self, mock_transform, mock_db):
        import modules.activities.activity_streams.crud as crud

        mock_transform.return_value = []
        mock_db.scalars.return_value.all.return_value = []
        assert crud.get_activity_streams(activity_id=1, db=mock_db) == []

    def test_db_error(self, mock_db):
        import modules.activities.activity_streams.crud as crud

        mock_db.scalars.return_value.all.side_effect = SQLAlchemyError("err")
        with pytest.raises(core_exceptions.ProcessingError) as e:
            crud.get_activity_streams(activity_id=1, db=mock_db)
        assert e.value.status_code == 500


class TestGetActivitiesStreams:
    """The batch read no longer joins the parent: it is handed scoped ids."""

    @patch("modules.activities.activity_streams.crud.activity_streams_utils.transform_activity_streams")
    def test_success(self, mock_transform, mock_db):
        import modules.activities.activity_streams.crud as crud
        import modules.activities.activity_streams.models as m

        mock_transform.return_value = [MagicMock()]
        mock_db.scalars.return_value.all.return_value = [MagicMock(spec=m.ActivityStreams, id=1, activity_id=1)]

        assert len(crud.get_activities_streams(activity_ids=[1], db=mock_db)) == 1

    def test_empty_ids_short_circuits(self, mock_db):
        import modules.activities.activity_streams.crud as crud

        assert crud.get_activities_streams(activity_ids=[], db=mock_db) == []
        mock_db.scalars.assert_not_called()

    def test_no_streams(self, mock_db):
        import modules.activities.activity_streams.crud as crud

        mock_db.scalars.return_value.all.return_value = []

        assert crud.get_activities_streams(activity_ids=[1], db=mock_db) == []

    def test_db_error(self, mock_db):
        import modules.activities.activity_streams.crud as crud

        mock_db.scalars.side_effect = SQLAlchemyError("err")
        with pytest.raises(core_exceptions.ProcessingError) as e:
            crud.get_activities_streams(activity_ids=[1], db=mock_db)
        assert e.value.status_code == 500


class TestGetGpsStreamWaypointsForActivities:
    def test_empty_ids_short_circuits(self, mock_db):
        import modules.activities.activity_streams.crud as crud

        assert crud.get_gps_stream_waypoints_for_activities([], mock_db) == {}
        mock_db.execute.assert_not_called()

    def test_returns_mapping_and_coalesces_none(self, mock_db):
        import modules.activities.activity_streams.crud as crud

        mock_db.execute.return_value.all.return_value = [
            (1, [{"lat": 38.0, "lon": -9.0}]),
            (2, None),
        ]
        result = crud.get_gps_stream_waypoints_for_activities([1, 2], mock_db)
        assert result == {1: [{"lat": 38.0, "lon": -9.0}], 2: []}
