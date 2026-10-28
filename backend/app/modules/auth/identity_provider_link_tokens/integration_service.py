"""Identity-provider link-token operations exposed to auth peers."""

from sqlalchemy.orm import Session

import modules.auth.identity_provider_link_tokens.crud as idp_link_token_crud
import modules.auth.identity_provider_link_tokens.schema as idp_link_token_schema
import modules.auth.identity_provider_link_tokens.service as idp_link_token_service


def hash_idp_link_token(token: str) -> str:
    """Return the digest used to persist one-time link tokens."""
    return idp_link_token_service.hash_idp_link_token(token)


def generate_idp_link_token(
    user_id: int,
    idp_id: int,
    ip_address: str | None,
    db: Session,
) -> idp_link_token_schema.IdentityProviderLinkTokenRead:
    """Generate and stage a one-time link token."""
    return idp_link_token_service.generate_idp_link_token(user_id, idp_id, ip_address, db)


def get_idp_link_token_by_hash(token_hash: str, db: Session) -> idp_link_token_schema.IdpLinkTokenRead | None:
    """Return a matching, unused link-token DTO."""
    return idp_link_token_crud.get_idp_link_token_by_hash(token_hash, db)


def mark_token_as_used(token_hash: str, db: Session) -> bool:
    """Stage an atomic claim of an unused link token."""
    return idp_link_token_crud.mark_token_as_used(token_hash, db)
