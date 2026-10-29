"""Auth-owned identity-provider link workflows exposed to profile routes."""

from __future__ import annotations

from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import core.logger as core_logger
import modules.auth.account_security.step_up_service as step_up_service
import modules.auth.account_security.step_up_store as account_security_step_up_store
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.identity_provider_link_tokens.integration_service as identity_provider_link_tokens_integration
import modules.auth.identity_provider_link_tokens.schema as idp_link_token_schema
import modules.auth.identity_provider_links.integration_service as identity_provider_links_integration
import modules.auth.identity_provider_links.schema as auth_identity_links_schema
import modules.auth.identity_providers.integration_service as identity_providers_integration
import modules.users.users.schema as users_schema

logger = core_logger.get_logger(__name__)


def generate_link_token(
    idp_id: int,
    link_request: idp_link_token_schema.IdpLinkTokenRequest,
    ip_address: str,
    token_user_id: int,
    step_up_store: account_security_step_up_store.StepUpStore,
    db: Session,
) -> idp_link_token_schema.IdentityProviderLinkTokenRead:
    """Generate a one-time IdP link token after step-up verification.

    Args:
        idp_id: The identity provider to link.
        link_request: Step-up credentials.
        ip_address: Client address the token is bound to.
        token_user_id: The authenticated user's ID.
        step_up_store: Step-up lockout store.
        db: Database session.

    Returns:
        The one-time link token and its expiry.

    Raises:
        NotFoundError: If the identity provider is missing or disabled.
        ConflictError: If the provider is already linked.
    """
    step_up_service.verify_step_up_credentials(
        token_user_id,
        link_request.current_password,
        link_request.mfa_code,
        step_up_store,
        db,
    )

    idp = identity_providers_integration.get_identity_provider(idp_id, db)
    if not idp or not idp.enabled:
        raise core_exceptions.NotFoundError("Identity provider not found or disabled")

    existing_link = identity_provider_links_integration.get_user_identity_provider_by_user_id_and_idp_id(
        token_user_id,
        idp_id,
        db,
    )
    if existing_link:
        raise core_exceptions.ConflictError(f"Identity provider {idp.name} is already linked to your account")

    link_token = identity_provider_link_tokens_integration.generate_idp_link_token(
        user_id=token_user_id,
        idp_id=idp_id,
        ip_address=ip_address,
        db=db,
    )
    db.commit()

    logger.debug(
        "Generated link token for user <token_user_id>, idp_id=<idp_id> (<name>)",
        extra=core_logger.context(token_user_id=token_user_id, idp_id=idp_id, name=idp.name),
    )

    return link_token


def delete_identity_provider_link(
    idp_id: int,
    step_up: users_schema.StepUpVerification,
    token_user_id: int,
    step_up_store: account_security_step_up_store.StepUpStore,
    db: Session,
) -> None:
    """Unlink an IdP while enforcing anti-lockout checks."""
    step_up_service.verify_step_up_credentials(
        token_user_id,
        step_up.current_password,
        step_up.mfa_code,
        step_up_store,
        db,
    )

    idp = identity_providers_integration.get_identity_provider(idp_id, db)
    if idp is None:
        raise core_exceptions.NotFoundError(f"Identity provider with id {idp_id} not found")

    link = identity_provider_links_integration.get_user_identity_provider_by_user_id_and_idp_id(
        token_user_id,
        idp_id,
        db,
    )
    if not link:
        raise core_exceptions.NotFoundError(f"Identity provider {idp.name} is not linked to your account")

    all_idp_links = identity_provider_links_integration.get_user_identity_providers_by_user_id(
        token_user_id,
        db,
    )
    remaining_idp_count = len(all_idp_links) - 1

    if not credentials_integration.has_local_password(token_user_id, db) and remaining_idp_count == 0:
        raise core_exceptions.InvalidInputError(
            "Cannot unlink last authentication method. Please set a password first."
        )

    success = identity_provider_links_integration.delete_user_identity_provider(
        token_user_id,
        idp_id,
        db,
    )

    if not success:
        raise core_exceptions.ProcessingError("Failed to unlink identity provider")
    db.commit()

    logger.info(
        "User <token_user_id> unlinked IdP: idp_id=<idp_id> (<name>)",
        extra=core_logger.context(token_user_id=token_user_id, idp_id=idp_id, name=idp.name),
    )


def admin_delete_identity_provider_link(
    user_id: int,
    idp_id: int,
    db: Session,
) -> None:
    """Stage the unlinking of an IdP from a user as an administrator; the caller commits.

    Unlike :func:`delete_identity_provider_link`, this is an
    administrative action against another user's account: it does not
    require step-up verification from the caller (authorization is
    enforced by the ``users:write`` scope on the route).

    Args:
        user_id: ID of the user to unlink the IdP from.
        idp_id: ID of the identity provider to unlink.
        db: Database session.

    Returns:
        None.

    Raises:
        DomainError: 404 if the IdP or the user-IdP link does not
            exist, 400 if unlinking would remove the user's last
            authentication method, 500 if the deletion fails at the
            database level.
    """
    idp = identity_providers_integration.get_identity_provider(idp_id, db)
    if idp is None:
        raise core_exceptions.NotFoundError(f"Identity provider with id {idp_id} not found")

    link = identity_provider_links_integration.get_user_identity_provider_by_user_id_and_idp_id(
        user_id,
        idp_id,
        db,
    )
    if not link:
        raise core_exceptions.NotFoundError(f"Identity provider {idp.name} is not linked to this user")

    all_idp_links = identity_provider_links_integration.get_user_identity_providers_by_user_id(
        user_id,
        db,
    )
    remaining_idp_count = len(all_idp_links) - 1

    has_local_password = credentials_integration.has_local_password(user_id, db)
    if not has_local_password and remaining_idp_count == 0:
        raise core_exceptions.InvalidInputError("Cannot unlink last authentication method. User has no password set.")

    success = identity_provider_links_integration.delete_user_identity_provider(user_id, idp_id, db)
    if not success:
        raise core_exceptions.ProcessingError("Failed to unlink identity provider")

    logger.info(
        "Admin unlinked IdP for user <user_id>: idp_id=<idp_id> (<name>)",
        extra=core_logger.context(user_id=user_id, idp_id=idp_id, name=idp.name),
    )


def get_user_identity_provider_links(
    user_id: int,
    db: Session,
) -> list[auth_identity_links_schema.IdentityProviderLinkRead]:
    """Return enriched identity provider links for the authenticated user."""
    idp_links = identity_provider_links_integration.get_user_identity_providers_by_user_id(user_id, db)
    return identity_providers_integration.enrich_user_identity_providers(idp_links, user_id, db)


def validate_and_claim_browser_link_token(
    link_token: str,
    idp_id: int,
    client_ip: str | None,
    db: Session,
) -> int:
    """Validate, IP-check, and atomically claim a browser-redirect link token.

    Encapsulates all auth-owned CRUD operations (identity_provider_link_tokens_integration and
    identity_provider_links_integration) so that the browser redirect router does not import
    low-level auth persistence modules directly.

    Args:
        link_token: Plaintext one-time link token from query parameter.
        idp_id: The identity provider ID expected in the token.
        client_ip: Caller IP address for soft IP-match check.
        db: SQLAlchemy database session.

    Returns:
        The user ID encoded in the token.

    Raises:
        DomainError: 401 if token is invalid, expired, or IdP mismatch.
        DomainError: 400 if token was already used (race/replay).
        DomainError: 409 if the IdP is already linked to the user.
    """
    link_token_hash = identity_provider_link_tokens_integration.hash_idp_link_token(link_token)
    db_token = identity_provider_link_tokens_integration.get_idp_link_token_by_hash(link_token_hash, db)
    if not db_token:
        logger.warning("IdP link refused: unknown or expired link token", extra=core_logger.context(idp_id=idp_id))
        raise core_exceptions.UnauthenticatedError("Invalid or expired link token")

    if db_token.idp_id != idp_id:
        logger.warning(
            "Link token IdP mismatch: token idp_id=<idp_id>, requested idp_id=<idp_id_2>",
            extra=core_logger.context(idp_id=db_token.idp_id, idp_id_2=idp_id),
        )
        raise core_exceptions.UnauthenticatedError("Invalid link token for this identity provider")

    if db_token.ip_address and client_ip and db_token.ip_address != client_ip:
        logger.warning(
            "Link token IP mismatch: token ip=<ip_address>, request ip=<client_ip>",
            extra=core_logger.context(ip_address=db_token.ip_address, client_ip=client_ip),
        )
        # Soft check — log but don't fail (NAT, proxies, etc.)

    token_user_id = db_token.user_id
    existing_link = identity_provider_links_integration.get_user_identity_provider_by_user_id_and_idp_id(
        token_user_id, idp_id, db
    )
    if existing_link:
        idp = identity_providers_integration.get_identity_provider(idp_id, db)
        idp_name = idp.name if idp else f"ID {idp_id}"
        raise core_exceptions.ConflictError(f"Identity provider {idp_name} is already linked to your account")

    if not identity_provider_link_tokens_integration.mark_token_as_used(link_token_hash, db):
        logger.warning(
            "IdP link token replay/race rejected for user <token_user_id>: token row <id>",
            extra=core_logger.context(token_user_id=token_user_id, id=db_token.id),
        )
        raise core_exceptions.InvalidInputError("Invalid or expired link token")

    return token_user_id


def get_identity_link_counts_for_users(
    user_ids: list[int],
    db: Session,
) -> dict[int, int]:
    """Return identity link count per user ID in a single grouped query.

    Args:
        user_ids: List of user IDs to query.
        db: SQLAlchemy database session.

    Returns:
        Dict mapping user_id to link count.
        Users with no links are absent (callers should use .get(id, 0)).
    """
    return identity_provider_links_integration.get_identity_link_counts_for_users(user_ids, db)
