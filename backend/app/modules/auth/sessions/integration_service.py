"""Session operations exposed to auth peers."""

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy.orm import Session

import core.pagination as core_pagination
import modules.auth.constants as auth_constants
import modules.auth.credentials.contracts as credentials_contracts
import modules.auth.oauth_state.schema as oauth_state_schema
import modules.auth.sessions.contracts as sessions_contracts
import modules.auth.sessions.crud as sessions_crud
import modules.auth.sessions.schema as sessions_schema
import modules.auth.sessions.service as sessions_service
import modules.auth.sessions.utils as sessions_utils
import modules.server_settings.contracts as server_settings_contracts
import modules.users.users.schema as users_schema


def list_user_sessions(
    user_id: uuid.UUID,
    page: core_pagination.PageParams,
    db: Session,
) -> sessions_schema.UserSessionsPage:
    """Return one page of a user's sessions."""
    return sessions_service.list_user_sessions(user_id, page, db)


def parse_user_agent(user_agent: str) -> sessions_contracts.DeviceInfo:
    """Return the device type, operating system and browser a user-agent string names, as sessions record them."""
    return sessions_utils.parse_user_agent(user_agent)


def get_session_by_id_not_expired(session_id: str, db: Session) -> sessions_contracts.SessionRead | None:
    """Return an unexpired session by ID."""
    return sessions_crud.get_session_by_id_not_expired(session_id, db)


def lock_live_session(
    session_id: str, db: Session, *, exclusive: bool = False
) -> sessions_contracts.SessionRead | None:
    """Return an unexpired session by ID, holding a row lock until the caller's transaction ends.

    The lock is shared unless ``exclusive`` is set, which a caller that will write the session needs.
    """
    return sessions_crud.lock_live_session(session_id, db, exclusive=exclusive)


def get_existing_session_ids(session_ids: Sequence[str], db: Session) -> set[str]:
    """Return which of the given session ids still name a session."""
    return sessions_crud.get_existing_session_ids(session_ids, db)


def get_session_with_oauth_state(
    session_id: str,
    db: Session,
) -> tuple[sessions_contracts.SessionRead, oauth_state_schema.OAuthStateRead | None] | None:
    """Return an unexpired session and its optional OAuth state."""
    return sessions_service.get_session_with_oauth_state(session_id, db)


def create_session(
    session_id: str,
    user: users_schema.UserRead,
    client_type: auth_constants.ClientType,
    ip_address: str,
    user_agent: str,
    refresh_token: str | None,
    password_hasher: credentials_contracts.SupportsHashPassword,
    expires_at: datetime,
    db: Session,
    oauth_state_id: str | None = None,
    csrf_token: str | None = None,
    *,
    amr: Sequence[str],
    device_hash: str | None,
    app_redirect_uri: str | None = None,
) -> sessions_contracts.SessionRead:
    """Stage a session, tied to the known device its sign-in recorded when ``device_hash`` names one."""
    return sessions_service.create_session(
        session_id,
        user,
        client_type,
        ip_address,
        user_agent,
        refresh_token,
        password_hasher,
        expires_at,
        db,
        oauth_state_id,
        csrf_token,
        amr=amr,
        device_hash=device_hash,
        app_redirect_uri=app_redirect_uri,
    )


def edit_session(
    session: sessions_contracts.SessionRead,
    ip_address: str,
    user_agent: str,
    new_refresh_token: str,
    password_hasher: credentials_contracts.SupportsHashPassword,
    expires_at: datetime,
    db: Session,
    new_csrf_token: str | None = None,
) -> sessions_contracts.SessionRead:
    """Stage a rotation of a session's refresh token."""
    return sessions_service.edit_session(
        session,
        ip_address,
        user_agent,
        new_refresh_token,
        password_hasher,
        expires_at,
        db,
        new_csrf_token,
    )


def update_session_csrf_token(session_id: str, new_csrf_token: str, db: Session) -> None:
    """Stage a new CSRF token for a session."""
    sessions_service.update_session_csrf_token(session_id, new_csrf_token, db)


def delete_session(session_id: str, user_id: uuid.UUID, db: Session) -> None:
    """Stage deletion of a session owned by a user."""
    sessions_service.stage_delete_session(session_id, user_id, db)


def delete_session_if_present(session_id: str, user_id: uuid.UUID, db: Session) -> bool:
    """Stage deletion of a session owned by a user; returns False when it was already gone."""
    return sessions_service.stage_delete_session_if_present(session_id, user_id, db)


def delete_sessions_by_user(user_id: uuid.UUID, db: Session, exclude_session_id: str | None = None) -> int:
    """Stage deletion of a user's sessions."""
    return sessions_service.delete_sessions_by_user(user_id, db, exclude_session_id)


def set_session_device_hash(session_id: str, device_hash: str, db: Session) -> None:
    """Stage the known device a session signed in from."""
    sessions_service.set_session_device_hash(session_id, device_hash, db)


def delete_sessions_by_device(user_id: uuid.UUID, device_hash: str, db: Session) -> int:
    """Stage deletion of a user's sessions that signed in from a known device; returns how many."""
    return sessions_service.delete_sessions_by_device(user_id, device_hash, db)


def claim_session_for_token_exchange(
    session_id: str, hashed_refresh_token: str, expires_at: datetime, amr: Sequence[str], db: Session
) -> datetime | None:
    """Atomically claim a session for its token exchange; returns its new expiry, or ``None`` if not claimed."""
    return sessions_service.claim_session_for_token_exchange(session_id, hashed_refresh_token, expires_at, amr, db)


def validate_session_timeout(
    session: sessions_contracts.SessionRead,
    policy: server_settings_contracts.SessionPolicy,
) -> None:
    """Validate configured session timeouts."""
    sessions_service.validate_session_timeout(session, policy)


def verify_csrf_token(candidate: str, stored_hmac: str) -> bool:
    """Verify a CSRF token."""
    return sessions_service.verify_csrf_token(candidate, stored_hmac)


def invalidate_token_family(token_family_id: str, db: Session) -> int:
    """Stage deletion of the sessions and rotated tokens of a token family."""
    return sessions_service.invalidate_token_family(token_family_id, db)
