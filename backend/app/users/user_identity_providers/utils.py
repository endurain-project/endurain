"""Utility functions for user identity providers."""

from sqlalchemy.orm import Session

import core.logger as core_logger
import users.user_identity_providers.crud as user_idp_crud
import users.user_identity_providers.schema as user_idp_schema
import users.user_identity_providers.models as user_idp_models
import auth.identity_providers.crud as idp_crud


def get_user_identity_provider_refresh_token_by_user_id_and_idp_id(
    user_id: int,
    idp_id: int,
    db: Session,
) -> str | None:
    """
    Get encrypted refresh token for a user-IdP link.

    Convenience wrapper that retrieves the link and extracts
    the refresh token field. Caller must decrypt using Fernet.

    Args:
        user_id: The ID of the user.
        idp_id: The ID of the identity provider.
        db: SQLAlchemy database session.

    Returns:
        The encrypted refresh token if found, None otherwise.

    Raises:
        HTTPException: 500 error if database query fails.
    """
    db_link = user_idp_crud.get_user_identity_provider_by_user_id_and_idp_id(
        user_id,
        idp_id,
        db,
    )
    if db_link:
        return db_link.idp_refresh_token
    return None


def enrich_user_identity_providers(
    idp_links: list[user_idp_models.UserIdentityProvider],
    user_id: int,
    db: Session,
) -> list[user_idp_schema.UserIdentityProviderResponse]:
    """
    Enrich identity provider links with IDP details.

    Batch fetches all IDPs in a single query to avoid N+1
    query performance issues.

    Args:
        idp_links: List of user identity provider ORM objects.
        user_id: User ID for logging purposes.
        db: SQLAlchemy database session.

    Returns:
        List of enriched UserIdentityProviderResponse objects.
    """
    if not idp_links:
        return []

    # Batch fetch all IDPs at once (single query)
    idp_ids = [link.idp_id for link in idp_links]
    idps = idp_crud.get_identity_providers_by_ids(idp_ids, db)
    idp_map = {idp.id: idp for idp in idps}

    enriched_links: list[user_idp_schema.UserIdentityProviderResponse] = []

    for link in idp_links:
        idp = idp_map.get(link.idp_id)
        if idp is None:
            core_logger.print_to_log(
                f"IDP with id {link.idp_id} not found for user "
                f"{user_id}, skipping enrichment",
                "warning",
            )
            continue

        link_data = user_idp_schema.UserIdentityProviderResponse(
            id=link.id,
            user_id=link.user_id,
            idp_id=link.idp_id,
            idp_subject=link.idp_subject,
            linked_at=link.linked_at,
            last_login=link.last_login,
            idp_access_token_expires_at=link.idp_access_token_expires_at,
            idp_refresh_token_updated_at=link.idp_refresh_token_updated_at,
            idp_name=idp.name,
            idp_slug=idp.slug,
            idp_icon=idp.icon,
            idp_provider_type=idp.provider_type,
        )

        enriched_links.append(link_data)

    return enriched_links
