from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.activities.activity_workout_steps.schema import ActivityWorkoutStepsPage


def _build_app(mock_db):
    import core.database as core_db
    import modules.activities.activity_workout_steps.router as router
    import modules.auth.dependencies as auth_deps

    app = FastAPI()
    app.include_router(router.router, prefix="/activities/{activity_id}")

    def _mock():
        return None

    def _uid():
        return 1

    app.dependency_overrides[auth_deps.check_scopes] = _mock
    app.dependency_overrides[auth_deps.get_current_user_id] = _uid
    app.dependency_overrides[core_db.get_db] = lambda: mock_db
    return app


class TestReadWorkoutSteps:
    @patch(
        "modules.activities.activity_workout_steps.router.activity_workout_steps_service.list_activity_workout_steps"
    )
    def test_read_steps_success(self, mock_get, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_get.return_value = ActivityWorkoutStepsPage.build([], 0, 1, 200)

        response = client.get(
            "/activities/00000000-0000-4000-8000-000000000001/workout-steps", headers={"Authorization": "Bearer x"}
        )
        assert response.status_code == 200

    def test_a_malformed_activity_id_answers_422(self, mock_db):
        client = TestClient(_build_app(mock_db))

        response = client.get("/activities/not-a-uuid/workout-steps", headers={"Authorization": "Bearer x"})
        assert response.status_code == 422
