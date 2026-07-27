from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _build_app(mock_db, with_media=None):
    import core.database as core_db
    import modules.activities.activity_media.router as router
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


class TestReadActivityMedia:
    @patch("modules.activities.activity_media.router.activity_media_service.list_activity_media")
    def test_read_media_success(self, mock_list, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_list.return_value = []

        response = client.get("/activities/1/media", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200
        mock_list.assert_called_once()

    @patch("modules.activities.activity_media.router.activity_media_service.list_activity_media")
    def test_read_media_not_found(self, mock_list, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_list.return_value = None

        response = client.get("/activities/999/media", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200
        assert response.json() is None


class TestUploadActivityMedia:
    @patch("modules.activities.activity_media.router.activity_media_service.store_activity_media")
    def test_upload_propagates_service_rejection(self, mock_store, mock_db):
        from fastapi import HTTPException

        client = TestClient(_build_app(mock_db))
        mock_store.side_effect = HTTPException(status_code=404, detail="Activity not found")

        response = client.post(
            "/activities/2/media",
            files={"file": ("test.jpg", b"fake-image-data", "image/jpeg")},
            headers={"Authorization": "Bearer x"},
        )

        assert response.status_code == 404

    @patch("modules.activities.activity_media.router.activity_media_service.store_activity_media")
    def test_upload_success(self, mock_store, mock_db):
        from modules.activities.activity_media.schema import ActivityMedia

        client = TestClient(_build_app(mock_db))
        mock_store.return_value = ActivityMedia(id=1, activity_id=1, media_path="test.jpg", media_type=1)

        response = client.post(
            "/activities/1/media",
            files={"file": ("test.jpg", b"fake-image-data", "image/jpeg")},
            headers={"Authorization": "Bearer x"},
        )
        assert response.status_code == 201
        assert response.json()["id"] == 1
        # The route passes the path activity id and the token user through unchanged.
        assert mock_store.call_args.args[0] == 1
        assert mock_store.call_args.args[1] == 1


class TestDeleteActivityMedia:
    @patch("modules.activities.activity_media.router.activity_media_service.delete_activity_media")
    def test_delete_success(self, mock_delete, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_delete.return_value = None

        response = client.delete("/activities/1/media/1", headers={"Authorization": "Bearer x"})
        assert response.status_code == 204
