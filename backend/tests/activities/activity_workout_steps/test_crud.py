from unittest.mock import MagicMock, patch


class TestCreateActivityWorkoutSteps:
    @patch("modules.activities.activity_workout_steps.crud.activity_workout_steps_models.ActivityWorkoutSteps")
    def test_success(self, mock_steps_model, mock_db):
        import modules.activities.activity_workout_steps.crud as crud
        from modules.activities.activity_workout_steps.contracts import ActivityWorkoutStepsCreate

        mock_steps_model.return_value = MagicMock()
        steps = [
            ActivityWorkoutStepsCreate(
                message_index=0,
                duration_type="time",
                duration_value=300.0,
            )
        ]
        crud.create_activity_workout_steps(steps, 1, mock_db)
        mock_db.add_all.assert_called_once()
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_not_called()

    def test_empty(self, mock_db):
        import modules.activities.activity_workout_steps.crud as crud

        crud.create_activity_workout_steps([], 1, mock_db)
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_not_called()


class TestGetActivityWorkoutSteps:
    """Persistence only — the access decision lives in ``activity_workout_steps.service``."""

    @patch("modules.activities.activity_workout_steps.serializers.to_read_schema")
    def test_success(self, mock_to_read, mock_db):
        import modules.activities.activity_workout_steps.crud as crud

        mock_to_read.return_value = MagicMock()
        mock_db.scalars.return_value.all.return_value = [MagicMock()]
        assert len(crud.get_activity_workout_steps(activity_id=1, db=mock_db)) == 1

    def test_empty(self, mock_db):
        import modules.activities.activity_workout_steps.crud as crud

        mock_db.scalars.return_value.all.return_value = []
        assert crud.get_activity_workout_steps(activity_id=1, db=mock_db) == []


class TestGetActivitiesWorkoutSteps:
    """The batch read no longer joins the parent: it is handed scoped ids."""

    @patch("modules.activities.activity_workout_steps.serializers.to_read_schema")
    def test_success(self, mock_to_read, mock_db):
        import modules.activities.activity_workout_steps.crud as crud
        import modules.activities.activity_workout_steps.models as m

        mock_to_read.return_value = MagicMock()
        mock_db.scalars.return_value.all.return_value = [MagicMock(spec=m.ActivityWorkoutSteps, id=1, activity_id=1)]

        assert len(crud.get_activities_workout_steps(activity_ids=[1], db=mock_db)) == 1

    def test_empty_ids_short_circuits(self, mock_db):
        import modules.activities.activity_workout_steps.crud as crud

        assert crud.get_activities_workout_steps(activity_ids=[], db=mock_db) == []
        mock_db.scalars.assert_not_called()

    def test_no_rows(self, mock_db):
        import modules.activities.activity_workout_steps.crud as crud

        mock_db.scalars.return_value.all.return_value = []

        assert crud.get_activities_workout_steps(activity_ids=[1], db=mock_db) == []
