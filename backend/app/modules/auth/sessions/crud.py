"""Persistence operations for auth sessions."""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import Select, delete, func, select, update
from sqlalchemy.orm import Session

import core.database as core_database
import core.exceptions as core_exceptions
import modules.auth.sessions.contracts as sessions_contracts
import modules.auth.sessions.models as sessions_models
import modules.auth.sessions.schema as sessions_schema
import modules.auth.sessions.serializers as sessions_serializers


def get_user_sessions_page(
    user_id: uuid.UUID,
    db: Session,
    *,
    limit: int,
    offset: int,
) -> list[sessions_contracts.SessionRead]:
    """Return one window of a user's exchanged sessions, newest first with the id as tiebreak."""
    rows = db.execute(
        select(sessions_models.UsersSessions)
        .where(
            sessions_models.UsersSessions.user_id == user_id, sessions_models.UsersSessions.tokens_exchanged.is_(True)
        )
        .order_by(sessions_models.UsersSessions.created_at.desc(), sessions_models.UsersSessions.id)
        .limit(limit)
        .offset(offset)
    ).scalars()
    return [sessions_serializers.to_read_schema(row) for row in rows]


def count_user_sessions(user_id: uuid.UUID, db: Session) -> int:
    """Return how many exchanged sessions a user has."""
    return db.execute(
        select(func.count(sessions_models.UsersSessions.id)).where(
            sessions_models.UsersSessions.user_id == user_id, sessions_models.UsersSessions.tokens_exchanged.is_(True)
        )
    ).scalar_one()


def get_session_by_id(session_id: uuid.UUID, db: Session) -> sessions_contracts.SessionRead | None:
    """Return a session by its ID."""
    row = db.execute(select(sessions_models.UsersSessions).where(sessions_models.UsersSessions.id == session_id))
    session = row.scalar_one_or_none()
    return sessions_serializers.to_read_schema(session) if session is not None else None


def get_session_by_id_and_user_id(
    session_id: uuid.UUID,
    user_id: uuid.UUID,
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


def get_existing_session_ids(session_ids: Sequence[uuid.UUID], db: Session) -> set[uuid.UUID]:
    """Return which of the given session ids still name a session."""
    if not session_ids:
        return set()
    model = sessions_models.UsersSessions
    return set(db.execute(select(model.id).where(model.id.in_(session_ids))).scalars())


def get_session_by_id_not_expired(session_id: uuid.UUID, db: Session) -> sessions_contracts.SessionRead | None:
    """Return a session by ID if it has not expired."""
    row = db.execute(
        select(sessions_models.UsersSessions).where(
            sessions_models.UsersSessions.id == session_id,
            sessions_models.UsersSessions.expires_at > datetime.now(UTC),
        )
    ).scalar_one_or_none()
    return sessions_serializers.to_read_schema(row) if row is not None else None


def lock_live_session(
    session_id: uuid.UUID, db: Session, *, exclusive: bool = False
) -> sessions_contracts.SessionRead | None:
    """Return an unexpired session by ID and hold a row lock on it until the transaction ends.

    The lock keeps a revocation of the session from committing before the caller's transaction does.

    Args:
        session_id: ID of the session.
        db: Database session.
        exclusive: Take an exclusive lock, for a caller that will write the session; two such callers then queue
            instead of both holding a shared lock and deadlocking on the upgrade.

    Returns:
        The session, or None when it does not exist or has expired.
    """
    row = db.execute(
        select(sessions_models.UsersSessions)
        .where(
            sessions_models.UsersSessions.id == session_id,
            sessions_models.UsersSessions.expires_at > datetime.now(UTC),
        )
        .with_for_update(read=not exclusive)
    ).scalar_one_or_none()
    return sessions_serializers.to_read_schema(row) if row is not None else None


def create_session(
    session: sessions_schema.UserSessionsInternal,
    db: Session,
) -> sessions_contracts.SessionRead:
    """Stage a new session row."""
    row = sessions_models.UsersSessions(**session.model_dump())
    db.add(row)
    db.flush()
    return sessions_serializers.to_read_schema(row)


def set_session_refresh_token_hash(
    session_id: uuid.UUID,
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


def claim_session_for_token_exchange(
    session_id: uuid.UUID, hashed_refresh_token: str, expires_at: datetime, amr: Sequence[str], db: Session
) -> bool:
    """Atomically claim a session for one-shot token exchange, give it its real expiry and record its final methods."""
    matched = core_database.rowcount(
        db,
        update(sessions_models.UsersSessions)
        .where(
            sessions_models.UsersSessions.id == session_id,
            sessions_models.UsersSessions.tokens_exchanged.is_(False),
        )
        .values(tokens_exchanged=True, refresh_token=hashed_refresh_token, expires_at=expires_at, amr=list(amr)),
    )
    return matched == 1


def set_session_device_hash(session_id: uuid.UUID, device_hash: str, db: Session) -> None:
    """Stage the known device a session signed in from."""
    db.execute(
        update(sessions_models.UsersSessions)
        .where(sessions_models.UsersSessions.id == session_id)
        .values(device_hash=device_hash)
    )


def clear_oauth_state_reference(session_id: uuid.UUID, db: Session) -> None:
    """Stage removal of a session's OAuth-state reference."""
    db.execute(
        update(sessions_models.UsersSessions)
        .where(sessions_models.UsersSessions.id == session_id)
        .values(oauth_state_id=None)
    )


def edit_session(
    session: sessions_schema.UserSessionsInternal,
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


def update_session_csrf_hash(session_id: uuid.UUID, csrf_token_hash: str, db: Session) -> None:
    """Stage a CSRF-token hash update."""
    matched = core_database.rowcount(
        db,
        update(sessions_models.UsersSessions)
        .where(sessions_models.UsersSessions.id == session_id)
        .values(csrf_token_hash=csrf_token_hash),
    )
    if matched != 1:
        raise core_exceptions.NotFoundError("Session not found")


def delete_session_if_present(
    session_id: uuid.UUID, user_id: uuid.UUID, db: Session
) -> sessions_contracts.SessionRead | None:
    """Stage deletion of a session owned by a user, or do nothing when there is none.

    Returns:
        The deleted session, or ``None`` when the user has no such session.
    """
    row = db.execute(
        select(sessions_models.UsersSessions).where(
            sessions_models.UsersSessions.id == session_id,
            sessions_models.UsersSessions.user_id == user_id,
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    session = sessions_serializers.to_read_schema(row)
    db.delete(row)
    db.flush()
    return session


def delete_session(session_id: uuid.UUID, user_id: uuid.UUID, db: Session) -> sessions_contracts.SessionRead:
    """Stage deletion of a session owned by a user.

    Raises:
        NotFoundError: When the user has no such session.
    """
    session = delete_session_if_present(session_id, user_id, db)
    if session is None:
        raise core_exceptions.NotFoundError("Session not found")
    return session


def delete_sessions_by_device(
    user_id: uuid.UUID, device_hash: str, db: Session
) -> list[sessions_contracts.SessionRead]:
    """Stage deletion of a user's sessions that signed in from a known device.

    Returns:
        The deleted sessions.
    """
    rows = list(
        db.execute(
            select(sessions_models.UsersSessions).where(
                sessions_models.UsersSessions.user_id == user_id,
                sessions_models.UsersSessions.device_hash == device_hash,
            )
        ).scalars()
    )
    sessions = [sessions_serializers.to_read_schema(row) for row in rows]
    for row in rows:
        db.delete(row)
    db.flush()
    return sessions


def delete_expired_sessions(now: datetime, limit: int, db: Session) -> list[tuple[uuid.UUID, uuid.UUID]]:
    """Stage deletion of up to ``limit`` sessions that expired before ``now``.

    Returns:
        The owner and id of each session staged for deletion.
    """
    model = sessions_models.UsersSessions
    return _delete_sessions(select(model.id).where(model.expires_at < now).limit(limit), db)


def delete_idle_sessions(cutoff_time: datetime, limit: int, db: Session) -> list[tuple[uuid.UUID, uuid.UUID]]:
    """Stage deletion of up to ``limit`` sessions last active before an idle cutoff.

    Returns:
        The owner and id of each session staged for deletion.
    """
    model = sessions_models.UsersSessions
    return _delete_sessions(select(model.id).where(model.last_activity_at < cutoff_time).limit(limit), db)


def _delete_sessions(session_ids: Select[tuple[uuid.UUID]], db: Session) -> list[tuple[uuid.UUID, uuid.UUID]]:
    """Stage deletion of the sessions a query selects.

    Args:
        session_ids: Selects the ids of the sessions to delete.
        db: Database session.

    Returns:
        The owner and id of each session staged for deletion.
    """
    model = sessions_models.UsersSessions
    rows = db.execute(delete(model).where(model.id.in_(session_ids)).returning(model.user_id, model.id)).all()
    return [(user_id, session_id) for user_id, session_id in rows]


def list_session_owners_by_family(token_family_id: uuid.UUID, db: Session) -> list[tuple[uuid.UUID, uuid.UUID]]:
    """Return the owner and id of each session in a token family."""
    rows = db.execute(
        select(sessions_models.UsersSessions.user_id, sessions_models.UsersSessions.id).where(
            sessions_models.UsersSessions.token_family_id == token_family_id
        )
    )
    return [(user_id, session_id) for user_id, session_id in rows]


def delete_sessions_by_family(token_family_id: uuid.UUID, db: Session) -> int:
    """Stage deletion of sessions in a token family."""
    return core_database.rowcount(
        db,
        delete(sessions_models.UsersSessions).where(sessions_models.UsersSessions.token_family_id == token_family_id),
    )


def list_oauth_state_ids_by_user(
    user_id: uuid.UUID, db: Session, exclude_session_id: uuid.UUID | None = None
) -> list[str]:
    """Return the OAuth state ids of a user's sessions, optionally leaving out one session."""
    stmt = select(sessions_models.UsersSessions.oauth_state_id).where(
        sessions_models.UsersSessions.user_id == user_id,
        sessions_models.UsersSessions.oauth_state_id.is_not(None),
    )
    if exclude_session_id is not None:
        stmt = stmt.where(sessions_models.UsersSessions.id != exclude_session_id)
    return [state_id for state_id in db.execute(stmt).scalars() if state_id is not None]


def delete_sessions_by_user(user_id: uuid.UUID, db: Session, exclude_session_id: uuid.UUID | None = None) -> int:
    """Stage deletion of a user's sessions, optionally keeping one session."""
    stmt = delete(sessions_models.UsersSessions).where(sessions_models.UsersSessions.user_id == user_id)
    if exclude_session_id is not None:
        stmt = stmt.where(sessions_models.UsersSessions.id != exclude_session_id)
    return core_database.rowcount(db, stmt)
