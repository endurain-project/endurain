"""Persistence operations for API keys."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

import core.database as core_database
import core.exceptions as core_exceptions
import modules.auth.api_keys.models as api_keys_models
import modules.auth.api_keys.schema as api_keys_schema
import modules.auth.api_keys.serializers as api_keys_serializers


def get_api_keys_page(
    user_id: uuid.UUID,
    db: Session,
    *,
    limit: int,
    offset: int,
) -> list[api_keys_schema.UserApiKeyRead]:
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


def count_api_keys(user_id: uuid.UUID, db: Session) -> int:
    """Return how many API keys an owner has."""
    return db.execute(
        select(func.count(api_keys_models.UsersApiKeys.id)).where(api_keys_models.UsersApiKeys.user_id == user_id)
    ).scalar_one()


def count_active_api_keys(user_id: uuid.UUID, now: datetime, db: Session) -> int:
    """Return how many API keys an owner has that are not revoked and expire after ``now``."""
    model = api_keys_models.UsersApiKeys
    return db.execute(
        select(func.count(model.id)).where(model.user_id == user_id, model.is_active.is_(True), model.expires_at > now)
    ).scalar_one()


def get_api_key_by_id(api_key_id: str, user_id: uuid.UUID, db: Session) -> api_keys_schema.UserApiKeyRead | None:
    """Return an API key by ID and owner."""
    stmt = select(api_keys_models.UsersApiKeys).where(
        api_keys_models.UsersApiKeys.id == api_key_id,
        api_keys_models.UsersApiKeys.user_id == user_id,
    )
    row = db.execute(stmt).scalar_one_or_none()
    return api_keys_serializers.to_read_schema(row) if row is not None else None


def get_api_key_by_hash(key_hash: str, db: Session) -> api_keys_schema.UserApiKeyRead | None:
    """Return an API key by its SHA-256 hash."""
    stmt = select(api_keys_models.UsersApiKeys).where(api_keys_models.UsersApiKeys.key_hash == key_hash)
    row = db.execute(stmt).scalar_one_or_none()
    return api_keys_serializers.to_read_schema(row) if row is not None else None


def create_api_key(
    user_id: uuid.UUID,
    data: api_keys_schema.UserApiKeyCreate,
    raw_key: str,
    key_hash: str,
    scopes_json: str,
    expires_at: datetime,
    db: Session,
) -> api_keys_schema.UserApiKeyRead:
    """Stage a new API key and return its raw value and safe representation."""
    db_api_key = api_keys_models.UsersApiKeys(
        id=str(uuid.uuid4()),
        user_id=user_id,
        name=data.name,
        key_prefix=raw_key[9:17],
        key_hash=key_hash,
        scopes=scopes_json,
        expires_at=expires_at,
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


def revoke_api_key(api_key_id: str, user_id: uuid.UUID, db: Session) -> None:
    """Stage revocation of an API key owned by the user."""
    row = db.execute(
        select(api_keys_models.UsersApiKeys).where(
            api_keys_models.UsersApiKeys.id == api_key_id,
            api_keys_models.UsersApiKeys.user_id == user_id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise core_exceptions.NotFoundError(f"API key {api_key_id} not found for user {user_id}")
    if row.is_active:
        row.is_active = False
        row.revoked_at = datetime.now(UTC)
    db.flush()


def revoke_all_api_keys_for_user(user_id: uuid.UUID, db: Session) -> int:
    """Stage revocation of every active API key a user owns and return how many were revoked."""
    model = api_keys_models.UsersApiKeys
    return core_database.rowcount(
        db,
        update(model)
        .where(model.user_id == user_id, model.is_active.is_(True))
        .values(is_active=False, revoked_at=datetime.now(UTC)),
    )


def delete_stale_api_keys(cutoff: datetime, limit: int, db: Session) -> int:
    """Stage deletion of up to ``limit`` keys revoked or expired before ``cutoff`` and return the row count."""
    model = api_keys_models.UsersApiKeys
    stale = select(model.id).where(or_(model.revoked_at < cutoff, model.expires_at < cutoff)).limit(limit)
    matched = core_database.rowcount(db, delete(model).where(model.id.in_(stale)))
    db.flush()
    return matched


def delete_api_key(api_key_id: str, user_id: uuid.UUID, db: Session) -> None:
    """Stage deletion of an API key owned by the user."""
    matched = core_database.rowcount(
        db,
        delete(api_keys_models.UsersApiKeys).where(
            api_keys_models.UsersApiKeys.id == api_key_id,
            api_keys_models.UsersApiKeys.user_id == user_id,
        ),
    )
    if matched == 0:
        raise core_exceptions.NotFoundError(f"API key {api_key_id} not found for user {user_id}")
    db.flush()
