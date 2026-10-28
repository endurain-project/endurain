"""API-key lookup for request authentication."""

from sqlalchemy.orm import Session

import modules.auth.api_keys.crud as api_keys_crud
import modules.auth.api_keys.schema as api_keys_schema


def get_api_key_by_hash(key_hash: str, db: Session) -> api_keys_schema.UsersApiKeyRead | None:
    """Look up an API key by its hash."""
    return api_keys_crud.get_api_key_by_hash(key_hash, db)


def update_last_used(api_key_id: str, db: Session) -> None:
    """Stage the API key's last-used timestamp."""
    api_keys_crud.update_last_used(api_key_id, db)
