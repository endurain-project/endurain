"""Tests for the uploaded identity-provider icon service."""

import io
from unittest.mock import MagicMock, patch

import jasil.providers as jasil_providers
import jasil.testing as jasil_testing
import pytest
from fastapi import UploadFile

import core.exceptions as core_exceptions
import core.file_uploads as core_file_uploads
import modules.auth.identity_providers.audit_actions as idp_audit_actions
import modules.auth.identity_providers.constants as idp_constants
import modules.auth.identity_providers.contracts as idp_contracts
import modules.auth.identity_providers.icon_service as icon_service
from tests._helpers import images

PNG = images.png_with_text()


def _upload(data: bytes):
    """The reader the service is handed; it returns the validated bytes."""
    return lambda: data


def _state(**overrides) -> idp_contracts.IdentityProviderState:
    values = {
        "id": 7,
        "name": "Tinyauth",
        "slug": "tinyauth",
        "provider_type": "oidc",
        "enabled": True,
        "client_id": None,
        "client_secret": None,
        "issuer_url": None,
        "authorization_endpoint": None,
        "token_endpoint": None,
        "userinfo_endpoint": None,
        "scopes": None,
        "icon": None,
        "icon_uploaded": True,
        "auto_create_users": True,
        "sync_user_info": True,
        "sync_email": False,
        "link_by_email": False,
        "user_mapping": None,
        "created_at": "2026-10-30T00:00:00Z",
        "updated_at": "2026-10-30T00:00:00Z",
        "version": 4,
    }
    values.update(overrides)
    return idp_contracts.IdentityProviderState(**values)


class TestUploadIcon:
    def test_stores_the_blob_with_its_detected_type_then_flags_and_commits(self):
        storage, db = MagicMock(), MagicMock()
        with (
            patch.object(icon_service.idp_crud, "identity_provider_exists", return_value=True),
            patch.object(icon_service.idp_crud, "set_icon_uploaded", return_value=(5, False)) as set_flag,
        ):
            staged = icon_service.upload_icon(7, _upload(PNG), storage, db)

        assert staged == (5, False)
        area, key, data, content_type = storage.save.call_args.args
        assert (area, key, content_type) == (idp_constants.ICON_STORAGE_AREA, "7", "image/png")
        assert not images.has_metadata(data)
        set_flag.assert_called_once_with(7, True, db)
        db.commit.assert_called_once()

    def test_a_missing_provider_is_refused_before_the_upload_is_read(self):
        storage, read_upload = MagicMock(), MagicMock()
        with (
            patch.object(icon_service.idp_crud, "identity_provider_exists", return_value=False),
            pytest.raises(core_exceptions.NotFoundError),
        ):
            icon_service.upload_icon(7, read_upload, storage, MagicMock())

        read_upload.assert_not_called()
        storage.save.assert_not_called()

    def test_an_oversized_image_is_refused(self):
        storage = MagicMock()
        data = PNG + b"0" * idp_constants.ICON_MAX_BYTES
        with (
            patch.object(icon_service.idp_crud, "identity_provider_exists", return_value=True),
            pytest.raises(core_exceptions.PayloadTooLargeError),
        ):
            icon_service.upload_icon(7, _upload(data), storage, MagicMock())

        storage.save.assert_not_called()

    def test_an_unrecognised_format_is_refused(self):
        storage = MagicMock()
        with (
            patch.object(icon_service.idp_crud, "identity_provider_exists", return_value=True),
            pytest.raises(core_exceptions.UnsupportedMediaTypeError),
        ):
            icon_service.upload_icon(7, _upload(b"<svg></svg>"), storage, MagicMock())

        storage.save.assert_not_called()

    def test_a_provider_deleted_during_the_write_leaves_no_blob(self):
        storage, db = MagicMock(), MagicMock()
        with (
            patch.object(icon_service.idp_crud, "identity_provider_exists", return_value=True),
            patch.object(icon_service.idp_crud, "set_icon_uploaded", return_value=None),
            pytest.raises(core_exceptions.NotFoundError),
        ):
            icon_service.upload_icon(7, _upload(PNG), storage, db)

        storage.delete.assert_called_once_with(idp_constants.ICON_STORAGE_AREA, "7")
        db.commit.assert_not_called()


class TestUploadIconTransaction:
    def test_the_read_transaction_ends_before_the_blob_is_written(self):
        storage, db = MagicMock(), MagicMock()
        order = MagicMock()
        order.attach_mock(db.rollback, "rollback")
        order.attach_mock(storage.save, "save")
        with (
            patch.object(icon_service.idp_crud, "identity_provider_exists", return_value=True),
            patch.object(icon_service.idp_crud, "set_icon_uploaded", return_value=(5, False)),
        ):
            icon_service.upload_icon(7, _upload(PNG), storage, db)

        assert [call[0] for call in order.mock_calls] == ["rollback", "save"]

    def test_the_transaction_is_ended_again_before_the_blob_is_removed_on_the_race_path(self):
        storage, db = MagicMock(), MagicMock()
        order = MagicMock()
        order.attach_mock(db.rollback, "rollback")
        order.attach_mock(storage.save, "save")
        order.attach_mock(storage.delete, "delete")
        with (
            patch.object(icon_service.idp_crud, "identity_provider_exists", return_value=True),
            patch.object(icon_service.idp_crud, "set_icon_uploaded", return_value=None),
            pytest.raises(core_exceptions.NotFoundError),
        ):
            icon_service.upload_icon(7, _upload(PNG), storage, db)

        assert [call[0] for call in order.mock_calls] == ["rollback", "save", "rollback", "delete"]


class TestReferencedIconKeys:
    def test_keeps_a_key_whose_provider_has_an_icon_and_any_key_that_is_not_an_id(self):
        db = MagicMock()
        with patch.object(icon_service.idp_crud, "get_ids_with_icon", return_value={1}) as ids:
            kept = icon_service._referenced_icon_keys(["1", "2", "3", "notes.txt", "٣"], db)

        assert kept == {"1", "notes.txt", "٣"}
        ids.assert_called_once_with([1, 2, 3], db)


class TestSweepUnreferencedIcons:
    @patch("modules.auth.identity_providers.icon_service.core_blob_sweep.sweep_unreferenced_blobs", return_value=2)
    def test_the_sweep_walks_the_icon_area(self, mock_sweep):
        storage = MagicMock()

        assert icon_service.sweep_unreferenced_icons(storage) == 2
        mock_sweep.assert_called_once_with(storage, "identity_provider_icons", icon_service._referenced_icon_keys)


class TestDeleteIcon:
    def test_clears_the_flag_before_deleting_the_blob(self):
        storage, db = MagicMock(), MagicMock()
        order: list[str] = []
        db.commit.side_effect = lambda: order.append("commit")
        storage.delete.side_effect = lambda *_: order.append("delete")
        with patch.object(icon_service.idp_crud, "set_icon_uploaded", return_value=(5, False)) as set_flag:
            icon_service.delete_icon(7, storage, db)

        set_flag.assert_called_once_with(7, False, db)
        assert order == ["commit", "delete"]

    def test_a_blob_that_cannot_be_deleted_is_not_an_error(self):
        storage = MagicMock()
        storage.delete.side_effect = jasil_providers.StorageBackendUnavailableError("storage down")
        with patch.object(icon_service.idp_crud, "set_icon_uploaded", return_value=(5, False)):
            icon_service.delete_icon(7, storage, MagicMock())

    def test_an_unexpected_storage_failure_propagates(self):
        storage = MagicMock()
        storage.delete.side_effect = ValueError("not a valid storage address")
        with (
            patch.object(icon_service.idp_crud, "set_icon_uploaded", return_value=(5, False)),
            pytest.raises(ValueError, match="not a valid storage address"),
        ):
            icon_service.delete_icon(7, storage, MagicMock())

    def test_a_missing_provider_is_not_found(self):
        with (
            patch.object(icon_service.idp_crud, "set_icon_uploaded", return_value=None),
            pytest.raises(core_exceptions.NotFoundError),
        ):
            icon_service.delete_icon(7, MagicMock(), MagicMock())


class TestGetPublicIcon:
    @pytest.mark.parametrize(
        ("state", "expected"),
        [
            (_state(), (7, 4)),
            (_state(enabled=False), (7, 4)),
            (_state(icon_uploaded=False), None),
            (None, None),
        ],
        ids=["served", "disabled-still-served", "no-upload", "unknown"],
    )
    def test_serves_only_a_provider_with_an_uploaded_icon(self, state, expected):
        with patch.object(icon_service.idp_crud, "get_identity_provider_by_slug", return_value=state):
            assert icon_service.get_public_icon("Tinyauth", MagicMock()) == expected

    def test_ends_the_read_transaction_before_storage_is_read(self):
        db = MagicMock()
        with patch.object(icon_service.idp_crud, "get_identity_provider_by_slug", return_value=_state()):
            icon_service.get_public_icon("tinyauth", db)

        db.rollback.assert_called_once()


class TestReadIcon:
    def test_returns_the_bytes_with_the_detected_type(self):
        storage = MagicMock()
        storage.get.return_value = PNG

        assert icon_service.read_icon(7, storage) == (PNG, "image/png")
        storage.get.assert_called_once_with(idp_constants.ICON_STORAGE_AREA, "7")

    def test_no_stored_blob_is_none(self):
        storage = MagicMock()
        storage.get.return_value = None

        assert icon_service.read_icon(7, storage) is None


class TestIconAudit:
    def test_an_upload_is_audited_as_a_provider_update(self):
        with (
            patch.object(icon_service.idp_crud, "identity_provider_exists", return_value=True),
            patch.object(icon_service.idp_crud, "set_icon_uploaded", return_value=(5, False)),
            jasil_testing.capture_audit() as audit,
        ):
            icon_service.upload_icon(7, _upload(PNG), MagicMock(), MagicMock())

        entry = audit.assert_audited(
            idp_audit_actions.IDENTITY_PROVIDER_UPDATE.id, target_type="identity_provider", target_id="7"
        )
        assert entry.details == {"changed_fields": ["icon_uploaded"], "sessions_ended": 0}

    def test_a_refused_upload_is_not_audited(self):
        with (
            patch.object(icon_service.idp_crud, "identity_provider_exists", return_value=True),
            jasil_testing.capture_audit() as audit,
            pytest.raises(core_exceptions.UnsupportedMediaTypeError),
        ):
            icon_service.upload_icon(7, _upload(b"not an image"), MagicMock(), MagicMock())

        audit.assert_not_audited(idp_audit_actions.IDENTITY_PROVIDER_UPDATE.id)

    def test_a_removal_is_audited_as_a_provider_update(self):
        with (
            patch.object(icon_service.idp_crud, "set_icon_uploaded", return_value=(5, False)),
            jasil_testing.capture_audit() as audit,
        ):
            icon_service.delete_icon(7, MagicMock(), MagicMock())

        entry = audit.assert_audited(
            idp_audit_actions.IDENTITY_PROVIDER_UPDATE.id, target_type="identity_provider", target_id="7"
        )
        assert entry.details == {"changed_fields": ["icon_uploaded"], "sessions_ended": 0}

    def test_removing_from_a_missing_provider_is_not_audited(self):
        with (
            patch.object(icon_service.idp_crud, "set_icon_uploaded", return_value=None),
            jasil_testing.capture_audit() as audit,
            pytest.raises(core_exceptions.NotFoundError),
        ):
            icon_service.delete_icon(7, MagicMock(), MagicMock())

        audit.assert_not_audited(idp_audit_actions.IDENTITY_PROVIDER_UPDATE.id)


class TestUploadIconImageFormats:
    @staticmethod
    def _reader(name: str, data: bytes):
        return lambda: core_file_uploads.read_validated_upload_sync(
            UploadFile(io.BytesIO(data), filename=name), kind=core_file_uploads.UploadKind.IMAGE
        )

    def test_a_webp_is_stored_without_its_metadata(self):
        storage = MagicMock()
        with (
            patch.object(icon_service.idp_crud, "identity_provider_exists", return_value=True),
            patch.object(icon_service.idp_crud, "set_icon_uploaded", return_value=(5, False)),
        ):
            icon_service.upload_icon(7, self._reader("icon.webp", images.webp_with_exif()), storage, MagicMock())

        _area, _key, data, content_type = storage.save.call_args.args
        assert content_type == "image/webp"
        assert not images.has_metadata(data)

    @pytest.mark.parametrize(
        ("name", "data"), [("a.gif", images.gif()), ("a.heic", images.heic_like())], ids=["gif", "heic"]
    )
    def test_gif_and_heic_are_refused(self, name: str, data: bytes):
        storage = MagicMock()
        with (
            patch.object(icon_service.idp_crud, "identity_provider_exists", return_value=True),
            pytest.raises(core_exceptions.DomainError) as exc,
        ):
            icon_service.upload_icon(7, self._reader(name, data), storage, MagicMock())

        assert exc.value.status_code == 415
        storage.save.assert_not_called()
