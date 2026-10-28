"""Tests for staged MFA backup-code persistence."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

import core.exceptions as core_exceptions
import modules.auth.mfa_backup_codes.contracts as backup_codes_contracts
import modules.auth.mfa_backup_codes.crud as backup_codes_crud


def _row(**overrides):
    values = {
        "id": 4,
        "user_id": 7,
        "code_hash": "hash",
        "created_at": datetime.now(UTC),
        "used": False,
        "expires_at": None,
        "used_at": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_get_user_backup_codes_returns_internal_dtos(mock_db):
    row = _row()
    mock_db.execute.return_value.scalars.return_value = [row]
    assert backup_codes_crud.get_user_backup_codes(7, mock_db) == [
        backup_codes_contracts.BackupCodeRead.model_validate(row)
    ]


def test_get_unused_codes_returns_internal_dtos(mock_db):
    row = _row()
    mock_db.execute.return_value.scalars.return_value = [row]
    assert backup_codes_crud.get_user_unused_backup_codes(7, mock_db)[0].id == row.id


def test_create_codes_replaces_existing_hashes_and_flushes(mock_db):
    backup_codes_crud.create_backup_codes(7, ["hash-a", "hash-b"], mock_db)
    mock_db.execute.assert_called_once()
    rows = mock_db.add_all.call_args.args[0]
    assert [row.code_hash for row in rows] == ["hash-a", "hash-b"]
    assert all(row.user_id == 7 for row in rows)
    mock_db.flush.assert_called_once()
    mock_db.commit.assert_not_called()


def test_mark_code_used_stages_update(mock_db):
    row = _row()
    mock_db.get.return_value = row
    backup_codes_crud.mark_backup_code_as_used(4, 7, mock_db)
    assert row.used is True
    assert row.used_at is not None
    mock_db.flush.assert_called_once()


def test_mark_code_used_missing_or_used_raises_not_found(mock_db):
    mock_db.get.return_value = None
    with pytest.raises(core_exceptions.NotFoundError):
        backup_codes_crud.mark_backup_code_as_used(4, 7, mock_db)
    mock_db.get.return_value = _row(used=True)
    with pytest.raises(core_exceptions.NotFoundError):
        backup_codes_crud.mark_backup_code_as_used(4, 7, mock_db)


def test_delete_codes_stages_and_returns_count(mock_db):
    mock_db.execute.return_value.rowcount = 3
    assert backup_codes_crud.delete_user_backup_codes(7, mock_db) == 3
    mock_db.flush.assert_called_once()
    mock_db.commit.assert_not_called()
