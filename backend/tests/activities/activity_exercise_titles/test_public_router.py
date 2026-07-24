from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _build_app(mock_db):
    import core.database as core_db
    import modules.activities.activity_exercise_titles.public_router as router

    app = FastAPI()
    app.include_router(router.router, prefix="/public/activity_exercise_titles")
    app.dependency_overrides[core_db.get_db] = lambda: mock_db
    return app


class TestReadPublicExerciseTitles:
    @patch(
        "modules.activities.activity_exercise_titles.public_router.activity_exercise_titles_crud.get_public_activity_exercise_titles"
    )
    def test_success(self, mock_get, mock_db):
        from modules.activities.activity_exercise_titles.schema import ActivityExerciseTitles

        client = TestClient(_build_app(mock_db))
        mock_get.return_value = [
            ActivityExerciseTitles(id=1, exercise_category=1, exercise_name=1, wkt_step_name="Run")
        ]

        response = client.get("/public/activity_exercise_titles/all")
        assert response.status_code == 200

    @patch(
        "modules.activities.activity_exercise_titles.public_router.activity_exercise_titles_crud.get_public_activity_exercise_titles"
    )
    def test_not_found(self, mock_get, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_get.return_value = None

        response = client.get("/public/activity_exercise_titles/all")
        assert response.status_code == 200
        assert response.json() is None
