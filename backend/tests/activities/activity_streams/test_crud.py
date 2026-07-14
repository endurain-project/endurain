from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError
from tests._helpers.db import setup_mock_execute
from tests._helpers.models import mock_model


class TestCreateActivityStreams:
    @patch("activities.activity_streams.crud.activity_streams_models.ActivityStreams")
    @patch("activities.activity_streams.crud.users_crud.get_user_by_id")
    @patch("activities.activity_streams.crud.activity_streams_utils.build_zone_percentages")
    async def test_success(
        self,
        mock_build_zone_percentages,
        mock_get_user_by_id,
        mock_streams_model,
        mock_db,
    ):
        import activities.activity_streams.crud as crud
        from activities.activity_streams.schema import ActivityStreamsCreate

        mock_activity = MagicMock(user_id=1, id=1)
        mock_streams_model.return_value = MagicMock()
        mock_get_user_by_id.return_value = MagicMock(max_heart_rate=200)
        mock_build_zone_percentages.return_value = {"hr": {}}
        s = [
            ActivityStreamsCreate(
                activity_id=1, stream_type=1, stream_waypoints=[{"hr": 145}], strava_activity_stream_id=None
            )
        ]
        await crud.create_activity_streams(s, mock_activity, mock_db)
        mock_db.add_all.assert_called_once()
        mock_db.commit.assert_called_once()

    @patch("activities.activity_streams.crud.users_crud.get_user_by_id")
    async def test_empty(self, mock_get_user_by_id, mock_db):
        import activities.activity_streams.crud as crud

        mock_activity = MagicMock(user_id=1, id=1)
        mock_get_user_by_id.return_value = MagicMock(max_heart_rate=200)
        await crud.create_activity_streams([], mock_activity, mock_db)

    @patch("activities.activity_streams.crud.activity_streams_models.ActivityStreams")
    @patch("activities.activity_streams.crud.users_crud.get_user_by_id")
    @patch("activities.activity_streams.crud.activity_streams_utils.build_zone_percentages")
    async def test_create_activity_streams_populates_zone_percentages(
        self,
        mock_build_zone_percentages,
        mock_get_user_by_id,
        mock_streams_model,
        mock_db,
    ):
        import activities.activity_streams.crud as crud
        from activities.activity_streams.schema import ActivityStreamsCreate

        expected_zone_percentages = {
            "hr": {
                "zone_1": {"percent": 20.0, "hr": "< 120", "time_seconds": 20},
                "zone_2": {"percent": 20.0, "hr": "120 - 139", "time_seconds": 20},
                "zone_3": {"percent": 20.0, "hr": "140 - 159", "time_seconds": 20},
                "zone_4": {"percent": 20.0, "hr": "160 - 179", "time_seconds": 20},
                "zone_5": {"percent": 20.0, "hr": ">= 180", "time_seconds": 20},
            }
        }

        mock_activity = MagicMock(user_id=1, id=1)
        mock_streams_model.side_effect = [MagicMock(), MagicMock()]
        mock_get_user_by_id.return_value = MagicMock(max_heart_rate=200)
        mock_build_zone_percentages.return_value = expected_zone_percentages

        streams = [
            ActivityStreamsCreate(
                activity_id=1,
                stream_type=1,
                stream_waypoints=[{"hr": 100}],
                strava_activity_stream_id=None,
            ),
            ActivityStreamsCreate(
                activity_id=2,
                stream_type=2,
                stream_waypoints=[],
                strava_activity_stream_id=None,
            ),
        ]

        await crud.create_activity_streams(streams, mock_activity, mock_db)

        assert mock_build_zone_percentages.call_count == 1
        assert mock_streams_model.call_args_list[0].kwargs["zone_percentages"] == expected_zone_percentages
        assert mock_streams_model.call_args_list[1].kwargs["zone_percentages"] is None

    @patch("activities.activity_streams.crud.activity_streams_models.ActivityStreams")
    @patch("activities.activity_streams.crud.users_crud.get_user_by_id")
    @patch("activities.activity_streams.crud.activity_streams_utils.build_zone_percentages")
    async def test_db_error(
        self,
        mock_build_zone_percentages,
        mock_get_user_by_id,
        mock_streams_model,
        mock_db,
    ):
        import activities.activity_streams.crud as crud
        from activities.activity_streams.schema import ActivityStreamsCreate

        mock_activity = MagicMock(user_id=1, id=1)
        mock_streams_model.return_value = MagicMock()
        mock_get_user_by_id.return_value = MagicMock(max_heart_rate=200)
        mock_build_zone_percentages.return_value = {"hr": {}}
        mock_db.commit.side_effect = SQLAlchemyError("err")
        s = [ActivityStreamsCreate(activity_id=1, stream_type=1, stream_waypoints=[], strava_activity_stream_id=None)]
        with pytest.raises(HTTPException) as e:
            await crud.create_activity_streams(s, mock_activity, mock_db)
        assert e.value.status_code == 500


class TestGetActivityStreams:
    @patch("activities.activity_streams.crud.activity_streams_utils.transform_activity_streams")
    @patch("activities.activity_streams.crud.activity_crud.get_activity_by_id")
    def test_success(self, mock_get_act, mock_transform, mock_db):
        import activities.activity_streams.crud as crud
        import activities.activity_streams.models as m
        from activities.activity_streams.schema import ActivityStreamsRead

        mock_get_act.return_value = MagicMock(user_id=1)
        mock_transform.return_value = [
            ActivityStreamsRead(id=1, activity_id=1, stream_type=1, stream_waypoints=[], strava_activity_stream_id=None)
        ]
        setup_mock_execute(
            mock_db, return_scalars_all=[mock_model(m.ActivityStreams, id=1, activity_id=1, stream_type=1)]
        )
        r = crud.get_activity_streams(activity_id=1, token_user_id=1, db=mock_db)
        assert len(r) == 1

    @patch("activities.activity_streams.crud.activity_crud.get_activity_by_id")
    @patch("activities.activity_streams.crud.activity_streams_schema.ActivityStreamsRead.model_validate")
    def test_by_type(self, mock_validate, mock_get_act, mock_db):
        import activities.activity_streams.crud as crud
        import activities.activity_streams.models as m
        from activities.activity_streams.schema import ActivityStreamsRead

        mock_get_act.return_value = MagicMock(user_id=1)
        mock_validate.return_value = ActivityStreamsRead(
            id=1, activity_id=1, stream_type=1, stream_waypoints=[], strava_activity_stream_id=None
        )
        setup_mock_execute(
            mock_db, return_one_or_none=mock_model(m.ActivityStreams, id=1, activity_id=1, stream_type=1)
        )
        r = crud.get_activity_stream_by_type(activity_id=1, stream_type=1, token_user_id=1, db=mock_db)
        assert r is not None

    @patch("activities.activity_streams.crud.activity_crud.get_activity_by_id")
    def test_not_found(self, mock_get_act, mock_db):
        import activities.activity_streams.crud as crud

        mock_get_act.return_value = None
        r = crud.get_activity_streams(activity_id=1, token_user_id=1, db=mock_db)
        assert r == []

    @patch("activities.activity_streams.crud.activity_streams_utils.transform_activity_streams")
    @patch("activities.activity_streams.crud.activity_crud.get_activity_by_id")
    def test_empty(self, mock_get_act, mock_transform, mock_db):
        import activities.activity_streams.crud as crud

        mock_get_act.return_value = MagicMock(user_id=1)
        mock_db.scalars.return_value.all.return_value = []
        r = crud.get_activity_streams(activity_id=1, token_user_id=1, db=mock_db)
        assert r == []

    @patch("activities.activity_streams.crud.activity_streams_utils.filter_visible_streams")
    @patch("activities.activity_streams.crud.activity_streams_utils.transform_activity_streams")
    @patch("activities.activity_streams.crud.activity_crud.get_activity_by_id")
    def test_non_owner(self, mock_get_act, mock_transform, mock_filter, mock_db):
        import activities.activity_streams.crud as crud
        import activities.activity_streams.models as m

        mock_get_act.return_value = MagicMock(user_id=2)
        mock_filter.return_value = [MagicMock(spec=m.ActivityStreams)]
        mock_transform.return_value = [MagicMock()]
        mock_db.scalars.return_value.all.return_value = [MagicMock(spec=m.ActivityStreams, id=1, activity_id=1)]
        r = crud.get_activity_streams(activity_id=1, token_user_id=1, db=mock_db)
        assert len(r) == 1

    @patch("activities.activity_streams.crud.activity_crud.get_activity_by_id")
    def test_db_error(self, mock_get_act, mock_db):
        import activities.activity_streams.crud as crud

        mock_get_act.return_value = MagicMock(user_id=1)
        mock_db.scalars.return_value.all.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.get_activity_streams(activity_id=1, token_user_id=1, db=mock_db)
        assert e.value.status_code == 500


class TestGetActivitiesStreams:
    @patch("activities.activity_streams.crud.activity_streams_utils.transform_activity_streams")
    def test_success(self, mock_transform, mock_db):
        import activities.activity.models as am
        import activities.activity_streams.crud as crud
        import activities.activity_streams.models as m

        mock_transform.return_value = [MagicMock()]
        mock_activity = MagicMock(spec=am.Activity, id=1, user_id=1)
        mock_stream = MagicMock(spec=m.ActivityStreams, id=1, activity_id=1)
        mock_db.scalars.return_value.all.return_value = [mock_stream]
        r = crud.get_activities_streams(activity_ids=[1], _user_id=1, db=mock_db, _activities=[mock_activity])
        assert len(r) == 1

    def test_empty_ids(self, mock_db):
        import activities.activity_streams.crud as crud

        r = crud.get_activities_streams(activity_ids=[], _user_id=1, db=mock_db, _activities=[])
        assert r == []

    def test_no_activities(self, mock_db):
        import activities.activity_streams.crud as crud

        mock_db.scalars.return_value.all.return_value = []
        r = crud.get_activities_streams(activity_ids=[1], _user_id=1, db=mock_db, _activities=[])
        assert r == []

    def test_no_allowed(self, mock_db):
        import activities.activity.models as am
        import activities.activity_streams.crud as crud

        mock_activity = MagicMock(spec=am.Activity, id=1, user_id=2)
        mock_db.scalars.return_value.all.return_value = []
        r = crud.get_activities_streams(activity_ids=[1], _user_id=1, db=mock_db, _activities=[mock_activity])
        assert r == []

    def test_no_streams(self, mock_db):
        import activities.activity.models as am
        import activities.activity_streams.crud as crud

        mock_activity = MagicMock(spec=am.Activity, id=1, user_id=1)
        mock_db.scalars.return_value.all.return_value = []
        r = crud.get_activities_streams(activity_ids=[1], _user_id=1, db=mock_db, _activities=[mock_activity])
        assert r == []

    def test_db_error(self, mock_db):
        import activities.activity_streams.crud as crud

        mock_db.scalars.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.get_activities_streams(activity_ids=[1], _user_id=1, db=mock_db, _activities=[])
        assert e.value.status_code == 500


class TestGetPublicActivityStreams:
    @patch("activities.activity_streams.crud.activity_streams_utils.filter_visible_streams")
    @patch("activities.activity_streams.crud.activity_streams_utils.transform_activity_streams")
    @patch("activities.activity_streams.crud.activity_crud.get_activity_by_id_if_is_public")
    @patch("activities.activity_streams.crud.server_settings_utils.get_server_settings_or_404")
    def test_success(self, mock_settings, mock_get_act, mock_transform, mock_filter, mock_db):
        import activities.activity_streams.crud as crud
        import activities.activity_streams.models as m

        mock_settings.return_value = MagicMock(public_shareable_links=True)
        mock_get_act.return_value = MagicMock()
        mock_transform.return_value = [MagicMock()]
        mock_filter.return_value = [MagicMock(spec=m.ActivityStreams)]
        mock_db.scalars.return_value.all.return_value = [MagicMock(spec=m.ActivityStreams, id=1)]
        r = crud.get_public_activity_streams(activity_id=1, db=mock_db)
        assert len(r) == 1

    @patch("activities.activity_streams.crud.server_settings_utils.get_server_settings_or_404")
    def test_no_public_links(self, mock_settings, mock_db):
        import activities.activity_streams.crud as crud

        mock_settings.return_value = MagicMock(public_shareable_links=False)
        r = crud.get_public_activity_streams(activity_id=1, db=mock_db)
        assert r == []

    @patch("activities.activity_streams.crud.activity_crud.get_activity_by_id_if_is_public")
    @patch("activities.activity_streams.crud.server_settings_utils.get_server_settings_or_404")
    def test_not_found(self, mock_settings, mock_get_act, mock_db):
        import activities.activity_streams.crud as crud

        mock_settings.return_value = MagicMock(public_shareable_links=True)
        mock_get_act.return_value = None
        r = crud.get_public_activity_streams(activity_id=1, db=mock_db)
        assert r == []

    @patch("activities.activity_streams.crud.activity_crud.get_activity_by_id_if_is_public")
    @patch("activities.activity_streams.crud.server_settings_utils.get_server_settings_or_404")
    def test_no_streams(self, mock_settings, mock_get_act, mock_db):
        import activities.activity_streams.crud as crud

        mock_settings.return_value = MagicMock(public_shareable_links=True)
        mock_get_act.return_value = MagicMock()
        mock_db.scalars.return_value.all.return_value = []
        r = crud.get_public_activity_streams(activity_id=1, db=mock_db)
        assert r == []

    @patch("activities.activity_streams.crud.activity_crud.get_activity_by_id_if_is_public")
    @patch("activities.activity_streams.crud.server_settings_utils.get_server_settings_or_404")
    def test_db_error(self, mock_settings, mock_get_act, mock_db):
        import activities.activity_streams.crud as crud

        mock_settings.return_value = MagicMock(public_shareable_links=True)
        mock_get_act.return_value = MagicMock()
        mock_db.scalars.return_value.all.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.get_public_activity_streams(activity_id=1, db=mock_db)
        assert e.value.status_code == 500


class TestGetActivityStreamByType:
    @patch("activities.activity_streams.crud.activity_streams_utils.transform_activity_streams")
    @patch("activities.activity_streams.crud.activity_crud.get_activity_by_id")
    def test_success(self, mock_get_act, mock_transform, mock_db):
        import activities.activity_streams.crud as crud
        import activities.activity_streams.models as m

        mock_get_act.return_value = MagicMock(user_id=1)
        mock_transform.return_value = MagicMock()
        mock_db.scalars.return_value.first.return_value = MagicMock(spec=m.ActivityStreams, id=1, stream_type=1)
        r = crud.get_activity_stream_by_type(activity_id=1, stream_type=1, token_user_id=1, db=mock_db)
        assert r is not None

    @patch("activities.activity_streams.crud.activity_crud.get_activity_by_id")
    def test_not_found(self, mock_get_act, mock_db):
        import activities.activity_streams.crud as crud

        mock_get_act.return_value = None
        r = crud.get_activity_stream_by_type(activity_id=1, stream_type=1, token_user_id=1, db=mock_db)
        assert r is None

    @patch("activities.activity_streams.crud.activity_crud.get_activity_by_id")
    def test_empty(self, mock_get_act, mock_db):
        import activities.activity_streams.crud as crud

        mock_get_act.return_value = MagicMock(user_id=1)
        mock_db.scalars.return_value.first.return_value = None
        r = crud.get_activity_stream_by_type(activity_id=1, stream_type=1, token_user_id=1, db=mock_db)
        assert r is None

    @patch("activities.activity_streams.crud.activity_streams_utils.is_stream_hidden")
    @patch("activities.activity_streams.crud.activity_crud.get_activity_by_id")
    def test_hidden(self, mock_get_act, mock_hidden, mock_db):
        import activities.activity_streams.crud as crud
        import activities.activity_streams.models as m

        mock_get_act.return_value = MagicMock(user_id=2)
        mock_hidden.return_value = True
        mock_db.scalars.return_value.first.return_value = MagicMock(spec=m.ActivityStreams, id=1, stream_type=1)
        r = crud.get_activity_stream_by_type(activity_id=1, stream_type=1, token_user_id=1, db=mock_db)
        assert r is None

    @patch("activities.activity_streams.crud.activity_crud.get_activity_by_id")
    def test_db_error(self, mock_get_act, mock_db):
        import activities.activity_streams.crud as crud

        mock_get_act.return_value = MagicMock(user_id=1)
        mock_db.scalars.return_value.first.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.get_activity_stream_by_type(activity_id=1, stream_type=1, token_user_id=1, db=mock_db)
        assert e.value.status_code == 500


class TestGetPublicActivityStreamByType:
    @patch("activities.activity_streams.crud.activity_streams_utils.transform_activity_streams")
    @patch("activities.activity_streams.crud.activity_streams_utils.is_stream_hidden")
    @patch("activities.activity_streams.crud.activity_crud.get_activity_by_id_if_is_public")
    @patch("activities.activity_streams.crud.server_settings_utils.get_server_settings_or_404")
    def test_success(self, mock_settings, mock_get_act, mock_hidden, mock_transform, mock_db):
        import activities.activity_streams.crud as crud
        import activities.activity_streams.models as m

        mock_settings.return_value = MagicMock(public_shareable_links=True)
        mock_get_act.return_value = MagicMock()
        mock_hidden.return_value = False
        mock_transform.return_value = MagicMock()
        mock_db.scalars.return_value.first.return_value = MagicMock(spec=m.ActivityStreams, id=1, stream_type=1)
        r = crud.get_public_activity_stream_by_type(activity_id=1, stream_type=1, db=mock_db)
        assert r is not None

    @patch("activities.activity_streams.crud.server_settings_utils.get_server_settings_or_404")
    def test_no_public_links(self, mock_settings, mock_db):
        import activities.activity_streams.crud as crud

        mock_settings.return_value = MagicMock(public_shareable_links=False)
        r = crud.get_public_activity_stream_by_type(activity_id=1, stream_type=1, db=mock_db)
        assert r is None

    @patch("activities.activity_streams.crud.activity_crud.get_activity_by_id_if_is_public")
    @patch("activities.activity_streams.crud.server_settings_utils.get_server_settings_or_404")
    def test_not_found(self, mock_settings, mock_get_act, mock_db):
        import activities.activity_streams.crud as crud

        mock_settings.return_value = MagicMock(public_shareable_links=True)
        mock_get_act.return_value = None
        r = crud.get_public_activity_stream_by_type(activity_id=1, stream_type=1, db=mock_db)
        assert r is None

    @patch("activities.activity_streams.crud.activity_crud.get_activity_by_id_if_is_public")
    @patch("activities.activity_streams.crud.server_settings_utils.get_server_settings_or_404")
    def test_no_stream(self, mock_settings, mock_get_act, mock_db):
        import activities.activity_streams.crud as crud

        mock_settings.return_value = MagicMock(public_shareable_links=True)
        mock_get_act.return_value = MagicMock()
        mock_db.scalars.return_value.first.return_value = None
        r = crud.get_public_activity_stream_by_type(activity_id=1, stream_type=1, db=mock_db)
        assert r is None

    @patch("activities.activity_streams.crud.activity_streams_utils.is_stream_hidden")
    @patch("activities.activity_streams.crud.activity_crud.get_activity_by_id_if_is_public")
    @patch("activities.activity_streams.crud.server_settings_utils.get_server_settings_or_404")
    def test_hidden(self, mock_settings, mock_get_act, mock_hidden, mock_db):
        import activities.activity_streams.crud as crud
        import activities.activity_streams.models as m

        mock_settings.return_value = MagicMock(public_shareable_links=True)
        mock_get_act.return_value = MagicMock()
        mock_hidden.return_value = True
        mock_db.scalars.return_value.first.return_value = MagicMock(spec=m.ActivityStreams, id=1, stream_type=1)
        r = crud.get_public_activity_stream_by_type(activity_id=1, stream_type=1, db=mock_db)
        assert r is None

    @patch("activities.activity_streams.crud.activity_crud.get_activity_by_id_if_is_public")
    @patch("activities.activity_streams.crud.server_settings_utils.get_server_settings_or_404")
    def test_db_error(self, mock_settings, mock_get_act, mock_db):
        import activities.activity_streams.crud as crud

        mock_settings.return_value = MagicMock(public_shareable_links=True)
        mock_get_act.return_value = MagicMock()
        mock_db.scalars.return_value.first.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.get_public_activity_stream_by_type(activity_id=1, stream_type=1, db=mock_db)
        assert e.value.status_code == 500


class TestRecomputeHrZonePercentagesForUser:
    @patch("activities.activity_streams.crud._get_user_hr_streams_batch")
    @patch("activities.activity_streams.crud.activity_streams_utils.compute_hr_zone_breakdown_sync")
    @patch("activities.activity_streams.crud.users_crud.get_user_by_id")
    def test_updates_streams_and_commits(self, mock_get_user, mock_compute, mock_batch, mock_db):
        import activities.activity_streams.crud as crud

        mock_get_user.return_value = MagicMock(max_heart_rate=200, birthdate=None)
        hr_block = {"zone_1": {"percent": 100.0, "hr": "< 120", "time_seconds": 60}}
        mock_compute.return_value = hr_block
        stream = MagicMock(id=7, stream_waypoints=[{"hr": 100}])
        mock_batch.side_effect = [[(stream, 60.0)], []]

        crud.recompute_hr_zone_percentages_for_user(1, mock_db)

        assert stream.zone_percentages == {"hr": hr_block}
        mock_compute.assert_called_once_with([{"hr": 100}], 200, 60.0)
        mock_db.commit.assert_called_once()

    @patch("activities.activity_streams.crud._get_user_hr_streams_batch")
    @patch("activities.activity_streams.crud.users_crud.get_user_by_id")
    def test_clears_zones_when_max_hr_unresolvable(self, mock_get_user, mock_batch, mock_db):
        import activities.activity_streams.crud as crud

        mock_get_user.return_value = MagicMock(max_heart_rate=None, birthdate=None)
        stream = MagicMock(id=7, stream_waypoints=[{"hr": 100}])
        mock_batch.side_effect = [[(stream, 60.0)], []]

        crud.recompute_hr_zone_percentages_for_user(1, mock_db)

        assert stream.zone_percentages is None
        mock_db.commit.assert_called_once()

    @patch("activities.activity_streams.crud._get_user_hr_streams_batch")
    @patch("activities.activity_streams.crud.users_crud.get_user_by_id")
    def test_no_user_is_noop(self, mock_get_user, mock_batch, mock_db):
        import activities.activity_streams.crud as crud

        mock_get_user.return_value = None

        crud.recompute_hr_zone_percentages_for_user(1, mock_db)

        mock_batch.assert_not_called()
        mock_db.commit.assert_not_called()

    @patch("activities.activity_streams.crud._get_user_hr_streams_batch")
    @patch("activities.activity_streams.crud.users_crud.get_user_by_id")
    def test_swallows_errors_and_rolls_back(self, mock_get_user, mock_batch, mock_db):
        import activities.activity_streams.crud as crud

        mock_get_user.return_value = MagicMock(max_heart_rate=200, birthdate=None)
        mock_batch.side_effect = SQLAlchemyError("boom")

        crud.recompute_hr_zone_percentages_for_user(1, mock_db)

        mock_db.rollback.assert_called_once()
