import uuid
from datetime import datetime
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.activities.activity_laps.schema import ActivityLapsPage


def _build_app(mock_db):
    import core.database as core_db
    import modules.activities.activity_laps.public_router as router

    app = FastAPI()
    app.include_router(router.router, prefix="/public/activities/{activity_id}")
    app.dependency_overrides[core_db.get_db] = lambda: mock_db
    return app


class TestReadPublicActivityLaps:
    @patch("modules.activities.activity_laps.public_router.activity_laps_service.list_public_activity_laps")
    def test_success(self, mock_get, mock_db):
        from modules.activities.activity_laps.schema import ActivityLapsRead

        client = TestClient(_build_app(mock_db))
        mock_get.return_value = ActivityLapsPage.build(
            [ActivityLapsRead(id=uuid.uuid4(), activity_id=uuid.uuid4(), start_time=datetime(2024, 1, 15, 8, 0, 0))],
            1,
            1,
            200,
        )

        response = client.get("/public/activities/00000000-0000-4000-8000-000000000001/laps")
        assert response.status_code == 200

    @patch("modules.activities.activity_laps.public_router.activity_laps_service.list_public_activity_laps")
    def test_not_found(self, mock_get, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_get.return_value = ActivityLapsPage.build([], 0, 1, 200)

        response = client.get("/public/activities/00000000-0000-4000-8000-000000000999/laps")
        assert response.status_code == 200
        assert response.json()["items"] == [] and response.json()["total"] == 0

    def test_a_malformed_activity_id_answers_422(self, mock_db):
        client = TestClient(_build_app(mock_db))

        response = client.get("/public/activities/not-a-uuid/laps")
        assert response.status_code == 422
