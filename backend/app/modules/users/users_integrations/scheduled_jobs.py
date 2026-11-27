"""Scheduled re-encryption of integration secrets after the FERNET_KEY list changes."""

import core.database as core_database
import modules.users.users_integrations.service as user_integrations_service

REENCRYPT_LOCK_NAME = "users_integrations_reencrypt"


def reencrypt_stored_secrets() -> None:
    """Re-encrypt integration secrets under the first FERNET_KEY; does nothing while one key is configured."""
    with core_database.SessionLocal() as db:
        user_integrations_service.reencrypt_stored_secrets(db)
