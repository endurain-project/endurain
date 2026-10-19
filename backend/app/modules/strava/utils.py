import time
from datetime import UTC, datetime, timedelta

import jasil.providers as platform_providers
import jasil.runtime as platform_runtime
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from stravalib.client import Client as StravaClient
from stravalib.exc import Fault as StravaFault

import core.cryptography as core_cryptography
import core.logger as core_logger
import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity.schema as activity_schema
import modules.users.users_integrations.crud as user_integrations_crud
import modules.users.users_integrations.schema as user_integrations_schema
from core.database import SessionLocal

logger = core_logger.get_logger(__name__)


class StravaRateLimitTracker:
    """Tracks Strava API rate limit state in the platform's shared state.

    The limits are Strava's, per application, so every process and replica has to
    see the same answer: a process-local flag would let each worker keep
    hammering an API another one was already told to back off from. The flags are
    TTL keys in the platform ``StateProvider`` (in-process under the ``local``
    profile, Redis when distributed), so they expire on their own.
    """

    # Short-term limits reset every 15 minutes
    SHORT_TERM_COOLDOWN_SECONDS = 15 * 60

    _SHORT_TERM_KEY = "strava:rate_limited:short"
    _LONG_TERM_KEY = "strava:rate_limited:long"

    @staticmethod
    def _state() -> platform_providers.StateProvider:
        return platform_runtime.get_active_platform().state

    def mark_rate_limited(self, is_long_term: bool = False) -> None:
        """
        Record that a rate limit was hit.

        Args:
            is_long_term: True for the daily limit (resets at UTC midnight),
                False for the 15-minute limit.
        """
        now = datetime.now(UTC)
        if is_long_term:
            tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            key, ttl = self._LONG_TERM_KEY, max(1, int((tomorrow - now).total_seconds()))
            logger.warning(f"Strava daily rate limit hit. Skipping until {tomorrow}")
        else:
            key, ttl = self._SHORT_TERM_KEY, self.SHORT_TERM_COOLDOWN_SECONDS
            logger.warning(f"Strava 15-min rate limit hit. Skipping for {ttl} seconds")
        try:
            self._state().set(key, b"1", ttl_seconds=ttl)
        except platform_providers.StateBackendUnavailableError as err:
            logger.error("Could not record the Strava rate limit", exc_info=err)

    def is_rate_limited(self) -> bool:
        """
        Check if Strava API calls should be skipped.

        Fails open when the shared state is unreachable: a missed back-off costs
        one rejected call, which marks the limit again, whereas failing closed
        would stop every sync for as long as the state store is down.

        Returns:
            True if currently rate-limited.
        """
        try:
            state = self._state()
            return state.get(self._LONG_TERM_KEY) is not None or state.get(self._SHORT_TERM_KEY) is not None
        except platform_providers.StateBackendUnavailableError as err:
            logger.warning("Could not read the Strava rate limit state; assuming not limited", exc_info=err)
            return False


# Global rate limit tracker instance
rate_limit_tracker = StravaRateLimitTracker()


def is_strava_rate_limit_error(err: Exception) -> bool:
    """
    Check if an exception is a Strava rate limit error.

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
    """
    Check if an exception is a Strava 404 Not Found error.

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
    """
    No-op rate limiter replacement for stravalib.

    Args:
        response_headers: HTTP response headers.
        method: HTTP method used.
    """
    pass


def refresh_user_strava_token(user_id: int) -> None:
    """Refresh a user's Strava access token when it is about to expire.

    Called at the start of the user's own sync job, so tokens are kept current
    without a separate pass over every user. The integration is read in one short
    session, the Strava call runs with none open, and the new tokens are written in
    another. A failure is logged and left to the sync that follows, which will fail
    visibly if the token really is unusable.

    Args:
        user_id: The user whose token to refresh.
    """
    if rate_limit_tracker.is_rate_limited():
        logger.warning(f"User {user_id}: Strava rate limit active, skipping token refresh")
        return

    with SessionLocal() as db:
        user_integrations = user_integrations_crud.get_user_integrations_by_user_id(user_id, db)

    if user_integrations is None:
        logger.info(f"User {user_id}: User integrations not found. Will skip processing")
        return

    if not (
        user_integrations.strava_token is not None
        and user_integrations.strava_refresh_token is not None
        and user_integrations.strava_token_expires_at is not None
        and user_integrations.strava_client_id is not None
        and user_integrations.strava_client_secret is not None
    ):
        logger.info(f"User {user_id}: No Strava token found. Will skip processing")
        return

    refresh_time = user_integrations.strava_token_expires_at.replace(tzinfo=UTC) - timedelta(minutes=60)
    if datetime.now(UTC) <= refresh_time:
        return

    try:
        strava_client = create_strava_client(user_integrations)
        tokens = strava_client.refresh_access_token(
            client_id=core_cryptography.decrypt_token_fernet(user_integrations.strava_client_id),
            client_secret=core_cryptography.decrypt_token_fernet(user_integrations.strava_client_secret),
            refresh_token=core_cryptography.decrypt_token_fernet(user_integrations.strava_refresh_token),
        )
    except Exception as err:
        if is_strava_rate_limit_error(err):
            err_str = str(err).lower()
            is_long = "long" in err_str or "daily" in err_str
            rate_limit_tracker.mark_rate_limited(is_long_term=is_long)
            logger.warning(f"User {user_id}: Strava rate limit hit during token refresh")
            return
        logger.error(f"User {user_id}: Error refreshing the Strava token", exc_info=err)
        return

    with SessionLocal() as db:
        user_integrations_crud.link_strava_account(user_id, tokens, db)
    logger.info(f"User {user_id}: Strava tokens refreshed")


def fetch_and_validate_activity(activity_id: int, user_id: int, db: Session) -> activity_schema.ActivityRead | None:
    # Get the activity by Strava ID from the user
    activity_db = activity_integration.get_activity_by_strava_id(activity_id, user_id, db)

    # Check if activity is None
    if activity_db:
        # Log an informational event if the activity already exists
        logger.info(f"User {user_id}: Activity {activity_id} already exists. Will skip processing")

        # Return None
        return activity_db
    else:
        return None


def fetch_user_integrations_and_validate_token(
    user_id: int, db: Session
) -> user_integrations_schema.UsersIntegrationsRead | None:
    # Get the user integrations by user ID
    user_integrations = user_integrations_crud.get_user_integrations_by_user_id(user_id, db)

    # Check if user integrations is None
    if user_integrations is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User information not found",
        )

    # Check if user_integrations.strava_token_expires_at is None
    if user_integrations.strava_token_expires_at is None:
        return None

    # Return the user integrations
    return user_integrations


def create_strava_client(
    user_integrations: user_integrations_schema.UsersIntegrationsRead,
) -> StravaClient:
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
        logger.error(f"Error in create_strava_client: {err}", exc_info=err, extra=core_logger.context(console=True))
        raise err
