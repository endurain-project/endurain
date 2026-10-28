"""Backup-code row serialization."""

import modules.auth.mfa_backup_codes.contracts as mfa_backup_codes_contracts
import modules.auth.mfa_backup_codes.models as mfa_backup_codes_models


def to_read_schema(row: mfa_backup_codes_models.MFABackupCode) -> mfa_backup_codes_contracts.BackupCodeRead:
    """Convert a backup-code row to the internal verification contract."""
    return mfa_backup_codes_contracts.BackupCodeRead.model_validate(row)
