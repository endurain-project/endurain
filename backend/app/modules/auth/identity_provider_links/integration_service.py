"""Identity-provider link operations exposed to auth peers."""

from datetime import datetime

from sqlalchemy.orm import Session

import modules.auth.identity_provider_links.contracts as identity_link_contracts
import modules.auth.identity_provider_links.crud as identity_link_crud
import modules.auth.identity_provider_links.schema as identity_link_schema
import modules.auth.identity_provider_links.service as identity_link_service


def check_user_identity_providers_by_idp_id(idp_id: int, db: Session) -> bool:
    """Return whether an identity provider has linked users."""
    return identity_link_crud.check_user_identity_providers_by_idp_id(idp_id, db)


def get_user_identity_providers_by_user_id(user_id: int, db: Session) -> list[identity_link_contracts.IdentityLinkRead]:
    """Return the user's identity-provider links."""
    return identity_link_crud.get_user_identity_providers_by_user_id(user_id, db)


def get_user_identity_provider_by_user_id_and_idp_id(
    user_id: int, idp_id: int, db: Session
) -> identity_link_contracts.IdentityLinkRead | None:
    """Return a link for a user and identity provider."""
    return identity_link_crud.get_user_identity_provider_by_user_id_and_idp_id(user_id, idp_id, db)


def get_user_identity_provider_by_subject_and_idp_id(
    idp_id: int, idp_subject: str, db: Session
) -> identity_link_contracts.IdentityLinkRead | None:
    """Return a link matching an identity provider and subject."""
    return identity_link_crud.get_user_identity_provider_by_subject_and_idp_id(idp_id, idp_subject, db)


def create_user_identity_provider(
    user_id: int, idp_id: int, idp_subject: str, db: Session
) -> identity_link_contracts.IdentityLinkRead:
    """Stage a user-to-provider link."""
    return identity_link_crud.create_user_identity_provider(user_id, idp_id, idp_subject, db)


def update_user_identity_provider_last_login(
    user_id: int, idp_id: int, db: Session
) -> identity_link_contracts.IdentityLinkRead | None:
    """Stage an update to a link's last-login timestamp."""
    return identity_link_crud.update_user_identity_provider_last_login(user_id, idp_id, db)


def store_user_identity_provider_tokens(
    user_id: int, idp_id: int, encrypted_refresh_token: str, access_token_expires_at: datetime, db: Session
) -> identity_link_contracts.IdentityLinkRead | None:
    """Stage encrypted provider-token metadata on a link."""
    return identity_link_crud.store_user_identity_provider_tokens(
        user_id, idp_id, encrypted_refresh_token, access_token_expires_at, db
    )


def clear_user_identity_provider_refresh_token(user_id: int, idp_id: int, db: Session) -> bool:
    """Stage removal of stored provider-token metadata."""
    return identity_link_crud.clear_user_identity_provider_refresh_token_by_user_id_and_idp_id(user_id, idp_id, db)


def replace_user_identity_provider_tokens_if_unchanged(
    user_id: int,
    idp_id: int,
    expected_refresh_token: str,
    encrypted_refresh_token: str,
    access_token_expires_at: datetime,
    db: Session,
) -> bool:
    """Stage new provider-token metadata only while the link still holds the token that was read."""
    return identity_link_crud.replace_refresh_token_if_unchanged(
        user_id, idp_id, expected_refresh_token, encrypted_refresh_token, access_token_expires_at, db
    )


def clear_user_identity_provider_refresh_token_if_unchanged(
    user_id: int, idp_id: int, expected_refresh_token: str, db: Session
) -> bool:
    """Stage removal of provider-token metadata only while the link still holds the token that was read."""
    return identity_link_crud.clear_refresh_token_if_unchanged(user_id, idp_id, expected_refresh_token, db)


def delete_user_identity_provider(user_id: int, idp_id: int, db: Session) -> bool:
    """Stage deletion of a user's identity-provider link."""
    return identity_link_crud.delete_user_identity_provider(user_id, idp_id, db)


def get_identity_link_counts_for_users(user_ids: list[int], db: Session) -> dict[int, int]:
    """Return the number of identity-provider links for each matching user."""
    return identity_link_crud.get_identity_link_counts_for_users(user_ids, db)


def get_user_identity_provider_refresh_token_by_user_id_and_idp_id(
    user_id: int,
    idp_id: int,
    db: Session,
) -> str | None:
    """Return an encrypted provider refresh token, if one is stored."""
    return identity_link_service.get_user_identity_provider_refresh_token_by_user_id_and_idp_id(user_id, idp_id, db)


def enrich_user_identity_providers(
    idp_links: list[identity_link_contracts.IdentityLinkRead],
    idps: list[identity_link_contracts.IdentityProviderDetails],
    user_id: int,
) -> list[identity_link_schema.IdentityProviderLinkRead]:
    """Add resolved provider display fields to the user's links."""
    return identity_link_service.enrich_user_identity_providers(idp_links, idps, user_id)
