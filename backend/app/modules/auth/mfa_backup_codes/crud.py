"""Persistence operations for MFA backup codes."""

from datetime import UTC, datetime

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import modules.auth.mfa_backup_codes.contracts as mfa_backup_codes_contracts
import modules.auth.mfa_backup_codes.models as mfa_backup_codes_models
import modules.auth.mfa_backup_codes.serializers as mfa_backup_codes_serializers


def get_user_backup_codes(user_id: int, db: Session) -> list[mfa_backup_codes_contracts.BackupCodeRead]:
    """Return stored backup codes for a user."""
    rows = db.execute(
        select(mfa_backup_codes_models.MFABackupCode).where(mfa_backup_codes_models.MFABackupCode.user_id == user_id)
    ).scalars()
    return [mfa_backup_codes_serializers.to_read_schema(row) for row in rows]


def get_user_unused_backup_codes(user_id: int, db: Session) -> list[mfa_backup_codes_contracts.BackupCodeRead]:
    """Return live, unused backup codes for a user."""
    now = datetime.now(UTC)
    stmt = select(mfa_backup_codes_models.MFABackupCode).where(
        mfa_backup_codes_models.MFABackupCode.user_id == user_id,
        mfa_backup_codes_models.MFABackupCode.used.is_(False),
        or_(
            mfa_backup_codes_models.MFABackupCode.expires_at.is_(None),
            mfa_backup_codes_models.MFABackupCode.expires_at > now,
        ),
    )
    rows = db.execute(stmt).scalars()
    return [mfa_backup_codes_serializers.to_read_schema(row) for row in rows]


def create_backup_codes(user_id: int, code_hashes: list[str], db: Session) -> None:
    """Replace a user's backup codes with already-hashed values."""
    db.execute(
        delete(mfa_backup_codes_models.MFABackupCode).where(mfa_backup_codes_models.MFABackupCode.user_id == user_id)
    )
    db.add_all(
        [
            mfa_backup_codes_models.MFABackupCode(
                user_id=user_id,
                code_hash=code_hash,
                created_at=datetime.now(UTC),
            )
            for code_hash in code_hashes
        ]
    )
    db.flush()


def mark_backup_code_as_used(code_id: int, user_id: int, db: Session) -> None:
    """Stage consumption of one unused backup code."""
    row = db.get(mfa_backup_codes_models.MFABackupCode, code_id)
    if row is None or row.user_id != user_id or row.used:
        raise core_exceptions.NotFoundError("Backup code not found or already used")
    row.used = True
    row.used_at = datetime.now(UTC)
    db.flush()


def delete_user_backup_codes(user_id: int, db: Session) -> int:
    """Stage deletion of all backup codes for a user."""
    result = db.execute(
        delete(mfa_backup_codes_models.MFABackupCode).where(mfa_backup_codes_models.MFABackupCode.user_id == user_id)
    )
    db.flush()
    return result.rowcount or 0
