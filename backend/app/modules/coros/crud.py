"""Persistence for the COROS integration rows.

Tokens are encrypted here so no plaintext credential reaches the database.
Functions stage changes and let the service decide when they become durable;
the only exception is the FIT download reservation, which the service commits
while the row is locked.
"""

import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import core.cryptography as core_cryptography
import core.timezone as core_timezone
import modules.coros.contracts as coros_contracts
import modules.coros.models as coros_models
import modules.coros.schema as coros_schema
from modules.coros.constants import (
    INVALID_FILE_RETRY_DAYS,
    MAX_FIT_DOWNLOADS_PER_DAY,
    SyncErrorCode,
    SyncStatus,
)


def _now() -> datetime:
    """Return the current UTC instant."""
    return datetime.now(UTC)


def _to_data(row: coros_models.CorosIntegration) -> coros_contracts.CorosIntegrationData:
    """Decrypt a row into the internal service view.

    Args:
        row: ORM row.

    Returns:
        The decrypted integration data.
    """
    return coros_contracts.CorosIntegrationData(
        id=row.id,
        user_id=row.user_id,
        mcp_url=row.mcp_url,
        issuer=row.issuer,
        redirect_uri=row.redirect_uri,
        scope=row.scope,
        client_id=row.client_id,
        client_secret=core_cryptography.decrypt_token_fernet(row.client_secret),
        state=row.state,
        code_verifier=core_cryptography.decrypt_token_fernet(row.code_verifier),
        state_expires_at=row.state_expires_at,
        access_token=core_cryptography.decrypt_token_fernet(row.access_token),
        refresh_token=core_cryptography.decrypt_token_fernet(row.refresh_token),
        token_expires_at=row.token_expires_at,
        refresh_token_expires_at=row.refresh_token_expires_at,
        last_sync_at=row.last_sync_at,
        last_sync_status=SyncStatus(row.last_sync_status),
        last_sync_error=SyncErrorCode(row.last_sync_error) if row.last_sync_error else None,
        last_sync_activity_count=row.last_sync_activity_count or 0,
        fit_download_date=row.fit_download_date,
        fit_download_count=row.fit_download_count or 0,
    )


def _get_model(
    user_id: uuid.UUID,
    db: Session,
    *,
    for_update: bool = False,
) -> coros_models.CorosIntegration | None:
    """Return a user's integration row, optionally locked.

    Args:
        user_id: Owning user id.
        db: Database session.
        for_update: Whether to lock the row for the transaction.

    Returns:
        The row, or None when the user never connected COROS.
    """
    stmt = select(coros_models.CorosIntegration).where(coros_models.CorosIntegration.user_id == user_id)
    if for_update:
        stmt = stmt.with_for_update()
    return db.execute(stmt).scalar_one_or_none()


def create_if_missing(user_id: uuid.UUID, db: Session) -> coros_models.CorosIntegration:
    """Return the user's integration row, creating an empty one if needed.

    Args:
        user_id: Owning user id.
        db: Database session.

    Returns:
        The row, staged but not committed.
    """
    row = _get_model(user_id, db)
    if row is not None:
        return row
    now = _now()
    row = coros_models.CorosIntegration(
        user_id=user_id,
        last_sync_status=SyncStatus.NEVER.value,
        last_sync_activity_count=0,
        fit_download_count=0,
        created_at=now,
        updated_at=now,
    )
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
        return row
    except IntegrityError:
        # A concurrent request created the row first. The savepoint keeps the
        # caller's transaction usable, so the winner can be read back.
        existing = _get_model(user_id, db)
        if existing is None:
            raise
        return existing


def get_integration(user_id: uuid.UUID, db: Session) -> coros_contracts.CorosIntegrationData | None:
    """Return a user's decrypted integration state.

    Args:
        user_id: Owning user id.
        db: Database session.

    Returns:
        The integration data, or None when not connected.
    """
    row = _get_model(user_id, db)
    return _to_data(row) if row is not None else None


def get_integration_for_update(user_id: uuid.UUID, db: Session) -> coros_contracts.CorosIntegrationData | None:
    """Return a user's integration state with its row locked.

    Args:
        user_id: Owning user id.
        db: Database session.

    Returns:
        The integration data, or None when not connected.
    """
    row = _get_model(user_id, db, for_update=True)
    return _to_data(row) if row is not None else None


def get_by_state(state: str, db: Session) -> coros_contracts.CorosIntegrationData | None:
    """Return the integration row carrying a pending OAuth state.

    Args:
        state: OAuth state echoed by COROS.
        db: Database session.

    Returns:
        The integration data, or None when no row has that state.
    """
    stmt = select(coros_models.CorosIntegration).where(coros_models.CorosIntegration.state == state)
    row = db.execute(stmt).scalar_one_or_none()
    return _to_data(row) if row is not None else None


def set_pending_authorization(
    user_id: uuid.UUID,
    metadata: coros_contracts.CorosOAuthMetadata,
    registration: coros_contracts.CorosClientRegistration,
    redirect_uri: str,
    state: str,
    code_verifier: str,
    state_expires_at: datetime,
    db: Session,
) -> None:
    """Stage a pending OAuth authorization on the user's row.

    Args:
        user_id: Owning user id.
        metadata: Discovered authorization-server metadata.
        registration: Registered OAuth client.
        redirect_uri: Registered callback URI.
        state: Generated CSRF state.
        code_verifier: Generated PKCE verifier (encrypted here).
        state_expires_at: State expiry.
        db: Database session.
    """
    row = create_if_missing(user_id, db)
    row.mcp_url = metadata.mcp_url
    row.issuer = metadata.issuer
    row.redirect_uri = redirect_uri
    row.scope = " ".join(metadata.scopes)
    row.client_id = registration.client_id
    row.client_secret = core_cryptography.encrypt_token_fernet(registration.client_secret)
    row.state = state
    row.code_verifier = core_cryptography.encrypt_token_fernet(code_verifier)
    row.state_expires_at = state_expires_at
    row.updated_at = _now()
    db.flush()


def save_tokens(
    user_id: uuid.UUID,
    tokens: coros_contracts.CorosTokenSet,
    db: Session,
) -> None:
    """Stage a new token pair and clear the pending authorization.

    Args:
        user_id: Owning user id.
        tokens: New token set.
        db: Database session.
    """
    row = create_if_missing(user_id, db)
    row.access_token = core_cryptography.encrypt_token_fernet(tokens.access_token)
    row.refresh_token = core_cryptography.encrypt_token_fernet(tokens.refresh_token)
    row.token_expires_at = tokens.token_expires_at
    row.refresh_token_expires_at = tokens.refresh_token_expires_at
    row.scope = tokens.scope
    row.state = None
    row.code_verifier = None
    row.state_expires_at = None
    row.last_sync_at = None
    row.last_sync_status = SyncStatus.NEVER.value
    row.last_sync_error = None
    row.last_sync_activity_count = 0
    row.fit_download_date = None
    row.fit_download_count = 0
    row.updated_at = _now()
    db.flush()


def update_tokens(
    user_id: uuid.UUID,
    tokens: coros_contracts.CorosTokenSet,
    db: Session,
) -> None:
    """Stage a rotated token pair without touching sync history or quota.

    Args:
        user_id: Owning user id.
        tokens: New token set.
        db: Database session.
    """
    row = _get_model(user_id, db)
    if row is None:
        return
    row.access_token = core_cryptography.encrypt_token_fernet(tokens.access_token)
    row.refresh_token = core_cryptography.encrypt_token_fernet(tokens.refresh_token)
    row.token_expires_at = tokens.token_expires_at
    row.refresh_token_expires_at = tokens.refresh_token_expires_at
    row.scope = tokens.scope
    row.updated_at = _now()
    db.flush()


def clear_pending_authorization(user_id: uuid.UUID, db: Session) -> None:
    """Stage clearing a pending OAuth state.

    Args:
        user_id: Owning user id.
        db: Database session.
    """
    row = _get_model(user_id, db)
    if row is None:
        return
    row.state = None
    row.code_verifier = None
    row.state_expires_at = None
    row.updated_at = _now()
    db.flush()


def clear_client_registration(user_id: uuid.UUID, db: Session) -> None:
    """Stage clearing a dynamically registered client that COROS rejected.

    Args:
        user_id: Owning user id.
        db: Database session.
    """
    row = _get_model(user_id, db)
    if row is None:
        return
    row.client_id = None
    row.client_secret = None
    row.updated_at = _now()
    db.flush()


def clear_tokens(user_id: uuid.UUID, db: Session) -> None:
    """Stage clearing every token and sync marker for a user.

    Args:
        user_id: Owning user id.
        db: Database session.
    """
    row = _get_model(user_id, db)
    if row is None:
        return
    row.access_token = None
    row.refresh_token = None
    row.token_expires_at = None
    row.refresh_token_expires_at = None
    row.state = None
    row.code_verifier = None
    row.state_expires_at = None
    row.last_sync_at = None
    row.last_sync_status = SyncStatus.NEVER.value
    row.last_sync_error = None
    row.last_sync_activity_count = 0
    row.fit_download_date = None
    row.fit_download_count = 0
    row.updated_at = _now()
    db.flush()


def mark_sync_success(user_id: uuid.UUID, activity_count: int, db: Session) -> None:
    """Stage a successful sync outcome.

    Args:
        user_id: Owning user id.
        activity_count: Activities stored by this sync.
        db: Database session.
    """
    row = _get_model(user_id, db)
    if row is None:
        return
    row.last_sync_at = _now()
    row.last_sync_status = SyncStatus.SUCCESS.value
    row.last_sync_error = None
    row.last_sync_activity_count = activity_count
    row.updated_at = _now()
    db.flush()


def mark_sync_error(user_id: uuid.UUID, error_code: SyncErrorCode, db: Session) -> None:
    """Stage a failed sync outcome.

    Args:
        user_id: Owning user id.
        error_code: Sanitized failure code.
        db: Database session.
    """
    row = _get_model(user_id, db)
    if row is None:
        return
    row.last_sync_at = _now()
    row.last_sync_status = SyncStatus.ERROR.value
    row.last_sync_error = error_code.value
    row.last_sync_activity_count = 0
    row.updated_at = _now()
    db.flush()


def reserve_fit_download(user_id: uuid.UUID, db: Session) -> bool:
    """Reserve one of the user's 50 daily FIT download requests.

    The row is locked so concurrent syncs cannot both pass the cap check.

    Args:
        user_id: Owning user id.
        db: Database session.

    Returns:
        True when a request may be made, False when the daily cap is reached.
    """
    row = _get_model(user_id, db, for_update=True)
    if row is None:
        return False
    today = datetime.now(UTC).date()
    if row.fit_download_date != today:
        row.fit_download_date = today
        row.fit_download_count = 0
    if (row.fit_download_count or 0) >= MAX_FIT_DOWNLOADS_PER_DAY:
        db.flush()
        return False
    row.fit_download_count = (row.fit_download_count or 0) + 1
    row.updated_at = _now()
    db.flush()
    return True


def list_linked_user_ids(after_id: uuid.UUID | None, limit: int, db: Session) -> list[uuid.UUID]:
    """Page through users who have a COROS access token.

    Args:
        after_id: Return only user ids greater than this, or ``None`` from the first page.
        limit: Maximum number of ids.
        db: Database session.

    Returns:
        The linked user ids, ascending.
    """
    stmt = select(coros_models.CorosIntegration.user_id).where(coros_models.CorosIntegration.access_token.is_not(None))
    if after_id is not None:
        stmt = stmt.where(coros_models.CorosIntegration.user_id > after_id)
    stmt = stmt.order_by(coros_models.CorosIntegration.user_id).limit(limit)
    return list(db.scalars(stmt).all())


def is_activity_skipped(user_id: uuid.UUID, label_id: str, db: Session) -> bool:
    """Return whether an activity should not be requested again yet.

    A missing file is permanent. A file that failed to parse is retried after a
    delay, so a transient database or parser failure does not hide an activity
    forever.

    Args:
        user_id: Owning user id.
        label_id: COROS activity identifier.
        db: Database session.

    Returns:
        True when the activity is marked skipped.
    """
    stmt = select(coros_models.CorosSkippedActivity).where(
        coros_models.CorosSkippedActivity.user_id == user_id,
        coros_models.CorosSkippedActivity.label_id == label_id,
    )
    row = db.execute(stmt).scalar_one_or_none()
    if row is None:
        return False
    if row.reason != "invalid_file":
        return True
    skipped_at = core_timezone.to_utc_aware(row.created_at)
    if skipped_at is None:
        return True
    return skipped_at > _now() - timedelta(days=INVALID_FILE_RETRY_DAYS)


def mark_activity_skipped(user_id: uuid.UUID, label_id: str, reason: str, db: Session) -> None:
    """Stage a skip marker for an activity without a usable FIT file.

    Re-marking an existing activity refreshes its retry date.

    Args:
        user_id: Owning user id.
        label_id: COROS activity identifier.
        reason: Skip reason.
        db: Database session.
    """
    stmt = select(coros_models.CorosSkippedActivity).where(
        coros_models.CorosSkippedActivity.user_id == user_id,
        coros_models.CorosSkippedActivity.label_id == label_id,
    )
    row = db.execute(stmt).scalar_one_or_none()
    if row is not None:
        row.reason = reason
        row.created_at = _now()
        db.flush()
        return
    db.add(
        coros_models.CorosSkippedActivity(
            user_id=user_id,
            label_id=label_id,
            reason=reason,
            created_at=_now(),
        )
    )
    db.flush()


def get_status(user_id: uuid.UUID, db: Session) -> coros_schema.CorosStatusRead | None:
    """Return the status view for a user's integration.

    Args:
        user_id: Owning user id.
        db: Database session.

    Returns:
        The status, or None when the user never connected COROS.
    """
    row = _get_model(user_id, db)
    if row is None:
        return None
    return coros_schema.CorosStatusRead(
        linked=row.access_token is not None,
        last_sync_at=row.last_sync_at,
        last_sync_status=SyncStatus(row.last_sync_status),
        last_sync_error=SyncErrorCode(row.last_sync_error) if row.last_sync_error else None,
        last_sync_activity_count=row.last_sync_activity_count or 0,
    )


def is_linked(user_id: uuid.UUID, db: Session) -> bool:
    """Return whether a user has a stored COROS access token.

    Args:
        user_id: Owning user id.
        db: Database session.

    Returns:
        True when COROS is connected.
    """
    stmt = select(coros_models.CorosIntegration.id).where(
        coros_models.CorosIntegration.user_id == user_id,
        coros_models.CorosIntegration.access_token.is_not(None),
    )
    return db.execute(stmt).scalar_one_or_none() is not None


def fit_downloads_today(user_id: uuid.UUID, db: Session) -> tuple[date | None, int]:
    """Return the FIT download counter for display or tests.

    Args:
        user_id: Owning user id.
        db: Database session.

    Returns:
        The counter's date and value; ``(None, 0)`` when the user has no row.
    """
    row = _get_model(user_id, db)
    if row is None:
        return None, 0
    return row.fit_download_date, row.fit_download_count or 0
