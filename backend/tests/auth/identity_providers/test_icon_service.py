"""Tests for the uploaded identity-provider icon service."""

from unittest.mock import MagicMock, patch

import pytest

import core.exceptions as core_exceptions
import modules.auth.identity_providers.constants as idp_constants
import modules.auth.identity_providers.contracts as idp_contracts
import modules.auth.identity_providers.icon_service as icon_service

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 16


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
        "jwks_uri": None,
        "scopes": None,
        "icon": None,
        "icon_uploaded": True,
        "auto_create_users": True,
        "sync_user_info": True,
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
            patch.object(icon_service.idp_crud, "set_icon_uploaded", return_value=5) as set_flag,
        ):
            version = icon_service.upload_icon(7, PNG, storage, db)

        assert version == 5
        storage.save.assert_called_once_with(idp_constants.ICON_STORAGE_AREA, "7", PNG, "image/png")
        set_flag.assert_called_once_with(7, True, db)
        db.commit.assert_called_once()

    def test_a_missing_provider_stores_nothing(self):
        storage = MagicMock()
        with (
            patch.object(icon_service.idp_crud, "identity_provider_exists", return_value=False),
            pytest.raises(core_exceptions.NotFoundError),
        ):
            icon_service.upload_icon(7, PNG, storage, MagicMock())

        storage.save.assert_not_called()

    def test_an_oversized_image_is_refused(self):
        storage = MagicMock()
        data = PNG + b"0" * idp_constants.ICON_MAX_BYTES
        with (
            patch.object(icon_service.idp_crud, "identity_provider_exists", return_value=True),
            pytest.raises(core_exceptions.PayloadTooLargeError),
        ):
            icon_service.upload_icon(7, data, storage, MagicMock())

        storage.save.assert_not_called()

    def test_an_unrecognised_format_is_refused(self):
        storage = MagicMock()
        with (
            patch.object(icon_service.idp_crud, "identity_provider_exists", return_value=True),
            pytest.raises(core_exceptions.UnsupportedMediaTypeError),
        ):
            icon_service.upload_icon(7, b"<svg></svg>", storage, MagicMock())

        storage.save.assert_not_called()

    def test_a_provider_deleted_during_the_write_leaves_no_blob(self):
        storage, db = MagicMock(), MagicMock()
        with (
            patch.object(icon_service.idp_crud, "identity_provider_exists", return_value=True),
            patch.object(icon_service.idp_crud, "set_icon_uploaded", return_value=None),
            pytest.raises(core_exceptions.NotFoundError),
        ):
            icon_service.upload_icon(7, PNG, storage, db)

        storage.delete.assert_called_once_with(idp_constants.ICON_STORAGE_AREA, "7")
        db.commit.assert_not_called()


class TestDeleteIcon:
    def test_clears_the_flag_before_deleting_the_blob(self):
        storage, db = MagicMock(), MagicMock()
        order: list[str] = []
        db.commit.side_effect = lambda: order.append("commit")
        storage.delete.side_effect = lambda *_: order.append("delete")
        with patch.object(icon_service.idp_crud, "set_icon_uploaded", return_value=5) as set_flag:
            icon_service.delete_icon(7, storage, db)

        set_flag.assert_called_once_with(7, False, db)
        assert order == ["commit", "delete"]

    def test_a_blob_that_cannot_be_deleted_is_not_an_error(self):
        storage = MagicMock()
        storage.delete.side_effect = RuntimeError("storage down")
        with patch.object(icon_service.idp_crud, "set_icon_uploaded", return_value=5):
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
