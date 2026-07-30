from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _build_app(mock_db):
    import core.database as core_db
    import modules.activities.activity_workout_steps.public_router as router

    app = FastAPI()
    app.include_router(router.router, prefix="/public/activities/{activity_id}")
    app.dependency_overrides[core_db.get_db] = lambda: mock_db
    return app


class TestReadPublicWorkoutSteps:
    @patch(
        "modules.activities.activity_workout_steps.public_router.activity_workout_steps_crud.get_public_activity_workout_steps"
    )
    def test_success(self, mock_get, mock_db):
        from modules.activities.activity_workout_steps.schema import ActivityWorkoutSteps

        client = TestClient(_build_app(mock_db))
        mock_get.return_value = [ActivityWorkoutSteps(id=1, activity_id=1, message_index=0, duration_type="active")]

        response = client.get("/public/activities/1/workout-steps")
        assert response.status_code == 200

    @patch(
        "modules.activities.activity_workout_steps.public_router.activity_workout_steps_crud.get_public_activity_workout_steps"
    )
    def test_not_found(self, mock_get, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_get.return_value = []

        response = client.get("/public/activities/999/workout-steps")
        assert response.status_code == 200
        assert response.json() == []
