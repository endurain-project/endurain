import threading
import time
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from stravalib.client import Client as StravaClient
from stravalib.exc import Fault as StravaFault

import activities.activity.crud as activities_crud
import activities.activity.schema as activities_schema
import core.cryptography as core_cryptography
import core.logger as core_logger
import users.users.crud as users_crud
import users.users_integrations.crud as user_integrations_crud
import users.users_integrations.models as user_integrations_models
from core.database import SessionLocal


class StravaRateLimitTracker:
    """
    Tracks Strava API rate limit state.

    Attributes:
        _lock: Thread lock for safe access.
        _short_term_reset: Short-term reset timestamp.
        _long_term_reset: Long-term reset timestamp.
    """

    # Short-term limits reset every 15 minutes
    SHORT_TERM_COOLDOWN_SECONDS = 15 * 60
    # Long-term limits reset at UTC midnight
    LONG_TERM_COOLDOWN_SECONDS = 24 * 60 * 60

    def __init__(self):
        """Initialize the rate limit tracker."""
        self._lock = threading.Lock()
        self._short_term_reset: datetime | None = None
        self._long_term_reset: datetime | None = None

    def mark_rate_limited(self, is_long_term: bool = False) -> None:
        """
        Record that a rate limit was hit.

        Args:
            is_long_term: True for daily limit,
                False for 15-min limit.
        """
        now = datetime.now(UTC)
        with self._lock:
            if is_long_term:
                # Reset at next UTC midnight
                tomorrow = (now + timedelta(days=1)).replace(
                    hour=0,
                    minute=0,
                    second=0,
                    microsecond=0,
                )
                self._long_term_reset = tomorrow
                core_logger.print_to_log(
                    f"Strava daily rate limit hit. Skipping until {tomorrow}",
                    "warning",
                )
            else:
                reset_at = now + timedelta(seconds=self.SHORT_TERM_COOLDOWN_SECONDS)
                self._short_term_reset = reset_at
                core_logger.print_to_log(
                    f"Strava 15-min rate limit hit. Skipping until {reset_at}",
                    "warning",
                )

    def is_rate_limited(self) -> bool:
        """
        Check if Strava API calls should be skipped.

        Returns:
            True if currently rate-limited.
        """
        now = datetime.now(UTC)
        with self._lock:
            if self._long_term_reset and now < self._long_term_reset:
                return True
            if self._short_term_reset and now < self._short_term_reset:
                return True
            # Clear expired entries
            self._long_term_reset = None
            self._short_term_reset = None
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


def refresh_strava_tokens(is_startup: bool = False):
    # Skip if Strava rate limit is active
    if rate_limit_tracker.is_rate_limited():
        core_logger.print_to_log(
            "Strava rate limit active, skipping token refresh",
            "warning",
        )
        return

    # Create a new database session using context manager
    with SessionLocal() as db:
        # Stream user IDs in bounded batches instead of loading the whole
        # users table into memory, refreshing each user's Strava token.
        for user_id in users_crud.stream_all_user_ids(db):
            refresh_user_strava_token(user_id, db, is_startup)


def refresh_user_strava_token(user_id: int, db: Session, is_startup: bool = False):
    # Get the user integrations by user ID
    user_integrations = user_integrations_crud.get_user_integrations_by_user_id(user_id, db)

    if user_integrations is None:
        # Log an informational event if the user integrations are not found
        core_logger.print_to_log(f"User {user_id}: User integrations not found. Will skip processing")

        # Return early since we cannot refresh tokens without user integrations
        return

    # Check if user_integrations strava token is not None
    if (
        user_integrations.strava_token is not None
        and user_integrations.strava_refresh_token is not None
        and user_integrations.strava_token_expires_at is not None
        and user_integrations.strava_client_id is not None
        and user_integrations.strava_client_secret is not None
    ):
        refresh_time = user_integrations.strava_token_expires_at.replace(tzinfo=UTC) - timedelta(minutes=60)

        if datetime.now(UTC) > refresh_time:
            try:
                strava_client = create_strava_client(user_integrations)
                tokens = strava_client.refresh_access_token(
                    client_id=core_cryptography.decrypt_token_fernet(user_integrations.strava_client_id),
                    client_secret=core_cryptography.decrypt_token_fernet(user_integrations.strava_client_secret),
                    refresh_token=core_cryptography.decrypt_token_fernet(user_integrations.strava_refresh_token),
                )

                # Update the user integrations with the tokens
                user_integrations_crud.link_strava_account(user_integrations.user_id, tokens, db)

                core_logger.print_to_log(f"User {user_id}: Strava tokens refreshed")
            except Exception as err:
                # Check for rate limit errors
                if is_strava_rate_limit_error(err):
                    err_str = str(err).lower()
                    is_long = "long" in err_str or "daily" in err_str
                    rate_limit_tracker.mark_rate_limited(is_long_term=is_long)
                    core_logger.print_to_log(
                        f"User {user_id}: Strava rate limit hit during token refresh",
                        "warning",
                    )
                    return

                # Log the exception
                core_logger.print_to_log(f"Error in refresh_strava_token: {err}", "error")

                # Raise an HTTPException with a 500 Internal Server Error status code
                if not is_startup:
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Internal Server Error",
                    ) from err
    else:
        # Log an informational event if the user does not have a Strava token
        core_logger.print_to_log(f"User {user_id}: No Strava token found. Will skip processing")


def fetch_and_validate_activity(activity_id: int, user_id: int, db: Session) -> activities_schema.Activity | None:
    # Get the activity by Strava ID from the user
    activity_db = activities_crud.get_activity_by_strava_id_from_user_id(activity_id, user_id, db)

    # Check if activity is None
    if activity_db:
        # Log an informational event if the activity already exists
        core_logger.print_to_log(f"User {user_id}: Activity {activity_id} already exists. Will skip processing")

        # Return None
        return activity_db
    else:
        return None


def fetch_user_integrations_and_validate_token(
    user_id: int, db: Session
) -> user_integrations_models.UsersIntegrations | None:
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
    user_integrations: user_integrations_models.UsersIntegrations,
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
        core_logger.print_to_log_and_console(f"Error in create_strava_client: {err}", "error", err)
        raise err
