import uuid
from unittest.mock import MagicMock, patch

_ACTIVITY_ID = uuid.UUID("00000000-0000-4000-8000-000000000005")


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
        crud.create_activity_workout_steps(steps, _ACTIVITY_ID, mock_db)
        mock_db.add_all.assert_called_once()
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_not_called()

    def test_empty(self, mock_db):
        import modules.activities.activity_workout_steps.crud as crud

        crud.create_activity_workout_steps([], _ACTIVITY_ID, mock_db)
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_not_called()


class TestGetActivityWorkoutSteps:
    """Persistence only — the access decision lives in ``activity_workout_steps.service``."""

    @patch("modules.activities.activity_workout_steps.serializers.to_read_schema")
    def test_success(self, mock_to_read, mock_db):
        import modules.activities.activity_workout_steps.crud as crud

        mock_to_read.return_value = MagicMock()
        mock_db.scalars.return_value.all.return_value = [MagicMock()]
        assert len(crud.get_activity_workout_steps(activity_id=_ACTIVITY_ID, db=mock_db)) == 1

    def test_empty(self, mock_db):
        import modules.activities.activity_workout_steps.crud as crud

        mock_db.scalars.return_value.all.return_value = []
        assert crud.get_activity_workout_steps(activity_id=_ACTIVITY_ID, db=mock_db) == []


class TestGetActivitiesWorkoutSteps:
    """The batch read no longer joins the parent: it is handed scoped ids."""

    @patch("modules.activities.activity_workout_steps.serializers.to_read_schema")
    def test_success(self, mock_to_read, mock_db):
        import modules.activities.activity_workout_steps.crud as crud
        import modules.activities.activity_workout_steps.models as m

        mock_to_read.return_value = MagicMock()
        mock_db.scalars.return_value.all.return_value = [
            MagicMock(spec=m.ActivityWorkoutSteps, id=uuid.uuid4(), activity_id=_ACTIVITY_ID)
        ]

        assert len(crud.get_activities_workout_steps(activity_ids=[_ACTIVITY_ID], db=mock_db)) == 1

    def test_empty_ids_short_circuits(self, mock_db):
        import modules.activities.activity_workout_steps.crud as crud

        assert crud.get_activities_workout_steps(activity_ids=[], db=mock_db) == []
        mock_db.scalars.assert_not_called()

    def test_no_rows(self, mock_db):
        import modules.activities.activity_workout_steps.crud as crud

        mock_db.scalars.return_value.all.return_value = []

        assert crud.get_activities_workout_steps(activity_ids=[_ACTIVITY_ID], db=mock_db) == []


def _ids(*numbers):
    return [uuid.UUID(int=n) for n in numbers]


class TestOrdering:
    """Rows come back by their natural key; the id only breaks a tie."""

    def _row(self, row_id, key):
        import modules.activities.activity_workout_steps.models as m

        return m.ActivityWorkoutSteps(id=row_id, activity_id=_ACTIVITY_ID, message_index=key, duration_type="time")

    def _read(self, rows, **page):
        from tests._helpers.db import create_sqlite_session

        import modules.activities.activity_workout_steps.crud as crud

        db = create_sqlite_session()
        try:
            for row in rows:
                db.add(row)
            db.commit()
            return [(r.message_index, r.id) for r in crud.get_activity_workout_steps(_ACTIVITY_ID, db, **page)]
        finally:
            db.close()

    def test_rows_inserted_out_of_order_come_back_by_message_index(self):
        a, b, c = _ids(3, 1, 2)
        rows = [self._row(a, 2), self._row(b, 0), self._row(c, 1)]

        assert [row_id for _, row_id in self._read(rows)] == [b, c, a]

    def test_a_tie_breaks_by_id(self):
        high, low = _ids(9, 4)
        rows = [self._row(high, 0), self._row(low, 0)]

        assert [row_id for _, row_id in self._read(rows)] == [low, high]

    def test_paging_follows_the_same_order(self):
        a, b, c = _ids(3, 1, 2)
        rows = [self._row(a, 2), self._row(b, 0), self._row(c, 1)]

        assert [row_id for _, row_id in self._read(rows, page_number=2, num_records=2)] == [a]
