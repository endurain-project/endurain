"""API-key lifecycle operations owned by account security."""

import jasil.audit as jasil_audit
from jasil.event_versioning import VersionedPayload
from sqlalchemy.orm import Session

import core.logger as core_logger
import core.pagination as core_pagination
import modules.auth.account_security.audit_actions as account_security_audit_actions
import modules.auth.account_security.event_publishers as account_security_event_publishers
import modules.auth.account_security.events as account_security_events
import modules.auth.account_security.step_up_service as step_up_service
import modules.auth.account_security.step_up_store as step_up_store_module
import modules.auth.api_keys.integration_service as api_keys_integration
import modules.auth.api_keys.schema as api_keys_schema
import modules.auth.identity_providers.constants as identity_providers_constants
import modules.users.users.integration_service as users_integration

logger = core_logger.get_logger(__name__)


def _stage_key_audit(
    action: jasil_audit.AuditAction,
    api_key_id: str,
    user_id: int,
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


def list_user_api_keys(user_id: int, page: core_pagination.PageParams, db: Session) -> api_keys_schema.UsersApiKeyPage:
    """Return one page of the user's API keys."""
    return api_keys_integration.list_user_api_keys(user_id, page, db)


def create_user_api_key(
    user_id: int,
    session_id: str,
    data: api_keys_schema.UsersApiKeyCreate,
    step_up_store: step_up_store_module.StepUpStore,
    db: Session,
) -> api_keys_schema.UsersApiKeyCreatedRead:
    """Verify step-up, stage a key, and commit it before returning its secret once.

    The scopes are checked before step-up, so a request refused for them does not spend an identity-provider
    step-up ticket.
    """
    api_keys_integration.validate_api_key_scopes(data.scopes)
    step_up_service.verify_step_up_credentials(
        user_id,
        data.current_password,
        data.mfa_code,
        step_up_store,
        db,
        idp_reauth=data.idp_reauth,
        session_id=session_id,
        action=identity_providers_constants.StepUpAction.API_KEY_CREATE,
    )
    users_integration.require_user(user_id, db)
    raw_key = api_keys_integration.generate_api_key()
    api_key = api_keys_integration.create_api_key(user_id, data, raw_key, db)
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
    return api_keys_schema.UsersApiKeyCreatedRead(**api_key.model_dump(), key=raw_key)


def revoke_user_api_key(api_key_id: str, user_id: int, db: Session) -> None:
    """Revoke an API key owned by the user."""
    api_keys_integration.revoke_api_key(api_key_id, user_id, db)
    _stage_key_audit(account_security_audit_actions.API_KEY_REVOKE, api_key_id, user_id, db)
    db.commit()
    logger.info("API key revoked", extra=core_logger.context(api_key_id=api_key_id, user_id=user_id))


def delete_user_api_key(api_key_id: str, user_id: int, db: Session) -> None:
    """Delete an API key owned by the user."""
    api_keys_integration.delete_api_key(api_key_id, user_id, db)
    _stage_key_audit(account_security_audit_actions.API_KEY_DELETE, api_key_id, user_id, db)
    db.commit()
    logger.info("API key deleted", extra=core_logger.context(api_key_id=api_key_id, user_id=user_id))
