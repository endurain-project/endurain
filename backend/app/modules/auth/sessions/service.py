"""Session lifecycle and transaction orchestration."""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

import core.config as core_config
import core.database as core_database
import core.hashing as core_hashing
import core.logger as core_logger
import core.pagination as core_pagination
import modules.auth.access_tokens.integration_service as access_tokens_integration
import modules.auth.credentials.contracts as credentials_contracts
import modules.auth.oauth_state.integration_service as oauth_state_integration
import modules.auth.oauth_state.schema as oauth_state_schema
import modules.auth.rotated_refresh_tokens.integration_service as rotated_refresh_tokens_integration
import modules.auth.sessions.contracts as sessions_contracts
import modules.auth.sessions.crud as sessions_crud
import modules.auth.sessions.schema as sessions_schema
import modules.auth.sessions.utils as sessions_utils
import modules.server_settings.contracts as server_settings_contracts
import modules.server_settings.integration_service as server_settings_integration
import modules.users.users.schema as users_schema

logger = core_logger.get_logger(__name__)


def list_user_sessions(
    user_id: int,
    page: core_pagination.PageParams,
    db: Session,
) -> sessions_schema.UsersSessionsPage:
    """Return one page of a user's sessions, hiding them in the demo environment."""
    if core_config.settings.ENVIRONMENT == "demo":
        logger.info("Session retrieval in demo environment", extra=core_logger.context(user_id=user_id))
        return sessions_schema.UsersSessionsPage.build([], 0, page.page_number, page.num_records)
    sessions = sessions_crud.get_user_sessions_page(
        user_id,
        db,
        limit=page.num_records,
        offset=(page.page_number - 1) * page.num_records,
    )
    total = sessions_crud.count_user_sessions(user_id, db)
    return sessions_schema.UsersSessionsPage.build(
        [sessions_schema.UsersSessionsRead.model_validate(session) for session in sessions],
        total,
        page.page_number,
        page.num_records,
    )


def get_session_with_oauth_state(
    session_id: str,
    db: Session,
) -> tuple[sessions_contracts.SessionRead, oauth_state_schema.OAuthStateRead | None] | None:
    """Return an unexpired session and its optional OAuth state."""
    session = sessions_crud.get_session_by_id_not_expired(session_id, db)
    if session is None:
        return None
    oauth_state = (
        oauth_state_integration.get_oauth_state_by_id_not_expired(session.oauth_state_id, db)
        if session.oauth_state_id
        else None
    )
    return session, oauth_state


def create_session(
    session_id: str,
    user: users_schema.UsersRead,
    ip_address: str,
    user_agent: str,
    refresh_token: str | None,
    password_hasher: credentials_contracts.SupportsHashPassword,
    expires_at: datetime,
    db: Session,
    oauth_state_id: str | None = None,
    csrf_token: str | None = None,
) -> sessions_contracts.SessionRead:
    """Stage a session with hashed tokens and the client's IP address and user agent; the caller commits."""
    device = sessions_utils.parse_user_agent(user_agent)
    csrf_hash = _hash_csrf_token(csrf_token) if csrf_token else None
    now = datetime.now(UTC)
    session_data = sessions_schema.UsersSessionsInternal(
        id=session_id,
        user_id=user.id,
        refresh_token=password_hasher.hash_password(refresh_token) if refresh_token else None,
        ip_address=ip_address,
        device_type=device.device_type.value,
        operating_system=device.operating_system,
        operating_system_version=device.operating_system_version,
        browser=device.browser,
        browser_version=device.browser_version,
        created_at=now,
        last_activity_at=now,
        expires_at=expires_at,
        oauth_state_id=oauth_state_id,
        tokens_exchanged=False,
        token_family_id=session_id,
        rotation_count=0,
        last_rotation_at=None,
        csrf_token_hash=csrf_hash,
    )
    session = sessions_crud.create_session(session_data, db)
    logger.info(
        "Session created",
        extra=core_logger.context(user_id=user.id, session_id=core_hashing.log_fingerprint(session_id)),
    )
    return session


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
    """Stage a refresh-token rotation and client metadata update; the caller commits."""
    device = sessions_utils.parse_user_agent(user_agent)
    csrf_hash = _hash_csrf_token(new_csrf_token) if new_csrf_token else None
    session_data = sessions_schema.UsersSessionsInternal.model_validate(session)
    session_data = session_data.model_copy(
        update={
            "refresh_token": password_hasher.hash_password(new_refresh_token),
            "ip_address": ip_address,
            "device_type": device.device_type.value,
            "operating_system": device.operating_system,
            "operating_system_version": device.operating_system_version,
            "browser": device.browser,
            "browser_version": device.browser_version,
            "last_activity_at": datetime.now(UTC),
            "expires_at": expires_at,
            "rotation_count": session.rotation_count + 1,
            "last_rotation_at": datetime.now(UTC),
            "csrf_token_hash": csrf_hash,
        }
    )
    updated = sessions_crud.edit_session(session_data, db)
    logger.debug(
        "Session refresh token rotated", extra=core_logger.context(session_id=core_hashing.log_fingerprint(session.id))
    )
    return updated


def update_session_csrf_token(session_id: str, new_csrf_token: str, db: Session) -> None:
    """Stage the binding of a newly issued CSRF token to a session; the caller commits."""
    sessions_crud.update_session_csrf_hash(session_id, _hash_csrf_token(new_csrf_token), db)
    logger.debug(
        "Session CSRF token updated", extra=core_logger.context(session_id=core_hashing.log_fingerprint(session_id))
    )


def stage_delete_session(session_id: str, user_id: int, db: Session) -> None:
    """Stage deletion of a session with its token and OAuth state records; the caller commits."""
    session = sessions_crud.delete_session(session_id, user_id, db)
    if session.oauth_state_id:
        oauth_state_integration.delete_oauth_state(session.oauth_state_id, db)
    rotated_refresh_tokens_integration.delete_by_family(session.token_family_id, db)


def delete_session(session_id: str, user_id: int, db: Session) -> None:
    """Delete a session with its token and OAuth state records and commit."""
    stage_delete_session(session_id, user_id, db)
    db.commit()
    logger.info(
        "Session deleted",
        extra=core_logger.context(user_id=user_id, session_id=core_hashing.log_fingerprint(session_id)),
    )


def claim_session_for_token_exchange(session_id: str, hashed_refresh_token: str, db: Session) -> bool:
    """Atomically claim a session for its one-shot token exchange; the caller commits."""
    session = sessions_crud.get_session_by_id(session_id, db)
    if not sessions_crud.claim_session_for_token_exchange(session_id, hashed_refresh_token, db):
        logger.warning(
            "Session token exchange claim lost",
            extra=core_logger.context(session_id=core_hashing.log_fingerprint(session_id)),
        )
        return False
    _clear_oauth_state(session, db)
    logger.info(
        "Session token exchange claimed", extra=core_logger.context(session_id=core_hashing.log_fingerprint(session_id))
    )
    return True


def _clear_oauth_state(session: sessions_contracts.SessionRead | None, db: Session) -> None:
    if session is None or session.oauth_state_id is None:
        return
    sessions_crud.clear_oauth_state_reference(session.id, db)
    oauth_state_integration.delete_oauth_state(session.oauth_state_id, db)


def invalidate_token_family(token_family_id: str, db: Session) -> int:
    """Stage deletion of a token family from sessions and rotated-token persistence; the caller commits."""
    sessions_deleted = sessions_crud.delete_sessions_by_family(token_family_id, db)
    tokens_deleted = rotated_refresh_tokens_integration.delete_by_family(token_family_id, db)
    logger.warning(
        "Invalidated refresh-token family after reuse detection",
        extra=core_logger.context(
            token_family_id=token_family_id,
            sessions_deleted=sessions_deleted,
            tokens_deleted=tokens_deleted,
        ),
    )
    return sessions_deleted


def delete_sessions_by_user(user_id: int, db: Session, exclude_session_id: str | None = None) -> int:
    """Stage deletion of a user's sessions for a larger auth transaction."""
    return sessions_crud.delete_sessions_by_user(user_id, db, exclude_session_id)


def delete_sessions_by_user_and_commit(user_id: int, db: Session, exclude_session_id: str | None = None) -> int:
    """Delete a user's sessions and commit the standalone operation."""
    deleted_count = sessions_crud.delete_sessions_by_user(user_id, db, exclude_session_id)
    db.commit()
    logger.info(
        "User sessions deleted",
        extra=core_logger.context(
            user_id=user_id,
            count=deleted_count,
            excluded_session_id=core_hashing.log_fingerprint(exclude_session_id) if exclude_session_id else None,
        ),
    )
    return deleted_count


def delete_expired_sessions(db: Session) -> int:
    """Delete sessions past their expiry, one batch per commit.

    An expired session can no longer be read or refreshed, whatever the idle policy, so it is always
    removed; its rotated refresh-token records go with it.
    """
    now = datetime.now(UTC)
    return core_database.delete_in_batches(lambda limit: sessions_crud.delete_expired_sessions(now, limit, db), db)


def delete_idle_sessions(db: Session) -> int:
    """Delete sessions that exceed the configured idle timeout, one batch per commit."""
    policy: server_settings_contracts.SessionPolicy = server_settings_integration.get_session_policy(db)
    if policy.idle_timeout is None:
        return 0
    cutoff_time = datetime.now(UTC) - policy.idle_timeout
    return core_database.delete_in_batches(lambda limit: sessions_crud.delete_idle_sessions(cutoff_time, limit, db), db)


def validate_session_timeout(
    session: sessions_contracts.SessionRead,
    policy: server_settings_contracts.SessionPolicy,
) -> None:
    """Validate session idle and absolute timeouts."""
    sessions_utils.validate_session_timeout(session, policy)


def verify_csrf_token(candidate: str, stored_hmac: str) -> bool:
    """Verify a CSRF token against its stored HMAC."""
    return sessions_utils.verify_csrf_token(stored_hmac, access_tokens_integration.hmac_sha256(candidate))


def _hash_csrf_token(token: str) -> str:
    return access_tokens_integration.hmac_sha256(token)
