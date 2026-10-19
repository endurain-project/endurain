from tests._helpers.db import setup_mock_execute
from tests._helpers.models import mock_model


class TestGetExerciseTitles:
    def test_get_all(self, mock_db):
        import modules.activities.activity_exercise_titles.crud as crud
        import modules.activities.activity_exercise_titles.models as m

        setup_mock_execute(
            mock_db,
            return_scalars_all=[
                mock_model(m.ActivityExerciseTitles, id=1, exercise_category=1, exercise_name=1, wkt_step_name="Run")
            ],
        )
        r = crud.get_activity_exercise_titles(db=mock_db)
        assert len(r) == 1


class TestGetAllExerciseTitles:
    def test_get_all_empty(self, mock_db):
        import modules.activities.activity_exercise_titles.crud as crud

        setup_mock_execute(mock_db, return_scalars_all=[])
        r = crud.get_activity_exercise_titles(db=mock_db)
        assert r == []


class TestCreateExerciseTitle:
    @staticmethod
    def _sql(db):
        from sqlalchemy.dialects import postgresql

        statement = db.execute.call_args.args[0]
        return str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))

    def test_empty_input(self, mock_db):
        import modules.activities.activity_exercise_titles.crud as crud

        crud.create_activity_exercise_titles([], mock_db)
        mock_db.execute.assert_not_called()

    def test_skips_existing_pairs_in_the_database(self, mock_db):
        """Repeats in the batch and rows from a concurrent import are skipped, not raised."""
        import modules.activities.activity_exercise_titles.crud as crud
        from modules.activities.activity_exercise_titles.contracts import ActivityExerciseTitlesCreate

        titles = [
            ActivityExerciseTitlesCreate(exercise_category=1, exercise_name=42, wkt_step_name="Sprint"),
            ActivityExerciseTitlesCreate(exercise_category=1, exercise_name=42, wkt_step_name="Sprint"),
        ]
        crud.create_activity_exercise_titles(titles, mock_db)

        sql = self._sql(mock_db)
        assert "INSERT INTO activity_exercise_titles" in sql
        assert "ON CONFLICT ON CONSTRAINT uq_activity_exercise_titles_category_name DO NOTHING" in sql
        assert sql.count("'Sprint'") == 2
        mock_db.commit.assert_not_called()
