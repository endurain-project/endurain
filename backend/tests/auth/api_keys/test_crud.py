"""Tests for staged API-key persistence operations."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import core.exceptions as core_exceptions
import modules.auth.api_keys.crud as api_keys_crud
import modules.auth.api_keys.models as api_keys_models
import modules.auth.api_keys.schema as api_keys_schema


def _row(**overrides):
    values = {
        "id": "api-key-id",
        "user_id": 1,
        "name": "CLI",
        "key_prefix": "12345678",
        "key_hash": "h" * 64,
        "scopes": '["activities:upload"]',
        "expires_at": datetime.now(UTC) + timedelta(days=30),
        "last_used_at": None,
        "created_at": datetime.now(UTC),
        "is_active": True,
        "revoked_at": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_get_api_keys_page_returns_read_dtos(mock_db):
    row = _row()
    mock_db.execute.return_value.scalars.return_value = [row]

    result = api_keys_crud.get_api_keys_page(1, mock_db, limit=25, offset=0)

    assert result == [api_keys_schema.UserApiKeyRead.model_validate(row)]


def test_count_api_keys_returns_owner_total(mock_db):
    mock_db.execute.return_value.scalar_one.return_value = 3

    assert api_keys_crud.count_api_keys(1, mock_db) == 3


def test_get_api_key_by_id_and_hash_return_read_dtos(mock_db):
    row = _row()
    mock_db.execute.return_value.scalar_one_or_none.return_value = row

    assert api_keys_crud.get_api_key_by_id(row.id, row.user_id, mock_db).id == row.id
    assert api_keys_crud.get_api_key_by_hash(row.key_hash, mock_db).id == row.id


def test_create_api_key_stages_hashed_key(mock_db):
    row = _row()
    data = api_keys_schema.UserApiKeyCreate(
        step_up={"current_password": "pw"}, name="CLI", scopes=["activities:upload"]
    )
    raw_key = "endurain_12345678secret"
    expires_at = datetime.now(UTC) + timedelta(days=30)
    with (
        patch.object(api_keys_models, "UsersApiKeys", return_value=row) as constructor,
        patch("modules.auth.api_keys.crud.uuid.uuid4", return_value="api-key-id"),
    ):
        result = api_keys_crud.create_api_key(1, data, raw_key, "h" * 64, '["activities:upload"]', expires_at, mock_db)

    constructor.assert_called_once()
    assert result.id == row.id
    mock_db.add.assert_called_once_with(row)
    mock_db.flush.assert_called_once()
    mock_db.commit.assert_not_called()


def test_update_last_used_stages_timestamp(mock_db):
    row = _row()
    mock_db.get.return_value = row

    api_keys_crud.update_last_used(row.id, mock_db)

    assert row.last_used_at is not None
    mock_db.flush.assert_called_once()
    mock_db.commit.assert_not_called()


def test_update_last_used_missing_key_raises_not_found(mock_db):
    mock_db.get.return_value = None
    with pytest.raises(core_exceptions.NotFoundError):
        api_keys_crud.update_last_used("missing", mock_db)


def test_revoke_and_delete_stage_owned_key(mock_db):
    row = _row()
    mock_db.execute.return_value.scalar_one_or_none.return_value = row
    api_keys_crud.revoke_api_key(row.id, row.user_id, mock_db)
    assert row.is_active is False
    assert row.revoked_at is not None
    mock_db.commit.assert_not_called()

    mock_db.execute.return_value.rowcount = 1
    api_keys_crud.delete_api_key(row.id, row.user_id, mock_db)
    mock_db.commit.assert_not_called()


def test_revoke_missing_key_raises_not_found(mock_db):
    mock_db.execute.return_value.scalar_one_or_none.return_value = None
    with pytest.raises(core_exceptions.NotFoundError):
        api_keys_crud.revoke_api_key("missing", 1, mock_db)


def test_revoking_a_revoked_key_keeps_its_first_revocation_time(mock_db):
    first = datetime.now(UTC) - timedelta(days=3)
    row = _row(is_active=False, revoked_at=first)
    mock_db.execute.return_value.scalar_one_or_none.return_value = row

    api_keys_crud.revoke_api_key(row.id, row.user_id, mock_db)

    assert row.revoked_at == first
