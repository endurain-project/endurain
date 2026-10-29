"""Persistence operations for API keys."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import modules.auth.api_keys.models as api_keys_models
import modules.auth.api_keys.schema as api_keys_schema
import modules.auth.api_keys.serializers as api_keys_serializers


def get_api_keys_page(
    user_id: int,
    db: Session,
    *,
    limit: int,
    offset: int,
) -> list[api_keys_schema.UsersApiKeyRead]:
    """Return one window of an owner's API keys, newest first with the id as tiebreak."""
    stmt = (
        select(api_keys_models.UsersApiKeys)
        .where(api_keys_models.UsersApiKeys.user_id == user_id)
        .order_by(api_keys_models.UsersApiKeys.created_at.desc(), api_keys_models.UsersApiKeys.id)
        .limit(limit)
        .offset(offset)
    )
    rows = db.execute(stmt).scalars()
    return [api_keys_serializers.to_read_schema(row) for row in rows]


def count_api_keys(user_id: int, db: Session) -> int:
    """Return how many API keys an owner has."""
    return db.execute(
        select(func.count(api_keys_models.UsersApiKeys.id)).where(api_keys_models.UsersApiKeys.user_id == user_id)
    ).scalar_one()


def get_api_key_by_id(api_key_id: str, user_id: int, db: Session) -> api_keys_schema.UsersApiKeyRead | None:
    """Return an API key by ID and owner."""
    stmt = select(api_keys_models.UsersApiKeys).where(
        api_keys_models.UsersApiKeys.id == api_key_id,
        api_keys_models.UsersApiKeys.user_id == user_id,
    )
    row = db.execute(stmt).scalar_one_or_none()
    return api_keys_serializers.to_read_schema(row) if row is not None else None


def get_api_key_by_hash(key_hash: str, db: Session) -> api_keys_schema.UsersApiKeyRead | None:
    """Return an API key by its SHA-256 hash."""
    stmt = select(api_keys_models.UsersApiKeys).where(api_keys_models.UsersApiKeys.key_hash == key_hash)
    row = db.execute(stmt).scalar_one_or_none()
    return api_keys_serializers.to_read_schema(row) if row is not None else None


def create_api_key(
    user_id: int,
    data: api_keys_schema.UsersApiKeyCreate,
    raw_key: str,
    key_hash: str,
    scopes_json: str,
    db: Session,
) -> api_keys_schema.UsersApiKeyRead:
    """Stage a new API key and return its raw value and safe representation."""
    db_api_key = api_keys_models.UsersApiKeys(
        id=str(uuid.uuid4()),
        user_id=user_id,
        name=data.name,
        key_prefix=raw_key[9:17],
        key_hash=key_hash,
        scopes=scopes_json,
        expires_at=data.expires_at,
        last_used_at=None,
        created_at=datetime.now(UTC),
        is_active=True,
    )
    db.add(db_api_key)
    db.flush()
    return api_keys_serializers.to_read_schema(db_api_key)


def update_last_used(api_key_id: str, db: Session) -> None:
    """Stage the last-used timestamp for an API key."""
    row = db.get(api_keys_models.UsersApiKeys, api_key_id)
    if row is None:
        raise core_exceptions.NotFoundError(f"API key {api_key_id} not found")
    row.last_used_at = datetime.now(UTC)
    db.flush()


def revoke_api_key(api_key_id: str, user_id: int, db: Session) -> None:
    """Stage revocation of an API key owned by the user."""
    row = db.execute(
        select(api_keys_models.UsersApiKeys).where(
            api_keys_models.UsersApiKeys.id == api_key_id,
            api_keys_models.UsersApiKeys.user_id == user_id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise core_exceptions.NotFoundError(f"API key {api_key_id} not found for user {user_id}")
    row.is_active = False
    db.flush()


def delete_api_key(api_key_id: str, user_id: int, db: Session) -> None:
    """Stage deletion of an API key owned by the user."""
    result = db.execute(
        delete(api_keys_models.UsersApiKeys).where(
            api_keys_models.UsersApiKeys.id == api_key_id,
            api_keys_models.UsersApiKeys.user_id == user_id,
        )
    )
    if result.rowcount == 0:
        raise core_exceptions.NotFoundError(f"API key {api_key_id} not found for user {user_id}")
    db.flush()
