from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _build_app(mock_db, with_media=None):
    import activities.activity_media.router as router
    import auth.dependencies as auth_deps
    import core.database as core_db

    app = FastAPI()
    app.include_router(router.router, prefix="/activities_media")

    def _mock():
        return None

    def _uid():
        return 1

    app.dependency_overrides[auth_deps.check_scopes] = _mock
    app.dependency_overrides[auth_deps.get_sub_from_access_token] = _uid
    app.dependency_overrides[core_db.get_db] = lambda: mock_db
    return app


class TestReadActivityMedia:
    @patch("activities.activity_media.router.activity_media_crud.get_activity_media")
    def test_read_media_success(self, mock_get, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_get.return_value = []

        response = client.get("/activities_media/activity_id/1", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200

    @patch("activities.activity_media.router.activity_media_crud.get_activity_media")
    def test_read_media_not_found(self, mock_get, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_get.return_value = None

        response = client.get("/activities_media/activity_id/999", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200
        assert response.json() is None


class TestUploadActivityMedia:
    @patch("activities.activity_media.router.activity_crud.get_activity_by_id_from_user_id")
    @patch("activities.activity_media.router.activity_media_crud.create_activity_media")
    @patch("activities.activity_media.router.core_file_uploads.save_validated_upload")
    def test_upload_rejects_activity_owned_by_another_user(self, mock_save, mock_create, mock_get_activity, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_get_activity.return_value = None

        response = client.post(
            "/activities_media/upload/activity_id/2",
            files={"file": ("test.jpg", b"fake-image-data", "image/jpeg")},
            headers={"Authorization": "Bearer x"},
        )

        assert response.status_code == 404
        mock_save.assert_not_called()
        mock_create.assert_not_called()

    @patch("activities.activity_media.router.activity_crud.get_activity_by_id_from_user_id")
    @patch("activities.activity_media.router.activity_media_crud.create_activity_media")
    @patch("activities.activity_media.router.core_file_uploads.save_validated_upload")
    def test_upload_success(self, mock_save, mock_create, mock_get_activity, mock_db):
        from activities.activity_media.schema import ActivityMedia

        client = TestClient(_build_app(mock_db))
        mock_get_activity.return_value = object()
        mock_save.return_value = "test.jpg"
        mock_create.return_value = ActivityMedia(id=1, activity_id=1, media_path="test.jpg", media_type=1)

        response = client.post(
            "/activities_media/upload/activity_id/1",
            files={"file": ("test.jpg", b"fake-image-data", "image/jpeg")},
            headers={"Authorization": "Bearer x"},
        )
        assert response.status_code == 201
        assert response.json()["id"] == 1

    @patch("activities.activity_media.router.activity_crud.get_activity_by_id_from_user_id")
    @patch("activities.activity_media.router.activity_media_crud.create_activity_media")
    @patch("activities.activity_media.router.core_file_uploads.save_validated_upload")
    def test_upload_and_cleanup_on_failure(self, mock_save, mock_create, mock_get_activity, mock_db):
        from fastapi import HTTPException

        client = TestClient(_build_app(mock_db))
        mock_get_activity.return_value = object()
        mock_save.return_value = "test.jpg"
        mock_create.side_effect = HTTPException(status_code=409, detail="Conflict")

        with patch("activities.activity_media.router.core_file_uploads.delete_files_by_pattern") as mock_cleanup:
            response = client.post(
                "/activities_media/upload/activity_id/1",
                files={"file": ("test.jpg", b"fake-image-data", "image/jpeg")},
                headers={"Authorization": "Bearer x"},
            )
            assert response.status_code == 409
            mock_cleanup.assert_called_once()


class TestDeleteActivityMedia:
    @patch("activities.activity_media.router.activity_media_crud.delete_activity_media")
    def test_delete_success(self, mock_delete, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_delete.return_value = None

        response = client.delete("/activities_media/1", headers={"Authorization": "Bearer x"})
        assert response.status_code == 204
