"""Audit rows of a confirmed email change and of an administrator's photo change."""

from unittest.mock import MagicMock, patch

import jasil.testing as jasil_testing
import pytest
from tests._helpers import images

import core.exceptions as core_exceptions
import modules.users.users.audit_actions as users_audit_actions
import modules.users.users.integration_service as users_integration
import modules.users.users.photo_service as users_photo_service
import modules.users.users.service as users_service

_SERVICE_CRUD = "modules.users.users.service.users_crud"
_PHOTO_CRUD = "modules.users.users.photo_service.users_crud"
_PNG = images.png_with_text()
_TARGET = {"target_type": "user", "target_id": "7", "target_owner_id": "7"}


class TestConfirmedEmailChange:
    def test_a_confirmed_change_is_recorded_without_the_address(self, mock_db):
        with jasil_testing.capture_audit() as audit, patch(_SERVICE_CRUD) as crud:
            crud.get_user_by_email.return_value = None
            users_service.stage_confirmed_email_change(7, "New@Example.com", mock_db)

        entry = audit.assert_audited(users_audit_actions.USER_EMAIL_CHANGE.id, **_TARGET)
        assert entry.details is None

    def test_a_taken_address_writes_no_row(self, mock_db):
        with jasil_testing.capture_audit() as audit, patch(_SERVICE_CRUD) as crud:
            crud.get_user_by_email.return_value = MagicMock(id=8)
            with pytest.raises(core_exceptions.ConflictError):
                users_service.stage_confirmed_email_change(7, "taken@example.com", mock_db)

        audit.assert_not_audited(users_audit_actions.USER_EMAIL_CHANGE.id)

    def test_the_integration_surface_records_it(self, mock_db):
        with jasil_testing.capture_audit() as audit, patch(_SERVICE_CRUD) as crud:
            crud.get_user_by_email.return_value = None
            users_integration.stage_confirmed_email_change(7, "new@example.com", mock_db)

        audit.assert_audited(users_audit_actions.USER_EMAIL_CHANGE.id, **_TARGET)


class TestAdministratorPhotoChange:
    @patch(_PHOTO_CRUD)
    def test_an_administrators_upload_records_the_changed_field(self, crud, mock_db):
        crud.get_user_by_id.return_value = MagicMock()

        with jasil_testing.capture_audit() as audit:
            users_photo_service.store_photo(7, ".png", _PNG, MagicMock(), mock_db, audit=True)

        entry = audit.assert_audited(users_audit_actions.USER_UPDATE.id, **_TARGET)
        assert entry.details == {"changed_fields": ["photo_path"]}

    @patch(_PHOTO_CRUD)
    def test_an_administrators_delete_records_the_changed_field(self, crud, mock_db):
        crud.replace_photo_key.return_value = "7.jpg"

        with jasil_testing.capture_audit() as audit:
            users_photo_service.delete_photo(7, MagicMock(), mock_db, audit=True)

        entry = audit.assert_audited(users_audit_actions.USER_UPDATE.id, **_TARGET)
        assert entry.details == {"changed_fields": ["photo_path"]}

    @patch(_PHOTO_CRUD)
    def test_deleting_a_photo_that_does_not_exist_writes_no_row(self, crud, mock_db):
        crud.replace_photo_key.return_value = None

        with jasil_testing.capture_audit() as audit:
            users_photo_service.delete_photo(7, MagicMock(), mock_db, audit=True)

        audit.assert_not_audited(users_audit_actions.USER_UPDATE.id)

    @patch(_PHOTO_CRUD)
    def test_the_users_own_photo_is_not_audited(self, crud, mock_db):
        crud.get_user_by_id.return_value = MagicMock()
        crud.replace_photo_key.return_value = "7.jpg"

        with jasil_testing.capture_audit() as audit:
            users_photo_service.store_photo(7, ".png", _PNG, MagicMock(), mock_db)
            users_photo_service.delete_photo(7, MagicMock(), mock_db)
            users_integration.delete_user_photo(7, MagicMock(), mock_db)

        audit.assert_not_audited(users_audit_actions.USER_UPDATE.id)

    @patch(_PHOTO_CRUD)
    def test_a_refused_upload_writes_no_row(self, crud, mock_db):
        crud.get_user_by_id.return_value = None

        with jasil_testing.capture_audit() as audit, pytest.raises(core_exceptions.NotFoundError):
            users_photo_service.store_photo(7, ".png", _PNG, MagicMock(), mock_db, audit=True)

        audit.assert_not_audited(users_audit_actions.USER_UPDATE.id)
