"""Persistence operations for auth sessions."""

from datetime import UTC, datetime

from sqlalchemy import CursorResult, Select, delete, func, select, update
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import modules.auth.sessions.contracts as sessions_contracts
import modules.auth.sessions.models as sessions_models
import modules.auth.sessions.schema as sessions_schema
import modules.auth.sessions.serializers as sessions_serializers


def get_user_sessions_page(
    user_id: int,
    db: Session,
    *,
    limit: int,
    offset: int,
) -> list[sessions_contracts.SessionRead]:
    """Return one window of a user's sessions, newest first with the id as tiebreak."""
    rows = db.execute(
        select(sessions_models.UsersSessions)
        .where(sessions_models.UsersSessions.user_id == user_id)
        .order_by(sessions_models.UsersSessions.created_at.desc(), sessions_models.UsersSessions.id)
        .limit(limit)
        .offset(offset)
    ).scalars()
    return [sessions_serializers.to_read_schema(row) for row in rows]


def count_user_sessions(user_id: int, db: Session) -> int:
    """Return how many sessions a user has."""
    return db.execute(
        select(func.count(sessions_models.UsersSessions.id)).where(sessions_models.UsersSessions.user_id == user_id)
    ).scalar_one()


def get_session_by_id(session_id: str, db: Session) -> sessions_contracts.SessionRead | None:
    """Return a session by its ID."""
    row = db.execute(select(sessions_models.UsersSessions).where(sessions_models.UsersSessions.id == session_id))
    session = row.scalar_one_or_none()
    return sessions_serializers.to_read_schema(session) if session is not None else None


def get_session_by_id_and_user_id(
    session_id: str,
    user_id: int,
    db: Session,
) -> sessions_contracts.SessionRead | None:
    """Return a user's session by ID."""
    row = db.execute(
        select(sessions_models.UsersSessions).where(
            sessions_models.UsersSessions.id == session_id,
            sessions_models.UsersSessions.user_id == user_id,
        )
    ).scalar_one_or_none()
    return sessions_serializers.to_read_schema(row) if row is not None else None


def get_session_by_id_not_expired(session_id: str, db: Session) -> sessions_contracts.SessionRead | None:
    """Return a session by ID if it has not expired."""
    row = db.execute(
        select(sessions_models.UsersSessions).where(
            sessions_models.UsersSessions.id == session_id,
            sessions_models.UsersSessions.expires_at > datetime.now(UTC),
        )
    ).scalar_one_or_none()
    return sessions_serializers.to_read_schema(row) if row is not None else None


def create_session(
    session: sessions_schema.UsersSessionsInternal,
    db: Session,
) -> sessions_contracts.SessionRead:
    """Stage a new session row."""
    row = sessions_models.UsersSessions(**session.model_dump())
    db.add(row)
    db.flush()
    return sessions_serializers.to_read_schema(row)


def set_session_refresh_token_hash(
    session_id: str,
    hashed_refresh_token: str,
    db: Session,
) -> sessions_contracts.SessionRead:
    """Stage a refresh-token hash update."""
    row = db.execute(
        select(sessions_models.UsersSessions).where(sessions_models.UsersSessions.id == session_id)
    ).scalar_one_or_none()
    if row is None:
        raise core_exceptions.NotFoundError("Session not found")
    row.refresh_token = hashed_refresh_token
    db.flush()
    return sessions_serializers.to_read_schema(row)


def claim_session_for_token_exchange(session_id: str, hashed_refresh_token: str, db: Session) -> bool:
    """Atomically claim a session for one-shot token exchange."""
    result: CursorResult[object] = db.execute(
        update(sessions_models.UsersSessions)
        .where(
            sessions_models.UsersSessions.id == session_id,
            sessions_models.UsersSessions.tokens_exchanged.is_(False),
        )
        .values(tokens_exchanged=True, refresh_token=hashed_refresh_token)
    )
    return result.rowcount == 1


def clear_oauth_state_reference(session_id: str, db: Session) -> None:
    """Stage removal of a session's OAuth-state reference."""
    db.execute(
        update(sessions_models.UsersSessions)
        .where(sessions_models.UsersSessions.id == session_id)
        .values(oauth_state_id=None)
    )


def edit_session(
    session: sessions_schema.UsersSessionsInternal,
    db: Session,
) -> sessions_contracts.SessionRead:
    """Stage updates to an existing session."""
    row = db.execute(
        select(sessions_models.UsersSessions).where(sessions_models.UsersSessions.id == session.id)
    ).scalar_one_or_none()
    if row is None:
        raise core_exceptions.NotFoundError("Session not found")
    for key, value in session.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    db.flush()
    return sessions_serializers.to_read_schema(row)


def update_session_csrf_hash(session_id: str, csrf_token_hash: str, db: Session) -> None:
    """Stage a CSRF-token hash update."""
    result = db.execute(
        update(sessions_models.UsersSessions)
        .where(sessions_models.UsersSessions.id == session_id)
        .values(csrf_token_hash=csrf_token_hash)
    )
    if result.rowcount != 1:
        raise core_exceptions.NotFoundError("Session not found")


def delete_session(session_id: str, user_id: int, db: Session) -> sessions_contracts.SessionRead:
    """Stage deletion of a session owned by a user."""
    row = db.execute(
        select(sessions_models.UsersSessions).where(
            sessions_models.UsersSessions.id == session_id,
            sessions_models.UsersSessions.user_id == user_id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise core_exceptions.NotFoundError("Session not found")
    session = sessions_serializers.to_read_schema(row)
    db.delete(row)
    db.flush()
    return session


def delete_expired_sessions(now: datetime, limit: int, db: Session) -> int:
    """Stage deletion of up to ``limit`` sessions that expired before ``now``."""
    model = sessions_models.UsersSessions
    return _delete_sessions(select(model.id).where(model.expires_at < now).limit(limit), db)


def delete_idle_sessions(cutoff_time: datetime, limit: int, db: Session) -> int:
    """Stage deletion of up to ``limit`` sessions last active before an idle cutoff."""
    model = sessions_models.UsersSessions
    return _delete_sessions(select(model.id).where(model.last_activity_at < cutoff_time).limit(limit), db)


def _delete_sessions(session_ids: Select[tuple[str]], db: Session) -> int:
    """Stage deletion of the sessions a query selects.

    Args:
        session_ids: Selects the ids of the sessions to delete.
        db: Database session.

    Returns:
        The number of sessions staged for deletion.
    """
    result: CursorResult[object] = db.execute(
        delete(sessions_models.UsersSessions).where(sessions_models.UsersSessions.id.in_(session_ids))
    )
    return result.rowcount or 0


def delete_sessions_by_family(token_family_id: str, db: Session) -> int:
    """Stage deletion of sessions in a token family."""
    result: CursorResult[object] = db.execute(
        delete(sessions_models.UsersSessions).where(sessions_models.UsersSessions.token_family_id == token_family_id)
    )
    return result.rowcount or 0


def delete_sessions_by_user(user_id: int, db: Session, exclude_session_id: str | None = None) -> int:
    """Stage deletion of a user's sessions, optionally keeping one session."""
    stmt = delete(sessions_models.UsersSessions).where(sessions_models.UsersSessions.user_id == user_id)
    if exclude_session_id is not None:
        stmt = stmt.where(sessions_models.UsersSessions.id != exclude_session_id)
    result: CursorResult[object] = db.execute(stmt)
    return result.rowcount or 0
