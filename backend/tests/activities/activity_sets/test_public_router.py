from datetime import datetime
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _build_app(mock_db):
    import core.database as core_db
    import modules.activities.activity_sets.public_router as router

    app = FastAPI()
    app.include_router(router.router, prefix="/public/activities_sets")
    app.dependency_overrides[core_db.get_db] = lambda: mock_db
    return app


class TestReadPublicActivitySets:
    @patch("modules.activities.activity_sets.public_router.activity_sets_crud.get_public_activity_sets")
    def test_success(self, mock_get, mock_db):
        from modules.activities.activity_sets.schema import ActivitySetsRead

        client = TestClient(_build_app(mock_db))
        mock_get.return_value = [
            ActivitySetsRead(
                id=1, activity_id=1, duration=300.0, set_type="active", start_time=datetime(2024, 1, 15, 8, 0, 0)
            )
        ]

        response = client.get("/public/activities_sets/activity_id/1/all")
        assert response.status_code == 200

    @patch("modules.activities.activity_sets.public_router.activity_sets_crud.get_public_activity_sets")
    def test_not_found(self, mock_get, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_get.return_value = None

        response = client.get("/public/activities_sets/activity_id/999/all")
        assert response.status_code == 200
        assert response.json() is None
