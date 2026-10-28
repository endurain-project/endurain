"""Tests for staged credential persistence operations."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import modules.auth.credentials.contracts as credentials_contracts
import modules.auth.credentials.crud as credentials_crud


def test_get_credential_returns_internal_dto(mock_db):
    row = SimpleNamespace(
        user_id=3, password_hash="secret-hash", created_at=datetime.now(UTC), updated_at=datetime.now(UTC)
    )
    mock_db.execute.return_value.scalar_one_or_none.return_value = row

    result = credentials_crud.get_credential(3, mock_db)

    assert result == credentials_contracts.CredentialRead.model_validate(row)


def test_upsert_password_hash_inserts_and_flushes(mock_db):
    mock_db.execute.return_value.scalar_one_or_none.return_value = None
    row = MagicMock()
    with (
        patch("modules.auth.credentials.crud.select", return_value=MagicMock()),
        patch("modules.auth.credentials.crud.credentials_models.LocalCredential", return_value=row),
    ):
        credentials_crud.upsert_password_hash(3, "new-hash", mock_db)
    mock_db.add.assert_called_once_with(row)
    mock_db.flush.assert_called_once()
    mock_db.commit.assert_not_called()


def test_upsert_password_hash_updates_existing_row(mock_db):
    row = MagicMock()
    mock_db.execute.return_value.scalar_one_or_none.return_value = row

    credentials_crud.upsert_password_hash(3, "new-hash", mock_db)

    assert row.password_hash == "new-hash"
    mock_db.flush.assert_called_once()
    mock_db.commit.assert_not_called()


def test_delete_credential_stages_deletion(mock_db):
    credentials_crud.delete_credential(3, mock_db)
    mock_db.execute.assert_called_once()
    mock_db.flush.assert_called_once()
    mock_db.commit.assert_not_called()
