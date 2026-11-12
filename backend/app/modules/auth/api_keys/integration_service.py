"""Operations exposed to authentication peers."""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

import core.pagination as core_pagination
import modules.auth.api_keys.crud as api_keys_crud
import modules.auth.api_keys.schema as api_keys_schema
import modules.auth.api_keys.service as api_keys_service
import modules.auth.api_keys.utils as api_keys_utils


def get_api_key_by_hash(key_hash: str, db: Session) -> api_keys_schema.UserApiKeyRead | None:
    """Look up an API key by its hash."""
    return api_keys_service.get_api_key_by_hash(key_hash, db)


def update_last_used(api_key_id: str, db: Session) -> None:
    """Update the timestamp of an API key used for authentication."""
    api_keys_service.update_last_used(api_key_id, db)


def hash_api_key(raw_key: str) -> str:
    """Hash a raw API key."""
    return api_keys_utils.hash_api_key(raw_key)


def generate_api_key() -> str:
    """Generate a raw API key for account-security workflows."""
    return api_keys_utils.generate_api_key()


def list_user_api_keys(user_id: int, page: core_pagination.PageParams, db: Session) -> api_keys_schema.UserApiKeyPage:
    """Return one page of the API keys owned by a user."""
    return api_keys_service.list_user_api_keys(user_id, page, db)


def create_api_key(
    user_id: int,
    data: api_keys_schema.UserApiKeyCreate,
    raw_key: str,
    expires_at: datetime,
    db: Session,
) -> api_keys_schema.UserApiKeyRead:
    """Stage a new API key expiring at ``expires_at`` for the account-security owner to commit."""
    return api_keys_crud.create_api_key(
        user_id,
        data,
        raw_key,
        api_keys_utils.hash_api_key(raw_key),
        api_keys_utils.scopes_to_json(data.scopes),
        expires_at,
        db,
    )


def count_active_api_keys(user_id: int, db: Session) -> int:
    """Return how many API keys a user holds that are not revoked and have not expired."""
    return api_keys_crud.count_active_api_keys(user_id, datetime.now(UTC), db)


def revoke_api_key(api_key_id: str, user_id: int, db: Session) -> None:
    """Stage revocation of a user's API key."""
    api_keys_crud.revoke_api_key(api_key_id, user_id, db)


def revoke_user_api_keys(user_id: int, db: Session) -> int:
    """Stage revocation of every active API key a user owns and return how many were revoked."""
    return api_keys_crud.revoke_all_api_keys_for_user(user_id, db)


def delete_api_key(api_key_id: str, user_id: int, db: Session) -> None:
    """Stage deletion of a user's API key."""
    api_keys_crud.delete_api_key(api_key_id, user_id, db)
