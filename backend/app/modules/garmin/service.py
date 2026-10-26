"""Unlinking a Garmin Connect account and the authenticated sessions its syncs use.

Linking lives in :mod:`modules.garmin.link_service`. The activity, gear and health syncs live in
:mod:`modules.garmin.activity_service`, :mod:`modules.garmin.gear_service` and
:mod:`modules.garmin.health_service`.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import NamedTuple

import garminconnect
from sqlalchemy.orm import Session

import core.database as core_database
import core.exceptions as core_exceptions
import core.logger as core_logger
import modules.garmin.constants as garmin_constants
import modules.garmin.token_utils as garmin_token_utils
import modules.notifications.integration_service as notifications_integration
import modules.users.users_integrations.integration_service as user_integrations_integration
import modules.users.users_integrations.schema as user_integrations_schema

logger = core_logger.get_logger(__name__)


def unlink_account(user_id: int, db: Session) -> None:
    """Unlink a user's Garmin Connect account.

    Args:
        user_id: The user unlinking Garmin Connect.
        db: Database session.
    """
    user_integrations_integration.unlink_garminconnect_account(user_id, db)
    db.commit()
    logger.info(
        "Garmin Connect unlinked",
        extra=core_logger.context(user_id=user_id),
    )


def get_linked_user_integrations(user_id: int, db: Session) -> user_integrations_schema.UsersIntegrationsRead | None:
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
    token: dict


def get_user_garminconnect_session(user_id: int, db: Session) -> GarminSession | None:
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
        logger.warning("Garmin Connect user has no integrations record", extra=core_logger.context(user_id=user_id))
        return None

    if user_integrations is None:
        logger.debug(
            "Garmin Connect not linked",
            extra=core_logger.context(user_id=user_id),
        )
        return None

    token = user_integrations.garminconnect_token
    client = garmin_token_utils.login_garminconnect_using_tokens(token)
    return GarminSession(client, token) if client is not None else None


@contextmanager
def linked_session(user_id: int) -> Iterator[GarminSession | None]:
    """Yield a linked user's session with no database session open, then store its refreshed token.

    The token is stored whether the body succeeds or raises, so the next sync restores a live one.
    Rejection by Garmin Connect is the body's to handle, as what follows it differs per sync.

    Args:
        user_id: The user whose Garmin Connect account to use.

    Yields:
        The session, or ``None`` when Garmin Connect is not linked or the stored session is rejected.
    """
    with core_database.SessionLocal() as db:
        session = get_user_garminconnect_session(user_id, db)
    if session is None:
        yield None
        return
    try:
        yield session
    finally:
        save_refreshed_token(user_id, session)


def get_user_garminconnect_client(user_id: int, db: Session) -> garminconnect.Garmin | None:
    """Return an authenticated Garmin Connect client for a linked user, changing nothing.

    Serves data migrations, which read the account and never unlink it.

    Args:
        user_id: The user whose Garmin Connect account to use.
        db: Database session.

    Returns:
        The client, or ``None`` when Garmin Connect is not linked or the stored session is unusable.
    """
    try:
        session = get_user_garminconnect_session(user_id, db)
    except core_exceptions.UndecryptableError:
        return None
    return session.client if session is not None else None


def save_refreshed_token(user_id: int, session: GarminSession) -> None:
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
    except Exception as err:
        logger.error(
            "Failed to store the refreshed Garmin Connect token",
            exc_info=err,
            extra=core_logger.context(user_id=user_id),
        )


def linked_user_ids(after_id: int, limit: int) -> list[int]:
    """Page through the users who have linked Garmin Connect, in a short session of its own.

    Args:
        after_id: Return only users with an id greater than this.
        limit: Maximum number of user ids to return.

    Returns:
        The linked user ids, ascending.
    """
    with core_database.SessionLocal() as db:
        return user_integrations_integration.list_user_ids_with_garminconnect_linked(after_id, limit, db)


def rate_limit_error(err: Exception) -> core_exceptions.TooManyRequestsError:
    """Build the error for Garmin Connect refusing a call as rate limited.

    Garmin Connect reports no reset time, so the refresh waits one cooldown before it tries again.

    Args:
        err: The rate-limit error Garmin Connect raised.

    Returns:
        The error to raise, carrying when the refresh may run again.
    """
    logger.warning("Garmin Connect rate limit hit", exc_info=err)
    return core_exceptions.TooManyRequestsError(
        "Garmin Connect rate limit exceeded. Please try again later.",
        retry_at=datetime.now(UTC) + timedelta(seconds=garmin_constants.RATE_LIMIT_COOLDOWN_SECONDS),
    )


def handle_rejected_token(user_id: int, session: GarminSession, err: Exception) -> None:
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


def unlink_expired_account(user_id: int, token: dict, db: Session) -> None:
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
    db.commit()
    notifications_integration.push_notification(user_id, notification, ws_message)
    logger.info(
        "Expired Garmin Connect account unlinked",
        extra=core_logger.context(user_id=user_id),
    )
