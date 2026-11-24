"""The login page photo: admin upload and removal, and the public route that serves it, on the real application."""

import jasil.providers as platform_providers
import jasil.runtime as jasil_runtime
import pytest
import sqlalchemy as sa
from jasil.audit.models import AuditLog

import core.exceptions as core_exceptions
import modules.server_settings.constants as server_settings_constants
import modules.server_settings.crud as server_settings_crud
import modules.server_settings.login_photo_service as server_settings_login_photo_service
from tests._helpers import images
from tests.server_settings.conftest import API

_ADMIN_URL = f"{API}/server-settings/login-photo"
_PUBLIC_URL = f"{API}/public/server-settings/login-photo"
_AREA = server_settings_constants.LOGIN_PHOTO_STORAGE_AREA
_KEY = server_settings_constants.LOGIN_PHOTO_STORAGE_KEY


def _upload(client, data: bytes, name: str = "login.png", media_type: str = "image/png"):
    return client.put(_ADMIN_URL, files={"file": (name, data, media_type)})


def _stored_blob() -> bytes | None:
    return jasil_runtime.get_active_platform().storage.get(_AREA, _KEY)


def _audit_rows(committed_sessions, action_id: str) -> list[AuditLog]:
    with committed_sessions() as db:
        rows = list(db.scalars(sa.select(AuditLog).where(AuditLog.action_id == action_id)))
        db.expunge_all()
    return rows


def _settings(committed_sessions):
    with committed_sessions() as db:
        stored = server_settings_crud.get_server_settings(db)
    assert stored is not None
    return stored


class TestUploadLoginPhoto:
    def test_the_first_photo_is_a_201_naming_the_version_that_identifies_it(self, admin_client, committed_sessions):
        response = _upload(admin_client, images.png_with_text())

        assert response.status_code == 201
        assert response.json() == {"version": 2}
        stored = _settings(committed_sessions)
        assert (stored.login_photo_set, stored.version) == (True, 2)
        assert _stored_blob() is not None

    def test_a_replacement_is_a_200_with_a_new_version(self, admin_client):
        _upload(admin_client, images.png_with_text())

        response = _upload(admin_client, images.png_with_text(size=(16, 16)))

        assert response.status_code == 200
        assert response.json() == {"version": 3}

    def test_the_stored_photo_has_no_metadata(self, admin_client):
        response = _upload(admin_client, images.jpeg_with_exif(), "photo.jpg", "image/jpeg")

        assert response.status_code == 201
        data = _stored_blob()
        assert data is not None
        assert not images.has_metadata(data)

    def test_a_webp_is_stored_without_its_metadata_and_served_as_a_webp(self, admin_client, client):
        _upload(admin_client, images.webp_with_exif(), "photo.webp", "image/webp")

        data = _stored_blob()
        assert data is not None
        assert not images.has_metadata(data)
        assert client.get(_PUBLIC_URL).headers["content-type"] == "image/webp"

    def test_an_upload_is_audited_without_a_file_name(self, admin_client, committed_sessions):
        _upload(admin_client, images.png_with_text(), "private-name.png")

        (row,) = _audit_rows(committed_sessions, "server_settings.login_photo.update")
        assert row.details is None
        assert "private-name" not in str([getattr(row, column.name) for column in AuditLog.__table__.columns])

    def test_bytes_that_are_not_an_image_are_a_415_and_change_nothing(self, admin_client, committed_sessions):
        response = _upload(admin_client, b"png")

        assert response.status_code == 415
        assert _settings(committed_sessions).version == 1
        assert _stored_blob() is None
        assert _audit_rows(committed_sessions, "server_settings.login_photo.update") == []

    @pytest.mark.parametrize(
        ("data", "name", "media_type"),
        [(images.gif(), "login.gif", "image/gif"), (images.heic_like(), "login.heic", "image/heic")],
        ids=["gif", "heic"],
    )
    def test_gif_and_heic_are_refused(self, admin_client, committed_sessions, data, name, media_type):
        response = _upload(admin_client, data, name, media_type)

        assert response.status_code == 415
        assert _stored_blob() is None
        assert _settings(committed_sessions).login_photo_set is False

    def test_a_photo_over_the_cap_is_a_413(self, admin_client, committed_sessions):
        response = _upload(
            admin_client, images.png_with_text() + b"\0" * server_settings_constants.LOGIN_PHOTO_MAX_BYTES
        )

        assert response.status_code == 413
        assert _settings(committed_sessions).login_photo_set is False


class TestDeleteLoginPhoto:
    def test_removing_the_photo_clears_the_flag_and_the_blob(self, admin_client, committed_sessions):
        _upload(admin_client, images.png_with_text())

        response = admin_client.delete(_ADMIN_URL)

        assert response.status_code == 204
        stored = _settings(committed_sessions)
        assert (stored.login_photo_set, stored.version) == (False, 3)
        assert _stored_blob() is None

    def test_a_removal_is_audited(self, admin_client, committed_sessions):
        _upload(admin_client, images.png_with_text())

        admin_client.delete(_ADMIN_URL)

        (row,) = _audit_rows(committed_sessions, "server_settings.login_photo.delete")
        assert row.details is None

    def test_removing_when_there_is_no_photo_is_still_a_204(self, admin_client, committed_sessions):
        response = admin_client.delete(_ADMIN_URL)

        assert response.status_code == 204
        assert _settings(committed_sessions).login_photo_set is False

    def test_a_blob_that_cannot_be_deleted_does_not_fail_the_removal_and_the_photo_stops_being_served(
        self, admin_client, client, committed_sessions, monkeypatch
    ):
        _upload(admin_client, images.png_with_text())

        def unavailable(_area: str, _key: str) -> None:
            raise platform_providers.StorageBackendUnavailableError("storage is down")

        monkeypatch.setattr(jasil_runtime.get_active_platform().storage, "delete", unavailable)

        response = admin_client.delete(_ADMIN_URL)

        assert response.status_code == 204
        assert _settings(committed_sessions).login_photo_set is False
        assert client.get(_PUBLIC_URL).status_code == 404
        assert len(_audit_rows(committed_sessions, "server_settings.login_photo.delete")) == 1


class TestServeLoginPhoto:
    def test_the_stored_image_is_served_with_the_version_as_its_etag_and_a_cache_lifetime(self, admin_client, client):
        png = images.png_with_text()
        _upload(admin_client, png)

        response = client.get(_PUBLIC_URL)

        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
        assert response.headers["ETag"] == '"2"'
        assert response.headers["Cache-Control"] == "public, max-age=300"
        assert response.content == _stored_blob()

    def test_a_client_holding_the_photo_gets_a_304_without_storage_being_read(self, admin_client, client):
        _upload(admin_client, images.png_with_text())
        jasil_runtime.get_active_platform().storage.delete(_AREA, _KEY)

        response = client.get(_PUBLIC_URL, headers={"If-None-Match": '"2"'})

        assert response.status_code == 304
        assert response.content == b""
        assert response.headers["ETag"] == '"2"'

    def test_a_tag_of_an_earlier_photo_is_served_the_new_one(self, admin_client, client):
        _upload(admin_client, images.png_with_text())
        _upload(admin_client, images.png_with_text(size=(16, 16)))

        response = client.get(_PUBLIC_URL, headers={"If-None-Match": '"2"'})

        assert response.status_code == 200
        assert response.headers["ETag"] == '"3"'

    def test_no_photo_is_a_404(self, client):
        assert client.get(_PUBLIC_URL).status_code == 404

    def test_a_flag_without_a_blob_is_a_404(self, admin_client, client):
        _upload(admin_client, images.png_with_text())
        jasil_runtime.get_active_platform().storage.delete(_AREA, _KEY)

        assert client.get(_PUBLIC_URL).status_code == 404

    def test_bytes_whose_type_cannot_be_detected_are_served_as_a_png(self, admin_client, client):
        _upload(admin_client, images.png_with_text())
        jasil_runtime.get_active_platform().storage.save(_AREA, _KEY, b"not an image at all", "image/png")

        response = client.get(_PUBLIC_URL)

        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"


class TestUploadLoginPhotoService:
    def test_bytes_over_the_cap_are_refused_before_storage_or_the_flag_is_touched(self, db):
        storage = jasil_runtime.get_active_platform().storage
        oversized = images.png_with_text() + b"\0" * server_settings_constants.LOGIN_PHOTO_MAX_BYTES

        with pytest.raises(core_exceptions.PayloadTooLargeError):
            server_settings_login_photo_service.upload_login_photo(oversized, storage, db)

        assert storage.get(_AREA, _KEY) is None
        stored = server_settings_crud.get_server_settings(db)
        assert stored is not None
        assert (stored.login_photo_set, stored.version) == (False, 1)

    def test_bytes_that_are_no_image_are_refused_before_storage_or_the_flag_is_touched(self, db):
        storage = jasil_runtime.get_active_platform().storage

        with pytest.raises(core_exceptions.UnsupportedMediaTypeError):
            server_settings_login_photo_service.upload_login_photo(images.gif(), storage, db)

        assert storage.get(_AREA, _KEY) is None
        stored = server_settings_crud.get_server_settings(db)
        assert stored is not None
        assert stored.login_photo_set is False
