"""API-key lifecycle operations owned by account security."""

import uuid
from datetime import datetime

import jasil.audit as jasil_audit
from jasil.event_versioning import VersionedPayload
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import core.logger as core_logger
import core.pagination as core_pagination
import modules.auth.account_security.audit_actions as account_security_audit_actions
import modules.auth.account_security.event_publishers as account_security_event_publishers
import modules.auth.account_security.events as account_security_events
import modules.auth.account_security.step_up_service as step_up_service
import modules.auth.account_security.step_up_store as step_up_store_module
import modules.auth.api_keys.constants as api_keys_constants
import modules.auth.api_keys.integration_service as api_keys_integration
import modules.auth.api_keys.schema as api_keys_schema
import modules.auth.identity_providers.constants as identity_providers_constants
import modules.auth.schema as auth_schema
import modules.users.users.integration_service as users_integration

logger = core_logger.get_logger(__name__)


def _stage_key_audit(
    action: jasil_audit.AuditAction,
    api_key_id: uuid.UUID,
    user_id: uuid.UUID,
    db: Session,
    *,
    details: VersionedPayload | None = None,
) -> None:
    """Stage the audit row of a change to one of a user's API keys.

    Args:
        action: The audit action to record.
        api_key_id: ID of the key.
        user_id: ID of the key's owner.
        db: SQLAlchemy session.
        details: The row's details, when the action declares any.
    """
    jasil_audit.stage(
        db, action, target_type="api_key", target_id=str(api_key_id), target_owner_id=str(user_id), details=details
    )


def list_user_api_keys(
    user_id: uuid.UUID, page: core_pagination.PageParams, db: Session
) -> api_keys_schema.UserApiKeyPage:
    """Return one page of the user's API keys."""
    return api_keys_integration.list_user_api_keys(user_id, page, db)


def create_user_api_key(
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    data: api_keys_schema.UserApiKeyCreate,
    expires_at: datetime,
    step_up_store: step_up_store_module.StepUpStore,
    db: Session,
) -> api_keys_schema.UserApiKeyCreatedRead:
    """Verify step-up, stage a key expiring at ``expires_at``, and commit it before returning its secret once.

    The request schema has already refused unsupported scopes, and a user at the key limit is refused here, so
    neither request spends an identity-provider step-up ticket.

    Raises:
        ApiKeyLimitError: When the user already holds the most active keys.
    """
    if api_keys_integration.count_active_api_keys(user_id, db) >= api_keys_constants.MAX_ACTIVE_API_KEYS_PER_USER:
        raise core_exceptions.ApiKeyLimitError
    step_up_service.verify_step_up_credentials(
        user_id,
        data.step_up.current_password,
        data.step_up.mfa_code,
        step_up_store,
        db,
        idp_reauth=data.step_up.idp_reauth,
        session_id=session_id,
        action=identity_providers_constants.StepUpAction.API_KEY_CREATE,
    )
    users_integration.require_user(user_id, db)
    raw_key = api_keys_integration.generate_api_key()
    api_key = api_keys_integration.create_api_key(user_id, data, raw_key, expires_at, db)
    _stage_key_audit(
        account_security_audit_actions.API_KEY_CREATE,
        api_key.id,
        user_id,
        db,
        details=account_security_audit_actions.ApiKeyCreateDetails(scopes=list(data.scopes)),
    )
    account_security_event_publishers.publish_account_security_changed(
        user_id, account_security_events.AccountSecurityChange.API_KEY_CREATED, db
    )
    db.commit()
    logger.info("API key created", extra=core_logger.context(user_id=user_id, api_key_id=api_key.id, name=data.name))
    return api_keys_schema.UserApiKeyCreatedRead(**api_key.model_dump(), key=raw_key)


def revoke_user_api_key(api_key_id: uuid.UUID, user_id: uuid.UUID, db: Session) -> None:
    """Revoke an API key owned by the user."""
    api_keys_integration.revoke_api_key(api_key_id, user_id, db)
    _stage_key_audit(account_security_audit_actions.API_KEY_REVOKE, api_key_id, user_id, db)
    db.commit()
    logger.info("API key revoked", extra=core_logger.context(api_key_id=api_key_id, user_id=user_id))


def delete_user_api_key(api_key_id: uuid.UUID, user_id: uuid.UUID, db: Session) -> None:
    """Delete an API key owned by the user."""
    api_keys_integration.delete_api_key(api_key_id, user_id, db)
    _stage_key_audit(account_security_audit_actions.API_KEY_DELETE, api_key_id, user_id, db)
    db.commit()
    logger.info("API key deleted", extra=core_logger.context(api_key_id=api_key_id, user_id=user_id))


def list_api_keys_of_user(
    user_id: uuid.UUID, page: core_pagination.PageParams, db: Session
) -> api_keys_schema.UserApiKeyPage:
    """Return one page of another user's API keys, which the user must have.

    Raises:
        NotFoundError: When the user does not exist.
    """
    users_integration.require_user(user_id, db)
    return api_keys_integration.list_user_api_keys(user_id, page, db)


def _verify_admin_step_up(
    admin_id: uuid.UUID,
    session_id: uuid.UUID,
    step_up: auth_schema.StepUpVerification,
    step_up_store: step_up_store_module.StepUpStore,
    db: Session,
) -> None:
    """Verify the administrator's own step-up for revoking another user's API keys."""
    step_up_service.verify_step_up_credentials(
        admin_id,
        step_up.current_password,
        step_up.mfa_code,
        step_up_store,
        db,
        idp_reauth=step_up.idp_reauth,
        session_id=session_id,
        action=identity_providers_constants.StepUpAction.ADMIN_API_KEYS_REVOKE,
    )


def revoke_api_key_of_user(
    api_key_id: uuid.UUID,
    user_id: uuid.UUID,
    admin_id: uuid.UUID,
    session_id: uuid.UUID,
    step_up: auth_schema.StepUpVerification,
    step_up_store: step_up_store_module.StepUpStore,
    db: Session,
) -> None:
    """Verify the administrator's step-up, then revoke one API key of another user, notify its owner and commit.

    Args:
        api_key_id: ID of the key to revoke.
        user_id: The user who owns the key.
        admin_id: The authenticated administrator.
        session_id: The administrator's session, which the step-up is bound to.
        step_up: The administrator's step-up verification.
        step_up_store: Step-up lockout store.
        db: Database session.

    Raises:
        NotFoundError: When the user has no such key.
    """
    _verify_admin_step_up(admin_id, session_id, step_up, step_up_store, db)
    api_keys_integration.revoke_api_key(api_key_id, user_id, db)
    _stage_key_audit(account_security_audit_actions.API_KEY_REVOKE, api_key_id, user_id, db)
    account_security_event_publishers.publish_account_security_changed(
        user_id, account_security_events.AccountSecurityChange.API_KEYS_REVOKED_BY_ADMIN, db
    )
    db.commit()
    logger.info(
        "API key revoked by an administrator", extra=core_logger.context(api_key_id=api_key_id, user_id=user_id)
    )


def revoke_api_keys_of_user(
    user_id: uuid.UUID,
    admin_id: uuid.UUID,
    session_id: uuid.UUID,
    step_up: auth_schema.StepUpVerification,
    step_up_store: step_up_store_module.StepUpStore,
    db: Session,
) -> None:
    """Verify the administrator's step-up, then revoke every active API key of another user, notify them and commit.

    The owner is notified only when a key was revoked.

    Args:
        user_id: The user whose keys to revoke.
        admin_id: The authenticated administrator.
        session_id: The administrator's session, which the step-up is bound to.
        step_up: The administrator's step-up verification.
        step_up_store: Step-up lockout store.
        db: Database session.

    Raises:
        NotFoundError: When the user does not exist.
    """
    _verify_admin_step_up(admin_id, session_id, step_up, step_up_store, db)
    users_integration.require_user(user_id, db)
    revoked = api_keys_integration.revoke_user_api_keys(user_id, db)
    jasil_audit.stage(
        db,
        account_security_audit_actions.API_KEYS_REVOKE,
        target_type="user",
        target_id=str(user_id),
        target_owner_id=str(user_id),
        details=account_security_audit_actions.ApiKeysRevokedDetails(api_keys_revoked=revoked),
    )
    if revoked:
        account_security_event_publishers.publish_account_security_changed(
            user_id, account_security_events.AccountSecurityChange.API_KEYS_REVOKED_BY_ADMIN, db
        )
    db.commit()
    logger.info(
        "API keys revoked by an administrator", extra=core_logger.context(user_id=user_id, api_keys_revoked=revoked)
    )
