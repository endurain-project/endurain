"""Persistence operations for MFA backup codes."""

from datetime import UTC, datetime

from sqlalchemy import delete, or_, select, update
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
    """Stage consumption of one unused backup code.

    The code is claimed by a single conditional ``UPDATE``, so of two concurrent requests presenting the
    same code only one matches a row.

    Args:
        code_id: The code to consume.
        user_id: The code's owner.
        db: Database session.

    Raises:
        NotFoundError: If the user has no such code, or it was already used.
    """
    claimed = db.execute(
        update(mfa_backup_codes_models.MFABackupCode)
        .where(
            mfa_backup_codes_models.MFABackupCode.id == code_id,
            mfa_backup_codes_models.MFABackupCode.user_id == user_id,
            mfa_backup_codes_models.MFABackupCode.used.is_(False),
        )
        .values(used=True, used_at=datetime.now(UTC))
        .returning(mfa_backup_codes_models.MFABackupCode.id)
        .execution_options(synchronize_session=False)
    ).scalar_one_or_none()
    if claimed is None:
        raise core_exceptions.NotFoundError("Backup code not found or already used")


def delete_user_backup_codes(user_id: int, db: Session) -> int:
    """Stage deletion of all backup codes for a user."""
    result = db.execute(
        delete(mfa_backup_codes_models.MFABackupCode).where(mfa_backup_codes_models.MFABackupCode.user_id == user_id)
    )
    db.flush()
    return result.rowcount or 0
