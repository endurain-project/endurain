"""API-key lookup for request authentication."""

from sqlalchemy.orm import Session

import core.pagination as core_pagination
import modules.auth.api_keys.crud as api_keys_crud
import modules.auth.api_keys.schema as api_keys_schema


def list_user_api_keys(user_id: int, page: core_pagination.PageParams, db: Session) -> api_keys_schema.UsersApiKeyPage:
    """Return one page of a user's API keys."""
    keys = api_keys_crud.get_api_keys_page(
        user_id,
        db,
        limit=page.num_records,
        offset=(page.page_number - 1) * page.num_records,
    )
    total = api_keys_crud.count_api_keys(user_id, db)
    return api_keys_schema.UsersApiKeyPage.build(keys, total, page.page_number, page.num_records)


def get_api_key_by_hash(key_hash: str, db: Session) -> api_keys_schema.UsersApiKeyRead | None:
    """Look up an API key by its hash."""
    return api_keys_crud.get_api_key_by_hash(key_hash, db)


def update_last_used(api_key_id: str, db: Session) -> None:
    """Stage the API key's last-used timestamp."""
    api_keys_crud.update_last_used(api_key_id, db)
