from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError
from tests._helpers.db import setup_mock_execute
from tests._helpers.models import mock_model


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
        with pytest.raises(HTTPException) as e:
            crud.create_activity_sets(sets, 1, mock_db)
        assert e.value.status_code == 500


class TestGetActivitySets:
    @patch("modules.activities.activity_sets.crud.activity_crud.get_viewable_activity_by_id_for_user")
    @patch("modules.activities.activity_sets.crud.activity_sets_schema.ActivitySetsRead.model_validate")
    def test_success(self, mock_validate, mock_get_act, mock_db):
        import modules.activities.activity_sets.crud as crud
        import modules.activities.activity_sets.models as m
        from modules.activities.activity_sets.schema import ActivitySetsRead

        mock_get_act.return_value = MagicMock(user_id=1, hide_workout_sets_steps=False, timezone="UTC")
        mock_validate.return_value = ActivitySetsRead(
            id=1,
            activity_id=1,
            duration=300.0,
            set_type="interval",
            start_time=MagicMock(),
        )
        setup_mock_execute(mock_db, return_scalars_all=[mock_model(m.ActivitySets, id=1, activity_id=1)])
        r = crud.get_activity_sets(activity_id=1, token_user_id=1, db=mock_db)
        assert len(r) == 1

    @patch("modules.activities.activity_sets.crud.activity_crud.get_viewable_activity_by_id_for_user")
    def test_not_found(self, mock_get_act, mock_db):
        import modules.activities.activity_sets.crud as crud

        mock_get_act.return_value = None
        r = crud.get_activity_sets(activity_id=1, token_user_id=1, db=mock_db)
        assert r is None

    @patch("modules.activities.activity_sets.crud.activity_crud.get_viewable_activity_by_id_for_user")
    def test_hidden(self, mock_get_act, mock_db):
        import modules.activities.activity_sets.crud as crud

        mock_get_act.return_value = MagicMock(user_id=2, hide_workout_sets_steps=True)
        r = crud.get_activity_sets(activity_id=1, token_user_id=1, db=mock_db)
        assert r is None

    @patch("modules.activities.activity_sets.crud.activity_crud.get_viewable_activity_by_id_for_user")
    def test_empty(self, mock_get_act, mock_db):
        import modules.activities.activity_sets.crud as crud

        mock_get_act.return_value = MagicMock(user_id=1, hide_workout_sets_steps=False)
        setup_mock_execute(mock_db, return_scalars_all=[])
        r = crud.get_activity_sets(activity_id=1, token_user_id=1, db=mock_db)
        assert r is None

    @patch("modules.activities.activity_sets.crud.activity_crud.get_viewable_activity_by_id_for_user")
    def test_db_error(self, mock_get_act, mock_db):
        import modules.activities.activity_sets.crud as crud

        mock_get_act.return_value = MagicMock(user_id=1, hide_workout_sets_steps=False)
        mock_db.scalars.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.get_activity_sets(activity_id=1, token_user_id=1, db=mock_db)
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
        with pytest.raises(HTTPException) as e:
            crud.get_activities_sets(activity_ids=[1], token_user_id=1, db=mock_db)
        assert e.value.status_code == 500


class TestGetPublicActivitySets:
    """The public gate itself lives in activity_crud.get_public_activity_for_child_read.

    These assert only that this CRUD delegates to it and honours its verdict; the
    gate's own rules (public_shareable_links, visibility, is_hidden, hide_*) are
    covered once in tests/activities/activity/test_crud.py.
    """

    @patch("modules.activities.activity_sets.crud._to_read_schema")
    @patch("modules.activities.activity_sets.crud.activity_crud.get_public_activity_for_child_read")
    def test_success(self, mock_gate, mock_to_read, mock_db):
        import modules.activities.activity_sets.crud as crud
        import modules.activities.activity_sets.models as m

        mock_gate.return_value = MagicMock(hide_workout_sets_steps=False, visibility=0, timezone="UTC")
        mock_to_read.return_value = MagicMock()
        mock_db.scalars.return_value.all.return_value = [MagicMock(spec=m.ActivitySets, id=1, activity_id=1)]
        r = crud.get_public_activity_sets(activity_id=1, db=mock_db)
        assert len(r) == 1
        mock_gate.assert_called_once_with(1, mock_db, hide_attr="hide_workout_sets_steps")

    @patch("modules.activities.activity_sets.crud.activity_crud.get_public_activity_for_child_read")
    def test_gate_denied_returns_none(self, mock_gate, mock_db):
        """Gate says no (not public, hidden, or hide_workout_sets_steps set) -> no rows are read at all."""
        import modules.activities.activity_sets.crud as crud

        mock_gate.return_value = None
        r = crud.get_public_activity_sets(activity_id=1, db=mock_db)
        assert r is None
        mock_db.scalars.assert_not_called()

    @patch("modules.activities.activity_sets.crud.activity_crud.get_public_activity_for_child_read")
    def test_no_sets(self, mock_gate, mock_db):
        import modules.activities.activity_sets.crud as crud

        mock_gate.return_value = MagicMock(hide_workout_sets_steps=False, visibility=0, timezone="UTC")
        mock_db.scalars.return_value.all.return_value = []
        r = crud.get_public_activity_sets(activity_id=1, db=mock_db)
        assert r is None

    @patch("modules.activities.activity_sets.crud.activity_crud.get_public_activity_for_child_read")
    def test_db_error(self, mock_gate, mock_db):
        import modules.activities.activity_sets.crud as crud

        mock_gate.return_value = MagicMock(hide_workout_sets_steps=False, visibility=0, timezone="UTC")
        mock_db.scalars.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.get_public_activity_sets(activity_id=1, db=mock_db)
        assert e.value.status_code == 500
