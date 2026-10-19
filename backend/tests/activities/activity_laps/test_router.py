from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.activities.activity_laps.schema import ActivityLapsPage


def _build_app(mock_db):
    import core.database as core_db
    import modules.activities.activity_laps.router as router
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


class TestReadActivityLaps:
    @patch("modules.activities.activity_laps.router.activity_laps_service.list_activity_laps")
    def test_read_laps_success(self, mock_get, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_get.return_value = ActivityLapsPage.build([], 0, 1, 200)

        response = client.get("/activities/1/laps", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200

    @patch("modules.activities.activity_laps.router.activity_laps_service.list_activity_laps")
    def test_read_laps_not_found(self, mock_get, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_get.return_value = ActivityLapsPage.build([], 0, 1, 200)

        response = client.get("/activities/999/laps", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200
        assert response.json()["items"] == [] and response.json()["total"] == 0
