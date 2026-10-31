"""MFA Backup Codes Module.

Persistence and helpers for one-time MFA backup codes used as a fallback
when a user's primary MFA device is unavailable. Codes are generated as
``XXXX-XXXX`` strings, stored only as Argon2 hashes, and consumed atomically
via the CRUD layer.

Exports:
    - CRUD: get_user_backup_codes, get_user_unused_backup_codes,
      create_backup_codes, mark_backup_code_as_used,
      delete_user_backup_codes
    - Schemas: MFABackupCodesResponse, MFABackupCodeStatus
    - Models: MFABackupCode (ORM model)
    - Utils: generate_backup_code, verify_and_consume_backup_code
"""

from .crud import (
    create_backup_codes,
    delete_user_backup_codes,
    get_user_backup_codes,
    get_user_unused_backup_codes,
    mark_backup_code_as_used,
)
from .models import MFABackupCode as MFABackupCodeModel
from .schema import MFABackupCodesResponse, MFABackupCodeStatus
from .utils import generate_backup_code, verify_and_consume_backup_code

__all__ = [
    # Database model
    "MFABackupCodeModel",
    "MFABackupCodeStatus",
    # Pydantic schemas
    "MFABackupCodesResponse",
    # CRUD operations
    "create_backup_codes",
    "delete_user_backup_codes",
    # Utilities
    "generate_backup_code",
    "get_user_backup_codes",
    "get_user_unused_backup_codes",
    "mark_backup_code_as_used",
    "verify_and_consume_backup_code",
]
