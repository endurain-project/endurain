from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _build_app(mock_db):
    import core.database as core_db
    import core.exceptions as core_exceptions
    import modules.activities.activity_streams.public_router as router

    app = FastAPI()
    app.include_router(router.router, prefix="/public/activities/{activity_id}")
    # Same domain-error boundary the real app registers, so these tests assert
    # the status codes clients actually receive.
    core_exceptions.register_exception_handlers(app)
    app.dependency_overrides[core_db.get_db] = lambda: mock_db
    return app


class TestReadPublicActivityStreams:
    @patch("modules.activities.activity_streams.public_router.activity_streams_service.list_public_activity_streams")
    def test_all_success(self, mock_get, mock_db):
        from modules.activities.activity_streams.schema import ActivityStreamsPage, ActivityStreamsRead

        client = TestClient(_build_app(mock_db))
        stream = ActivityStreamsRead(id=1, activity_id=1, stream_type=1, stream_waypoints=[{"x": 1}])
        mock_get.return_value = ActivityStreamsPage.build([stream], 1, 1, 200)

        response = client.get("/public/activities/1/streams")
        assert response.status_code == 200
        assert response.json()["total"] == 1

    @patch("modules.activities.activity_streams.public_router.activity_streams_service.list_public_activity_streams")
    def test_all_not_found(self, mock_get, mock_db):
        from modules.activities.activity_streams.schema import ActivityStreamsPage

        client = TestClient(_build_app(mock_db))
        # Not-found is an empty page, never None: the refusal and the empty
        # collection answer alike so the endpoint cannot be used to probe which
        # activities exist.
        mock_get.return_value = ActivityStreamsPage.build([], 0, 1, 200)

        response = client.get("/public/activities/999/streams")
        assert response.status_code == 200
        assert response.json() == {"items": [], "total": 0, "page": 1, "num_records": 200, "next": None}

    @patch("modules.activities.activity_streams.public_router.activity_streams_service.get_public_activity_stream")
    def test_by_type_success(self, mock_get, mock_db):
        from modules.activities.activity_streams.schema import ActivityStreamsRead

        client = TestClient(_build_app(mock_db))
        mock_get.return_value = ActivityStreamsRead(id=1, activity_id=1, stream_type=1, stream_waypoints=[{"x": 1}])

        response = client.get("/public/activities/1/streams/1")
        assert response.status_code == 200

    @patch("modules.activities.activity_streams.public_router.activity_streams_service.get_public_activity_stream")
    def test_by_type_not_found(self, mock_get, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_get.return_value = None

        response = client.get("/public/activities/999/streams/1")
        # Missing, not public, and public-links-disabled are one answer: this
        # endpoint is unauthenticated, so distinguishing them would let anyone
        # enumerate activity ids.
        assert response.status_code == 404
        assert response.json()["detail"] == "Activity stream not found"
