"""Unlinking a Garmin Connect account and the authenticated sessions its syncs use.

Linking lives in :mod:`modules.garmin.link_service`. The activity, gear and health syncs live in
:mod:`modules.garmin.activity_service`, :mod:`modules.garmin.gear_service` and
:mod:`modules.garmin.health_service`.
"""

import time
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any, NamedTuple

import garminconnect
import jasil.audit as jasil_audit
import jasil.providers as platform_providers
import sqlalchemy.exc
from sqlalchemy.orm import Session

import core.database as core_database
import core.exceptions as core_exceptions
import core.logger as core_logger
import modules.auth.identity_providers.constants as identity_providers_constants
import modules.auth.identity_providers.contracts as identity_providers_contracts
import modules.auth.schema as auth_schema
import modules.garmin.audit_actions as garmin_audit_actions
import modules.garmin.constants as garmin_constants
import modules.garmin.rate_limit_store as garmin_rate_limit_store
import modules.garmin.token_utils as garmin_token_utils
import modules.notifications.integration_service as notifications_integration
import modules.users.users_integrations.integration_service as user_integrations_integration
import modules.users.users_integrations.schema as user_integrations_schema

logger = core_logger.get_logger(__name__)


def unlink_account(
    user_id: uuid.UUID,
    step_up: auth_schema.StepUpVerification,
    verify_step_up: identity_providers_contracts.StepUpVerifier,
    db: Session,
) -> None:
    """Unlink a user's Garmin Connect account after the user's step-up.

    The step-up is verified before anything is changed, and committed with the unlink.

    Args:
        user_id: The user unlinking Garmin Connect.
        step_up: The user's step-up verification.
        verify_step_up: Verifies the step-up for the calling user.
        db: Database session.

    Raises:
        StepUpFailedError: If the step-up does not verify.
    """
    verify_step_up(step_up, identity_providers_constants.StepUpAction.GARMIN_UNLINK)
    user_integrations_integration.unlink_garminconnect_account(user_id, db)
    jasil_audit.stage(
        db,
        garmin_audit_actions.ACCOUNT_UNLINK,
        target_type="user",
        target_id=str(user_id),
        target_owner_id=str(user_id),
    )
    db.commit()
    logger.info(
        "Garmin Connect unlinked",
        extra=core_logger.context(user_id=user_id),
    )


def get_linked_user_integrations(
    user_id: uuid.UUID, db: Session
) -> user_integrations_schema.UserIntegrationsRead | None:
    """Return a user's integrations when Garmin Connect is linked.

    Args:
        user_id: The user to look up.
        db: Database session.

    Returns:
        The user's integrations, or ``None`` when Garmin Connect is not linked.

    Raises:
        NotFoundError: When the user has no integrations record.
    """
    user_integrations = user_integrations_integration.get_user_integrations(user_id, db)

    if user_integrations is None:
        raise core_exceptions.NotFoundError("User information not found")

    if user_integrations.garminconnect_token is None:
        return None

    return user_integrations


class GarminSession(NamedTuple):
    """A linked user's authenticated client and the stored token it was restored from.

    Attributes:
        client: The authenticated Garmin Connect client.
        token: The token as stored when the client was restored, so a rejection can be
            told apart from a later re-link.
    """

    client: garminconnect.Garmin
    token: dict[str, Any]


def get_user_garminconnect_session(user_id: uuid.UUID, db: Session) -> GarminSession | None:
    """Restore the session of a linked user from the token stored for them.

    Args:
        user_id: The user whose Garmin Connect account to use.
        db: Database session.

    Returns:
        The session, or ``None`` when Garmin Connect is not linked or the stored session is rejected.

    Raises:
        UndecryptableError: When the stored token cannot be decrypted with the configured key. The
            account stays linked: the fault is the key, not the token.
    """
    try:
        user_integrations = get_linked_user_integrations(user_id, db)
    except core_exceptions.NotFoundError:
        logger.debug("Garmin Connect user has no integrations record", extra=core_logger.context(user_id=user_id))
        return None

    token = user_integrations.garminconnect_token if user_integrations is not None else None
    if token is None:
        logger.debug(
            "Garmin Connect not linked",
            extra=core_logger.context(user_id=user_id),
        )
        return None

    client = garmin_token_utils.login_garminconnect_using_tokens(token)
    return GarminSession(client, token) if client is not None else None


@contextmanager
def linked_session(
    user_id: uuid.UUID, rate_limits: garmin_rate_limit_store.GarminRateLimitStore
) -> Generator[GarminSession | None]:
    """Yield a linked user's session with no database session open, then store its refreshed token.

    The token is stored whether the body succeeds or raises, so the next sync restores a live one.
    Rejection by Garmin Connect is the body's to handle, as what follows it differs per sync.

    Args:
        user_id: The user whose Garmin Connect account to use.
        rate_limits: The shared Garmin Connect rate-limit state, checked before the session is restored.

    Yields:
        The session, or ``None`` when Garmin Connect is not linked or the stored session is rejected.

    Raises:
        TooManyRequestsError: When the account is rate limited, or another process keeps refreshing the token.
    """
    raise_if_rate_limited(user_id, rate_limits)
    with core_database.SessionLocal() as db:
        session = get_user_garminconnect_session(user_id, db)
    if session is not None:
        session = fresh_session(user_id, session, rate_limits)
    if session is None:
        yield None
        return
    try:
        yield session
    finally:
        save_refreshed_token(user_id, session)


def fresh_session(
    user_id: uuid.UUID, session: GarminSession, claims: garmin_rate_limit_store.GarminRateLimitStore
) -> GarminSession | None:
    """Return a session whose token is not about to expire, refreshing it under the user's shared claim.

    The client would otherwise refresh the token itself in the middle of a call, and two syncs of one
    user doing so at once can invalidate each other's refresh token. Only the holder of the claim
    refreshes; a caller that finds it held waits for the holder, then restores the token it stored.

    Args:
        user_id: The user the session belongs to.
        session: The session as restored from the stored token.
        claims: The shared Garmin Connect state holding the refresh claim.

    Returns:
        A session that needs no refresh, or ``None`` when the account was unlinked meanwhile.

    Raises:
        TooManyRequestsError: When another process still holds the refresh claim after the wait.
    """
    deadline = time.monotonic() + garmin_constants.TOKEN_REFRESH_WAIT_SECONDS
    current: GarminSession | None = session
    while current is not None and garmin_token_utils.expires_soon(current.client.client):
        if _claim_refresh(user_id, claims):
            try:
                return _refresh_under_claim(user_id)
            finally:
                _release_refresh(user_id, claims)
        if time.monotonic() >= deadline:
            logger.warning(
                "Another process is refreshing the Garmin Connect token", extra=core_logger.context(user_id=user_id)
            )
            raise core_exceptions.TooManyRequestsError(
                "Another process is refreshing the Garmin Connect token",
                scope=core_exceptions.TooManyRequestsScope.PROVIDER,
                retry_at=datetime.now(UTC) + timedelta(seconds=garmin_constants.TOKEN_REFRESH_CLAIM_TTL_SECONDS),
            )
        time.sleep(garmin_constants.TOKEN_REFRESH_POLL_SECONDS)
        with core_database.SessionLocal() as db:
            current = get_user_garminconnect_session(user_id, db)
    return current


def _claim_refresh(user_id: uuid.UUID, claims: garmin_rate_limit_store.GarminRateLimitStore) -> bool:
    """Claim the user's token refresh, failing open when the shared state is unreachable.

    A refresh that races is recoverable by relinking, whereas failing closed would stop every sync for as
    long as the state is down.

    Args:
        user_id: The user whose token is about to be refreshed.
        claims: The shared Garmin Connect state holding the refresh claim.

    Returns:
        True when this caller may refresh, False when another already is.
    """
    try:
        return claims.claim_token_refresh(user_id)
    except platform_providers.StateBackendUnavailableError as err:
        logger.warning(
            "Could not claim the Garmin Connect token refresh; refreshing anyway",
            exc_info=err,
            extra=core_logger.context(user_id=user_id),
        )
        return True


def _release_refresh(user_id: uuid.UUID, claims: garmin_rate_limit_store.GarminRateLimitStore) -> None:
    """Release the user's token refresh claim; when the shared state is unreachable it expires on its own.

    Args:
        user_id: The user whose token was refreshed.
        claims: The shared Garmin Connect state holding the refresh claim.
    """
    try:
        claims.release_token_refresh(user_id)
    except platform_providers.StateBackendUnavailableError as err:
        logger.warning(
            "Could not release the Garmin Connect token refresh claim; it expires",
            exc_info=err,
            extra=core_logger.context(user_id=user_id),
        )


def _refresh_under_claim(user_id: uuid.UUID) -> GarminSession | None:
    """Refresh the stored token of a user while this process holds the refresh claim.

    The token is read again first, as the process that held the claim before may have refreshed it. When
    Garmin Connect refuses the refresh the session is returned as it is: the client retries it on its
    first call and a rejection is handled there, as for any other call.

    Args:
        user_id: The user whose token to refresh.

    Returns:
        The session holding the refreshed token, or ``None`` when the account was unlinked meanwhile.
    """
    with core_database.SessionLocal() as db:
        stored = get_user_garminconnect_session(user_id, db)
    if stored is None or not garmin_token_utils.expires_soon(stored.client.client):
        return stored
    try:
        garmin_token_utils.refresh(stored.client.client)
    except garminconnect.GarminConnectAuthenticationError as err:
        logger.warning(
            "Garmin Connect refused the token refresh", exc_info=err, extra=core_logger.context(user_id=user_id)
        )
        return stored
    save_refreshed_token(user_id, stored)
    return stored


def save_refreshed_token(user_id: uuid.UUID, session: GarminSession) -> None:
    """Store the token a sync's client refreshed, so the next sync restores a live one.

    Garmin Connect may rotate the refresh token, in which case the stored one stops working.
    A failure is logged, not raised: the sync itself has already finished.

    Args:
        user_id: The user the session belongs to.
        session: The session the sync used.
    """
    try:
        token = garmin_token_utils.refreshed_token(session.token, session.client.client)
        if token is None:
            return
        with core_database.SessionLocal() as db:
            if user_integrations_integration.replace_garminconnect_token_if_token(user_id, session.token, token, db):
                db.commit()
                logger.debug("Garmin Connect token refreshed", extra=core_logger.context(user_id=user_id))
    except (sqlalchemy.exc.SQLAlchemyError, core_exceptions.CryptographyError) as err:
        logger.error(
            "Failed to store the refreshed Garmin Connect token",
            exc_info=err,
            extra=core_logger.context(user_id=user_id),
        )


def linked_user_ids(after_id: uuid.UUID | None, limit: int) -> list[uuid.UUID]:
    """Page through the users who have linked Garmin Connect, in a short session of its own.

    Args:
        after_id: Return only users with an id greater than this.
        limit: Maximum number of user ids to return.

    Returns:
        The linked user ids, ascending.
    """
    with core_database.SessionLocal() as db:
        return user_integrations_integration.list_user_ids_with_garminconnect_linked(after_id, limit, db)


def rate_limit_error(
    err: Exception, user_id: uuid.UUID, rate_limits: garmin_rate_limit_store.GarminRateLimitStore
) -> core_exceptions.TooManyRequestsError:
    """Record that Garmin Connect refused a call as rate limited, and build the error for it.

    Garmin Connect reports no reset time, so the account is left alone for one cooldown, in every
    process, and the refresh waits that long before it tries again.

    Args:
        err: The rate-limit error Garmin Connect raised.
        user_id: The user whose account was limited.
        rate_limits: The shared Garmin Connect rate-limit state.

    Returns:
        The error to raise, carrying when the refresh may run again.
    """
    logger.warning("Garmin Connect rate limit hit", exc_info=err, extra=core_logger.context(user_id=user_id))
    return core_exceptions.TooManyRequestsError(
        "Garmin Connect rate limit exceeded. Please try again later.",
        scope=core_exceptions.TooManyRequestsScope.PROVIDER,
        retry_at=rate_limits.mark_rate_limited(user_id),
    )


def raise_if_rate_limited(user_id: uuid.UUID, rate_limits: garmin_rate_limit_store.GarminRateLimitStore) -> None:
    """Refuse a Garmin Connect call while the user's account is rate limited.

    Args:
        user_id: The user about to be synced.
        rate_limits: The shared Garmin Connect rate-limit state.

    Raises:
        TooManyRequestsError: When the account is rate limited, carrying when the limit clears.
    """
    retry_at = rate_limits.rate_limited_until(user_id)
    if retry_at is not None:
        logger.debug("Garmin Connect rate limit active, skipping the call", extra=core_logger.context(user_id=user_id))
        raise core_exceptions.TooManyRequestsError(
            "Garmin Connect rate limit exceeded. Please try again later.",
            scope=core_exceptions.TooManyRequestsScope.PROVIDER,
            retry_at=retry_at,
        )


def handle_rejected_token(user_id: uuid.UUID, session: GarminSession, err: Exception) -> None:
    """Unlink an account whose token Garmin Connect rejected during a sync, and tell the user.

    Args:
        user_id: The user whose sync was rejected.
        session: The session the sync used.
        err: The authentication error Garmin Connect raised.
    """
    logger.warning(
        "Garmin Connect token expired. Unlinking account. User must re-link",
        exc_info=err,
        extra=core_logger.context(user_id=user_id),
    )
    with core_database.SessionLocal() as db:
        unlink_expired_account(user_id, session.token, db)


def unlink_expired_account(user_id: uuid.UUID, token: dict[str, Any], db: Session) -> None:
    """Unlink an account whose Garmin Connect token expired and tell the user.

    The unlink and the notification row commit together; the live push is published after.
    Nothing happens when the stored token is no longer ``token``: the user re-linked, or
    another job already unlinked it and told them.

    Args:
        user_id: The user whose account to unlink.
        token: The stored token that Garmin Connect rejected.
        db: The caller's session, which this commits.
    """
    if not user_integrations_integration.unlink_garminconnect_account_if_token(user_id, token, db):
        db.rollback()
        logger.info(
            "Garmin Connect token changed since it expired; account left linked",
            extra=core_logger.context(user_id=user_id),
        )
        return
    notification, ws_message = notifications_integration.create_garmin_token_expired_notification(user_id, db)
    jasil_audit.stage(
        db,
        garmin_audit_actions.ACCOUNT_REVOKE,
        target_type="user",
        target_id=str(user_id),
        target_owner_id=str(user_id),
    )
    db.commit()
    notifications_integration.push_notification(user_id, notification, ws_message)
    logger.info(
        "Expired Garmin Connect account unlinked",
        extra=core_logger.context(user_id=user_id),
    )
