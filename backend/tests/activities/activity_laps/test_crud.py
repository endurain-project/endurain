from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError
from tests._helpers.db import setup_mock_execute
from tests._helpers.models import mock_model


class TestCreateActivityLaps:
    @patch("modules.activities.activity_laps.crud.activity_laps_models.ActivityLaps")
    def test_success(self, mock_laps_model, mock_db):
        import modules.activities.activity_laps.crud as crud

        mock_laps_model.return_value = MagicMock()
        laps = [{"lap_number": 1, "lap_time": 3600.0}]
        crud.create_activity_laps(laps, 1, mock_db)
        mock_db.add_all.assert_called_once()
        mock_db.commit.assert_called_once()

    def test_empty(self, mock_db):
        import modules.activities.activity_laps.crud as crud

        crud.create_activity_laps([], 1, mock_db)
        mock_db.commit.assert_called_once()

    @patch("modules.activities.activity_laps.crud.activity_laps_models.ActivityLaps")
    def test_db_error(self, mock_laps_model, mock_db):
        import modules.activities.activity_laps.crud as crud

        mock_laps_model.return_value = MagicMock()
        mock_db.commit.side_effect = SQLAlchemyError("err")
        laps = [{"lap_number": 1}]
        with pytest.raises(HTTPException) as e:
            crud.create_activity_laps(laps, 1, mock_db)
        assert e.value.status_code == 500


class TestGetActivityLaps:
    @patch("modules.activities.activity_laps.crud.activity_crud.get_activity_by_id")
    @patch("modules.activities.activity_laps.crud._to_read_schema")
    def test_success(self, mock_to_read, mock_get_act, mock_db):
        import modules.activities.activity_laps.crud as crud
        import modules.activities.activity_laps.models as m

        mock_get_act.return_value = MagicMock(user_id=1, hide_laps=False, timezone="UTC")
        mock_to_read.return_value = MagicMock()
        setup_mock_execute(mock_db, return_scalars_all=[mock_model(m.ActivityLaps, id=1, activity_id=1)])
        r = crud.get_activity_laps(activity_id=1, token_user_id=1, db=mock_db)
        assert len(r) == 1

    @patch("modules.activities.activity_laps.crud.activity_crud.get_activity_by_id")
    def test_empty(self, mock_get_act, mock_db):
        import modules.activities.activity_laps.crud as crud

        mock_get_act.return_value = MagicMock(user_id=1, hide_laps=False)
        setup_mock_execute(mock_db, return_scalars_all=[])
        r = crud.get_activity_laps(activity_id=1, token_user_id=1, db=mock_db)
        assert r is None

    @patch("modules.activities.activity_laps.crud.activity_crud.get_activity_by_id")
    def test_not_found(self, mock_get_act, mock_db):
        import modules.activities.activity_laps.crud as crud

        mock_get_act.return_value = None
        r = crud.get_activity_laps(activity_id=1, token_user_id=1, db=mock_db)
        assert r is None

    @patch("modules.activities.activity_laps.crud.activity_crud.get_activity_by_id")
    def test_hidden(self, mock_get_act, mock_db):
        import modules.activities.activity_laps.crud as crud

        mock_get_act.return_value = MagicMock(user_id=2, hide_laps=True)
        r = crud.get_activity_laps(activity_id=1, token_user_id=1, db=mock_db)
        assert r is None

    @patch("modules.activities.activity_laps.crud.activity_crud.get_activity_by_id")
    def test_db_error(self, mock_get_act, mock_db):
        import modules.activities.activity_laps.crud as crud

        mock_get_act.return_value = MagicMock(user_id=1, hide_laps=False)
        mock_db.scalars.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.get_activity_laps(activity_id=1, token_user_id=1, db=mock_db)
        assert e.value.status_code == 500


class TestGetActivitiesLaps:
    @patch("modules.activities.activity_laps.crud._to_read_schema")
    def test_success(self, mock_to_read, mock_db):
        import modules.activities.activity.models as am
        import modules.activities.activity_laps.crud as crud
        import modules.activities.activity_laps.models as m

        mock_to_read.return_value = MagicMock()
        mock_activity = MagicMock(spec=am.Activity, id=1, user_id=1, timezone="UTC")
        mock_lap = MagicMock(spec=m.ActivityLaps, id=1, activity_id=1)
        mock_db.scalars.return_value.all.side_effect = [
            [mock_activity],
            [mock_lap],
        ]
        r = crud.get_activities_laps(activity_ids=[1], token_user_id=1, db=mock_db)
        assert len(r) == 1

    def test_empty_ids(self, mock_db):
        import modules.activities.activity_laps.crud as crud

        r = crud.get_activities_laps(activity_ids=[], token_user_id=1, db=mock_db)
        assert r == []

    def test_no_activities(self, mock_db):
        import modules.activities.activity_laps.crud as crud

        mock_db.scalars.return_value.all.return_value = []
        r = crud.get_activities_laps(activity_ids=[1], token_user_id=1, db=mock_db)
        assert r == []

    def test_no_allowed_ids(self, mock_db):
        import modules.activities.activity.models as am
        import modules.activities.activity_laps.crud as crud

        mock_activity = MagicMock(spec=am.Activity, id=1, user_id=2)
        mock_db.scalars.return_value.all.return_value = [mock_activity]
        r = crud.get_activities_laps(activity_ids=[1], token_user_id=1, db=mock_db)
        assert r == []

    def test_no_laps(self, mock_db):
        import modules.activities.activity.models as am
        import modules.activities.activity_laps.crud as crud

        mock_activity = MagicMock(spec=am.Activity, id=1, user_id=1, timezone="UTC")
        mock_db.scalars.return_value.all.side_effect = [
            [mock_activity],
            [],
        ]
        r = crud.get_activities_laps(activity_ids=[1], token_user_id=1, db=mock_db)
        assert r == []

    def test_db_error(self, mock_db):
        import modules.activities.activity_laps.crud as crud

        mock_db.scalars.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.get_activities_laps(activity_ids=[1], token_user_id=1, db=mock_db)
        assert e.value.status_code == 500


class TestGetPublicActivityLaps:
    @patch("modules.activities.activity_laps.crud._to_read_schema")
    @patch("modules.activities.activity_laps.crud.server_settings_utils.get_server_settings_or_404")
    @patch("modules.activities.activity_laps.crud.activity_crud.get_activity_by_id")
    def test_success(self, mock_get_act, mock_settings, mock_to_read, mock_db):
        import modules.activities.activity_laps.crud as crud
        import modules.activities.activity_laps.models as m

        mock_get_act.return_value = MagicMock(hide_laps=False, visibility=0, timezone="UTC")
        mock_settings.return_value = MagicMock(public_shareable_links=True)
        mock_to_read.return_value = MagicMock()
        mock_db.scalars.return_value.all.return_value = [MagicMock(spec=m.ActivityLaps, id=1, activity_id=1)]
        r = crud.get_public_activity_laps(activity_id=1, db=mock_db)
        assert len(r) == 1

    @patch("modules.activities.activity_laps.crud.activity_crud.get_activity_by_id")
    def test_not_found(self, mock_get_act, mock_db):
        import modules.activities.activity_laps.crud as crud

        mock_get_act.return_value = None
        r = crud.get_public_activity_laps(activity_id=1, db=mock_db)
        assert r is None

    @patch("modules.activities.activity_laps.crud.activity_crud.get_activity_by_id")
    def test_hidden(self, mock_get_act, mock_db):
        import modules.activities.activity_laps.crud as crud

        mock_get_act.return_value = MagicMock(hide_laps=True)
        r = crud.get_public_activity_laps(activity_id=1, db=mock_db)
        assert r is None

    @patch("modules.activities.activity_laps.crud.server_settings_utils.get_server_settings_or_404")
    @patch("modules.activities.activity_laps.crud.activity_crud.get_activity_by_id")
    def test_no_public_links(self, mock_get_act, mock_settings, mock_db):
        import modules.activities.activity_laps.crud as crud

        mock_get_act.return_value = MagicMock(hide_laps=False)
        mock_settings.return_value = MagicMock(public_shareable_links=False)
        r = crud.get_public_activity_laps(activity_id=1, db=mock_db)
        assert r is None

    @patch("modules.activities.activity_laps.crud.server_settings_utils.get_server_settings_or_404")
    @patch("modules.activities.activity_laps.crud.activity_crud.get_activity_by_id")
    def test_not_public(self, mock_get_act, mock_settings, mock_db):
        import modules.activities.activity_laps.crud as crud

        mock_get_act.return_value = MagicMock(hide_laps=False, visibility=2)
        mock_settings.return_value = MagicMock(public_shareable_links=True)
        r = crud.get_public_activity_laps(activity_id=1, db=mock_db)
        assert r is None

    @patch("modules.activities.activity_laps.crud.server_settings_utils.get_server_settings_or_404")
    @patch("modules.activities.activity_laps.crud.activity_crud.get_activity_by_id")
    def test_no_laps(self, mock_get_act, mock_settings, mock_db):
        import modules.activities.activity_laps.crud as crud

        mock_get_act.return_value = MagicMock(hide_laps=False, visibility=0, timezone="UTC")
        mock_settings.return_value = MagicMock(public_shareable_links=True)
        mock_db.scalars.return_value.all.return_value = []
        r = crud.get_public_activity_laps(activity_id=1, db=mock_db)
        assert r is None

    @patch("modules.activities.activity_laps.crud.server_settings_utils.get_server_settings_or_404")
    @patch("modules.activities.activity_laps.crud.activity_crud.get_activity_by_id")
    def test_db_error(self, mock_get_act, mock_settings, mock_db):
        import modules.activities.activity_laps.crud as crud

        mock_get_act.return_value = MagicMock(hide_laps=False, visibility=0, timezone="UTC")
        mock_settings.return_value = MagicMock(public_shareable_links=True)
        mock_db.scalars.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.get_public_activity_laps(activity_id=1, db=mock_db)
        assert e.value.status_code == 500


class TestToReadSchema:
    @patch("modules.activities.activity_laps.crud.activity_laps_schema.ActivityLapsRead.model_validate")
    def test_success(self, mock_validate):
        import modules.activities.activity_laps.crud as crud

        mock_schema = MagicMock()
        mock_validate.return_value = mock_schema
        orm_lap = MagicMock()
        result = crud._to_read_schema(orm_lap, "Europe/London")
        mock_validate.assert_called_once_with(orm_lap)
        assert mock_schema.timezone == "Europe/London"
        assert result == mock_schema
