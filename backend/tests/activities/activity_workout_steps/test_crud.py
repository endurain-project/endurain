from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

import core.exceptions as core_exceptions


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
        with pytest.raises(core_exceptions.ProcessingError) as e:
            crud.create_activity_workout_steps(steps, 1, mock_db)
        assert e.value.status_code == 500


class TestGetActivityWorkoutSteps:
    """Persistence only — the access decision lives in ``activity_workout_steps.service``."""

    @patch("modules.activities.activity_workout_steps.crud._to_read_schema")
    def test_success(self, mock_to_read, mock_db):
        import modules.activities.activity_workout_steps.crud as crud

        mock_to_read.return_value = MagicMock()
        mock_db.scalars.return_value.all.return_value = [MagicMock()]
        assert len(crud.get_activity_workout_steps(activity_id=1, db=mock_db)) == 1

    def test_empty(self, mock_db):
        import modules.activities.activity_workout_steps.crud as crud

        mock_db.scalars.return_value.all.return_value = []
        assert crud.get_activity_workout_steps(activity_id=1, db=mock_db) == []

    def test_db_error(self, mock_db):
        import modules.activities.activity_workout_steps.crud as crud

        mock_db.scalars.side_effect = SQLAlchemyError("err")
        with pytest.raises(core_exceptions.ProcessingError) as e:
            crud.get_activity_workout_steps(activity_id=1, db=mock_db)
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
        with pytest.raises(core_exceptions.ProcessingError) as e:
            crud.get_activities_workout_steps(activity_ids=[1], token_user_id=1, db=mock_db)
        assert e.value.status_code == 500
