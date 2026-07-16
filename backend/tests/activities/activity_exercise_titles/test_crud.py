from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from tests._helpers.db import setup_mock_execute
from tests._helpers.models import mock_model


class TestGetExerciseTitles:
    def test_get_all(self, mock_db):
        import modules.activities.activity_exercise_titles.crud as crud
        import modules.activities.activity_exercise_titles.models as m

        setup_mock_execute(mock_db, return_scalars_all=[mock_model(m.ActivityExerciseTitles, id=1, title="Run")])
        r = crud.get_activity_exercise_titles(db=mock_db)
        assert len(r) == 1


class TestGetAllExerciseTitles:
    def test_get_all_empty(self, mock_db):
        import modules.activities.activity_exercise_titles.crud as crud

        setup_mock_execute(mock_db, return_scalars_all=[])
        r = crud.get_activity_exercise_titles(db=mock_db)
        assert r is None

    def test_db_error(self, mock_db):
        import modules.activities.activity_exercise_titles.crud as crud

        mock_db.execute.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException):
            crud.get_activity_exercise_titles(db=mock_db)


class TestGetPublicExerciseTitles:
    @patch("modules.activities.activity_exercise_titles.crud.server_settings_utils.get_server_settings_or_404")
    def test_no_public_links(self, mock_settings, mock_db):
        import modules.activities.activity_exercise_titles.crud as crud

        mock_settings.return_value = MagicMock(public_shareable_links=False)
        r = crud.get_public_activity_exercise_titles(db=mock_db)
        assert r is None

    @patch("modules.activities.activity_exercise_titles.crud.server_settings_utils.get_server_settings_or_404")
    def test_success(self, mock_settings, mock_db):
        import modules.activities.activity_exercise_titles.crud as crud
        import modules.activities.activity_exercise_titles.models as m

        mock_settings.return_value = MagicMock(public_shareable_links=True)
        setup_mock_execute(mock_db, return_scalars_all=[mock_model(m.ActivityExerciseTitles, id=1)])
        r = crud.get_public_activity_exercise_titles(db=mock_db)
        assert len(r) == 1

    @patch("modules.activities.activity_exercise_titles.crud.server_settings_utils.get_server_settings_or_404")
    def test_db_error(self, mock_settings, mock_db):
        import modules.activities.activity_exercise_titles.crud as crud

        mock_settings.return_value = MagicMock(public_shareable_links=True)
        mock_db.execute.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException):
            crud.get_public_activity_exercise_titles(db=mock_db)


class TestGetExerciseTitleByExerciseName:
    def test_found(self, mock_db):
        import modules.activities.activity_exercise_titles.crud as crud
        import modules.activities.activity_exercise_titles.models as m

        mock_title = mock_model(m.ActivityExerciseTitles, id=1, exercise_name=42)
        setup_mock_execute(mock_db, return_one_or_none=mock_title)
        r = crud.get_activity_exercise_title_by_exercise_name(42, mock_db)
        assert r is not None
        assert r.id == 1

    def test_not_found(self, mock_db):
        import modules.activities.activity_exercise_titles.crud as crud

        setup_mock_execute(mock_db, return_one_or_none=None)
        r = crud.get_activity_exercise_title_by_exercise_name(99, mock_db)
        assert r is None

    def test_db_error(self, mock_db):
        import modules.activities.activity_exercise_titles.crud as crud

        mock_db.execute.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException):
            crud.get_activity_exercise_title_by_exercise_name(42, mock_db)


class TestCreateExerciseTitle:
    def test_empty_input(self, mock_db):
        import modules.activities.activity_exercise_titles.crud as crud

        crud.create_activity_exercise_titles([], mock_db)
        mock_db.add_all.assert_not_called()

    @patch("modules.activities.activity_exercise_titles.crud.tuple_")
    @patch("modules.activities.activity_exercise_titles.crud.select")
    @patch("modules.activities.activity_exercise_titles.crud.activity_exercise_titles_models.ActivityExerciseTitles")
    def test_all_existing(self, mock_model_cls, mock_select, mock_tuple, mock_db):
        import modules.activities.activity_exercise_titles.crud as crud
        from modules.activities.activity_exercise_titles.schema import ActivityExerciseTitles

        titles = [
            ActivityExerciseTitles(exercise_category=1, exercise_name=1, wkt_step_name="Run"),
        ]
        mock_db.execute.return_value.all.return_value = [(1, 1)]
        crud.create_activity_exercise_titles(titles, mock_db)
        mock_db.add_all.assert_not_called()

    @patch("modules.activities.activity_exercise_titles.crud.tuple_")
    @patch("modules.activities.activity_exercise_titles.crud.select")
    @patch("modules.activities.activity_exercise_titles.crud.activity_exercise_titles_models.ActivityExerciseTitles")
    def test_new_entries(self, mock_model_cls, mock_select, mock_tuple, mock_db):
        import modules.activities.activity_exercise_titles.crud as crud
        from modules.activities.activity_exercise_titles.schema import ActivityExerciseTitles

        titles = [
            ActivityExerciseTitles(exercise_category=1, exercise_name=42, wkt_step_name="Sprint"),
        ]
        mock_db.execute.return_value.all.return_value = []
        mock_instance = MagicMock()
        mock_model_cls.return_value = mock_instance
        crud.create_activity_exercise_titles(titles, mock_db)
        mock_db.add_all.assert_called_once_with([mock_instance])
        mock_db.commit.assert_called_once()

    @patch("modules.activities.activity_exercise_titles.crud.tuple_")
    @patch("modules.activities.activity_exercise_titles.crud.select")
    @patch("modules.activities.activity_exercise_titles.crud.activity_exercise_titles_models.ActivityExerciseTitles")
    def test_integrity_error(self, mock_model_cls, mock_select, mock_tuple, mock_db):
        import modules.activities.activity_exercise_titles.crud as crud
        from modules.activities.activity_exercise_titles.schema import ActivityExerciseTitles

        titles = [
            ActivityExerciseTitles(exercise_category=1, exercise_name=42, wkt_step_name="Sprint"),
        ]
        mock_db.execute.return_value.all.return_value = []
        mock_model_cls.return_value = MagicMock()
        mock_db.commit.side_effect = IntegrityError("stmt", "params", "orig")
        with pytest.raises(HTTPException) as e:
            crud.create_activity_exercise_titles(titles, mock_db)
        assert e.value.status_code == 409
