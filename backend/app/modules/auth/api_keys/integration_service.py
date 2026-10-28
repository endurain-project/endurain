"""Operations exposed to authentication peers."""

from sqlalchemy.orm import Session

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
