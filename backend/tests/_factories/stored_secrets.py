"""Rows that hold encrypted secrets and the rows they depend on, for tests on the real database."""

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

import modules.auth.sessions.crud as sessions_crud
import modules.auth.sessions.schema as sessions_schema


def make_session_row(db: Session, user_id: uuid.UUID) -> sessions_schema.UserSessionsInternal:
    """Stage a session of a user through the module's create function (flushed, not committed).

    Args:
        db: Database session.
        user_id: The user the session belongs to.

    Returns:
        The staged session; its ``id`` and ``token_family_id`` are what rows that depend on a session reference.
    """
    now = datetime.now(UTC)
    session = sessions_schema.UserSessionsInternal(
        id=uuid.uuid4(),
        ip_address="127.0.0.1",
        device_type="PC",
        operating_system="Linux",
        operating_system_version="6",
        browser="Firefox",
        browser_version="130",
        created_at=now,
        last_activity_at=now,
        expires_at=now,
        user_id=user_id,
        token_family_id=uuid.uuid4(),
        client_type="web",
        auth_time=now,
        amr=["pwd"],
    )
    sessions_crud.create_session(session, db)
    return session
