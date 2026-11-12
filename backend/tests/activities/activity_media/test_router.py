import uuid
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

ACT = "00000000-0000-4000-8000-000000000001"
OTHER = "00000000-0000-4000-8000-000000000999"
MEDIA = "00000000-0000-4000-8000-0000000000a1"


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
    app.dependency_overrides[auth_deps.get_current_user_id] = _uid
    app.dependency_overrides[core_db.get_db] = lambda: mock_db
    return app


class TestReadActivityMedia:
    @patch("modules.activities.activity_media.router.activity_media_service.list_activity_media")
    def test_read_media_success(self, mock_list, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_list.return_value = {"items": [], "total": 0, "page": 1, "num_records": 200, "next": None}

        response = client.get(f"/activities/{ACT}/media", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200
        mock_list.assert_called_once()

    @patch("modules.activities.activity_media.router.activity_media_service.list_activity_media")
    def test_read_media_not_found(self, mock_list, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_list.return_value = {"items": [], "total": 0, "page": 1, "num_records": 200, "next": None}

        # A collection endpoint answers with the page envelope: no media (or an
        # activity the caller cannot see) is an empty page, not ``null``.
        response = client.get(f"/activities/{OTHER}/media", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200
        assert response.json()["items"] == []


class TestUploadActivityMedia:
    @patch("modules.activities.activity_media.router.core_file_uploads")
    @patch("modules.activities.activity_media.router.activity_media_service.store_activity_media")
    def test_upload_propagates_service_rejection(self, mock_store, mock_uploads, mock_db):
        from fastapi import HTTPException

        client = TestClient(_build_app(mock_db))
        mock_store.side_effect = HTTPException(status_code=404, detail="Activity not found")

        response = client.post(
            f"/activities/{OTHER}/media",
            files={"file": ("test.jpg", b"fake-image-data", "image/jpeg")},
            headers={"Authorization": "Bearer x"},
        )

        assert response.status_code == 404

    @patch("modules.activities.activity_media.router.core_file_uploads")
    @patch("modules.activities.activity_media.router.activity_media_service.store_activity_media")
    def test_upload_success(self, mock_store, mock_uploads, mock_db):
        from modules.activities.activity_media.schema import ActivityMediaRead

        client = TestClient(_build_app(mock_db))
        mock_store.return_value = ActivityMediaRead(
            id=uuid.UUID(MEDIA),
            activity_id=uuid.UUID(ACT),
            media_type=1,
            url=f"/api/v1/activities/{ACT}/media/{MEDIA}/file?t=tok",
        )

        response = client.post(
            f"/activities/{ACT}/media",
            files={"file": ("test.jpg", b"fake-image-data", "image/jpeg")},
            headers={"Authorization": "Bearer x"},
        )
        assert response.status_code == 201
        assert response.json()["id"] == MEDIA
        # The opaque storage key is not part of the API contract.
        assert "media_path" not in response.json()
        # The route passes the path activity id and the token user through unchanged.
        assert mock_store.call_args.args[0] == uuid.UUID(ACT)
        assert mock_store.call_args.args[1] == 1


class TestDeleteActivityMedia:
    @patch("modules.activities.activity_media.router.activity_media_service.delete_activity_media")
    def test_delete_success(self, mock_delete, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_delete.return_value = None

        response = client.delete(f"/activities/{ACT}/media/{MEDIA}", headers={"Authorization": "Bearer x"})
        assert response.status_code == 204


class TestMalformedIds:
    def test_a_malformed_activity_id_is_unprocessable(self, mock_db):
        client = TestClient(_build_app(mock_db))

        assert client.get("/activities/1/media", headers={"Authorization": "Bearer x"}).status_code == 422

    def test_a_malformed_media_id_is_unprocessable(self, mock_db):
        client = TestClient(_build_app(mock_db))

        response = client.delete(f"/activities/{ACT}/media/5", headers={"Authorization": "Bearer x"})

        assert response.status_code == 422
