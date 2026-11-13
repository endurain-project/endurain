"""Consuming a backup code is audited in the transaction that consumes it, without the code."""

import uuid
from unittest.mock import MagicMock, patch

import jasil.testing as jasil_testing

import core.exceptions as core_exceptions
import modules.auth.mfa_backup_codes.audit_actions as mfa_backup_codes_audit_actions
import modules.auth.mfa_backup_codes.crud as backup_crud
import modules.auth.mfa_backup_codes.service as backup_service
from tests._helpers.auth import MOCK_USER_ID

_ACTION = mfa_backup_codes_audit_actions.BACKUP_CODE_USE.id
_CODE = "A3K9-7BDF"


def _stored(code, hasher):
    return MagicMock(id=uuid.uuid4(), code_hash=hasher.hash_password(code))


def test_a_consumed_code_is_staged_with_the_number_left(mock_db, password_hasher):
    stored = [_stored(_CODE, password_hasher), _stored("ZZZZ-ZZZZ", password_hasher)]
    with (
        patch.object(backup_crud, "get_user_unused_backup_codes", return_value=stored),
        patch.object(backup_crud, "mark_backup_code_as_used"),
        jasil_testing.capture_audit() as audit,
    ):
        assert backup_service.verify_and_consume_backup_code(MOCK_USER_ID, _CODE, password_hasher, mock_db) is True

    entry = audit.assert_audited(
        _ACTION, outcome="success", target_type="user", target_id=str(MOCK_USER_ID), target_owner_id=str(MOCK_USER_ID)
    )
    assert entry.details == {"remaining_codes": 1}
    assert _CODE not in repr(entry)


def test_a_wrong_code_writes_nothing(mock_db, password_hasher):
    with (
        patch.object(backup_crud, "get_user_unused_backup_codes", return_value=[_stored(_CODE, password_hasher)]),
        patch.object(backup_crud, "mark_backup_code_as_used"),
        jasil_testing.capture_audit() as audit,
    ):
        assert (
            backup_service.verify_and_consume_backup_code(MOCK_USER_ID, "WRONG-CODE", password_hasher, mock_db) is False
        )

    audit.assert_not_audited(_ACTION)


def test_a_code_consumed_by_a_concurrent_request_writes_nothing(mock_db, password_hasher):
    with (
        patch.object(backup_crud, "get_user_unused_backup_codes", return_value=[_stored(_CODE, password_hasher)]),
        patch.object(
            backup_crud, "mark_backup_code_as_used", side_effect=core_exceptions.NotFoundError("already used")
        ),
        jasil_testing.capture_audit() as audit,
    ):
        assert backup_service.verify_and_consume_backup_code(MOCK_USER_ID, _CODE, password_hasher, mock_db) is False

    audit.assert_not_audited(_ACTION)
