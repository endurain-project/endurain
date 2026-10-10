from datetime import datetime
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.activities.activity_sets.schema import ActivitySetsPage


def _build_app(mock_db):
    import core.database as core_db
    import modules.activities.activity_sets.public_router as router

    app = FastAPI()
    app.include_router(router.router, prefix="/public/activities/{activity_id}")
    app.dependency_overrides[core_db.get_db] = lambda: mock_db
    return app


class TestReadPublicActivitySets:
    @patch("modules.activities.activity_sets.public_router.activity_sets_service.list_public_activity_sets")
    def test_success(self, mock_get, mock_db):
        from modules.activities.activity_sets.schema import ActivitySetsRead

        client = TestClient(_build_app(mock_db))
        mock_get.return_value = ActivitySetsPage.build(
            [
                ActivitySetsRead(
                    id=1, activity_id=1, duration=300.0, set_type="active", start_time=datetime(2024, 1, 15, 8, 0, 0)
                )
            ],
            1,
            1,
            200,
        )

        response = client.get("/public/activities/1/sets")
        assert response.status_code == 200

    @patch("modules.activities.activity_sets.public_router.activity_sets_service.list_public_activity_sets")
    def test_not_found(self, mock_get, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_get.return_value = ActivitySetsPage.build([], 0, 1, 200)

        response = client.get("/public/activities/999/sets")
        assert response.status_code == 200
        assert response.json()["items"] == [] and response.json()["total"] == 0
