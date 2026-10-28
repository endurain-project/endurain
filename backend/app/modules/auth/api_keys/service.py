"""API-key lifecycle and ownership decisions."""

from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import core.logger as core_logger
import modules.auth.api_keys.crud as api_keys_crud
import modules.auth.api_keys.schema as api_keys_schema
import modules.auth.api_keys.utils as api_keys_utils
import modules.users.users.integration_service as users_integration

logger = core_logger.get_logger(__name__)


def get_user_api_keys(user_id: int, db: Session) -> list[api_keys_schema.UsersApiKeyRead]:
    """List the user's API keys."""
    return api_keys_crud.get_api_keys_by_user_id(user_id, db)


def create_user_api_key(user_id: int, data: api_keys_schema.UsersApiKeyCreate, db: Session) -> api_keys_schema.UsersApiKeyCreated:
    """Create a user API key and return its raw secret once."""
    user = users_integration.get_user(user_id, db)
    if user is None:
        raise core_exceptions.NotFoundError("User not found")
    api_keys_utils.validate_api_key_scopes(data.scopes, user.access_type)

    raw_key = api_keys_utils.generate_api_key()
    api_key = api_keys_crud.create_api_key(
        user_id,
        data,
        raw_key,
        api_keys_utils.hash_api_key(raw_key),
        api_keys_utils.scopes_to_json(data.scopes),
        db,
    )
    db.commit()
    logger.info("API key created", extra=core_logger.context(user_id=user_id, api_key_id=api_key.id, name=data.name))
    return api_keys_schema.UsersApiKeyCreated(**api_key.model_dump(), key=raw_key)


def revoke_user_api_key(api_key_id: str, user_id: int, db: Session) -> None:
    """Revoke an API key owned by the user."""
    api_keys_crud.revoke_api_key(api_key_id, user_id, db)
    db.commit()
    logger.info("API key revoked", extra=core_logger.context(api_key_id=api_key_id, user_id=user_id))


def delete_user_api_key(api_key_id: str, user_id: int, db: Session) -> None:
    """Delete an API key owned by the user."""
    api_keys_crud.delete_api_key(api_key_id, user_id, db)
    db.commit()
    logger.info("API key deleted", extra=core_logger.context(api_key_id=api_key_id, user_id=user_id))


def get_api_key_by_hash(key_hash: str, db: Session) -> api_keys_schema.UsersApiKeyRead | None:
    """Look up an API key by its hash."""
    return api_keys_crud.get_api_key_by_hash(key_hash, db)


def update_last_used(api_key_id: str, db: Session) -> None:
    """Update and commit the API key's last-used timestamp."""
    api_keys_crud.update_last_used(api_key_id, db)
    db.commit()
