"""Strava API access: the client, its token refresh and the rate-limit checks."""

import calendar
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, NamedTuple

import jasil.audit as jasil_audit
import requests
import sqlalchemy.exc
from sqlalchemy.orm import Session
from stravalib.client import Client as StravaClient
from stravalib.exc import AccessUnauthorized, ObjectNotFound, RateLimitExceeded
from stravalib.exc import Fault as StravaFault

import core.cryptography as core_cryptography
import core.database as core_database
import core.exceptions as core_exceptions
import core.logger as core_logger
import modules.notifications.integration_service as notifications_integration
import modules.strava.audit_actions as strava_audit_actions
import modules.strava.constants as strava_constants
import modules.strava.rate_limit_store as strava_rate_limit_store
import modules.users.users_integrations.constants as user_integrations_constants
import modules.users.users_integrations.integration_service as user_integrations_integration
import modules.users.users_integrations.schema as user_integrations_schema

if TYPE_CHECKING:
    from requests.cookies import RequestsCookieJar
    from requests.models import _JSON
    from requests.sessions import (
        _Auth,
        _Cert,
        _Data,
        _Files,
        _HeadersUpdateMapping,
        _HooksInput,
        _Params,
        _TextMapping,
        _Timeout,
        _Verify,
    )

logger = core_logger.get_logger(__name__)


class StravaTokenRejectedError(core_exceptions.DependencyFailedError):
    """Raised when Strava rejected the user's token and the account was unlinked, so a sync must stop."""


def get_client_id(user_integrations: user_integrations_schema.UserIntegrationsRead) -> str:
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


def get_client_secret(user_integrations: user_integrations_schema.UserIntegrationsRead) -> str:
    """Get the secret of the Strava application a user's integration belongs to.

    Args:
        user_integrations: The user's integration settings.

    Returns:
        The decrypted client secret.

    Raises:
        DependencyFailedError: When the user has no Strava client secret stored.
    """
    if user_integrations.strava_client_secret is None:
        raise core_exceptions.DependencyFailedError(
            "Strava client secret not configured. Please reconnect your Strava account."
        )
    return core_cryptography.decrypt_token_fernet(user_integrations.strava_client_secret)


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


def is_strava_client_error(err: Exception) -> bool:
    """Check if an exception is Strava refusing a request with a 4xx answer.

    Args:
        err: The exception to check.

    Returns:
        True if the error is a response with a 4xx status.
    """
    status = _fault_status(err)
    return status is not None and 400 <= status < 500


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


def _refresh_grant_refused(err: Exception) -> bool:
    """Check if an exception is Strava's token endpoint refusing a refresh token.

    Args:
        err: The exception ``refresh_access_token`` raised.

    Returns:
        True if Strava answered 400 or 401, which it does for a refresh token that was revoked or replaced.
    """
    return isinstance(err, AccessUnauthorized) or _fault_status(err) in (400, 401)


def handle_rejected_token(user_id: int, refresh_token: str | None, err: Exception, *, revoked: bool = False) -> None:
    """Unlink an account whose token Strava rejected during a sync, and tell the user.

    The tokens are cleared and the notification row committed together; the live push is
    published after. The client id and secret stay, so relinking is one step. Nothing happens
    when the stored refresh token is no longer ``refresh_token``: the user relinked, or
    another job already unlinked it and told them. When ``revoked`` is set the user withdrew Endurain's
    access on Strava: the time is stored with the tokens, the data stays for the grace period, and the notice
    names the day it is deleted unless the user relinks.

    Args:
        user_id: The user whose sync was rejected.
        refresh_token: The stored (encrypted) refresh token that Strava rejected.
        err: The unauthorized error Strava raised.
        revoked: Whether Strava refused the refresh token, or an access token it had just issued from it.
    """
    logger.warning(
        "Strava token rejected. Unlinking account. User must re-link",
        exc_info=err,
        extra=core_logger.context(user_id=user_id, revoked=revoked),
    )
    if refresh_token is None:
        return
    revoked_at = datetime.now(UTC) if revoked else None
    delete_on = (
        (revoked_at + timedelta(days=user_integrations_constants.STRAVA_REVOKED_DATA_GRACE_DAYS)).date()
        if revoked_at
        else None
    )
    with core_database.SessionLocal() as db:
        if not user_integrations_integration.unlink_strava_tokens_if_refresh_token(
            user_id, refresh_token, db, revoked_at=revoked_at
        ):
            db.rollback()
            logger.info(
                "Strava token changed since it was rejected; account left linked",
                extra=core_logger.context(user_id=user_id),
            )
            return
        notification, ws_message = notifications_integration.create_strava_token_expired_notification(
            user_id, db, delete_on=delete_on
        )
        jasil_audit.stage(
            db,
            strava_audit_actions.ACCOUNT_REVOKE,
            target_type="user",
            target_id=str(user_id),
            target_owner_id=str(user_id),
        )
        db.commit()
    notifications_integration.push_notification(user_id, notification, ws_message)
    logger.info("Rejected Strava account unlinked", extra=core_logger.context(user_id=user_id, revoked=revoked))


def call_strava[T](
    call: Callable[[StravaClient], T],
    strava_client: StravaClient,
    user_id: int,
    user_integrations: user_integrations_schema.UserIntegrationsRead,
    rate_limits: strava_rate_limit_store.StravaRateLimitStore,
) -> T:
    """Make one Strava call, confirming a 401 with the token endpoint instead of trusting it.

    A 401 can mean the access token expired or that the user withdrew Endurain's access on Strava. So the
    stored refresh token is used once, through :func:`refresh_user_strava_token`, and the call is made again
    with the new token. Only Strava refusing the refresh token, or refusing the new access token as well, is a
    revocation. A refresh that fails for any other reason leaves the tokens and the data alone and stops the
    sync, which tries again on its next run. Failures other than a 401 are the caller's to handle.

    Args:
        call: Makes the Strava call with the client it is given.
        strava_client: A client authenticated as the user.
        user_id: The user the call is for.
        user_integrations: The integration settings ``strava_client`` was built from.
        rate_limits: The shared Strava rate-limit state.

    Returns:
        What ``call`` returned.

    Raises:
        StravaTokenRejectedError: When Strava refused the refresh token or the new access token, so the account
            was unlinked as revoked; or when the account is no longer linked.
        TooManyRequestsError: When Strava's rate limit is active or another process is refreshing the token.
        DependencyFailedError: When the refresh failed without Strava refusing the refresh token.
    """
    try:
        return call(strava_client)
    except Exception as err:
        if not is_strava_unauthorized_error(err):
            raise
        logger.info(
            "Strava answered 401, confirming it with a token refresh", extra=core_logger.context(user_id=user_id)
        )

    if user_integrations.strava_refresh_token is None:
        raise StravaTokenRejectedError("Strava is not linked. Please reconnect your Strava account.")
    refresh_user_strava_token(user_id, rate_limits, rejected_refresh_token=user_integrations.strava_refresh_token)
    with core_database.SessionLocal() as db:
        refreshed = fetch_user_integrations_and_validate_token(user_id, db)
    if refreshed is None:
        raise StravaTokenRejectedError("Strava is not linked. Please reconnect your Strava account.")
    try:
        return call(create_strava_client(refreshed))
    except Exception as err:
        if not is_strava_unauthorized_error(err):
            raise
        handle_rejected_token(user_id, refreshed.strava_refresh_token, err, revoked=True)
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

    def request(
        self,
        method: str | bytes,
        url: str | bytes,
        params: "_Params | None" = None,
        data: "_Data | None" = None,
        headers: "_HeadersUpdateMapping | None" = None,
        cookies: "RequestsCookieJar | _TextMapping | None" = None,
        files: "_Files | None" = None,
        auth: "_Auth | None" = None,
        timeout: "_Timeout | None" = strava_constants.HTTP_TIMEOUT_SECONDS,
        allow_redirects: bool = True,
        proxies: "_TextMapping | None" = None,
        hooks: "_HooksInput | None" = None,
        stream: bool | None = None,
        verify: "_Verify | None" = None,
        cert: "_Cert | None" = None,
        json: "_JSON | None" = None,
    ) -> requests.Response:
        """Send a request, bounded by :data:`strava_constants.HTTP_TIMEOUT_SECONDS` unless one is given.

        Args:
            method: The HTTP method.
            url: The URL to request.
            params: The query parameters.
            data: The request body.
            headers: The request headers.
            cookies: The cookies to send.
            files: The files to upload.
            auth: The authentication to apply.
            timeout: How long to wait for the server, in seconds.
            allow_redirects: Whether to follow redirects.
            proxies: The proxies by protocol.
            hooks: The hooks by event.
            stream: Whether to stream the response body.
            verify: Whether, or against which CA bundle, to verify TLS.
            cert: The client certificate.
            json: The JSON body.

        Returns:
            The response.
        """
        return super().request(
            method,
            url,
            params=params,
            data=data,
            headers=headers,
            cookies=cookies,
            files=files,
            auth=auth,
            timeout=timeout,
            allow_redirects=allow_redirects,
            proxies=proxies,
            hooks=hooks,
            stream=stream,
            verify=verify,
            cert=cert,
            json=json,
        )


def _noop_rate_limiter(response_headers: dict[str, str], method: str) -> None:
    """No-op rate limiter replacement for stravalib.

    Args:
        response_headers: HTTP response headers.
        method: HTTP method used.
    """


class _LinkedToken(NamedTuple):
    """A user's linked Strava token, with the stored values its refresh needs.

    Attributes:
        integrations: The user's integration settings, with every Strava credential stored.
        refresh_token: The stored (encrypted) refresh token.
        expires_at: When the access token expires.
    """

    integrations: user_integrations_schema.UserIntegrationsRead
    refresh_token: str
    expires_at: datetime


def _linked_token(user_integrations: user_integrations_schema.UserIntegrationsRead | None) -> _LinkedToken | None:
    """Return a user's Strava token when it is linked.

    Args:
        user_integrations: The user's integration settings, or ``None``.

    Returns:
        The linked token, or ``None`` when a token, its expiry or an application credential is not stored.
    """
    if (
        user_integrations is None
        or user_integrations.strava_token is None
        or user_integrations.strava_refresh_token is None
        or user_integrations.strava_token_expires_at is None
        or user_integrations.strava_client_id is None
        or user_integrations.strava_client_secret is None
    ):
        return None
    return _LinkedToken(
        user_integrations, user_integrations.strava_refresh_token, user_integrations.strava_token_expires_at
    )


def _token_refresh_due(token: _LinkedToken) -> bool:
    """Whether a linked Strava token expires within the hour.

    Args:
        token: The user's linked token.

    Returns:
        True when the token expires within the hour.
    """
    return datetime.now(UTC) > token.expires_at.replace(tzinfo=UTC) - timedelta(minutes=60)


def _token_expired(token: _LinkedToken) -> bool:
    """Whether a user's Strava access token has already expired.

    Args:
        token: The user's linked token.

    Returns:
        True when the token's expiry has passed.
    """
    return datetime.now(UTC) >= token.expires_at.replace(tzinfo=UTC)


def refresh_user_strava_token(
    user_id: int,
    rate_limits: strava_rate_limit_store.StravaRateLimitStore,
    *,
    rejected_refresh_token: str | None = None,
) -> None:
    """Refresh a user's Strava access token when it is about to expire, or when Strava rejected it.

    Called at the start of the user's own sync job, so tokens are kept current
    without a separate pass over every user. Strava rotates the refresh token, so
    only one process refreshes a user at a time: the claim is taken first, released when the
    refresh is over, and the integration is read again under it, in case another process just finished.
    The new tokens are stored only while the refresh token is still the one they were refreshed from. The
    integration is read in short sessions, the Strava call runs with none open, and
    the new tokens are written in another. A failure is logged and left to the sync
    that follows, which will fail visibly if the token really is unusable.

    A token that has already expired is never handed to a sync unrefreshed: Strava would answer 401
    and the sync would unlink an account that is only waiting for its refresh. Only the token endpoint
    refusing the refresh token counts as the user revoking access: the account is unlinked as a revocation
    and the sync stops.

    With ``rejected_refresh_token`` the refresh is asked for, whatever the token's expiry, because Strava
    answered 401 to the access token. Nothing is then left to the sync that follows: when the refresh cannot
    be done, or Strava's answer cannot be read as a refusal, an error stops the sync with the tokens kept. A
    refresh token that is no longer ``rejected_refresh_token`` was replaced by another process, so nothing
    is refreshed again.

    Args:
        user_id: The user whose token to refresh.
        rate_limits: The shared Strava rate-limit state.
        rejected_refresh_token: The stored (encrypted) refresh token whose access token Strava rejected, when
            the refresh is a confirmation of that rejection.

    Raises:
        TooManyRequestsError: When the token has expired or a refresh was asked for, and another process
            holds the refresh or the application is rate limited; the work is deferred.
        DependencyFailedError: When the token has expired or a refresh was asked for, and Strava could not
            refresh it.
        StravaTokenRejectedError: When Strava refused the refresh token, so the account was unlinked.
    """
    forced = rejected_refresh_token is not None
    with core_database.SessionLocal() as db:
        linked = _linked_token(user_integrations_integration.get_user_integrations(user_id, db))

    if linked is None or not _refresh_wanted(linked, rejected_refresh_token):
        logger.debug("No Strava token refresh due", extra=core_logger.context(user_id=user_id))
        return

    client_id = get_client_id(linked.integrations)
    if rate_limits.is_rate_limited(client_id):
        logger.warning("Strava rate limit active, skipping token refresh", extra=core_logger.context(user_id=user_id))
        if forced:
            raise core_exceptions.TooManyRequestsError(
                "Strava API rate limit exceeded. Please try again later.",
                retry_at=rate_limits.rate_limited_until(client_id),
            )
        return

    if not rate_limits.claim_token_refresh(user_id):
        logger.debug("Another process is refreshing the Strava token", extra=core_logger.context(user_id=user_id))
        if forced or _token_expired(linked):
            raise core_exceptions.TooManyRequestsError(
                "Another process is refreshing the Strava token",
                retry_at=datetime.now(UTC) + timedelta(seconds=strava_constants.TOKEN_REFRESH_CLAIM_TTL_SECONDS),
            )
        return

    try:
        _refresh_under_claim(user_id, client_id, rate_limits, rejected_refresh_token)
    finally:
        rate_limits.release_token_refresh(user_id)


def _refresh_wanted(linked: _LinkedToken, rejected_refresh_token: str | None) -> bool:
    """Whether a linked token needs refreshing.

    Args:
        linked: The user's linked token.
        rejected_refresh_token: The refresh token whose access token Strava rejected, or ``None``.

    Returns:
        For a rejected token, whether it is still the stored one; otherwise whether the access token
        expires within the hour.
    """
    if rejected_refresh_token is None:
        return _token_refresh_due(linked)
    return core_cryptography.same_secret(linked.refresh_token, rejected_refresh_token)


def _refresh_under_claim(
    user_id: int,
    client_id: str,
    rate_limits: strava_rate_limit_store.StravaRateLimitStore,
    rejected_refresh_token: str | None,
) -> None:
    """Refresh a user's tokens once this process holds the refresh claim, and store them.

    Args:
        user_id: The user whose token to refresh.
        client_id: The Strava application (client ID) the user's link belongs to.
        rate_limits: The shared Strava rate-limit state.
        rejected_refresh_token: The refresh token whose access token Strava rejected, or ``None`` for a
            refresh that was due.

    Raises:
        TooManyRequestsError: When a refresh was asked for and Strava's rate limit was hit.
        DependencyFailedError: When the token has expired or a refresh was asked for, and it could not be
            done or stored.
        StravaTokenRejectedError: When Strava refused the refresh token, so the account was unlinked.
    """
    forced = rejected_refresh_token is not None
    with core_database.SessionLocal() as db:
        linked = _linked_token(user_integrations_integration.get_user_integrations(user_id, db))
    if linked is None or not _refresh_wanted(linked, rejected_refresh_token):
        return

    try:
        tokens = create_strava_client(linked.integrations).refresh_access_token(
            # Stored from the positive integer the credentials form accepts.
            client_id=int(client_id),
            client_secret=get_client_secret(linked.integrations),
            refresh_token=core_cryptography.decrypt_token_fernet(linked.refresh_token),
        )
    except Exception as err:
        try:
            raise_if_rate_limited(err, client_id, rate_limits)
        except core_exceptions.TooManyRequestsError:
            logger.warning("Strava rate limit hit during token refresh", extra=core_logger.context(user_id=user_id))
            if forced:
                raise
            return
        if _refresh_grant_refused(err):
            handle_rejected_token(user_id, linked.refresh_token, err, revoked=True)
            raise StravaTokenRejectedError(
                "Strava refused the refresh token. Please reconnect your Strava account."
            ) from err
        logger.error("Error refreshing the Strava token", extra=core_logger.context(user_id=user_id), exc_info=err)
        if forced or _token_expired(linked):
            raise core_exceptions.DependencyFailedError("The Strava token could not be refreshed") from err
        return

    try:
        with core_database.SessionLocal() as db:
            if not user_integrations_integration.replace_strava_tokens_if_refresh_token(
                user_id, linked.refresh_token, tokens, db
            ):
                db.rollback()
                logger.warning(
                    "Strava tokens changed during the refresh; the refreshed ones were discarded",
                    extra=core_logger.context(user_id=user_id),
                )
                return
            db.commit()
    except (sqlalchemy.exc.SQLAlchemyError, core_exceptions.CryptographyError) as err:
        # Strava has already invalidated the old refresh token, so the rotated one is lost. A due refresh leaves
        # the access token working until it expires; a confirmation stops the sync here.
        logger.error(
            "Strava tokens were refreshed but could not be stored; the account must be relinked",
            extra=core_logger.context(user_id=user_id),
            exc_info=err,
        )
        if forced:
            raise core_exceptions.DependencyFailedError("The refreshed Strava token could not be stored") from err
        return
    logger.debug("Strava tokens refreshed", extra=core_logger.context(user_id=user_id))


def fetch_user_integrations_and_validate_token(
    user_id: int, db: Session
) -> user_integrations_schema.UserIntegrationsRead | None:
    """Return a user's integrations when Strava is linked.

    Args:
        user_id: The user to look up.
        db: Database session.

    Returns:
        The user's integrations, or ``None`` when Strava is not linked.

    Raises:
        NotFoundError: When the user has no integrations row.
    """
    user_integrations = user_integrations_integration.require_user_integrations(user_id, db)
    if user_integrations.strava_token_expires_at is None:
        return None
    return user_integrations


def create_strava_client(
    user_integrations: user_integrations_schema.UserIntegrationsRead,
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
