"""Additional API-key persistence contract tests."""

from unittest.mock import MagicMock

import pytest

import core.exceptions as core_exceptions
import modules.auth.api_keys.crud as api_keys_crud


def test_delete_missing_key_raises_not_found(mock_db):
    mock_db.execute.return_value.rowcount = 0
    with pytest.raises(core_exceptions.NotFoundError):
        api_keys_crud.delete_api_key("missing", 1, mock_db)


def test_revoke_uses_id_and_owner_predicates(mock_db):
    mock_db.execute.return_value.scalar_one_or_none.return_value = MagicMock(is_active=True)
    api_keys_crud.revoke_api_key("key-id", 7, mock_db)
    statement = mock_db.execute.call_args.args[0]
    assert "users_api_keys.id" in str(statement)
    assert "users_api_keys.user_id" in str(statement)


def test_revoke_all_deactivates_only_the_users_active_keys(mock_db):
    mock_db.execute.return_value.rowcount = 2

    assert api_keys_crud.revoke_all_api_keys_for_user(7, mock_db) == 2

    statement = str(mock_db.execute.call_args.args[0])
    assert statement.startswith("UPDATE users_api_keys SET is_active=")
    assert "users_api_keys.user_id" in statement
    assert "users_api_keys.is_active" in statement
