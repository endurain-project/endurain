"""Additional API-key persistence contract tests."""

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

import core.exceptions as core_exceptions
import modules.auth.api_keys.crud as api_keys_crud
from tests._helpers.auth import MOCK_USER_ID

KEY_ID = uuid.UUID("00000000-0000-4000-8000-0000000000a1")


def test_delete_missing_key_raises_not_found(mock_db):
    mock_db.execute.return_value.rowcount = 0
    with pytest.raises(core_exceptions.NotFoundError):
        api_keys_crud.delete_api_key(KEY_ID, MOCK_USER_ID, mock_db)


def test_revoke_uses_id_and_owner_predicates(mock_db):
    mock_db.execute.return_value.scalar_one_or_none.return_value = MagicMock(is_active=True)
    api_keys_crud.revoke_api_key(KEY_ID, MOCK_USER_ID, mock_db)
    statement = mock_db.execute.call_args.args[0]
    assert "users_api_keys.id" in str(statement)
    assert "users_api_keys.user_id" in str(statement)


def test_revoke_all_deactivates_only_the_users_active_keys(mock_db):
    mock_db.execute.return_value.rowcount = 2

    assert api_keys_crud.revoke_all_api_keys_for_user(MOCK_USER_ID, mock_db) == 2

    statement = str(mock_db.execute.call_args.args[0])
    assert statement.startswith("UPDATE users_api_keys SET is_active=")
    assert "users_api_keys.user_id" in statement
    assert "users_api_keys.is_active" in statement
    assert "revoked_at=" in statement


def test_count_active_counts_the_users_unrevoked_unexpired_keys(mock_db):
    mock_db.execute.return_value.scalar_one.return_value = 4

    assert api_keys_crud.count_active_api_keys(MOCK_USER_ID, datetime.now(UTC), mock_db) == 4

    statement = str(mock_db.execute.call_args.args[0])
    assert "users_api_keys.user_id" in statement
    assert "users_api_keys.is_active" in statement
    assert "users_api_keys.expires_at >" in statement


def test_delete_stale_removes_keys_revoked_or_expired_before_the_cutoff(mock_db):
    mock_db.execute.return_value.rowcount = 3

    assert api_keys_crud.delete_stale_api_keys(datetime.now(UTC), 100, mock_db) == 3

    statement = str(mock_db.execute.call_args.args[0])
    assert statement.startswith("DELETE FROM users_api_keys")
    assert "users_api_keys.revoked_at <" in statement
    assert "users_api_keys.expires_at <" in statement
