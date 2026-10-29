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
        "modules.activities.activity_exercise_titles.public_router.activity_exercise_titles_service.list_public_activity_exercise_titles"
    )
    def test_success(self, mock_get, mock_db):
        from modules.activities.activity_exercise_titles.schema import (
            ActivityExerciseTitlesPage,
            ActivityExerciseTitlesRead,
        )

        client = TestClient(_build_app(mock_db))
        mock_get.return_value = ActivityExerciseTitlesPage.build(
            [ActivityExerciseTitlesRead(id=1, exercise_category=1, exercise_name=1, wkt_step_name="Run")], 1, 1, 25
        )

        response = client.get("/public/activity_exercise_titles")
        assert response.status_code == 200
        assert response.json()["total"] == 1

    @patch(
        "modules.activities.activity_exercise_titles.public_router.activity_exercise_titles_service.list_public_activity_exercise_titles"
    )
    def test_not_found(self, mock_get, mock_db):
        from modules.activities.activity_exercise_titles.schema import ActivityExerciseTitlesPage

        client = TestClient(_build_app(mock_db))
        mock_get.return_value = ActivityExerciseTitlesPage.build([], 0, 1, 25)

        response = client.get("/public/activity_exercise_titles")
        assert response.status_code == 200
        assert response.json()["items"] == []
