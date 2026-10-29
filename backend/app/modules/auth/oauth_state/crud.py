"""Persistence operations for OAuth state."""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import CursorResult, delete, select, update
from sqlalchemy.orm import Session

import modules.auth.oauth_state.constants as oauth_state_constants
import modules.auth.oauth_state.models as oauth_state_models
import modules.auth.oauth_state.schema as oauth_state_schema
import modules.auth.oauth_state.serializers as oauth_state_serializers


def get_oauth_state_by_id_and_not_used(state_id: str, db: Session) -> oauth_state_schema.OAuthStateRead | None:
    """Return an unused, unexpired OAuth state by ID."""
    stmt = select(oauth_state_models.OAuthState).where(
        oauth_state_models.OAuthState.id == state_id,
        oauth_state_models.OAuthState.used.is_(False),
        oauth_state_models.OAuthState.expires_at > datetime.now(UTC),
    )
    row = db.execute(stmt).scalar_one_or_none()
    return oauth_state_serializers.to_read_schema(row) if row is not None else None


def get_oauth_state_by_id_not_expired(state_id: str, db: Session) -> oauth_state_schema.OAuthStateRead | None:
    """Return an unexpired OAuth state by ID."""
    stmt = select(oauth_state_models.OAuthState).where(
        oauth_state_models.OAuthState.id == state_id,
        oauth_state_models.OAuthState.expires_at > datetime.now(UTC),
    )
    row = db.execute(stmt).scalar_one_or_none()
    return oauth_state_serializers.to_read_schema(row) if row is not None else None


def create_oauth_state(
    state_id: str,
    nonce: str,
    client_type: str,
    ip_address: str | None,
    db: Session,
    *,
    idp_id: int | None = None,
    redirect_path: str | None = None,
    code_challenge: str | None = None,
    code_challenge_method: str | None = None,
    user_id: int | None = None,
    browser_binding_hash: str | None = None,
    idp_code_verifier: str | None = None,
) -> oauth_state_schema.OAuthStateRead:
    """Stage a new OAuth state with its fixed ten-minute expiry."""
    row = oauth_state_models.OAuthState(
        id=state_id,
        idp_id=idp_id,
        nonce=nonce,
        client_type=client_type,
        ip_address=ip_address,
        redirect_path=redirect_path,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        user_id=user_id,
        browser_binding_hash=browser_binding_hash,
        idp_code_verifier=idp_code_verifier,
        expires_at=datetime.now(UTC) + timedelta(seconds=oauth_state_constants.STATE_TTL_SECONDS),
        used=False,
    )
    db.add(row)
    db.flush()
    return oauth_state_serializers.to_read_schema(row)


def mark_oauth_state_used(state_id: str, db: Session) -> bool:
    """Atomically stage the claim of an unused, unexpired OAuth state."""
    stmt = (
        update(oauth_state_models.OAuthState)
        .where(
            oauth_state_models.OAuthState.id == state_id,
            oauth_state_models.OAuthState.used.is_(False),
            oauth_state_models.OAuthState.expires_at > datetime.now(UTC),
        )
        .values(used=True)
    )
    result: CursorResult[Any] = db.execute(stmt)
    return result.rowcount == 1


def delete_oauth_state(oauth_state_id: str, db: Session) -> int:
    """Stage deletion of an OAuth state."""
    result: CursorResult[Any] = db.execute(
        delete(oauth_state_models.OAuthState).where(oauth_state_models.OAuthState.id == oauth_state_id)
    )
    return result.rowcount or 0


def delete_expired_oauth_states(now: datetime, limit: int, db: Session) -> int:
    """Stage deletion of up to ``limit`` OAuth states that expired before ``now``."""
    model = oauth_state_models.OAuthState
    expired = select(model.id).where(model.expires_at < now).limit(limit)
    result: CursorResult[Any] = db.execute(delete(model).where(model.id.in_(expired)))
    return result.rowcount or 0
