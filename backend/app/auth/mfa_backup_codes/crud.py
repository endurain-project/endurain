from datetime import datetime, timezone
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

import auth.mfa_backup_codes.models as mfa_backup_codes_models
import auth.mfa_backup_codes.utils as mfa_backup_codes_utils

import auth.password_hasher as auth_password_hasher

import core.logger as core_logger


def get_user_backup_codes(
    user_id: int, db: Session
) -> list[mfa_backup_codes_models.MFABackupCode]:
    try:
        return (
            db.query(mfa_backup_codes_models.MFABackupCode)
            .filter(
                mfa_backup_codes_models.MFABackupCode.user_id == user_id,
            )
            .all()
        )
    except Exception as err:
        core_logger.print_to_log(
            f"Error in get_user_backup_codes: {err}", "error", exc=err
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve backup codes",
        ) from err


def get_user_unused_backup_codes(
    user_id: int, db: Session
) -> list[mfa_backup_codes_models.MFABackupCode]:
    try:
        return (
            db.query(mfa_backup_codes_models.MFABackupCode)
            .filter(
                mfa_backup_codes_models.MFABackupCode.user_id == user_id,
                mfa_backup_codes_models.MFABackupCode.used == False,
            )
            .all()
        )
    except Exception as err:
        core_logger.print_to_log(
            f"Error in get_user_unused_backup_codes: {err}", "error", exc=err
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve unused backup codes",
        ) from err


def create_backup_codes(
    user_id: int,
    password_hasher: auth_password_hasher.PasswordHasher,
    db: Session,
    count: int = 10,
) -> list[str]:
    try:
        delete_user_backup_codes(user_id, db)

        plaintext_codes = []

        for _ in range(count):
            # Generate unique code
            code = mfa_backup_codes_utils.generate_backup_code()

            # Hash the code (bcrypt)
            code_hash = password_hasher.hash_password(code)

            # Store hash in database
            backup_code = mfa_backup_codes_models.MFABackupCode(
                user_id=user_id,
                code_hash=code_hash,
                created_at=datetime.now(timezone.utc),
            )
            db.add(backup_code)

            # Keep plaintext for return (only time it's available)
            plaintext_codes.append(code)

        db.commit()

        core_logger.print_to_log(f"Created backup codes for user ID {user_id}", "info")

        return plaintext_codes
    except HTTPException as err:
        raise err
    except Exception as err:
        core_logger.print_to_log(
            f"Error creating backup codes for user ID {user_id}: {err}",
            "error",
            exc=err,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to regenerate backup codes",
        ) from err


def mark_backup_code_as_used(
    backup_code_hashed: str, user_id: int, db: Session
) -> None:
    try:
        db_code = (
            db.query(mfa_backup_codes_models.MFABackupCode)
            .filter(
                mfa_backup_codes_models.MFABackupCode.user_id == user_id,
                mfa_backup_codes_models.MFABackupCode.code_hash == backup_code_hashed,
                mfa_backup_codes_models.MFABackupCode.used == False,
            )
            .first()
        )

        if db_code:
            db_code.used = True
            db_code.used_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(db_code)
            core_logger.print_to_log(
                f"Marked backup code as used for user ID {user_id}", "info"
            )
        else:
            core_logger.print_to_log(
                f"No unused backup code found to mark as used for user ID {user_id}",
                "warning",
            )
            HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Backup code not found or already used",
            )
    except Exception as err:
        db.rollback()
        core_logger.print_to_log(
            f"Error in mark_backup_code_as_used: {err}", "error", exc=err
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def delete_user_backup_codes(user_id: int, db: Session) -> int:
    try:
        # Delete existing codes
        num_deleted = (
            db.query(mfa_backup_codes_models.MFABackupCode)
            .filter(mfa_backup_codes_models.MFABackupCode.user_id == user_id)
            .delete()
        )

        db.commit()

        core_logger.print_to_log(
            f"Deleted {num_deleted} backup codes for user ID: {user_id}", "info"
        )

        return num_deleted
    except Exception as err:
        db.rollback()
        core_logger.print_to_log(
            f"Error in delete_user_backup_codes: {err}", "error", exc=err
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err
