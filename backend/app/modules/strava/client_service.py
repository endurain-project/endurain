"""Strava API access: the client, its token refresh and the rate-limit checks."""

import calendar
from datetime import UTC, datetime, timedelta

import requests
from sqlalchemy.orm import Session
from stravalib.client import Client as StravaClient
from stravalib.exc import AccessUnauthorized, ObjectNotFound, RateLimitExceeded
from stravalib.exc import Fault as StravaFault

import core.cryptography as core_cryptography
import core.database as core_database
import core.exceptions as core_exceptions
import core.logger as core_logger
import modules.notifications.integration_service as notifications_integration
import modules.strava.constants as strava_constants
import modules.strava.rate_limit_store as strava_rate_limit_store
import modules.users.users_integrations.integration_service as user_integrations_integration
import modules.users.users_integrations.schema as user_integrations_schema

logger = core_logger.get_logger(__name__)


class StravaTokenRejectedError(core_exceptions.DependencyFailedError):
    """Raised when Strava rejected the user's token and the account was unlinked, so a sync must stop."""


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


def _fault_status(err: Exception) -> int | None:
    """Return the HTTP status a Strava fault carries.

    Args:
        err: The exception to inspect.

    Returns:
        The response's status code, or ``None`` when ``err`` is not a Strava fault with a response.
    """
    if isinstance(err, StravaFault):
        return getattr(getattr(err, "response", None), "status_code", None)
    return None


def is_strava_rate_limit_error(err: Exception) -> bool:
    """Check if an exception is a Strava rate limit error.

    Args:
        err: The exception to check.

    Returns:
        True if the error is a 429 rate limit response.
    """
    return isinstance(err, RateLimitExceeded) or _fault_status(err) == 429


def is_strava_not_found_error(err: Exception) -> bool:
    """Check if an exception is a Strava 404 Not Found error.

    This occurs for activities that have no streams, such as
    those manually added via Apple Health and imported into Strava.

    Args:
        err: The exception to check.

    Returns:
        True if the error is a 404 not-found response.
    """
    return isinstance(err, ObjectNotFound) or _fault_status(err) == 404


def is_strava_unauthorized_error(err: Exception) -> bool:
    """Check if an exception is Strava rejecting the user's access token.

    Args:
        err: The exception to check.

    Returns:
        True if the error is a 401 unauthorized response.
    """
    return isinstance(err, AccessUnauthorized) or _fault_status(err) == 401


def handle_rejected_token(user_id: int, refresh_token: str | None, err: Exception) -> None:
    """Unlink an account whose token Strava rejected during a sync, and tell the user.

    The tokens are cleared and the notification row committed together; the live push is
    published after. The client id and secret stay, so relinking is one step. Nothing happens
    when the stored refresh token is no longer ``refresh_token``: the user relinked, or
    another job already unlinked it and told them.

    Args:
        user_id: The user whose sync was rejected.
        refresh_token: The stored (encrypted) refresh token that Strava rejected.
        err: The unauthorized error Strava raised.
    """
    logger.warning(
        "Strava token rejected. Unlinking account. User must re-link",
        exc_info=err,
        extra=core_logger.context(user_id=user_id),
    )
    if refresh_token is None:
        return
    with core_database.SessionLocal() as db:
        if not user_integrations_integration.unlink_strava_tokens_if_refresh_token(user_id, refresh_token, db):
            db.rollback()
            logger.info(
                "Strava token changed since it was rejected; account left linked",
                extra=core_logger.context(user_id=user_id),
            )
            return
        notification, ws_message = notifications_integration.create_strava_token_expired_notification(user_id, db)
        db.commit()
    notifications_integration.push_notification(user_id, notification, ws_message)
    logger.info("Rejected Strava account unlinked", extra=core_logger.context(user_id=user_id))


def raise_if_unauthorized(
    err: Exception, user_id: int, user_integrations: user_integrations_schema.UsersIntegrationsRead
) -> None:
    """Unlink the account and refuse the call when ``err`` is Strava rejecting the token.

    Args:
        err: The exception a Strava call raised.
        user_id: The user the call was for.
        user_integrations: The integration settings the call was made with.

    Raises:
        StravaTokenRejectedError: When ``err`` is an unauthorized response.
    """
    if not is_strava_unauthorized_error(err):
        return
    handle_rejected_token(user_id, user_integrations.strava_refresh_token, err)
    raise StravaTokenRejectedError("Strava authentication failed. Please reconnect your Strava account.") from err


def _daily_limit_reached(err: Exception) -> bool:
    """Check from Strava's rate-limit headers whether ``err`` is the daily limit rather than the 15-minute one.

    Strava reports ``<short>,<daily>`` pairs in ``X-RateLimit-Limit`` and ``-Usage``, and in the
    ``X-ReadRateLimit-*`` pair for reads. The daily limit is reached when its usage is at its limit.
    Headers that are missing or unreadable count as the 15-minute limit: marking too short a
    back-off costs one rejected call, which marks the limit again.

    Args:
        err: The exception a Strava call raised.

    Returns:
        True when the response says the daily usage reached the daily limit.
    """
    headers = getattr(getattr(err, "response", None), "headers", None)
    if not headers:
        return False
    headers = {name.casefold(): value for name, value in headers.items()}
    for prefix in ("x-readratelimit", "x-ratelimit"):
        try:
            usage = int(headers[f"{prefix}-usage"].split(",")[1])
            limit = int(headers[f"{prefix}-limit"].split(",")[1])
        except (KeyError, IndexError, ValueError, AttributeError):
            continue
        if usage >= limit:
            return True
    return False


def raise_if_rate_limited(
    err: Exception, client_id: str, rate_limits: strava_rate_limit_store.StravaRateLimitStore
) -> None:
    """Record a Strava rate limit and refuse the call when ``err`` is one.

    Args:
        err: The exception a Strava call raised.
        client_id: The Strava application (client ID) that made the call.
        rate_limits: The shared Strava rate-limit state.

    Raises:
        TooManyRequestsError: When ``err`` is a Strava rate limit error.
    """
    if not is_strava_rate_limit_error(err):
        return
    retry_at = rate_limits.mark_rate_limited(client_id, is_long_term=_daily_limit_reached(err))
    raise core_exceptions.TooManyRequestsError(
        "Strava API rate limit exceeded. Please try again later.", retry_at=retry_at
    ) from err


def raise_if_rate_limit_active(
    client_id: str, user_id: int, rate_limits: strava_rate_limit_store.StravaRateLimitStore
) -> None:
    """Refuse a Strava call while the application's rate limit is active.

    Args:
        client_id: The Strava application (client ID) about to be called.
        user_id: The user the call is for, for the log.
        rate_limits: The shared Strava rate-limit state.

    Raises:
        TooManyRequestsError: When the application is rate limited.
    """
    if rate_limits.is_rate_limited(client_id):
        logger.warning("Strava rate limit active, skipping the call", extra=core_logger.context(user_id=user_id))
        raise core_exceptions.TooManyRequestsError(
            "Strava API rate limit exceeded. Please try again later.",
            retry_at=rate_limits.rate_limited_until(client_id),
        )


class _TimeoutSession(requests.Session):
    """A requests session that gives every call a timeout, as stravalib sets none."""

    def request(self, *args, **kwargs):
        """Send a request, bounded by :data:`strava_constants.HTTP_TIMEOUT_SECONDS` unless one is given."""
        kwargs.setdefault("timeout", strava_constants.HTTP_TIMEOUT_SECONDS)
        return super().request(*args, **kwargs)


def _noop_rate_limiter(response_headers: dict, method: str) -> None:
    """No-op rate limiter replacement for stravalib.

    Args:
        response_headers: HTTP response headers.
        method: HTTP method used.
    """


def _token_refresh_due(user_integrations: user_integrations_schema.UsersIntegrationsRead | None) -> bool:
    """Whether a user's Strava token is linked and about to expire.

    Args:
        user_integrations: The user's integration settings, or ``None``.

    Returns:
        True when every credential is stored and the token expires within the hour.
    """
    if (
        user_integrations is None
        or user_integrations.strava_token is None
        or user_integrations.strava_refresh_token is None
        or user_integrations.strava_token_expires_at is None
        or user_integrations.strava_client_id is None
        or user_integrations.strava_client_secret is None
    ):
        return False
    refresh_time = user_integrations.strava_token_expires_at.replace(tzinfo=UTC) - timedelta(minutes=60)
    return datetime.now(UTC) > refresh_time


def _token_expired(user_integrations: user_integrations_schema.UsersIntegrationsRead) -> bool:
    """Whether a user's Strava access token has already expired.

    Args:
        user_integrations: The user's integration settings, with a stored expiry.

    Returns:
        True when the token's expiry has passed.
    """
    return datetime.now(UTC) >= user_integrations.strava_token_expires_at.replace(tzinfo=UTC)


def refresh_user_strava_token(user_id: int, rate_limits: strava_rate_limit_store.StravaRateLimitStore) -> None:
    """Refresh a user's Strava access token when it is about to expire.

    Called at the start of the user's own sync job, so tokens are kept current
    without a separate pass over every user. Strava rotates the refresh token, so
    only one process refreshes a user at a time: the claim is taken first and the
    integration is read again under it, in case another process just finished. The new tokens are
    stored only while the refresh token is still the one they were refreshed from. The
    integration is read in short sessions, the Strava call runs with none open, and
    the new tokens are written in another. A failure is logged and left to the sync
    that follows, which will fail visibly if the token really is unusable.

    A token that has already expired is never handed to a sync unrefreshed: Strava would answer 401
    and the sync would unlink an account that is only waiting for its refresh.

    Args:
        user_id: The user whose token to refresh.
        rate_limits: The shared Strava rate-limit state.

    Raises:
        TooManyRequestsError: When the token has expired and another process holds the refresh; the work
            is deferred until that refresh has finished.
        DependencyFailedError: When the token has expired and Strava could not refresh it.
    """
    with core_database.SessionLocal() as db:
        user_integrations = user_integrations_integration.get_user_integrations(user_id, db)

    if not _token_refresh_due(user_integrations):
        logger.debug("No Strava token refresh due", extra=core_logger.context(user_id=user_id))
        return

    client_id = get_client_id(user_integrations)
    if rate_limits.is_rate_limited(client_id):
        logger.warning("Strava rate limit active, skipping token refresh", extra=core_logger.context(user_id=user_id))
        return

    if not rate_limits.claim_token_refresh(user_id):
        logger.debug("Another process is refreshing the Strava token", extra=core_logger.context(user_id=user_id))
        if _token_expired(user_integrations):
            raise core_exceptions.TooManyRequestsError(
                "Another process is refreshing the Strava token",
                retry_at=datetime.now(UTC) + timedelta(seconds=strava_constants.TOKEN_REFRESH_CLAIM_TTL_SECONDS),
            )
        return

    with core_database.SessionLocal() as db:
        user_integrations = user_integrations_integration.get_user_integrations(user_id, db)
    if not _token_refresh_due(user_integrations):
        return

    try:
        tokens = create_strava_client(user_integrations).refresh_access_token(
            client_id=client_id,
            client_secret=core_cryptography.decrypt_token_fernet(user_integrations.strava_client_secret),
            refresh_token=core_cryptography.decrypt_token_fernet(user_integrations.strava_refresh_token),
        )
    except Exception as err:
        try:
            raise_if_rate_limited(err, client_id, rate_limits)
        except core_exceptions.TooManyRequestsError:
            logger.warning("Strava rate limit hit during token refresh", extra=core_logger.context(user_id=user_id))
            return
        logger.error("Error refreshing the Strava token", extra=core_logger.context(user_id=user_id), exc_info=err)
        if _token_expired(user_integrations):
            raise core_exceptions.DependencyFailedError("The Strava token could not be refreshed") from err
        return

    try:
        with core_database.SessionLocal() as db:
            if not user_integrations_integration.replace_strava_tokens_if_refresh_token(
                user_id, user_integrations.strava_refresh_token, tokens, db
            ):
                db.rollback()
                logger.warning(
                    "Strava tokens changed during the refresh; the refreshed ones were discarded",
                    extra=core_logger.context(user_id=user_id),
                )
                return
            db.commit()
    except Exception as err:
        # Strava has already invalidated the old refresh token, so the rotated one is lost. The access
        # token still works until it expires; the sync that then fails on it unlinks the account and tells the user.
        logger.error(
            "Strava tokens were refreshed but could not be stored; the account must be relinked",
            extra=core_logger.context(user_id=user_id),
            exc_info=err,
        )
        return
    logger.debug("Strava tokens refreshed", extra=core_logger.context(user_id=user_id))


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
    user_integrations = user_integrations_integration.get_user_integrations(user_id, db)
    if user_integrations is None:
        raise core_exceptions.NotFoundError("User information not found")
    if user_integrations.strava_token_expires_at is None:
        return None
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

    Raises:
        UndecryptableError: When a stored token cannot be decrypted with the configured key.
    """
    epoch_time = (
        calendar.timegm(user_integrations.strava_token_expires_at.utctimetuple())
        if user_integrations.strava_token_expires_at
        else None
    )

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
        requests_session=_TimeoutSession(),
    )
    client.protocol.rate_limiter = _noop_rate_limiter
    return client
