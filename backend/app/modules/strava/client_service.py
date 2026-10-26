"""Strava API access: the client, its token refresh and the rate-limit checks."""

import time
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session
from stravalib.client import Client as StravaClient
from stravalib.exc import Fault as StravaFault

import core.cryptography as core_cryptography
import core.exceptions as core_exceptions
import core.logger as core_logger
import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity.schema as activity_schema
import modules.strava.rate_limit_store as strava_rate_limit_store
import modules.users.users_integrations.integration_service as user_integrations_integration
import modules.users.users_integrations.schema as user_integrations_schema
from core.database import SessionLocal

logger = core_logger.get_logger(__name__)


def get_client_id(user_integrations: user_integrations_schema.UsersIntegrationsRead) -> str:
    """Get the Strava application (client ID) a user's integration belongs to.

    It is the scope of Strava's rate limits, so every call that checks or records
    one needs it.

    Args:
        user_integrations: The user's integration settings.

    Returns:
        The decrypted client ID.

    Raises:
        DependencyFailedError: When the user has no Strava client ID stored.
    """
    if user_integrations.strava_client_id is None:
        raise core_exceptions.DependencyFailedError(
            "Strava client ID not configured. Please reconnect your Strava account."
        )
    return core_cryptography.decrypt_token_fernet(user_integrations.strava_client_id)


def is_strava_rate_limit_error(err: Exception) -> bool:
    """Check if an exception is a Strava rate limit error.

    Args:
        err: The exception to check.

    Returns:
        True if the error is a 429 rate limit response.
    """
    if isinstance(err, StravaFault):
        response = getattr(err, "response", None)
        if response is not None and getattr(response, "status_code", 0) == 429:
            return True
    err_str = str(err).lower()
    return "rate limit" in err_str or "429" in err_str


def is_strava_not_found_error(err: Exception) -> bool:
    """Check if an exception is a Strava 404 Not Found error.

    This occurs for activities that have no streams, such as
    those manually added via Apple Health and imported into Strava.

    Args:
        err: The exception to check.

    Returns:
        True if the error is a 404 not-found response.
    """
    if isinstance(err, StravaFault):
        response = getattr(err, "response", None)
        if response is not None and getattr(response, "status_code", 0) == 404:
            return True
    err_str = str(err).lower()
    return "not found" in err_str or "404" in err_str


def _noop_rate_limiter(response_headers: dict, method: str) -> None:
    """No-op rate limiter replacement for stravalib.

    Args:
        response_headers: HTTP response headers.
        method: HTTP method used.
    """
    pass


def refresh_user_strava_token(user_id: int, rate_limits: strava_rate_limit_store.StravaRateLimitStore) -> None:
    """Refresh a user's Strava access token when it is about to expire.

    Called at the start of the user's own sync job, so tokens are kept current
    without a separate pass over every user. The integration is read in one short
    session, the Strava call runs with none open, and the new tokens are written in
    another. A failure is logged and left to the sync that follows, which will fail
    visibly if the token really is unusable.

    Args:
        user_id: The user whose token to refresh.
        rate_limits: The shared Strava rate-limit state.
    """
    with SessionLocal() as db:
        user_integrations = user_integrations_integration.get_user_integrations(user_id, db)

    if user_integrations is None:
        logger.info(
            "User integrations not found, skipping Strava token refresh", extra=core_logger.context(user_id=user_id)
        )
        return

    if not (
        user_integrations.strava_token is not None
        and user_integrations.strava_refresh_token is not None
        and user_integrations.strava_token_expires_at is not None
        and user_integrations.strava_client_id is not None
        and user_integrations.strava_client_secret is not None
    ):
        logger.info("No Strava token found, skipping token refresh", extra=core_logger.context(user_id=user_id))
        return

    refresh_time = user_integrations.strava_token_expires_at.replace(tzinfo=UTC) - timedelta(minutes=60)
    if datetime.now(UTC) <= refresh_time:
        return

    client_id = core_cryptography.decrypt_token_fernet(user_integrations.strava_client_id)
    if rate_limits.is_rate_limited(client_id):
        logger.warning("Strava rate limit active, skipping token refresh", extra=core_logger.context(user_id=user_id))
        return

    try:
        strava_client = create_strava_client(user_integrations)
        tokens = strava_client.refresh_access_token(
            client_id=client_id,
            client_secret=core_cryptography.decrypt_token_fernet(user_integrations.strava_client_secret),
            refresh_token=core_cryptography.decrypt_token_fernet(user_integrations.strava_refresh_token),
        )
    except Exception as err:
        if is_strava_rate_limit_error(err):
            err_str = str(err).lower()
            is_long = "long" in err_str or "daily" in err_str
            rate_limits.mark_rate_limited(client_id, is_long_term=is_long)
            logger.warning("Strava rate limit hit during token refresh", extra=core_logger.context(user_id=user_id))
            return
        logger.error("Error refreshing the Strava token", extra=core_logger.context(user_id=user_id), exc_info=err)
        return

    with SessionLocal() as db:
        user_integrations_integration.link_strava_account(user_id, tokens, db)
        db.commit()
    logger.info("Strava tokens refreshed", extra=core_logger.context(user_id=user_id))


def fetch_and_validate_activity(activity_id: int, user_id: int, db: Session) -> activity_schema.ActivityRead | None:
    """Return the user's stored activity for a Strava activity id, if there is one.

    Args:
        activity_id: The Strava activity id.
        user_id: The user the activity belongs to.
        db: Database session.

    Returns:
        The stored activity, or ``None`` when it has not been imported.
    """
    # Get the activity by Strava ID from the user
    activity_db = activity_integration.get_activity_by_strava_id(activity_id, user_id, db)

    # Check if activity is None
    if activity_db:
        # Log an informational event if the activity already exists
        logger.info(
            "Strava activity already exists, skipping",
            extra=core_logger.context(user_id=user_id, strava_activity_id=activity_id),
        )

        # Return None
        return activity_db
    else:
        return None


def fetch_user_integrations_and_validate_token(
    user_id: int, db: Session
) -> user_integrations_schema.UsersIntegrationsRead | None:
    """Return a user's integrations when Strava is linked.

    Args:
        user_id: The user to look up.
        db: Database session.

    Returns:
        The user's integrations, or ``None`` when Strava is not linked.

    Raises:
        NotFoundError: When the user has no integrations row.
    """
    # Get the user integrations by user ID
    user_integrations = user_integrations_integration.get_user_integrations(user_id, db)

    # Check if user integrations is None
    if user_integrations is None:
        raise core_exceptions.NotFoundError("User information not found")

    # Check if user_integrations.strava_token_expires_at is None
    if user_integrations.strava_token_expires_at is None:
        return None

    # Return the user integrations
    return user_integrations


def create_strava_client(
    user_integrations: user_integrations_schema.UsersIntegrationsRead,
) -> StravaClient:
    """Build a Strava client from a user's stored tokens.

    stravalib's own rate limiting is replaced by a no-op: it would block the thread
    for minutes or hours when a limit is hit, and the shared rate-limit state decides
    instead.

    Args:
        user_integrations: The user's integration settings.

    Returns:
        A client authenticated as the user.
    """
    # Convert to epoch timestamp
    epoch_time = (
        int(time.mktime(user_integrations.strava_token_expires_at.timetuple()))
        if user_integrations.strava_token_expires_at
        else None
    )

    # Create a Strava client with rate_limit_requests
    # disabled to prevent stravalib from blocking the
    # thread for minutes/hours when limits are hit.
    try:
        client = StravaClient(
            access_token=(
                core_cryptography.decrypt_token_fernet(user_integrations.strava_token)
                if user_integrations.strava_token
                else None
            ),
            refresh_token=(
                core_cryptography.decrypt_token_fernet(user_integrations.strava_refresh_token)
                if user_integrations.strava_refresh_token
                else None
            ),
            token_expires=epoch_time,
            rate_limit_requests=False,
        )
        # Replace the no-op limiter with our own no-op
        # to suppress stravalib rate limit warnings
        client.protocol.rate_limiter = _noop_rate_limiter
        return client
    except Exception as err:
        # Log the error and re-raise the exception
        logger.error("Error creating the Strava client", extra=core_logger.context(error=str(err)), exc_info=err)
        raise err
