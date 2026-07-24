from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _build_app(mock_db):
    import core.database as core_db
    import modules.activities.activity_streams.public_router as router

    app = FastAPI()
    app.include_router(router.router, prefix="/public/activities_streams")
    app.dependency_overrides[core_db.get_db] = lambda: mock_db
    return app


class TestReadPublicActivityStreams:
    @patch("modules.activities.activity_streams.public_router.activity_streams_crud.get_public_activity_streams")
    def test_all_success(self, mock_get, mock_db):
        from modules.activities.activity_streams.schema import ActivityStreamsRead

        client = TestClient(_build_app(mock_db))
        mock_get.return_value = [ActivityStreamsRead(id=1, activity_id=1, stream_type=1, stream_waypoints=[{"x": 1}])]

        response = client.get("/public/activities_streams/activity_id/1/all")
        assert response.status_code == 200

    @patch("modules.activities.activity_streams.public_router.activity_streams_crud.get_public_activity_streams")
    def test_all_not_found(self, mock_get, mock_db):
        client = TestClient(_build_app(mock_db))
        # The "all" endpoint returns a list; not-found is an empty list, never None
        # (the response_model is list[...], so None would fail response validation).
        mock_get.return_value = []

        response = client.get("/public/activities_streams/activity_id/999/all")
        assert response.status_code == 200
        assert response.json() == []

    @patch("modules.activities.activity_streams.public_router.activity_streams_crud.get_public_activity_stream_by_type")
    def test_by_type_success(self, mock_get, mock_db):
        from modules.activities.activity_streams.schema import ActivityStreamsRead

        client = TestClient(_build_app(mock_db))
        mock_get.return_value = ActivityStreamsRead(id=1, activity_id=1, stream_type=1, stream_waypoints=[{"x": 1}])

        response = client.get("/public/activities_streams/activity_id/1/stream_type/1")
        assert response.status_code == 200

    @patch("modules.activities.activity_streams.public_router.activity_streams_crud.get_public_activity_stream_by_type")
    def test_by_type_not_found(self, mock_get, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_get.return_value = None

        response = client.get("/public/activities_streams/activity_id/999/stream_type/1")
        assert response.status_code == 200
        assert response.json() is None
