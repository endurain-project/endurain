from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _build_app(mock_db):
    import core.database as core_db
    import modules.activities.activity.public_router as router

    app = FastAPI()
    app.include_router(router.router, prefix="/public/activities")
    app.dependency_overrides[core_db.get_db] = lambda: mock_db
    return app


def _valid_activity(**kw):
    from modules.activities.activity.schema import Activity

    data = dict(
        distance=10000,
        name="Test",
        activity_type=1,
        start_time="2024-01-15T08:00:00Z",
        end_time="2024-01-15T09:00:00Z",
        timezone="UTC",
        total_elapsed_time=3600.0,
        total_timer_time=3600.0,
        calories=500,
        visibility=0,
        elevation_gain=50,
        elevation_loss=45,
        pace=300.0,
        average_hr=145,
        max_hr=175,
        average_speed=2.78,
        max_speed=5.0,
        city="City",
        town="Town",
        country="Country",
        description="desc",
        gear_id=1,
        id=1,
        user_id=1,
    )
    data.update(kw)
    return Activity(**data)


class TestReadPublicActivity:
    @patch("modules.activities.activity.public_router.activities_crud.get_activity_by_id_if_is_public")
    def test_success(self, mock_get, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_get.return_value = _valid_activity()

        response = client.get("/public/activities/1")
        assert response.status_code == 200
        assert response.json()["id"] == 1

    @patch("modules.activities.activity.public_router.activities_crud.get_activity_by_id_if_is_public")
    def test_not_found(self, mock_get, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_get.return_value = None

        response = client.get("/public/activities/999")
        assert response.status_code == 200
        assert response.json() is None
