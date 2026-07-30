from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError
from tests._helpers.db import setup_mock_execute
from tests._helpers.models import mock_model

import core.exceptions as core_exceptions


class TestCreateActivitySets:
    @patch("modules.activities.activity_sets.crud.activity_sets_models.ActivitySets")
    def test_success(self, mock_sets_model, mock_db):
        import modules.activities.activity_sets.crud as crud
        from modules.activities.activity_sets.schema import ActivitySetsCreate

        mock_sets_model.return_value = MagicMock()
        sets = [
            ActivitySetsCreate(activity_id=1, duration=300.0, set_type="interval", start_time="2024-01-15T08:00:00")
        ]
        crud.create_activity_sets(sets, 1, mock_db)
        mock_db.add_all.assert_called_once()
        mock_db.commit.assert_called_once()

    def test_empty(self, mock_db):
        import modules.activities.activity_sets.crud as crud

        crud.create_activity_sets([], 1, mock_db)
        mock_db.commit.assert_called_once()

    @patch("modules.activities.activity_sets.crud.activity_sets_models.ActivitySets")
    def test_db_error(self, mock_sets_model, mock_db):
        import modules.activities.activity_sets.crud as crud
        from modules.activities.activity_sets.schema import ActivitySetsCreate

        mock_sets_model.return_value = MagicMock()
        mock_db.commit.side_effect = SQLAlchemyError("err")
        sets = [
            ActivitySetsCreate(activity_id=1, duration=300.0, set_type="interval", start_time="2024-01-15T08:00:00")
        ]
        with pytest.raises(core_exceptions.ProcessingError) as e:
            crud.create_activity_sets(sets, 1, mock_db)
        assert e.value.status_code == 500


class TestGetActivitySets:
    """Persistence only — the access decision lives in ``activity_sets.service``."""

    @patch("modules.activities.activity_sets.crud.activity_sets_schema.ActivitySetsRead.model_validate")
    def test_success(self, mock_validate, mock_db):
        import modules.activities.activity_sets.crud as crud
        import modules.activities.activity_sets.models as m
        from modules.activities.activity_sets.schema import ActivitySetsRead

        mock_validate.return_value = ActivitySetsRead(
            id=1,
            activity_id=1,
            duration=300.0,
            set_type="interval",
            start_time=MagicMock(),
        )
        setup_mock_execute(mock_db, return_scalars_all=[mock_model(m.ActivitySets, id=1, activity_id=1)])
        assert len(crud.get_activity_sets(activity_id=1, db=mock_db)) == 1

    def test_empty(self, mock_db):
        import modules.activities.activity_sets.crud as crud

        setup_mock_execute(mock_db, return_scalars_all=[])
        assert crud.get_activity_sets(activity_id=1, db=mock_db) == []

    def test_db_error(self, mock_db):
        import modules.activities.activity_sets.crud as crud

        mock_db.scalars.side_effect = SQLAlchemyError("err")
        with pytest.raises(core_exceptions.ProcessingError) as e:
            crud.get_activity_sets(activity_id=1, db=mock_db)
        assert e.value.status_code == 500


class TestGetActivitiesSets:
    @patch("modules.activities.activity_sets.crud._to_read_schema")
    def test_success(self, mock_to_read, mock_db):
        import modules.activities.activity.models as am
        import modules.activities.activity_sets.crud as crud
        import modules.activities.activity_sets.models as m

        mock_to_read.return_value = MagicMock()
        mock_activity = MagicMock(spec=am.Activity, id=1, user_id=1, timezone="UTC")
        mock_set = MagicMock(spec=m.ActivitySets, id=1, activity_id=1)
        mock_db.scalars.return_value.all.side_effect = [
            [mock_activity],
            [mock_set],
        ]
        r = crud.get_activities_sets(activity_ids=[1], token_user_id=1, db=mock_db)
        assert len(r) == 1

    def test_empty_ids(self, mock_db):
        import modules.activities.activity_sets.crud as crud

        r = crud.get_activities_sets(activity_ids=[], token_user_id=1, db=mock_db)
        assert r == []

    def test_no_activities(self, mock_db):
        import modules.activities.activity_sets.crud as crud

        mock_db.scalars.return_value.all.return_value = []
        r = crud.get_activities_sets(activity_ids=[1], token_user_id=1, db=mock_db)
        assert r == []

    def test_no_allowed_ids(self, mock_db):
        import modules.activities.activity.models as am
        import modules.activities.activity_sets.crud as crud

        mock_activity = MagicMock(spec=am.Activity, id=1, user_id=2)
        mock_db.scalars.return_value.all.return_value = [mock_activity]
        r = crud.get_activities_sets(activity_ids=[1], token_user_id=1, db=mock_db)
        assert r == []

    def test_no_sets(self, mock_db):
        import modules.activities.activity.models as am
        import modules.activities.activity_sets.crud as crud

        mock_activity = MagicMock(spec=am.Activity, id=1, user_id=1, timezone="UTC")
        mock_db.scalars.return_value.all.side_effect = [
            [mock_activity],
            [],
        ]
        r = crud.get_activities_sets(activity_ids=[1], token_user_id=1, db=mock_db)
        assert r == []

    def test_db_error(self, mock_db):
        import modules.activities.activity_sets.crud as crud

        mock_db.scalars.side_effect = SQLAlchemyError("err")
        with pytest.raises(core_exceptions.ProcessingError) as e:
            crud.get_activities_sets(activity_ids=[1], token_user_id=1, db=mock_db)
        assert e.value.status_code == 500
