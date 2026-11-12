"""Consuming a backup code stages the notice event in the transaction that consumes it."""

import uuid
from unittest.mock import MagicMock, patch

import core.exceptions as core_exceptions
import modules.auth.mfa_backup_codes.crud as backup_crud
import modules.auth.mfa_backup_codes.event_publishers as backup_event_publishers
import modules.auth.mfa_backup_codes.events as backup_events
import modules.auth.mfa_backup_codes.service as backup_service

_CODE = "A3K9-7BDF"


def _stored(code, hasher):
    return MagicMock(id=uuid.uuid4(), code_hash=hasher.hash_password(code))


def test_a_consumed_code_stages_the_event_with_the_number_left(mock_db, password_hasher):
    stored = [_stored(_CODE, password_hasher), _stored("ZZZZ-ZZZZ", password_hasher)]
    with (
        patch.object(backup_crud, "get_user_unused_backup_codes", return_value=stored),
        patch.object(backup_crud, "mark_backup_code_as_used"),
        patch.object(backup_event_publishers, "publish_backup_code_used") as publish,
    ):
        assert backup_service.verify_and_consume_backup_code(5, _CODE, password_hasher, mock_db) is True

    publish.assert_called_once_with(5, 1, mock_db)


def test_a_wrong_code_publishes_nothing(mock_db, password_hasher):
    with (
        patch.object(backup_crud, "get_user_unused_backup_codes", return_value=[_stored(_CODE, password_hasher)]),
        patch.object(backup_event_publishers, "publish_backup_code_used") as publish,
    ):
        assert backup_service.verify_and_consume_backup_code(5, "WRONG-CODE", password_hasher, mock_db) is False

    publish.assert_not_called()


def test_a_code_consumed_by_a_concurrent_request_publishes_nothing(mock_db, password_hasher):
    with (
        patch.object(backup_crud, "get_user_unused_backup_codes", return_value=[_stored(_CODE, password_hasher)]),
        patch.object(
            backup_crud, "mark_backup_code_as_used", side_effect=core_exceptions.NotFoundError("already used")
        ),
        patch.object(backup_event_publishers, "publish_backup_code_used") as publish,
    ):
        assert backup_service.verify_and_consume_backup_code(5, _CODE, password_hasher, mock_db) is False

    publish.assert_not_called()


def test_the_event_names_the_user_and_the_count_and_never_the_code(mock_db):
    with patch("modules.auth.mfa_backup_codes.event_publishers.platform_publisher.publish_on_commit") as publish:
        backup_event_publishers.publish_backup_code_used(5, 2, mock_db)

    event_type, payload = publish.call_args.args
    assert event_type == backup_events.BACKUP_CODE_USED
    assert payload == {"user_id": 5, "backup_codes_remaining": 2}
    assert publish.call_args.kwargs["db"] is mock_db
