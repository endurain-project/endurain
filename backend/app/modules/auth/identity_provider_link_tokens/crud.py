"""Persistence operations for IdP link tokens."""

from datetime import UTC, datetime

from sqlalchemy import CursorResult, delete, select, update
from sqlalchemy.orm import Session

import modules.auth.identity_provider_link_tokens.models as idp_link_token_models
import modules.auth.identity_provider_link_tokens.schema as idp_link_token_schema
import modules.auth.identity_provider_link_tokens.serializers as idp_link_token_serializers


def get_idp_link_token_by_hash(
    token_hash: str,
    db: Session,
) -> idp_link_token_schema.IdpLinkTokenRead | None:
    """Return a live, unused token by hash."""
    stmt = select(idp_link_token_models.IdpLinkToken).where(
        idp_link_token_models.IdpLinkToken.token_hash == token_hash,
        idp_link_token_models.IdpLinkToken.used.is_(False),
        idp_link_token_models.IdpLinkToken.expires_at > datetime.now(UTC),
    )
    row = db.execute(stmt).scalar_one_or_none()
    return idp_link_token_serializers.to_read_schema(row) if row is not None else None


def create_idp_link_token(
    token_data: idp_link_token_schema.IdpLinkTokenCreate,
    db: Session,
) -> idp_link_token_schema.IdpLinkTokenRead:
    """Stage a one-time link token."""
    row = idp_link_token_models.IdpLinkToken(**token_data.model_dump())
    db.add(row)
    db.flush()
    return idp_link_token_serializers.to_read_schema(row)


def mark_token_as_used(token_hash: str, db: Session) -> bool:
    """Stage an atomic claim of a live, unused token."""
    stmt = (
        update(idp_link_token_models.IdpLinkToken)
        .where(
            idp_link_token_models.IdpLinkToken.token_hash == token_hash,
            idp_link_token_models.IdpLinkToken.used.is_(False),
            idp_link_token_models.IdpLinkToken.expires_at > datetime.now(UTC),
        )
        .values(used=True)
    )
    result: CursorResult[object] = db.execute(stmt)
    return result.rowcount == 1


def delete_expired_tokens(now: datetime, limit: int, db: Session) -> int:
    """Stage deletion of up to ``limit`` tokens that expired before ``now``."""
    model = idp_link_token_models.IdpLinkToken
    expired = select(model.id).where(model.expires_at < now).limit(limit)
    result: CursorResult[object] = db.execute(delete(model).where(model.id.in_(expired)))
    return result.rowcount or 0
