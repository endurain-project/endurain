import uuid
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.activities.activity_workout_steps.schema import ActivityWorkoutStepsPage


def _build_app(mock_db):
    import core.database as core_db
    import modules.activities.activity_workout_steps.public_router as router

    app = FastAPI()
    app.include_router(router.router, prefix="/public/activities/{activity_id}")
    app.dependency_overrides[core_db.get_db] = lambda: mock_db
    return app


class TestReadPublicWorkoutSteps:
    @patch(
        "modules.activities.activity_workout_steps.public_router.activity_workout_steps_service.list_public_activity_workout_steps"
    )
    def test_success(self, mock_get, mock_db):
        from modules.activities.activity_workout_steps.schema import ActivityWorkoutStepsRead

        client = TestClient(_build_app(mock_db))
        mock_get.return_value = ActivityWorkoutStepsPage.build(
            [
                ActivityWorkoutStepsRead(
                    id=uuid.uuid4(), activity_id=uuid.uuid4(), message_index=0, duration_type="active"
                )
            ],
            1,
            1,
            200,
        )

        response = client.get("/public/activities/00000000-0000-4000-8000-000000000001/workout-steps")
        assert response.status_code == 200

    @patch(
        "modules.activities.activity_workout_steps.public_router.activity_workout_steps_service.list_public_activity_workout_steps"
    )
    def test_not_found(self, mock_get, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_get.return_value = ActivityWorkoutStepsPage.build([], 0, 1, 200)

        response = client.get("/public/activities/00000000-0000-4000-8000-000000000999/workout-steps")
        assert response.status_code == 200
        assert response.json()["items"] == [] and response.json()["total"] == 0

    def test_a_malformed_activity_id_answers_422(self, mock_db):
        client = TestClient(_build_app(mock_db))

        response = client.get("/public/activities/not-a-uuid/workout-steps")
        assert response.status_code == 422
