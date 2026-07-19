from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError
from tests._helpers.db import setup_mock_execute


class TestCreateActivityWorkoutSteps:
    @patch("modules.activities.activity_workout_steps.crud.activity_workout_steps_models.ActivityWorkoutSteps")
    def test_success(self, mock_steps_model, mock_db):
        import modules.activities.activity_workout_steps.crud as crud
        from modules.activities.activity_workout_steps.schema import ActivityWorkoutSteps

        mock_steps_model.return_value = MagicMock()
        steps = [
            ActivityWorkoutSteps(
                activity_id=1,
                step_number=1,
                step_type="warm_up",
                step_duration=300.0,
                message_index=0,
                duration_type="time",
            )
        ]
        crud.create_activity_workout_steps(steps, 1, mock_db)
        mock_db.add_all.assert_called_once()
        mock_db.commit.assert_called_once()

    def test_empty(self, mock_db):
        import modules.activities.activity_workout_steps.crud as crud

        crud.create_activity_workout_steps([], 1, mock_db)
        mock_db.commit.assert_called_once()

    @patch("modules.activities.activity_workout_steps.crud.activity_workout_steps_models.ActivityWorkoutSteps")
    def test_db_error(self, mock_steps_model, mock_db):
        import modules.activities.activity_workout_steps.crud as crud

        mock_steps_model.return_value = MagicMock()
        mock_db.commit.side_effect = SQLAlchemyError("err")
        steps = [
            MagicMock(
                activity_id=1,
                step_number=1,
                step_type="warm_up",
                step_duration=300.0,
                message_index=0,
                duration_type="time",
            )
        ]
        with pytest.raises(HTTPException) as e:
            crud.create_activity_workout_steps(steps, 1, mock_db)
        assert e.value.status_code == 500


class TestGetActivityWorkoutSteps:
    @patch("modules.activities.activity_workout_steps.crud.activity_crud.get_activity_by_id")
    def test_success(self, mock_get_act, mock_db):
        import modules.activities.activity_workout_steps.crud as crud

        mock_get_act.return_value = MagicMock(user_id=1, hide_workout_sets_steps=False)
        setup_mock_execute(
            mock_db,
            return_scalars_all=[SimpleNamespace(id=1, activity_id=1, message_index=0, duration_type="time")],
        )
        r = crud.get_activity_workout_steps(activity_id=1, token_user_id=1, db=mock_db)
        assert len(r) == 1

    @patch("modules.activities.activity_workout_steps.crud.activity_crud.get_activity_by_id")
    def test_not_found(self, mock_get_act, mock_db):
        import modules.activities.activity_workout_steps.crud as crud

        mock_get_act.return_value = None
        r = crud.get_activity_workout_steps(activity_id=1, token_user_id=1, db=mock_db)
        assert r is None

    @patch("modules.activities.activity_workout_steps.crud.activity_crud.get_activity_by_id")
    def test_hidden(self, mock_get_act, mock_db):
        import modules.activities.activity_workout_steps.crud as crud

        mock_get_act.return_value = MagicMock(user_id=2, hide_workout_sets_steps=True)
        r = crud.get_activity_workout_steps(activity_id=1, token_user_id=1, db=mock_db)
        assert r is None

    @patch("modules.activities.activity_workout_steps.crud.activity_crud.get_activity_by_id")
    def test_empty(self, mock_get_act, mock_db):
        import modules.activities.activity_workout_steps.crud as crud

        mock_get_act.return_value = MagicMock(user_id=1, hide_workout_sets_steps=False)
        mock_db.scalars.return_value.all.return_value = []
        r = crud.get_activity_workout_steps(activity_id=1, token_user_id=1, db=mock_db)
        assert r is None

    @patch("modules.activities.activity_workout_steps.crud.activity_crud.get_activity_by_id")
    def test_db_error(self, mock_get_act, mock_db):
        import modules.activities.activity_workout_steps.crud as crud

        mock_get_act.return_value = MagicMock(user_id=1, hide_workout_sets_steps=False)
        mock_db.scalars.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.get_activity_workout_steps(activity_id=1, token_user_id=1, db=mock_db)
        assert e.value.status_code == 500


class TestGetActivitiesWorkoutSteps:
    def test_success(self, mock_db):
        import modules.activities.activity.models as am
        import modules.activities.activity_workout_steps.crud as crud

        mock_activity = MagicMock(spec=am.Activity, id=1, user_id=1, hide_workout_sets_steps=False)
        mock_steps = [SimpleNamespace(id=1, activity_id=1, message_index=0, duration_type="time")]
        mock_db.scalars.return_value.all.side_effect = [
            [mock_activity],
            mock_steps,
        ]
        r = crud.get_activities_workout_steps(activity_ids=[1], token_user_id=1, db=mock_db)
        assert len(r) == 1

    def test_empty_ids(self, mock_db):
        import modules.activities.activity_workout_steps.crud as crud

        r = crud.get_activities_workout_steps(activity_ids=[], token_user_id=1, db=mock_db)
        assert r == []

    def test_no_activities(self, mock_db):
        import modules.activities.activity_workout_steps.crud as crud

        mock_db.scalars.return_value.all.return_value = []
        r = crud.get_activities_workout_steps(activity_ids=[1], token_user_id=1, db=mock_db)
        assert r == []

    def test_no_allowed_ids(self, mock_db):
        import modules.activities.activity.models as am
        import modules.activities.activity_workout_steps.crud as crud

        mock_activity = MagicMock(spec=am.Activity, id=1, user_id=2, hide_workout_sets_steps=True)
        mock_db.scalars.return_value.all.return_value = [mock_activity]
        r = crud.get_activities_workout_steps(activity_ids=[1], token_user_id=1, db=mock_db)
        assert r == []

    def test_no_steps(self, mock_db):
        import modules.activities.activity.models as am
        import modules.activities.activity_workout_steps.crud as crud

        mock_activity = MagicMock(spec=am.Activity, id=1, user_id=1, hide_workout_sets_steps=False)
        mock_db.scalars.return_value.all.side_effect = [
            [mock_activity],
            [],
        ]
        r = crud.get_activities_workout_steps(activity_ids=[1], token_user_id=1, db=mock_db)
        assert r == []

    def test_db_error(self, mock_db):
        import modules.activities.activity_workout_steps.crud as crud

        mock_db.scalars.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.get_activities_workout_steps(activity_ids=[1], token_user_id=1, db=mock_db)
        assert e.value.status_code == 500


class TestGetPublicActivityWorkoutSteps:
    @patch("modules.activities.activity_workout_steps.crud.server_settings_utils.get_server_settings_or_404")
    @patch("modules.activities.activity_workout_steps.crud.activity_crud.get_activity_by_id")
    def test_success(self, mock_get_act, mock_settings, mock_db):
        import modules.activities.activity_workout_steps.crud as crud

        mock_get_act.return_value = MagicMock(hide_workout_sets_steps=False, visibility=0)
        mock_settings.return_value = MagicMock(public_shareable_links=True)
        mock_db.scalars.return_value.all.return_value = [
            SimpleNamespace(id=1, activity_id=1, message_index=0, duration_type="time")
        ]
        r = crud.get_public_activity_workout_steps(activity_id=1, db=mock_db)
        assert len(r) == 1

    @patch("modules.activities.activity_workout_steps.crud.activity_crud.get_activity_by_id")
    def test_not_found(self, mock_get_act, mock_db):
        import modules.activities.activity_workout_steps.crud as crud

        mock_get_act.return_value = None
        r = crud.get_public_activity_workout_steps(activity_id=1, db=mock_db)
        assert r is None

    @patch("modules.activities.activity_workout_steps.crud.activity_crud.get_activity_by_id")
    def test_hidden(self, mock_get_act, mock_db):
        import modules.activities.activity_workout_steps.crud as crud

        mock_get_act.return_value = MagicMock(hide_workout_sets_steps=True)
        r = crud.get_public_activity_workout_steps(activity_id=1, db=mock_db)
        assert r is None

    @patch("modules.activities.activity_workout_steps.crud.server_settings_utils.get_server_settings_or_404")
    @patch("modules.activities.activity_workout_steps.crud.activity_crud.get_activity_by_id")
    def test_no_public_links(self, mock_get_act, mock_settings, mock_db):
        import modules.activities.activity_workout_steps.crud as crud

        mock_get_act.return_value = MagicMock(hide_workout_sets_steps=False)
        mock_settings.return_value = MagicMock(public_shareable_links=False)
        r = crud.get_public_activity_workout_steps(activity_id=1, db=mock_db)
        assert r is None

    @patch("modules.activities.activity_workout_steps.crud.server_settings_utils.get_server_settings_or_404")
    @patch("modules.activities.activity_workout_steps.crud.activity_crud.get_activity_by_id")
    def test_not_public(self, mock_get_act, mock_settings, mock_db):
        import modules.activities.activity_workout_steps.crud as crud

        mock_get_act.return_value = MagicMock(hide_workout_sets_steps=False, visibility=2)
        mock_settings.return_value = MagicMock(public_shareable_links=True)
        r = crud.get_public_activity_workout_steps(activity_id=1, db=mock_db)
        assert r is None

    @patch("modules.activities.activity_workout_steps.crud.server_settings_utils.get_server_settings_or_404")
    @patch("modules.activities.activity_workout_steps.crud.activity_crud.get_activity_by_id")
    def test_no_steps(self, mock_get_act, mock_settings, mock_db):
        import modules.activities.activity_workout_steps.crud as crud

        mock_get_act.return_value = MagicMock(hide_workout_sets_steps=False, visibility=0)
        mock_settings.return_value = MagicMock(public_shareable_links=True)
        mock_db.scalars.return_value.all.return_value = []
        r = crud.get_public_activity_workout_steps(activity_id=1, db=mock_db)
        assert r is None

    @patch("modules.activities.activity_workout_steps.crud.server_settings_utils.get_server_settings_or_404")
    @patch("modules.activities.activity_workout_steps.crud.activity_crud.get_activity_by_id")
    def test_db_error(self, mock_get_act, mock_settings, mock_db):
        import modules.activities.activity_workout_steps.crud as crud

        mock_get_act.return_value = MagicMock(hide_workout_sets_steps=False, visibility=0)
        mock_settings.return_value = MagicMock(public_shareable_links=True)
        mock_db.scalars.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.get_public_activity_workout_steps(activity_id=1, db=mock_db)
        assert e.value.status_code == 500
