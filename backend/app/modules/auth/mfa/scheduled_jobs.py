"""Scheduled re-encryption of MFA secrets after the FERNET_KEY list changes."""

import core.database as core_database
import modules.auth.mfa.service as mfa_service

REENCRYPT_LOCK_NAME = "auth_mfa_reencrypt"


def reencrypt_stored_secrets() -> None:
    """Re-encrypt MFA secrets under the first FERNET_KEY; does nothing while one key is configured."""
    with core_database.SessionLocal() as db:
        mfa_service.reencrypt_stored_secrets(db)
