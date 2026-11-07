"""Scheduled re-encryption of server-setting secrets after the FERNET_KEY list changes."""

import core.database as core_database
import modules.server_settings.service as server_settings_service

REENCRYPT_LOCK_NAME = "server_settings_reencrypt"


def reencrypt_stored_secrets() -> None:
    """Re-encrypt server-setting secrets under the first FERNET_KEY; does nothing while one key is configured."""
    with core_database.SessionLocal() as db:
        server_settings_service.reencrypt_stored_secrets(db)
