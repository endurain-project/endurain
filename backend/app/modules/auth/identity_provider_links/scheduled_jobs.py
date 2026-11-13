"""Scheduled re-encryption of identity-provider refresh tokens after the FERNET_KEY list changes."""

import core.database as core_database
import modules.auth.identity_provider_links.service as identity_links_service

REENCRYPT_LOCK_NAME = "auth_identity_provider_links_reencrypt"


def reencrypt_stored_secrets() -> None:
    """Re-encrypt identity-provider refresh tokens under the first FERNET_KEY; does nothing while one key is configured."""
    with core_database.SessionLocal() as db:
        identity_links_service.reencrypt_stored_secrets(db)
