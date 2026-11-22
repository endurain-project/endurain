"""API-key lookup for request authentication."""

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

import core.database as core_database
import core.pagination as core_pagination
import modules.auth.api_keys.constants as api_keys_constants
import modules.auth.api_keys.crud as api_keys_crud
import modules.auth.api_keys.schema as api_keys_schema


def list_user_api_keys(
    user_id: uuid.UUID, page: core_pagination.PageParams, db: Session
) -> api_keys_schema.UserApiKeyPage:
    """Return one page of a user's API keys."""
    keys = api_keys_crud.get_api_keys_page(
        user_id,
        db,
        limit=page.num_records,
        offset=(page.page_number - 1) * page.num_records,
    )
    total = api_keys_crud.count_api_keys(user_id, db)
    return api_keys_schema.UserApiKeyPage.build(keys, total, page.page_number, page.num_records)


def get_api_key_by_hash(key_hash: str, db: Session) -> api_keys_schema.UserApiKeyRead | None:
    """Look up an API key by its hash."""
    return api_keys_crud.get_api_key_by_hash(key_hash, db)


def update_last_used(api_key_id: uuid.UUID, db: Session) -> None:
    """Stage the API key's last-used timestamp."""
    api_keys_crud.update_last_used(api_key_id, db)


def delete_stale_api_keys(db: Session) -> int:
    """Delete the keys revoked or expired longer ago than the retention, one batch per commit."""
    cutoff = datetime.now(UTC) - api_keys_constants.STALE_API_KEY_RETENTION
    return core_database.delete_in_batches(lambda limit: api_keys_crud.delete_stale_api_keys(cutoff, limit, db), db)
