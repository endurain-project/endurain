"""Utility helpers for IdP link token generation and cleanup."""

import secrets
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy.orm import Session

import core.database as core_database
import core.logger as core_logger
import modules.auth.computation as token_hashing
import modules.auth.identity_provider_link_tokens.crud as idp_link_token_crud
import modules.auth.identity_provider_link_tokens.schema as idp_link_token_schema

logger = core_logger.get_logger(__name__)

# Token expiry duration in seconds
TOKEN_EXPIRY_SECONDS = 60


def hash_idp_link_token(token: str) -> str:
    """Hash an IdP link token for storage or lookup.

    Args:
        token: Plaintext link token.

    Returns:
        SHA-256 hexadecimal digest of the token.
    """
    return token_hashing.sha256_hex(token)


def generate_idp_link_token(
    user_id: int, idp_id: int, ip_address: str | None, db: Session
) -> idp_link_token_schema.IdentityProviderLinkTokenRead:
    """Generate a one-time, short-lived token for IdP linking.

    Args:
        user_id: The user ID linking the identity provider.
        idp_id: The identity provider ID being linked.
        ip_address: Client IP address for optional validation.
        db: Database session.

    Returns:
        IdentityProviderLinkTokenRead containing the token and expiration.
    """
    # Generate random token and store only its hash.
    token = secrets.token_urlsafe(32)
    token_hash = hash_idp_link_token(token)

    # Calculate expiration
    created_at = datetime.now(UTC)
    expires_at = created_at + timedelta(seconds=TOKEN_EXPIRY_SECONDS)

    # Create token data
    token_data = idp_link_token_schema.IdpLinkTokenCreate(
        id=str(uuid4()),
        token_hash=token_hash,
        user_id=user_id,
        idp_id=idp_id,
        created_at=created_at,
        expires_at=expires_at,
        used=False,
        ip_address=ip_address,
    )

    # Store in database
    db_token = idp_link_token_crud.create_idp_link_token(token_data, db)

    logger.debug("Generated identity-provider link token", extra=core_logger.context(user_id=user_id, idp_id=idp_id))

    return idp_link_token_schema.IdentityProviderLinkTokenRead(token=token, expires_at=db_token.expires_at)


def delete_expired_tokens(db: Session) -> int:
    """Delete expired one-time link tokens, one batch per commit."""
    now = datetime.now(UTC)
    return core_database.delete_in_batches(lambda limit: idp_link_token_crud.delete_expired_tokens(now, limit, db), db)
