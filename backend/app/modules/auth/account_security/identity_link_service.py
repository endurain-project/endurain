"""Auth-owned identity-provider link workflows exposed to profile routes."""

from __future__ import annotations

import uuid

import jasil.audit as jasil_audit
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import core.logger as core_logger
import core.pagination as core_pagination
import modules.auth.account_security.audit_actions as account_security_audit_actions
import modules.auth.account_security.event_publishers as account_security_event_publishers
import modules.auth.account_security.events as account_security_events
import modules.auth.account_security.step_up_service as step_up_service
import modules.auth.account_security.step_up_store as account_security_step_up_store
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.identity_provider_links.integration_service as identity_provider_links_integration
import modules.auth.identity_provider_links.schema as auth_identity_links_schema
import modules.auth.identity_providers.constants as identity_providers_constants
import modules.auth.identity_providers.contracts as identity_providers_contracts
import modules.auth.identity_providers.integration_service as identity_providers_integration
import modules.auth.identity_providers.schema as identity_providers_schema
import modules.auth.schema as auth_schema
import modules.auth.security_generation.integration_service as security_generation_integration
import modules.auth.sessions.audit_actions as sessions_audit_actions
import modules.users.users.schema as users_schema

logger = core_logger.get_logger(__name__)


def start_idp_link(
    idp_id: uuid.UUID,
    link: users_schema.IdentityProviderLinkStart,
    client_ip: str,
    token_user_id: uuid.UUID,
    session_id: uuid.UUID,
    step_up_store: account_security_step_up_store.StepUpStore,
    db: Session,
) -> identity_providers_contracts.BrowserFlowStart:
    """Start linking an identity provider to the signed-in user's account, after step-up verification.

    The return path, the provider and the existing links are checked before step-up, so a refused request does
    not spend an identity-provider step-up ticket or count a step-up attempt. The OAuth state is committed before the provider URL is built, because
    building it may run OIDC discovery, a network call no open transaction may span.

    Args:
        idp_id: The identity provider to link.
        link: The frontend return path, the step-up verification and whether the completed link ends the other sessions.
        client_ip: Address of the client.
        token_user_id: The authenticated user's ID.
        session_id: The caller's session, kept when the completed link ends the user's other sessions.
        step_up_store: Step-up lockout store.
        db: Database session.

    Returns:
        The provider URL and the browser binding the route sets as a cookie.

    Raises:
        NotFoundError: If the identity provider is missing or disabled.
        ConflictError: If the provider is already linked.
        InvalidInputError: If the return path is not allowed.
    """
    identity_providers_integration.validate_redirect(link.redirect)
    # Read before the step-up is verified: a security change that commits during the verification must outdate the
    # state this link starts.
    security_generation = security_generation_integration.current_generation(token_user_id, db)
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

    step_up_service.verify_step_up_credentials(
        token_user_id,
        link.step_up.current_password,
        link.step_up.mfa_code,
        step_up_store,
        db,
        idp_reauth=link.step_up.idp_reauth,
        session_id=session_id,
        action=identity_providers_constants.StepUpAction.IDP_LINK,
    )

    # The callback runs without the caller's session, so the state carries the session that started the link and
    # whether the callback ends the others.
    staged = identity_providers_integration.stage_browser_link(
        token_user_id,
        idp_id,
        link.redirect,
        client_ip,
        session_id,
        link.revoke_other_sessions,
        db,
        security_generation=security_generation,
    )
    db.commit()
    logger.info(
        "Identity provider link started for user <token_user_id>: idp_id=<idp_id> (<name>)",
        extra=core_logger.context(token_user_id=token_user_id, idp_id=idp_id, name=idp.name),
    )
    return identity_providers_contracts.BrowserFlowStart(
        authorization_url=identity_providers_integration.authorization_url(staged),
        browser_binding=staged.browser_binding,
    )


def start_idp_step_up(
    idp_id: uuid.UUID,
    start: identity_providers_schema.StepUpStartRequest,
    client_ip: str,
    token_user_id: uuid.UUID,
    session_id: uuid.UUID,
    step_up_store: account_security_step_up_store.StepUpStore,
    db: Session,
) -> identity_providers_contracts.BrowserFlowStart:
    """Start the fresh identity-provider sign-in an account without a local password steps up with.

    The OAuth state is committed before the provider URL is built, because building it may run OIDC discovery,
    a network call no open transaction may span.

    Args:
        idp_id: The linked provider to sign in with again.
        start: The PKCE challenge, the operation and the return path.
        client_ip: Address of the client.
        token_user_id: The authenticated user's ID.
        session_id: The caller's session; the resulting ticket is valid only in it.
        step_up_store: Step-up lockout store.
        db: Database session.

    Returns:
        The provider URL and the browser binding the route sets as a cookie.

    Raises:
        TooManyRequestsError: If the session is locked out of step-up attempts.
        ConflictError: If the account has a local password.
        InvalidInputError: If the request or provider is unusable.
        NotFoundError: If the provider is missing, disabled or not linked to the user.
    """
    security_generation = security_generation_integration.current_generation(token_user_id, db)
    step_up_service.require_not_locked_out(token_user_id, session_id, step_up_store)
    if credentials_integration.has_local_password(token_user_id, db):
        logger.warning(
            "Identity-provider step-up refused for user <user_id>: the account has a local password",
            extra=core_logger.context(user_id=token_user_id),
        )
        raise core_exceptions.ConflictError("This account confirms sensitive changes with its password")
    staged = identity_providers_integration.stage_step_up(
        token_user_id,
        session_id,
        idp_id,
        start.action,
        start.code_challenge,
        start.redirect,
        client_ip,
        db,
        security_generation=security_generation,
    )
    db.commit()
    logger.debug("Identity-provider step-up state committed", extra=core_logger.context(user_id=token_user_id))
    return identity_providers_contracts.BrowserFlowStart(
        authorization_url=identity_providers_integration.authorization_url(staged),
        browser_binding=staged.browser_binding,
    )


def _stage_unlink(user_id: uuid.UUID, idp_id: uuid.UUID, db: Session) -> None:
    """Stage the audit rows and the event of an identity provider unlinked from an account.

    Every session the user signed in to through the provider ends with the link, which is audited as a
    session revocation of its own.

    Args:
        user_id: ID of the user whose account lost the link.
        idp_id: ID of the identity provider.
        db: Database session.
    """
    jasil_audit.stage(
        db,
        account_security_audit_actions.IDENTITY_LINK_UNLINK,
        target_type="user",
        target_id=str(user_id),
        target_owner_id=str(user_id),
        details=account_security_audit_actions.IdentityLinkDetails(idp_id=idp_id),
    )
    ended = identity_provider_links_integration.end_idp_sessions(user_id, idp_id, db)
    if ended:
        jasil_audit.stage(
            db,
            sessions_audit_actions.SESSION_REVOKE,
            target_type="user",
            target_id=str(user_id),
            target_owner_id=str(user_id),
            details=sessions_audit_actions.SessionsRevokedDetails(sessions_revoked=ended),
        )
    account_security_event_publishers.publish_account_security_changed(
        user_id, account_security_events.AccountSecurityChange.IDENTITY_PROVIDER_UNLINKED, db, idp_id=idp_id
    )


def delete_identity_provider_link(
    idp_id: uuid.UUID,
    step_up: auth_schema.StepUpVerification,
    token_user_id: uuid.UUID,
    session_id: uuid.UUID,
    step_up_store: account_security_step_up_store.StepUpStore,
    db: Session,
) -> None:
    """Unlink an IdP while enforcing anti-lockout checks.

    The provider, the link and the last-sign-in-method rule are checked before step-up, so a refused request
    does not spend an identity-provider step-up ticket.
    """
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
        raise core_exceptions.LastSignInMethodError(
            "Cannot unlink last authentication method. Link another identity provider first."
        )

    step_up_service.verify_step_up_credentials(
        token_user_id,
        step_up.current_password,
        step_up.mfa_code,
        step_up_store,
        db,
        idp_reauth=step_up.idp_reauth,
        session_id=session_id,
        action=identity_providers_constants.StepUpAction.IDP_UNLINK,
    )

    security_generation_integration.stage_bump(token_user_id, db)
    success = identity_provider_links_integration.delete_user_identity_provider(
        token_user_id,
        idp_id,
        db,
    )

    if not success:
        raise core_exceptions.ProcessingError("Failed to unlink identity provider")
    _stage_unlink(token_user_id, idp_id, db)
    db.commit()

    logger.info(
        "User <token_user_id> unlinked IdP: idp_id=<idp_id> (<name>)",
        extra=core_logger.context(token_user_id=token_user_id, idp_id=idp_id, name=idp.name),
    )


def admin_delete_identity_provider_link(
    user_id: uuid.UUID,
    idp_id: uuid.UUID,
    db: Session,
) -> None:
    """Stage the unlinking of an IdP from a user as an administrator; the caller commits.

    Unlike :func:`delete_identity_provider_link`, this is an
    administrative action against another user's account: it does not
    verify step-up itself. The users service verifies the administrator's
    own step-up before it calls this.

    Args:
        user_id: ID of the user to unlink the IdP from.
        idp_id: ID of the identity provider to unlink.
        db: Database session.

    Returns:
        None.

    Raises:
        DomainError: 404 if the IdP or the user-IdP link does not
            exist, 409 if unlinking would remove the user's last
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
        raise core_exceptions.LastSignInMethodError(
            "Cannot unlink last authentication method. User has no password set."
        )

    security_generation_integration.stage_bump(user_id, db)
    success = identity_provider_links_integration.delete_user_identity_provider(user_id, idp_id, db)
    if not success:
        raise core_exceptions.ProcessingError("Failed to unlink identity provider")
    _stage_unlink(user_id, idp_id, db)

    logger.info(
        "Admin unlinked IdP for user <user_id>: idp_id=<idp_id> (<name>)",
        extra=core_logger.context(user_id=user_id, idp_id=idp_id, name=idp.name),
    )


def get_user_identity_provider_links(
    user_id: uuid.UUID,
    page: core_pagination.PageParams,
    db: Session,
) -> auth_identity_links_schema.IdentityProviderLinkPage:
    """Return one page of a user's identity provider links, enriched with provider details."""
    idp_links = identity_provider_links_integration.get_identity_links_page(
        user_id, db, limit=page.num_records, offset=(page.page_number - 1) * page.num_records
    )
    total = identity_provider_links_integration.count_identity_links(user_id, db)
    return auth_identity_links_schema.IdentityProviderLinkPage.build(
        identity_providers_integration.enrich_user_identity_providers(idp_links, user_id, db),
        total,
        page.page_number,
        page.num_records,
    )


def get_identity_link_counts_for_users(
    user_ids: list[uuid.UUID],
    db: Session,
) -> dict[uuid.UUID, int]:
    """Return identity link count per user ID in a single grouped query.

    Args:
        user_ids: List of user IDs to query.
        db: SQLAlchemy database session.

    Returns:
        Dict mapping user_id to link count.
        Users with no links are absent (callers should use .get(id, 0)).
    """
    return identity_provider_links_integration.get_identity_link_counts_for_users(user_ids, db)
