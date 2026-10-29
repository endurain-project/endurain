"""API-key lifecycle operations owned by account security."""

from sqlalchemy.orm import Session

import core.logger as core_logger
import core.pagination as core_pagination
import modules.auth.account_security.step_up_service as step_up_service
import modules.auth.account_security.step_up_store as step_up_store_module
import modules.auth.api_keys.integration_service as api_keys_integration
import modules.auth.api_keys.schema as api_keys_schema
import modules.users.users.integration_service as users_integration

logger = core_logger.get_logger(__name__)


def list_user_api_keys(user_id: int, page: core_pagination.PageParams, db: Session) -> api_keys_schema.UsersApiKeyPage:
    """Return one page of the user's API keys."""
    return api_keys_integration.list_user_api_keys(user_id, page, db)


def create_user_api_key(
    user_id: int,
    data: api_keys_schema.UsersApiKeyCreate,
    step_up_store: step_up_store_module.StepUpStore,
    db: Session,
) -> api_keys_schema.UsersApiKeyCreatedRead:
    """Verify step-up, stage a key, and commit it before returning its secret once."""
    step_up_service.verify_step_up_credentials(user_id, data.current_password, data.mfa_code, step_up_store, db)
    users_integration.require_user(user_id, db)
    api_keys_integration.validate_api_key_scopes(data.scopes)
    raw_key = api_keys_integration.generate_api_key()
    api_key = api_keys_integration.create_api_key(user_id, data, raw_key, db)
    db.commit()
    logger.info("API key created", extra=core_logger.context(user_id=user_id, api_key_id=api_key.id, name=data.name))
    return api_keys_schema.UsersApiKeyCreatedRead(**api_key.model_dump(), key=raw_key)


def revoke_user_api_key(api_key_id: str, user_id: int, db: Session) -> None:
    """Revoke an API key owned by the user."""
    api_keys_integration.revoke_api_key(api_key_id, user_id, db)
    db.commit()
    logger.info("API key revoked", extra=core_logger.context(api_key_id=api_key_id, user_id=user_id))


def delete_user_api_key(api_key_id: str, user_id: int, db: Session) -> None:
    """Delete an API key owned by the user."""
    api_keys_integration.delete_api_key(api_key_id, user_id, db)
    db.commit()
    logger.info("API key deleted", extra=core_logger.context(api_key_id=api_key_id, user_id=user_id))
