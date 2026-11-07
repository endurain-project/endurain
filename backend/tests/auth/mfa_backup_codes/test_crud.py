"""Tests for staged MFA backup-code persistence."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import update
from sqlalchemy.orm import sessionmaker

import core.exceptions as core_exceptions
import modules.auth.mfa_backup_codes.contracts as backup_codes_contracts
import modules.auth.mfa_backup_codes.crud as backup_codes_crud
import modules.auth.mfa_backup_codes.models as backup_codes_models
from tests._helpers.db import create_sqlite_session, ensure_user


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


class TestMarkBackupCodeAsUsed:
    """Single use is decided by the database, so these run against a real session."""

    @pytest.fixture
    def db(self):
        session = create_sqlite_session()
        ensure_user(sessionmaker(bind=session.get_bind()), 7)
        ensure_user(sessionmaker(bind=session.get_bind()), 8)
        yield session
        session.close()

    @staticmethod
    def _add_code(db, user_id=7, **overrides):
        row = backup_codes_models.MFABackupCode(
            user_id=user_id, code_hash=f"hash-{user_id}-{id(overrides)}", **overrides
        )
        db.add(row)
        db.flush()
        return row

    def test_consumes_an_unused_code(self, db):
        row = self._add_code(db)

        backup_codes_crud.mark_backup_code_as_used(row.id, 7, db)

        db.refresh(row)
        assert row.used is True
        assert row.used_at is not None

    def test_a_second_use_of_the_same_code_is_refused(self, db):
        row = self._add_code(db)
        backup_codes_crud.mark_backup_code_as_used(row.id, 7, db)

        with pytest.raises(core_exceptions.NotFoundError):
            backup_codes_crud.mark_backup_code_as_used(row.id, 7, db)

    def test_a_stale_copy_of_the_row_cannot_consume_a_used_code(self, db):
        row = self._add_code(db)
        db.commit()
        db.refresh(row)
        # A concurrent request already consumed it; this session's identity map still holds used=False.
        db.execute(
            update(backup_codes_models.MFABackupCode).values(used=True).execution_options(synchronize_session=False)
        )
        assert row.used is False

        with pytest.raises(core_exceptions.NotFoundError):
            backup_codes_crud.mark_backup_code_as_used(row.id, 7, db)

    def test_another_users_code_is_refused(self, db):
        row = self._add_code(db, user_id=8)

        with pytest.raises(core_exceptions.NotFoundError):
            backup_codes_crud.mark_backup_code_as_used(row.id, 7, db)

    def test_a_missing_code_is_refused(self, db):
        with pytest.raises(core_exceptions.NotFoundError):
            backup_codes_crud.mark_backup_code_as_used(999, 7, db)


def test_delete_codes_stages_and_returns_count(mock_db):
    mock_db.execute.return_value.rowcount = 3
    assert backup_codes_crud.delete_user_backup_codes(7, mock_db) == 3
    mock_db.flush.assert_called_once()
    mock_db.commit.assert_not_called()
