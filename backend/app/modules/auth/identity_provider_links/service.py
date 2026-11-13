"""Utility functions for user identity provider links."""

import uuid
from collections.abc import Sequence

from sqlalchemy.orm import Session

import core.key_rotation as core_key_rotation
import core.logger as core_logger
import modules.auth.identity_provider_links.contracts as auth_identity_links_contracts
import modules.auth.identity_provider_links.crud as identity_links_crud
import modules.auth.identity_provider_links.schema as auth_identity_links_schema
import modules.auth.sessions.integration_service as sessions_integration

logger = core_logger.get_logger(__name__)


def get_orphaned_idp_session_tokens_page(
    after_id: uuid.UUID | None, limit: int, db: Session, *, user_id: uuid.UUID | None = None
) -> tuple[list[auth_identity_links_contracts.IdpSessionTokenRead], uuid.UUID | None]:
    """Find the sign-ins in one window whose Endurain session no longer exists.

    Args:
        after_id: Keyset cursor; None reads from the first sign-in, otherwise only sign-ins with a greater id are read.
        limit: Maximum number of sign-ins to read.
        db: SQLAlchemy database session.
        user_id: Restrict the window to one user's sign-ins.

    Returns:
        The sign-ins without a session and the last id the window read, or None when no sign-in followed the
        cursor.
    """
    window = identity_links_crud.get_idp_session_tokens_page(after_id, limit, db, user_id=user_id)
    if not window:
        return [], None
    alive = sessions_integration.get_existing_session_ids([row.session_id for row in window], db)
    return [row for row in window if row.session_id not in alive], window[-1].id


def end_idp_sessions(user_id: uuid.UUID, idp_id: uuid.UUID, db: Session) -> int:
    """Stage the end of every session the user signed in to through the provider; the caller commits.

    The sessions go through the sessions surface, which publishes the revocation, so each sign-in's token is
    revoked at the provider afterwards.

    Args:
        user_id: The user whose sessions end.
        idp_id: The provider they signed in through.
        db: SQLAlchemy database session.

    Returns:
        How many sessions ended.
    """
    session_ids = identity_links_crud.get_idp_session_token_ids_by_user_and_idp(user_id, idp_id, db)
    return _end_live_sessions([(session_id, user_id) for session_id in session_ids], db).get(user_id, 0)


def end_all_idp_sessions(idp_id: uuid.UUID, db: Session) -> int:
    """Stage the end of every session signed in through the provider; the caller commits.

    The sessions go through the sessions surface, which publishes the revocation, so each sign-in's token is
    revoked at the provider afterwards.

    Args:
        idp_id: The provider whose sign-ins end.
        db: SQLAlchemy database session.

    Returns:
        How many sessions ended.
    """
    owners = identity_links_crud.get_idp_session_owners(idp_id, db)
    return sum(_end_live_sessions(owners, db).values())


def end_idp_sessions_by_sid(
    idp_id: uuid.UUID, idp_sid: str, db: Session, *, user_id: uuid.UUID | None = None
) -> dict[uuid.UUID, int]:
    """Stage the end of every session signed in through the provider under a provider session id; the caller commits.

    The sessions go through the sessions surface, which publishes the revocation, so each sign-in's token is
    revoked at the provider afterwards.

    Args:
        idp_id: The provider the sessions signed in through.
        idp_sid: The provider session id their ID token named.
        db: SQLAlchemy database session.
        user_id: End only this user's sessions.

    Returns:
        How many sessions ended, per user; a user with none ended is absent.
    """
    owners = identity_links_crud.get_idp_session_owners_by_sid(idp_id, idp_sid, db, user_id=user_id)
    return _end_live_sessions(owners, db)


def _end_live_sessions(owners: list[tuple[str, uuid.UUID]], db: Session) -> dict[uuid.UUID, int]:
    """Stage the end of the sessions that still exist among the given ones.

    A sign-in row outlives its session, and a session can end between the lookup and here, so a session that is
    already gone is skipped and not counted.

    Args:
        owners: ``(session_id, user_id)`` per session.
        db: SQLAlchemy database session.

    Returns:
        How many sessions ended, per user; a user with none ended is absent.
    """
    ended: dict[uuid.UUID, int] = {}
    for session_id, owner_id in owners:
        if sessions_integration.delete_session_if_present(session_id, owner_id, db):
            ended[owner_id] = ended.get(owner_id, 0) + 1
    return ended


def enrich_user_identity_providers(
    idp_links: list[auth_identity_links_contracts.IdentityLinkRead],
    idps: Sequence[auth_identity_links_contracts.IdentityProviderDetails],
    user_id: uuid.UUID,
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
            idp_name=idp.name,
            idp_slug=idp.slug,
            idp_icon=idp.icon,
            idp_icon_uploaded=idp.icon_uploaded,
            idp_provider_type=idp.provider_type,
        )

        enriched_links.append(link_data)

    return enriched_links


def reencrypt_stored_secrets(db: Session) -> None:
    """Re-encrypt this module's stored secrets under the first FERNET_KEY; does nothing while one key is configured.

    Args:
        db: SQLAlchemy database session.
    """
    core_key_rotation.reencrypt_in_batches(
        "identity_provider_links",
        lambda after_id, limit: identity_links_crud.stage_reencrypt_batch_session_tokens(after_id, limit, db),
        db,
    )
