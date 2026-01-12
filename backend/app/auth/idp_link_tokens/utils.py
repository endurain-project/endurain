import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

import auth.idp_link_tokens.crud as idp_link_token_crud
import auth.idp_link_tokens.schema as idp_link_token_schema

import core.database as core_database
import core.logger as core_logger


# Token expiry duration in seconds
TOKEN_EXPIRY_SECONDS = 60


def generate_idp_link_token(
    user_id: int, idp_id: int, ip_address: str | None, db: Session
) -> idp_link_token_schema.IdpLinkTokenResponse:
    """
    Generate a one-time, short-lived token for IdP linking.

    Args:
        user_id: The user ID linking the identity provider.
        idp_id: The identity provider ID being linked.
        ip_address: Client IP address for optional validation.
        db: Database session.

    Returns:
        IdpLinkTokenResponse containing the token and expiration.
    """
    # Generate random token
    token_id = secrets.token_urlsafe(32)

    # Calculate expiration
    created_at = datetime.now(timezone.utc)
    expires_at = created_at + timedelta(seconds=TOKEN_EXPIRY_SECONDS)

    # Create token data
    token_data = idp_link_token_schema.IdpLinkTokenCreate(
        id=token_id,
        user_id=user_id,
        idp_id=idp_id,
        created_at=created_at,
        expires_at=expires_at,
        used=False,
        ip_address=ip_address,
    )

    # Store in database
    db_token = idp_link_token_crud.create_idp_link_token(token_data, db)

    core_logger.print_to_log(
        f"Generated IdP link token for user {user_id}, idp {idp_id} (expires in {TOKEN_EXPIRY_SECONDS}s)",
        "debug",
    )

    return idp_link_token_schema.IdpLinkTokenResponse(
        token=db_token.id, expires_at=db_token.expires_at
    )


def delete_idp_link_expired_tokens_from_db() -> None:
    """
    Remove expired IdP link tokens from the database.

    Opens a new database session and deletes any expired IdP link tokens
    (older than 60 seconds). Logs the number of deleted tokens if one or
    more were removed.

    This function is designed to be run as a scheduled task on application
    startup to clean up expired one-time link tokens.

    Returns:
        None

    Notes:
        - IdP link tokens expire after 60 seconds (set during creation).
        - The operation is idempotent: running it repeatedly when there
          are no expired tokens will have no further effect.
    """
    with core_database.SessionLocal() as db:
        num_deleted = idp_link_token_crud.delete_expired_tokens(db)

        if num_deleted > 0:
            core_logger.print_to_log(
                f"Deleted {num_deleted} expired IdP link token(s) from database",
                "info",
            )
