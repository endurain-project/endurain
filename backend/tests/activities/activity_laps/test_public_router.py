from datetime import datetime
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _build_app(mock_db):
    import core.database as core_db
    import modules.activities.activity_laps.public_router as router

    app = FastAPI()
    app.include_router(router.router, prefix="/public/activities/{activity_id}")
    app.dependency_overrides[core_db.get_db] = lambda: mock_db
    return app


class TestReadPublicActivityLaps:
    @patch("modules.activities.activity_laps.public_router.activity_laps_crud.get_public_activity_laps")
    def test_success(self, mock_get, mock_db):
        from modules.activities.activity_laps.schema import ActivityLapsRead

        client = TestClient(_build_app(mock_db))
        mock_get.return_value = [ActivityLapsRead(id=1, activity_id=1, start_time=datetime(2024, 1, 15, 8, 0, 0))]

        response = client.get("/public/activities/1/laps")
        assert response.status_code == 200

    @patch("modules.activities.activity_laps.public_router.activity_laps_crud.get_public_activity_laps")
    def test_not_found(self, mock_get, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_get.return_value = []

        response = client.get("/public/activities/999/laps")
        assert response.status_code == 200
        assert response.json() == []
