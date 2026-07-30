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
    @patch("modules.activities.activity_streams.crud.activity_streams_utils.transform_activity_streams")
    @patch("modules.activities.activity_streams.crud.activity_crud.get_viewable_activity_by_id_for_user")
    def test_success(self, mock_get_act, mock_transform, mock_db):
        import modules.activities.activity_streams.crud as crud
        import modules.activities.activity_streams.models as m
        from modules.activities.activity_streams.schema import ActivityStreamsRead

        mock_get_act.return_value = MagicMock(user_id=1)
        mock_transform.return_value = [
            ActivityStreamsRead(id=1, activity_id=1, stream_type=1, stream_waypoints=[], strava_activity_stream_id=None)
        ]
        setup_mock_execute(
            mock_db, return_scalars_all=[mock_model(m.ActivityStreams, id=1, activity_id=1, stream_type=1)]
        )
        r = crud.get_activity_streams(activity_id=1, token_user_id=1, db=mock_db)
        assert len(r) == 1

    @patch("modules.activities.activity_streams.crud.activity_crud.get_viewable_activity_by_id_for_user")
    @patch("modules.activities.activity_streams.crud.activity_streams_schema.ActivityStreamsRead.model_validate")
    def test_by_type(self, mock_validate, mock_get_act, mock_db):
        import modules.activities.activity_streams.crud as crud
        import modules.activities.activity_streams.models as m
        from modules.activities.activity_streams.schema import ActivityStreamsRead

        mock_get_act.return_value = MagicMock(user_id=1)
        mock_validate.return_value = ActivityStreamsRead(
            id=1, activity_id=1, stream_type=1, stream_waypoints=[], strava_activity_stream_id=None
        )
        setup_mock_execute(
            mock_db, return_one_or_none=mock_model(m.ActivityStreams, id=1, activity_id=1, stream_type=1)
        )
        r = crud.get_activity_stream_by_type(activity_id=1, stream_type=1, token_user_id=1, db=mock_db)
        assert r is not None

    @patch("modules.activities.activity_streams.crud.activity_crud.get_viewable_activity_by_id_for_user")
    def test_not_found(self, mock_get_act, mock_db):
        import modules.activities.activity_streams.crud as crud

        mock_get_act.return_value = None
        r = crud.get_activity_streams(activity_id=1, token_user_id=1, db=mock_db)
        assert r == []

    @patch("modules.activities.activity_streams.crud.activity_streams_utils.transform_activity_streams")
    @patch("modules.activities.activity_streams.crud.activity_crud.get_viewable_activity_by_id_for_user")
    def test_empty(self, mock_get_act, mock_transform, mock_db):
        import modules.activities.activity_streams.crud as crud

        mock_get_act.return_value = MagicMock(user_id=1)
        mock_db.scalars.return_value.all.return_value = []
        r = crud.get_activity_streams(activity_id=1, token_user_id=1, db=mock_db)
        assert r == []

    @patch("modules.activities.activity_streams.crud.activity_streams_utils.filter_visible_streams")
    @patch("modules.activities.activity_streams.crud.activity_streams_utils.transform_activity_streams")
    @patch("modules.activities.activity_streams.crud.activity_crud.get_viewable_activity_by_id_for_user")
    def test_non_owner(self, mock_get_act, mock_transform, mock_filter, mock_db):
        import modules.activities.activity_streams.crud as crud
        import modules.activities.activity_streams.models as m

        mock_get_act.return_value = MagicMock(user_id=2)
        mock_filter.return_value = [MagicMock(spec=m.ActivityStreams)]
        mock_transform.return_value = [MagicMock()]
        mock_db.scalars.return_value.all.return_value = [MagicMock(spec=m.ActivityStreams, id=1, activity_id=1)]
        r = crud.get_activity_streams(activity_id=1, token_user_id=1, db=mock_db)
        assert len(r) == 1

    @patch("modules.activities.activity_streams.crud.activity_crud.get_viewable_activity_by_id_for_user")
    def test_db_error(self, mock_get_act, mock_db):
        import modules.activities.activity_streams.crud as crud

        mock_get_act.return_value = MagicMock(user_id=1)
        mock_db.scalars.return_value.all.side_effect = SQLAlchemyError("err")
        with pytest.raises(core_exceptions.ProcessingError) as e:
            crud.get_activity_streams(activity_id=1, token_user_id=1, db=mock_db)
        assert e.value.status_code == 500


class TestGetActivitiesStreams:
    @patch("modules.activities.activity_streams.crud.activity_streams_utils.transform_activity_streams")
    def test_success(self, mock_transform, mock_db):
        import modules.activities.activity.models as am
        import modules.activities.activity_streams.crud as crud
        import modules.activities.activity_streams.models as m

        mock_transform.return_value = [MagicMock()]
        mock_activity = MagicMock(spec=am.Activity, id=1, user_id=1)
        mock_stream = MagicMock(spec=m.ActivityStreams, id=1, activity_id=1)
        mock_db.scalars.return_value.all.return_value = [mock_stream]
        r = crud.get_activities_streams(activity_ids=[1], _user_id=1, db=mock_db, _activities=[mock_activity])
        assert len(r) == 1

    def test_empty_ids(self, mock_db):
        import modules.activities.activity_streams.crud as crud

        r = crud.get_activities_streams(activity_ids=[], _user_id=1, db=mock_db, _activities=[])
        assert r == []

    def test_no_activities(self, mock_db):
        import modules.activities.activity_streams.crud as crud

        mock_db.scalars.return_value.all.return_value = []
        r = crud.get_activities_streams(activity_ids=[1], _user_id=1, db=mock_db, _activities=[])
        assert r == []

    def test_no_allowed(self, mock_db):
        import modules.activities.activity.models as am
        import modules.activities.activity_streams.crud as crud

        mock_activity = MagicMock(spec=am.Activity, id=1, user_id=2)
        mock_db.scalars.return_value.all.return_value = []
        r = crud.get_activities_streams(activity_ids=[1], _user_id=1, db=mock_db, _activities=[mock_activity])
        assert r == []

    def test_no_streams(self, mock_db):
        import modules.activities.activity.models as am
        import modules.activities.activity_streams.crud as crud

        mock_activity = MagicMock(spec=am.Activity, id=1, user_id=1)
        mock_db.scalars.return_value.all.return_value = []
        r = crud.get_activities_streams(activity_ids=[1], _user_id=1, db=mock_db, _activities=[mock_activity])
        assert r == []

    def test_db_error(self, mock_db):
        import modules.activities.activity_streams.crud as crud

        mock_db.scalars.side_effect = SQLAlchemyError("err")
        with pytest.raises(core_exceptions.ProcessingError) as e:
            crud.get_activities_streams(activity_ids=[1], _user_id=1, db=mock_db, _activities=[])
        assert e.value.status_code == 500


class TestGetPublicActivityStreams:
    @patch("modules.activities.activity_streams.crud.activity_streams_utils.filter_visible_streams")
    @patch("modules.activities.activity_streams.crud.activity_streams_utils.transform_activity_streams")
    @patch("modules.activities.activity_streams.crud.activity_crud.get_activity_by_id_if_is_public")
    @patch("modules.activities.activity_streams.crud.server_settings_utils.get_server_settings_or_404")
    def test_success(self, mock_settings, mock_get_act, mock_transform, mock_filter, mock_db):
        import modules.activities.activity_streams.crud as crud
        import modules.activities.activity_streams.models as m

        mock_settings.return_value = MagicMock(public_shareable_links=True)
        mock_get_act.return_value = MagicMock()
        mock_transform.return_value = [MagicMock()]
        mock_filter.return_value = [MagicMock(spec=m.ActivityStreams)]
        mock_db.scalars.return_value.all.return_value = [MagicMock(spec=m.ActivityStreams, id=1)]
        r = crud.get_public_activity_streams(activity_id=1, db=mock_db)
        assert len(r) == 1

    @patch("modules.activities.activity_streams.crud.server_settings_utils.get_server_settings_or_404")
    def test_no_public_links(self, mock_settings, mock_db):
        import modules.activities.activity_streams.crud as crud

        mock_settings.return_value = MagicMock(public_shareable_links=False)
        r = crud.get_public_activity_streams(activity_id=1, db=mock_db)
        assert r == []

    @patch("modules.activities.activity_streams.crud.activity_crud.get_activity_by_id_if_is_public")
    @patch("modules.activities.activity_streams.crud.server_settings_utils.get_server_settings_or_404")
    def test_not_found(self, mock_settings, mock_get_act, mock_db):
        import modules.activities.activity_streams.crud as crud

        mock_settings.return_value = MagicMock(public_shareable_links=True)
        mock_get_act.return_value = None
        r = crud.get_public_activity_streams(activity_id=1, db=mock_db)
        assert r == []

    @patch("modules.activities.activity_streams.crud.activity_crud.get_activity_by_id_if_is_public")
    @patch("modules.activities.activity_streams.crud.server_settings_utils.get_server_settings_or_404")
    def test_no_streams(self, mock_settings, mock_get_act, mock_db):
        import modules.activities.activity_streams.crud as crud

        mock_settings.return_value = MagicMock(public_shareable_links=True)
        mock_get_act.return_value = MagicMock()
        mock_db.scalars.return_value.all.return_value = []
        r = crud.get_public_activity_streams(activity_id=1, db=mock_db)
        assert r == []

    @patch("modules.activities.activity_streams.crud.activity_crud.get_activity_by_id_if_is_public")
    @patch("modules.activities.activity_streams.crud.server_settings_utils.get_server_settings_or_404")
    def test_db_error(self, mock_settings, mock_get_act, mock_db):
        import modules.activities.activity_streams.crud as crud

        mock_settings.return_value = MagicMock(public_shareable_links=True)
        mock_get_act.return_value = MagicMock()
        mock_db.scalars.return_value.all.side_effect = SQLAlchemyError("err")
        with pytest.raises(core_exceptions.ProcessingError) as e:
            crud.get_public_activity_streams(activity_id=1, db=mock_db)
        assert e.value.status_code == 500


class TestGetActivityStreamByType:
    @patch("modules.activities.activity_streams.crud.activity_streams_utils.transform_activity_streams")
    @patch("modules.activities.activity_streams.crud.activity_crud.get_viewable_activity_by_id_for_user")
    def test_success(self, mock_get_act, mock_transform, mock_db):
        import modules.activities.activity_streams.crud as crud
        import modules.activities.activity_streams.models as m

        mock_get_act.return_value = MagicMock(user_id=1)
        mock_transform.return_value = MagicMock()
        mock_db.scalars.return_value.first.return_value = MagicMock(spec=m.ActivityStreams, id=1, stream_type=1)
        r = crud.get_activity_stream_by_type(activity_id=1, stream_type=1, token_user_id=1, db=mock_db)
        assert r is not None

    @patch("modules.activities.activity_streams.crud.activity_crud.get_viewable_activity_by_id_for_user")
    def test_not_found(self, mock_get_act, mock_db):
        import modules.activities.activity_streams.crud as crud

        mock_get_act.return_value = None
        r = crud.get_activity_stream_by_type(activity_id=1, stream_type=1, token_user_id=1, db=mock_db)
        assert r is None

    @patch("modules.activities.activity_streams.crud.activity_crud.get_viewable_activity_by_id_for_user")
    def test_empty(self, mock_get_act, mock_db):
        import modules.activities.activity_streams.crud as crud

        mock_get_act.return_value = MagicMock(user_id=1)
        mock_db.scalars.return_value.first.return_value = None
        r = crud.get_activity_stream_by_type(activity_id=1, stream_type=1, token_user_id=1, db=mock_db)
        assert r is None

    @patch("modules.activities.activity_streams.crud.activity_streams_utils.is_stream_hidden")
    @patch("modules.activities.activity_streams.crud.activity_crud.get_viewable_activity_by_id_for_user")
    def test_hidden(self, mock_get_act, mock_hidden, mock_db):
        import modules.activities.activity_streams.crud as crud
        import modules.activities.activity_streams.models as m

        mock_get_act.return_value = MagicMock(user_id=2)
        mock_hidden.return_value = True
        mock_db.scalars.return_value.first.return_value = MagicMock(spec=m.ActivityStreams, id=1, stream_type=1)
        r = crud.get_activity_stream_by_type(activity_id=1, stream_type=1, token_user_id=1, db=mock_db)
        assert r is None

    @patch("modules.activities.activity_streams.crud.activity_crud.get_viewable_activity_by_id_for_user")
    def test_db_error(self, mock_get_act, mock_db):
        import modules.activities.activity_streams.crud as crud

        mock_get_act.return_value = MagicMock(user_id=1)
        mock_db.scalars.return_value.first.side_effect = SQLAlchemyError("err")
        with pytest.raises(core_exceptions.ProcessingError) as e:
            crud.get_activity_stream_by_type(activity_id=1, stream_type=1, token_user_id=1, db=mock_db)
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


class TestGetPublicActivityStreamByType:
    @patch("modules.activities.activity_streams.crud.activity_streams_utils.transform_activity_streams")
    @patch("modules.activities.activity_streams.crud.activity_streams_utils.is_stream_hidden")
    @patch("modules.activities.activity_streams.crud.activity_crud.get_activity_by_id_if_is_public")
    @patch("modules.activities.activity_streams.crud.server_settings_utils.get_server_settings_or_404")
    def test_success(self, mock_settings, mock_get_act, mock_hidden, mock_transform, mock_db):
        import modules.activities.activity_streams.crud as crud
        import modules.activities.activity_streams.models as m

        mock_settings.return_value = MagicMock(public_shareable_links=True)
        mock_get_act.return_value = MagicMock()
        mock_hidden.return_value = False
        mock_transform.return_value = MagicMock()
        mock_db.scalars.return_value.first.return_value = MagicMock(spec=m.ActivityStreams, id=1, stream_type=1)
        r = crud.get_public_activity_stream_by_type(activity_id=1, stream_type=1, db=mock_db)
        assert r is not None

    @patch("modules.activities.activity_streams.crud.server_settings_utils.get_server_settings_or_404")
    def test_no_public_links(self, mock_settings, mock_db):
        import modules.activities.activity_streams.crud as crud

        mock_settings.return_value = MagicMock(public_shareable_links=False)
        r = crud.get_public_activity_stream_by_type(activity_id=1, stream_type=1, db=mock_db)
        assert r is None

    @patch("modules.activities.activity_streams.crud.activity_crud.get_activity_by_id_if_is_public")
    @patch("modules.activities.activity_streams.crud.server_settings_utils.get_server_settings_or_404")
    def test_not_found(self, mock_settings, mock_get_act, mock_db):
        import modules.activities.activity_streams.crud as crud

        mock_settings.return_value = MagicMock(public_shareable_links=True)
        mock_get_act.return_value = None
        r = crud.get_public_activity_stream_by_type(activity_id=1, stream_type=1, db=mock_db)
        assert r is None

    @patch("modules.activities.activity_streams.crud.activity_crud.get_activity_by_id_if_is_public")
    @patch("modules.activities.activity_streams.crud.server_settings_utils.get_server_settings_or_404")
    def test_no_stream(self, mock_settings, mock_get_act, mock_db):
        import modules.activities.activity_streams.crud as crud

        mock_settings.return_value = MagicMock(public_shareable_links=True)
        mock_get_act.return_value = MagicMock()
        mock_db.scalars.return_value.first.return_value = None
        r = crud.get_public_activity_stream_by_type(activity_id=1, stream_type=1, db=mock_db)
        assert r is None

    @patch("modules.activities.activity_streams.crud.activity_streams_utils.is_stream_hidden")
    @patch("modules.activities.activity_streams.crud.activity_crud.get_activity_by_id_if_is_public")
    @patch("modules.activities.activity_streams.crud.server_settings_utils.get_server_settings_or_404")
    def test_hidden(self, mock_settings, mock_get_act, mock_hidden, mock_db):
        import modules.activities.activity_streams.crud as crud
        import modules.activities.activity_streams.models as m

        mock_settings.return_value = MagicMock(public_shareable_links=True)
        mock_get_act.return_value = MagicMock()
        mock_hidden.return_value = True
        mock_db.scalars.return_value.first.return_value = MagicMock(spec=m.ActivityStreams, id=1, stream_type=1)
        r = crud.get_public_activity_stream_by_type(activity_id=1, stream_type=1, db=mock_db)
        assert r is None

    @patch("modules.activities.activity_streams.crud.activity_crud.get_activity_by_id_if_is_public")
    @patch("modules.activities.activity_streams.crud.server_settings_utils.get_server_settings_or_404")
    def test_db_error(self, mock_settings, mock_get_act, mock_db):
        import modules.activities.activity_streams.crud as crud

        mock_settings.return_value = MagicMock(public_shareable_links=True)
        mock_get_act.return_value = MagicMock()
        mock_db.scalars.return_value.first.side_effect = SQLAlchemyError("err")
        with pytest.raises(core_exceptions.ProcessingError) as e:
            crud.get_public_activity_stream_by_type(activity_id=1, stream_type=1, db=mock_db)
        assert e.value.status_code == 500


class TestRecomputeHrZonePercentagesForUser:
    @patch("modules.activities.activity_streams.crud._get_user_hr_streams_batch")
    @patch("modules.activities.activity_streams.crud.activity_streams_utils.compute_hr_zone_breakdown_sync")
    @patch("modules.activities.activity_streams.crud.users_integration_service.get_user")
    def test_updates_streams_and_commits(self, mock_get_user, mock_compute, mock_batch, mock_db):
        import modules.activities.activity_streams.crud as crud

        mock_get_user.return_value = MagicMock(max_heart_rate=200, birthdate=None)
        hr_block = {"zone_1": {"percent": 100.0, "hr": "< 120", "time_seconds": 60}}
        mock_compute.return_value = hr_block
        stream = MagicMock(id=7, stream_waypoints=[{"hr": 100}])
        mock_batch.side_effect = [[(stream, 60.0)], []]

        crud.recompute_hr_zone_percentages_for_user(1, mock_db)

        assert stream.zone_percentages == {"hr": hr_block}
        mock_compute.assert_called_once_with([{"hr": 100}], 200, 60.0)
        mock_db.commit.assert_called_once()

    @patch("modules.activities.activity_streams.crud._get_user_hr_streams_batch")
    @patch("modules.activities.activity_streams.crud.users_integration_service.get_user")
    def test_clears_zones_when_max_hr_unresolvable(self, mock_get_user, mock_batch, mock_db):
        import modules.activities.activity_streams.crud as crud

        mock_get_user.return_value = MagicMock(max_heart_rate=None, birthdate=None)
        stream = MagicMock(id=7, stream_waypoints=[{"hr": 100}])
        mock_batch.side_effect = [[(stream, 60.0)], []]

        crud.recompute_hr_zone_percentages_for_user(1, mock_db)

        assert stream.zone_percentages is None
        mock_db.commit.assert_called_once()

    @patch("modules.activities.activity_streams.crud._get_user_hr_streams_batch")
    @patch("modules.activities.activity_streams.crud.users_integration_service.get_user")
    def test_no_user_is_noop(self, mock_get_user, mock_batch, mock_db):
        import modules.activities.activity_streams.crud as crud

        mock_get_user.return_value = None

        crud.recompute_hr_zone_percentages_for_user(1, mock_db)

        mock_batch.assert_not_called()
        mock_db.commit.assert_not_called()

    @patch("modules.activities.activity_streams.crud._get_user_hr_streams_batch")
    @patch("modules.activities.activity_streams.crud.users_integration_service.get_user")
    def test_swallows_errors_and_rolls_back(self, mock_get_user, mock_batch, mock_db):
        import modules.activities.activity_streams.crud as crud

        mock_get_user.return_value = MagicMock(max_heart_rate=200, birthdate=None)
        mock_batch.side_effect = SQLAlchemyError("boom")

        crud.recompute_hr_zone_percentages_for_user(1, mock_db)

        mock_db.rollback.assert_called_once()


class TestComputeAndStoreHrZonePercentagesForActivity:
    @patch("modules.activities.activity_streams.crud.users_integration_service.get_user", return_value=None)
    def test_noop_when_user_missing(self, mock_user, mock_db):
        import modules.activities.activity_streams.crud as crud

        crud.compute_and_store_hr_zone_percentages_for_activity(1, 2, mock_db)

        mock_db.commit.assert_not_called()

    @patch("modules.activities.activity_streams.crud.activity_streams_utils.resolve_max_heart_rate", return_value=None)
    @patch("modules.activities.activity_streams.crud.users_integration_service.get_user", return_value=MagicMock())
    def test_noop_when_no_max_hr(self, mock_user, mock_max, mock_db):
        import modules.activities.activity_streams.crud as crud

        crud.compute_and_store_hr_zone_percentages_for_activity(1, 2, mock_db)

        mock_db.commit.assert_not_called()

    @patch("modules.activities.activity_streams.crud.activity_streams_utils.resolve_max_heart_rate", return_value=190)
    @patch("modules.activities.activity_streams.crud.users_integration_service.get_user", return_value=MagicMock())
    def test_noop_when_no_hr_stream(self, mock_user, mock_max, mock_db):
        import modules.activities.activity_streams.crud as crud

        mock_db.execute.return_value.first.return_value = None

        crud.compute_and_store_hr_zone_percentages_for_activity(1, 2, mock_db)

        mock_db.commit.assert_not_called()

    @patch(
        "modules.activities.activity_streams.crud.activity_streams_utils.compute_hr_zone_breakdown_sync",
        return_value={"zone_1": 1},
    )
    @patch("modules.activities.activity_streams.crud.activity_streams_utils.resolve_max_heart_rate", return_value=190)
    @patch("modules.activities.activity_streams.crud.users_integration_service.get_user", return_value=MagicMock())
    def test_stores_zone_percentages(self, mock_user, mock_max, mock_compute, mock_db):
        import modules.activities.activity_streams.crud as crud

        stream = MagicMock(stream_waypoints=[{"hr": 100}])
        mock_db.execute.return_value.first.return_value = (stream, 600.0)

        crud.compute_and_store_hr_zone_percentages_for_activity(1, 2, mock_db)

        assert stream.zone_percentages == {"hr": {"zone_1": 1}}
        mock_db.commit.assert_called_once()


class TestBackfillMissingHrZonePercentages:
    @patch(
        "modules.activities.activity_streams.crud.activity_streams_utils.compute_hr_zone_breakdown_sync",
        return_value={"zone_1": 1},
    )
    @patch("modules.activities.activity_streams.crud.activity_streams_utils.resolve_max_heart_rate", return_value=190)
    @patch("modules.activities.activity_streams.crud.users_integration_service.get_user", return_value=MagicMock())
    def test_scores_missing_streams(self, mock_user, mock_max, mock_compute, mock_db):
        import modules.activities.activity_streams.crud as crud

        stream = MagicMock(id=5, stream_waypoints=[{"hr": 100}])
        # First batch returns one (stream, total_timer_time, owner_id); second is empty.
        mock_db.execute.return_value.all.side_effect = [[(stream, 600.0, 2)], []]

        updated = crud.backfill_missing_hr_zone_percentages(mock_db)

        assert updated == 1
        assert stream.zone_percentages == {"hr": {"zone_1": 1}}

    @patch("modules.activities.activity_streams.crud.activity_streams_utils.resolve_max_heart_rate", return_value=None)
    @patch("modules.activities.activity_streams.crud.users_integration_service.get_user", return_value=MagicMock())
    def test_skips_when_owner_has_no_max_hr(self, mock_user, mock_max, mock_db):
        import modules.activities.activity_streams.crud as crud

        stream = MagicMock(id=5, stream_waypoints=[{"hr": 100}])
        mock_db.execute.return_value.all.side_effect = [[(stream, 600.0, 2)], []]

        updated = crud.backfill_missing_hr_zone_percentages(mock_db)

        assert updated == 0
