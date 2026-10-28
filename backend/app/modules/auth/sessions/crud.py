"""Persistence operations for auth sessions."""

from datetime import UTC, datetime

from sqlalchemy import CursorResult, delete, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import modules.auth.sessions.contracts as sessions_contracts
import modules.auth.sessions.models as sessions_models
import modules.auth.sessions.schema as sessions_schema
import modules.auth.sessions.serializers as sessions_serializers


def get_user_sessions(user_id: int, db: Session) -> list[sessions_contracts.SessionRead]:
    """Return a user's sessions ordered from newest to oldest."""
    try:
        rows = db.execute(
            select(sessions_models.UsersSessions)
            .where(sessions_models.UsersSessions.user_id == user_id)
            .order_by(sessions_models.UsersSessions.created_at.desc())
        ).scalars()
        return [sessions_serializers.to_read_schema(row) for row in rows]
    except SQLAlchemyError as err:
        raise core_exceptions.ProcessingError("Database error occurred") from err


def get_session_by_id(session_id: str, db: Session) -> sessions_contracts.SessionRead | None:
    """Return a session by its ID."""
    try:
        row = db.execute(select(sessions_models.UsersSessions).where(sessions_models.UsersSessions.id == session_id))
        session = row.scalar_one_or_none()
        return sessions_serializers.to_read_schema(session) if session is not None else None
    except SQLAlchemyError as err:
        raise core_exceptions.ProcessingError("Database error occurred") from err


def get_session_by_id_and_user_id(
    session_id: str,
    user_id: int,
    db: Session,
) -> sessions_contracts.SessionRead | None:
    """Return a user's session by ID."""
    try:
        row = db.execute(
            select(sessions_models.UsersSessions).where(
                sessions_models.UsersSessions.id == session_id,
                sessions_models.UsersSessions.user_id == user_id,
            )
        ).scalar_one_or_none()
        return sessions_serializers.to_read_schema(row) if row is not None else None
    except SQLAlchemyError as err:
        raise core_exceptions.ProcessingError("Database error occurred") from err


def get_session_by_id_not_expired(session_id: str, db: Session) -> sessions_contracts.SessionRead | None:
    """Return a session by ID if it has not expired."""
    try:
        row = db.execute(
            select(sessions_models.UsersSessions).where(
                sessions_models.UsersSessions.id == session_id,
                sessions_models.UsersSessions.expires_at > datetime.now(UTC),
            )
        ).scalar_one_or_none()
        return sessions_serializers.to_read_schema(row) if row is not None else None
    except SQLAlchemyError as err:
        raise core_exceptions.ProcessingError("Database error occurred") from err


def create_session(
    session: sessions_schema.UsersSessionsInternal,
    db: Session,
) -> sessions_contracts.SessionRead:
    """Stage a new session row."""
    try:
        row = sessions_models.UsersSessions(**session.model_dump())
        db.add(row)
        db.flush()
        return sessions_serializers.to_read_schema(row)
    except SQLAlchemyError as err:
        raise core_exceptions.ProcessingError("Database error occurred") from err


def set_session_refresh_token_hash(
    session_id: str,
    hashed_refresh_token: str,
    db: Session,
) -> sessions_contracts.SessionRead:
    """Stage a refresh-token hash update."""
    try:
        row = db.execute(
            select(sessions_models.UsersSessions).where(sessions_models.UsersSessions.id == session_id)
        ).scalar_one_or_none()
        if row is None:
            raise core_exceptions.NotFoundError("Session not found")
        row.refresh_token = hashed_refresh_token
        db.flush()
        return sessions_serializers.to_read_schema(row)
    except SQLAlchemyError as err:
        raise core_exceptions.ProcessingError("Database error occurred") from err


def claim_session_for_token_exchange(session_id: str, hashed_refresh_token: str, db: Session) -> bool:
    """Atomically claim a session for one-shot token exchange."""
    try:
        result: CursorResult[object] = db.execute(
            update(sessions_models.UsersSessions)
            .where(
                sessions_models.UsersSessions.id == session_id,
                sessions_models.UsersSessions.tokens_exchanged.is_(False),
            )
            .values(tokens_exchanged=True, refresh_token=hashed_refresh_token)
        )
        return result.rowcount == 1
    except SQLAlchemyError as err:
        raise core_exceptions.ProcessingError("Database error occurred") from err


def clear_oauth_state_reference(session_id: str, db: Session) -> None:
    """Stage removal of a session's OAuth-state reference."""
    try:
        db.execute(
            update(sessions_models.UsersSessions)
            .where(sessions_models.UsersSessions.id == session_id)
            .values(oauth_state_id=None)
        )
    except SQLAlchemyError as err:
        raise core_exceptions.ProcessingError("Database error occurred") from err


def edit_session(
    session: sessions_schema.UsersSessionsInternal,
    db: Session,
) -> sessions_contracts.SessionRead:
    """Stage updates to an existing session."""
    try:
        row = db.execute(
            select(sessions_models.UsersSessions).where(sessions_models.UsersSessions.id == session.id)
        ).scalar_one_or_none()
        if row is None:
            raise core_exceptions.NotFoundError("Session not found")
        for key, value in session.model_dump(exclude_unset=True).items():
            setattr(row, key, value)
        db.flush()
        return sessions_serializers.to_read_schema(row)
    except SQLAlchemyError as err:
        raise core_exceptions.ProcessingError("Database error occurred") from err


def update_session_csrf_hash(session_id: str, csrf_token_hash: str, db: Session) -> None:
    """Stage a CSRF-token hash update."""
    try:
        result = db.execute(
            update(sessions_models.UsersSessions)
            .where(sessions_models.UsersSessions.id == session_id)
            .values(csrf_token_hash=csrf_token_hash)
        )
        if result.rowcount != 1:
            raise core_exceptions.NotFoundError("Session not found")
    except SQLAlchemyError as err:
        raise core_exceptions.ProcessingError("Database error occurred") from err


def delete_session(session_id: str, user_id: int, db: Session) -> sessions_contracts.SessionRead:
    """Stage deletion of a session owned by a user."""
    try:
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
    except SQLAlchemyError as err:
        raise core_exceptions.ProcessingError("Database error occurred") from err


def delete_idle_sessions(cutoff_time: datetime, db: Session) -> int:
    """Stage deletion of sessions older than an idle cutoff."""
    try:
        result: CursorResult[object] = db.execute(
            delete(sessions_models.UsersSessions).where(sessions_models.UsersSessions.last_activity_at < cutoff_time)
        )
        return result.rowcount or 0
    except SQLAlchemyError as err:
        raise core_exceptions.ProcessingError("Database error occurred") from err


def delete_sessions_by_family(token_family_id: str, db: Session) -> int:
    """Stage deletion of sessions in a token family."""
    try:
        result: CursorResult[object] = db.execute(
            delete(sessions_models.UsersSessions).where(
                sessions_models.UsersSessions.token_family_id == token_family_id
            )
        )
        return result.rowcount or 0
    except SQLAlchemyError as err:
        raise core_exceptions.ProcessingError("Database error occurred") from err


def delete_sessions_by_user(user_id: int, db: Session, exclude_session_id: str | None = None) -> int:
    """Stage deletion of a user's sessions, optionally keeping one session."""
    try:
        stmt = delete(sessions_models.UsersSessions).where(sessions_models.UsersSessions.user_id == user_id)
        if exclude_session_id is not None:
            stmt = stmt.where(sessions_models.UsersSessions.id != exclude_session_id)
        result: CursorResult[object] = db.execute(stmt)
        return result.rowcount or 0
    except SQLAlchemyError as err:
        raise core_exceptions.ProcessingError("Database error occurred") from err
