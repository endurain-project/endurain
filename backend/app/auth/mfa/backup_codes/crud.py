"""CRUD operations for MFA backup codes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import CursorResult, delete, or_, select
from sqlalchemy.orm import Session

import auth.mfa.backup_codes.models as mfa_backup_codes_models
import auth.mfa.backup_codes.utils as mfa_backup_codes_utils
import core.decorators as core_decorators
import core.logger as core_logger
from auth._internal.password_hasher import SupportsHashPassword


@core_decorators.handle_db_errors
def get_user_backup_codes(user_id: int, db: Session) -> list[mfa_backup_codes_models.MFABackupCode]:
    """Retrieve all MFA backup codes for a user.

    Args:
        user_id: User ID to fetch backup codes for.
        db: Database session.

    Returns:
        List of MFABackupCode models for the user (used and unused).

    Raises:
        HTTPException: If a database error occurs.
    """
    stmt = select(mfa_backup_codes_models.MFABackupCode).where(
        mfa_backup_codes_models.MFABackupCode.user_id == user_id,
    )
    return list(db.execute(stmt).scalars().all())


@core_decorators.handle_db_errors
def get_user_unused_backup_codes(user_id: int, db: Session) -> list[mfa_backup_codes_models.MFABackupCode]:
    """Retrieve all unused MFA backup codes for a user.

    Args:
        user_id: User ID to fetch unused backup codes for.
        db: Database session.

    Returns:
        List of MFABackupCode models that have not been consumed.

    Raises:
        HTTPException: If a database error occurs.
    """
    now = datetime.now(UTC)
    stmt = select(mfa_backup_codes_models.MFABackupCode).where(
        mfa_backup_codes_models.MFABackupCode.user_id == user_id,
        mfa_backup_codes_models.MFABackupCode.used.is_(False),
        or_(
            mfa_backup_codes_models.MFABackupCode.expires_at.is_(None),
            mfa_backup_codes_models.MFABackupCode.expires_at > now,
        ),
    )
    return list(db.execute(stmt).scalars().all())


@core_decorators.handle_db_errors
def create_backup_codes(
    user_id: int,
    password_hasher: SupportsHashPassword,
    db: Session,
    count: int = 10,
) -> list[str]:
    """Atomically (re)generate MFA backup codes for a user.

    Existing codes for the user are removed and replaced with ``count`` newly
    generated codes within a single transaction. The plaintext codes are
    returned to the caller exactly once and only the Argon2 hashes are
    persisted.

    Args:
        user_id: User ID to (re)generate backup codes for.
        password_hasher: Object implementing SupportsHashPassword, used to hash the generated codes.
        db: Database session.
        count: Number of backup codes to generate. Defaults to 10.

    Returns:
        List of plaintext backup codes shown to the user once.

    Raises:
        HTTPException: If a database error occurs. The transaction is rolled
            back so previously stored codes remain intact.
    """
    # Remove any existing codes within the same transaction so that a failure
    # below leaves the user's previous backup codes intact.
    db.execute(
        delete(mfa_backup_codes_models.MFABackupCode).where(mfa_backup_codes_models.MFABackupCode.user_id == user_id)
    )

    plaintext_codes: list[str] = []
    for _ in range(count):
        code = mfa_backup_codes_utils.generate_backup_code()
        code_hash = password_hasher.hash_password(code)
        db.add(
            mfa_backup_codes_models.MFABackupCode(
                user_id=user_id,
                code_hash=code_hash,
                created_at=datetime.now(UTC),
            )
        )
        plaintext_codes.append(code)

    db.commit()

    core_logger.print_to_log(f"Created backup codes for user ID {user_id}", "info")

    return plaintext_codes


@core_decorators.handle_db_errors
def mark_backup_code_as_used(code_id: int, user_id: int, db: Session) -> None:
    """Mark a single backup code as used by primary key.

    Args:
        code_id: Primary key of the backup code to consume.
        user_id: Expected owner of the backup code; mismatches raise 404 to
            avoid leaking ownership information.
        db: Database session.

    Raises:
        HTTPException: 404 if the code does not exist, does not belong to the
            user, or has already been consumed. 500 on database errors.
    """
    db_code = db.get(mfa_backup_codes_models.MFABackupCode, code_id)

    if db_code is None or db_code.user_id != user_id or db_code.used:
        core_logger.print_to_log(
            f"No unused backup code found to mark as used for user ID {user_id}",
            "warning",
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backup code not found or already used",
        )

    db_code.used = True
    db_code.used_at = datetime.now(UTC)
    db.commit()
    db.refresh(db_code)

    core_logger.print_to_log(f"Marked backup code as used for user ID {user_id}", "info")


@core_decorators.handle_db_errors
def delete_user_backup_codes(user_id: int, db: Session) -> int:
    """Delete all MFA backup codes for a user.

    Args:
        user_id: User ID whose backup codes should be removed.
        db: Database session.

    Returns:
        Number of backup code rows deleted.

    Raises:
        HTTPException: If a database error occurs.
    """
    stmt = delete(mfa_backup_codes_models.MFABackupCode).where(mfa_backup_codes_models.MFABackupCode.user_id == user_id)
    result: CursorResult[Any] = db.execute(stmt)
    db.commit()

    num_deleted = result.rowcount or 0
    core_logger.print_to_log(f"Deleted {num_deleted} backup codes for user ID: {user_id}", "info")

    return num_deleted
