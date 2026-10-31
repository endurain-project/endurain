"""Operations exposed to authentication peers."""

from sqlalchemy.orm import Session

import core.pagination as core_pagination
import modules.auth.api_keys.crud as api_keys_crud
import modules.auth.api_keys.schema as api_keys_schema
import modules.auth.api_keys.service as api_keys_service
import modules.auth.api_keys.utils as api_keys_utils


def get_api_key_by_hash(key_hash: str, db: Session) -> api_keys_schema.UsersApiKeyRead | None:
    """Look up an API key by its hash."""
    return api_keys_service.get_api_key_by_hash(key_hash, db)


def update_last_used(api_key_id: str, db: Session) -> None:
    """Update the timestamp of an API key used for authentication."""
    api_keys_service.update_last_used(api_key_id, db)


def hash_api_key(raw_key: str) -> str:
    """Hash a raw API key."""
    return api_keys_utils.hash_api_key(raw_key)


def json_to_scopes(scopes_json: str) -> list[str]:
    """Decode the scopes stored on an API key."""
    return api_keys_utils.json_to_scopes(scopes_json)


def generate_api_key() -> str:
    """Generate a raw API key for account-security workflows."""
    return api_keys_utils.generate_api_key()


def validate_api_key_scopes(scopes: list[str]) -> None:
    """Validate requested scopes against the scopes an API key may hold."""
    api_keys_utils.validate_api_key_scopes(scopes)


def list_user_api_keys(user_id: int, page: core_pagination.PageParams, db: Session) -> api_keys_schema.UsersApiKeyPage:
    """Return one page of the API keys owned by a user."""
    return api_keys_service.list_user_api_keys(user_id, page, db)


def create_api_key(
    user_id: int,
    data: api_keys_schema.UsersApiKeyCreate,
    raw_key: str,
    db: Session,
) -> api_keys_schema.UsersApiKeyRead:
    """Stage a new API key for the account-security owner to commit."""
    return api_keys_crud.create_api_key(
        user_id,
        data,
        raw_key,
        api_keys_utils.hash_api_key(raw_key),
        api_keys_utils.scopes_to_json(data.scopes),
        db,
    )


def revoke_api_key(api_key_id: str, user_id: int, db: Session) -> None:
    """Stage revocation of a user's API key."""
    api_keys_crud.revoke_api_key(api_key_id, user_id, db)


def delete_api_key(api_key_id: str, user_id: int, db: Session) -> None:
    """Stage deletion of a user's API key."""
    api_keys_crud.delete_api_key(api_key_id, user_id, db)
