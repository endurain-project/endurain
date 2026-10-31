"""Operations used by MFA workflows."""

from sqlalchemy.orm import Session

import modules.auth.credentials.contracts as credentials_contracts
import modules.auth.mfa_backup_codes.contracts as mfa_backup_codes_contracts
import modules.auth.mfa_backup_codes.crud as mfa_backup_codes_crud
import modules.auth.mfa_backup_codes.service as mfa_backup_codes_service


def get_user_backup_codes(user_id: int, db: Session) -> list[mfa_backup_codes_contracts.BackupCodeRead]:
    """Return stored backup codes for an MFA status response."""
    return mfa_backup_codes_crud.get_user_backup_codes(user_id, db)


def create_backup_codes(
    user_id: int,
    password_hasher: credentials_contracts.SupportsHashPassword,
    db: Session,
) -> list[str]:
    """Generate and stage replacement backup codes."""
    return mfa_backup_codes_service.create_backup_codes(user_id, password_hasher, db)


def delete_user_backup_codes(user_id: int, db: Session) -> int:
    """Stage deletion of a user's backup codes."""
    return mfa_backup_codes_crud.delete_user_backup_codes(user_id, db)


def verify_and_consume_backup_code(
    user_id: int,
    code: str,
    password_verifier: credentials_contracts.SupportsVerifyPassword,
    db: Session,
) -> bool:
    """Verify and stage consumption of a backup code."""
    return mfa_backup_codes_service.verify_and_consume_backup_code(user_id, code, password_verifier, db)
