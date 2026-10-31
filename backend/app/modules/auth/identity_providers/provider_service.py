"""Administration of identity-provider configuration."""

import jasil.providers as platform_providers
from sqlalchemy.orm import Session

import core.etag as core_etag
import core.exceptions as core_exceptions
import core.logger as core_logger
import modules.auth.identity_provider_links.integration_service as identity_provider_links_integration
import modules.auth.identity_providers.crud as idp_crud
import modules.auth.identity_providers.icon_service as idp_icon_service
import modules.auth.identity_providers.schema as identity_provider_schema
import modules.auth.identity_providers.serializers as identity_provider_serializers
import modules.auth.identity_providers.utils as identity_provider_utils

logger = core_logger.get_logger(__name__)


def list_identity_providers(db: Session) -> list[identity_provider_schema.IdentityProviderRead]:
    """List configured providers for the admin interface."""
    return [identity_provider_serializers.to_read_schema(state) for state in idp_crud.get_all_identity_providers(db)]


def get_enabled_identity_providers(db: Session) -> list[identity_provider_schema.IdentityProviderPublicRead]:
    """Return public fields for enabled identity providers."""
    return [
        identity_provider_schema.IdentityProviderPublicRead(
            id=state.id, name=state.name, slug=state.slug, icon=state.icon, icon_uploaded=state.icon_uploaded
        )
        for state in idp_crud.get_enabled_identity_providers(db)
    ]


def get_idp_templates() -> list[identity_provider_schema.IdentityProviderTemplateRead]:
    """Return the configured provider templates."""
    return identity_provider_utils.get_idp_templates()


def create_identity_provider(
    data: identity_provider_schema.IdentityProviderCreate, db: Session
) -> identity_provider_schema.IdentityProviderRead:
    """Create a provider after checking its normalized slug."""
    slug = data.slug.lower()
    if idp_crud.get_identity_provider_by_slug(slug, db) is not None:
        raise core_exceptions.ConflictError(f"Identity provider with slug '{slug}' already exists")
    state = idp_crud.create_identity_provider(data, db)
    db.commit()
    logger.info("Created identity provider", extra=core_logger.context(idp_id=state.id))
    return identity_provider_serializers.to_read_schema(state)


def update_identity_provider(
    idp_id: int,
    data: identity_provider_schema.IdentityProviderUpdate,
    db: Session,
    *,
    if_match: str,
) -> identity_provider_schema.IdentityProviderRead:
    """Update a provider only when the client's version is current.

    Args:
        idp_id: Identity-provider row to update.
        data: Replacement fields.
        db: Database session.
        if_match: Version tag the client read.

    Returns:
        The updated provider.

    Raises:
        NotFoundError: When the provider is missing or removed during the update.
        PreconditionFailedError: When the provider changed since the client read it.
        ConflictError: When the new slug is already in use.
    """
    current = idp_crud.get_identity_provider(idp_id, db)
    if current is None:
        raise core_exceptions.NotFoundError("Identity provider not found")
    values = data.model_dump(exclude_unset=True)
    slug = values.get("slug")
    if slug and slug.lower() != current.slug and idp_crud.get_identity_provider_by_slug(slug.lower(), db):
        raise core_exceptions.ConflictError(f"Identity provider with slug '{slug.lower()}' already exists")
    with core_etag.refuse_stale_write(
        db,
        "identity provider",
        lambda: idp_crud.identity_provider_exists(idp_id, db),
        "Identity provider not found",
    ):
        state = idp_crud.update_identity_provider(idp_id, data, db, if_match=if_match)
        if state is None:
            raise core_exceptions.NotFoundError("Identity provider not found")
        db.commit()
    logger.info("Updated identity provider", extra=core_logger.context(idp_id=state.id))
    return identity_provider_serializers.to_read_schema(state)


def delete_identity_provider(
    idp_id: int, storage: platform_providers.StorageProvider, db: Session, *, if_match: str
) -> None:
    """Delete an unlinked provider, commit the change and remove its uploaded icon.

    Args:
        idp_id: The provider to delete.
        storage: The platform storage provider.
        db: Database session.
        if_match: The ``If-Match`` precondition.

    Raises:
        NotFoundError: If the provider does not exist.
        ConflictError: If users are still linked to the provider.
        PreconditionFailedError: If the provider changed since the client read it.
    """
    current = idp_crud.get_identity_provider(idp_id, db)
    if current is None:
        raise core_exceptions.NotFoundError("Identity provider not found")
    if identity_provider_links_integration.check_user_identity_providers_by_idp_id(idp_id, db):
        raise core_exceptions.ConflictError("Cannot delete identity provider with linked users")
    with core_etag.refuse_stale_write(
        db,
        "identity provider",
        lambda: idp_crud.identity_provider_exists(idp_id, db),
        "Identity provider not found",
    ):
        if not idp_crud.delete_identity_provider(idp_id, db, if_match=if_match):
            raise core_exceptions.NotFoundError("Identity provider not found")
        db.commit()
    if current.icon_uploaded:
        idp_icon_service.delete_blob(idp_id, storage)
    logger.info("Deleted identity provider", extra=core_logger.context(idp_id=idp_id))
