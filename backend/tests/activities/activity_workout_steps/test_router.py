from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


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
    app.dependency_overrides[auth_deps.get_sub_from_access_token] = _uid
    app.dependency_overrides[core_db.get_db] = lambda: mock_db
    return app


class TestReadWorkoutSteps:
    @patch(
        "modules.activities.activity_workout_steps.router.activity_workout_steps_service.list_activity_workout_steps"
    )
    def test_read_steps_success(self, mock_get, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_get.return_value = []

        response = client.get("/activities/1/workout-steps", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200
