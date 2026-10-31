"""Utility functions for user identity provider links."""

from sqlalchemy.orm import Session

import core.logger as core_logger
import modules.auth.identity_provider_links.contracts as auth_identity_links_contracts
import modules.auth.identity_provider_links.integration_service as identity_provider_links_integration
import modules.auth.identity_provider_links.schema as auth_identity_links_schema

logger = core_logger.get_logger(__name__)


def get_user_identity_provider_refresh_token_by_user_id_and_idp_id(
    user_id: int,
    idp_id: int,
    db: Session,
) -> str | None:
    """Get encrypted refresh token for a user-IdP link.

    Convenience wrapper that retrieves the link and extracts
    the refresh token field. Caller must decrypt using Fernet.

    Args:
        user_id: The ID of the user.
        idp_id: The ID of the identity provider.
        db: SQLAlchemy database session.

    Returns:
        The encrypted refresh token if found, None otherwise.

    Raises:
        ProcessingError: If the database query fails.
    """
    db_link = identity_provider_links_integration.get_user_identity_provider_by_user_id_and_idp_id(
        user_id,
        idp_id,
        db,
    )
    if db_link:
        return db_link.idp_refresh_token
    return None


def enrich_user_identity_providers(
    idp_links: list[auth_identity_links_contracts.IdentityLinkRead],
    idps: list[auth_identity_links_contracts.IdentityProviderDetails],
    user_id: int,
) -> list[auth_identity_links_schema.IdentityProviderLinkRead]:
    """Enrich identity provider links with IDP details.

    Batch fetches all IDPs in a single query to avoid N+1
    query performance issues.

    Args:
        idp_links: List of user identity provider ORM objects.
        user_id: User ID for logging purposes.
        db: SQLAlchemy database session.
        idps: Identity providers to enrich.

    Returns:
        List of enriched IdentityProviderLinkRead objects.
    """
    if not idp_links:
        return []

    idp_map = {idp.id: idp for idp in idps}

    enriched_links: list[auth_identity_links_schema.IdentityProviderLinkRead] = []

    for link in idp_links:
        idp = idp_map.get(link.idp_id)
        if idp is None:
            logger.warning(
                "Identity provider not found while enriching user links",
                extra=core_logger.context(user_id=user_id, idp_id=link.idp_id),
            )
            continue

        link_data = auth_identity_links_schema.IdentityProviderLinkRead(
            id=link.id,
            user_id=link.user_id,
            idp_id=link.idp_id,
            idp_subject=link.idp_subject,
            linked_at=link.linked_at,
            last_login=link.last_login,
            idp_access_token_expires_at=(link.idp_access_token_expires_at),
            idp_refresh_token_updated_at=(link.idp_refresh_token_updated_at),
            idp_name=idp.name,
            idp_slug=idp.slug,
            idp_icon=idp.icon,
            idp_icon_uploaded=idp.icon_uploaded,
            idp_provider_type=idp.provider_type,
        )

        enriched_links.append(link_data)

    return enriched_links
