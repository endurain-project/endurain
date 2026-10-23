"""Application logic for linking, unlinking and syncing a Garmin Connect account.

Owns the unlink transaction and the background link thread. The activity, gear and health
syncs live in :mod:`modules.garmin.activity_service`, :mod:`modules.garmin.gear_service` and
:mod:`modules.garmin.health_service`.
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from typing import NamedTuple

import garminconnect
import jasil.providers as platform_providers
import requests
from sqlalchemy.orm import Session

import core.database as core_database
import core.exceptions as core_exceptions
import core.logger as core_logger
import modules.activities.activity_ingestion.integration_service as activity_ingestion_integration
import modules.activities.activity_ingestion.schema as activity_ingestion_schema
import modules.garmin.constants as garmin_constants
import modules.garmin.link_state_store as garmin_link_state_store
import modules.garmin.mfa_code_store as garmin_mfa_code_store
import modules.garmin.schema as garmin_schema
import modules.garmin.token_utils as garmin_token_utils
import modules.notifications.integration_service as notifications_integration
import modules.users.users_integrations.integration_service as user_integrations_integration
import modules.users.users_integrations.schema as user_integrations_schema

logger = core_logger.get_logger(__name__)


# Logins run here, not on the request threadpool: one waits up to MFA_WAIT_SECONDS for the
# user's code, and a few users linking at once must not leave the API without worker threads.
# A login past this capacity is refused rather than queued: a queued one would outlive its
# polled state while holding the user's credentials in memory.
MAX_CONCURRENT_LINKS = 4
_LINK_EXECUTOR = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_LINKS, thread_name_prefix="garmin-link")
_link_slots = threading.BoundedSemaphore(MAX_CONCURRENT_LINKS)


def shutdown_link_executor(*, wait: bool = False) -> None:
    """Stop accepting link attempts and release the login threads.

    Args:
        wait: Whether to wait for logins still running.
    """
    _LINK_EXECUTOR.shutdown(wait=wait, cancel_futures=True)


def _http_failure(err: requests.exceptions.HTTPError) -> garmin_constants.LinkFailure:
    """Classify an HTTP error from a login by who is at fault.

    Args:
        err: The error Garmin Connect's login raised.

    Returns:
        ``INVALID_CREDENTIALS`` for 401/403, ``TOO_MANY_REQUESTS`` for 429, else ``INTERNAL``.
    """
    status_code = err.response.status_code if err.response is not None else None
    if status_code in (401, 403):
        return garmin_constants.LinkFailure.INVALID_CREDENTIALS
    if status_code == 429:
        return garmin_constants.LinkFailure.TOO_MANY_REQUESTS
    return garmin_constants.LinkFailure.INTERNAL


def wait_for_mfa_code(
    user_id: int,
    mfa_codes: garmin_mfa_code_store.GarminMFACodeStore,
    link_states: garmin_link_state_store.GarminLinkStateStore,
) -> str | None:
    """Ask for an MFA code through the shared link state and wait for the user to submit it.

    The prompt is the ``mfa_required`` state the browser polls, so it reaches the user on
    whichever replica answers the poll. The code arrives through the shared code store the
    same way.

    Args:
        user_id: The user linking Garmin Connect.
        mfa_codes: Shared store the submitted code lands in.
        link_states: Shared store of the link attempt's state.

    Returns:
        The code, or None when none arrived within ``MFA_WAIT_SECONDS``.
    """
    link_states.set_status(user_id, garmin_constants.LinkStatus.MFA_REQUIRED)
    for _ in range(garmin_constants.MFA_WAIT_SECONDS):
        code = mfa_codes.get_code(user_id)
        if code is not None:
            link_states.set_status(user_id, garmin_constants.LinkStatus.PENDING)
            return code
        time.sleep(1)
    return None


def start_link(
    user_id: int,
    login: garmin_schema.GarminLogin,
    mfa_codes: garmin_mfa_code_store.GarminMFACodeStore,
    link_states: garmin_link_state_store.GarminLinkStateStore,
) -> garmin_schema.GarminLinkStatus:
    """Start linking a Garmin Connect account on a dedicated worker thread and return at once.

    The outcome is recorded in the shared link state. The credentials stay in this
    process's memory and are never stored, which is why this is not a durable job.

    Args:
        user_id: The user linking Garmin Connect.
        login: The Garmin Connect credentials.
        mfa_codes: Shared store the submitted MFA code lands in.
        link_states: Shared store of the link attempt's state.

    Returns:
        The attempt's initial status.

    Raises:
        ConflictError: When an attempt for this user is already running.
        ServiceUnavailableError: When every login thread of this process is busy.
    """
    if not _link_slots.acquire(blocking=False):
        raise core_exceptions.ServiceUnavailableError("Too many Garmin Connect links in progress; try again shortly")
    try:
        if not link_states.begin(user_id):
            raise core_exceptions.ConflictError("A Garmin Connect link is already in progress")
        try:
            future = _LINK_EXECUTOR.submit(
                link_garminconnect, user_id, login.username, login.password, mfa_codes, link_states, login.is_cn
            )
        except BaseException:
            # The attempt never started, so nothing would ever release its claim.
            link_states.release(user_id)
            raise
    except BaseException:
        _link_slots.release()
        raise
    future.add_done_callback(lambda _: _link_slots.release())
    return garmin_schema.GarminLinkStatus(status=garmin_constants.LinkStatus.PENDING)


def link_garminconnect(
    user_id: int,
    email: str,
    password: str,
    mfa_codes: garmin_mfa_code_store.GarminMFACodeStore,
    link_states: garmin_link_state_store.GarminLinkStateStore,
    is_cn: bool = False,
) -> None:
    """Log in to Garmin Connect, store the token and record the outcome in the link state.

    Blocking; call it through :func:`start_link`. It never raises: every outcome, including a
    failure, ends as the recorded state.

    Args:
        user_id: The user linking Garmin Connect.
        email: Garmin Connect username.
        password: Garmin Connect password.
        mfa_codes: Shared store the submitted MFA code lands in.
        link_states: Shared store of the link attempt's state.
        is_cn: Whether to authenticate against Garmin's China region.
    """
    # A code left by an earlier attempt must not answer this one's prompt.
    mfa_codes.delete_code(user_id)
    mfa_prompted = False

    def prompt_mfa() -> str | None:
        nonlocal mfa_prompted
        mfa_prompted = True
        return wait_for_mfa_code(user_id, mfa_codes, link_states)

    try:
        garmin = garminconnect.Garmin(email=email, password=password, is_cn=is_cn, prompt_mfa=prompt_mfa)
        garmin.login()

        if not garmin.client.di_token:
            raise garminconnect.GarminConnectAuthenticationError("Garmin Connect returned no token")

        with core_database.SessionLocal() as db:
            user_integrations_integration.link_garminconnect_account(
                user_id,
                garmin_token_utils.serialize_garmin_token(garmin.client, is_cn),
                db,
            )
            db.commit()
    except garminconnect.GarminConnectAuthenticationError as err:
        logger.error("There was an authentication error using Garmin Connect. Check credentials", exc_info=err)
        link_states.set_status(
            user_id, garmin_constants.LinkStatus.FAILED, garmin_constants.LinkFailure.INVALID_CREDENTIALS
        )
    except requests.exceptions.HTTPError as err:
        reason = _http_failure(err)
        logger.error("Garmin Connect answered the link attempt with an HTTP error", exc_info=err)
        link_states.set_status(user_id, garmin_constants.LinkStatus.FAILED, reason)
    except garminconnect.GarminConnectTooManyRequestsError:
        logger.warning(
            "Garmin Connect refused the link attempt: too many requests",
            extra=core_logger.context(user_id=user_id),
        )
        link_states.set_status(
            user_id, garmin_constants.LinkStatus.FAILED, garmin_constants.LinkFailure.TOO_MANY_REQUESTS
        )
    except TypeError as err:
        # The library fails this way when the MFA prompt returns no code or a wrong one.
        if not mfa_prompted:
            logger.error("Internal error while linking Garmin Connect", exc_info=err)
            link_states.set_status(user_id, garmin_constants.LinkStatus.FAILED, garmin_constants.LinkFailure.INTERNAL)
        else:
            logger.warning(
                "Garmin Connect link failed on the MFA code",
                extra=core_logger.context(user_id=user_id),
            )
            link_states.set_status(
                user_id, garmin_constants.LinkStatus.FAILED, garmin_constants.LinkFailure.INCORRECT_MFA
            )
    except Exception as err:
        logger.error("Internal error while linking Garmin Connect", exc_info=err)
        link_states.set_status(user_id, garmin_constants.LinkStatus.FAILED, garmin_constants.LinkFailure.INTERNAL)
    else:
        link_states.set_status(user_id, garmin_constants.LinkStatus.COMPLETED)
    finally:
        mfa_codes.delete_code(user_id)


def get_link_status(
    user_id: int,
    link_states: garmin_link_state_store.GarminLinkStateStore,
) -> garmin_schema.GarminLinkStatus:
    """Report where a user's Garmin Connect link attempt is.

    Args:
        user_id: The user linking Garmin Connect.
        link_states: Shared store of the link attempt's state.

    Returns:
        The attempt's status and, when it failed, why.

    Raises:
        NotFoundError: When no attempt is recorded or it has expired.
    """
    state = link_states.get(user_id)
    if state is None:
        raise core_exceptions.NotFoundError("No Garmin Connect link in progress")
    return garmin_schema.GarminLinkStatus(status=state.status, reason=state.reason)


def submit_mfa_code(
    user_id: int,
    mfa_code: str,
    mfa_codes: garmin_mfa_code_store.GarminMFACodeStore,
    link_states: garmin_link_state_store.GarminLinkStateStore,
) -> garmin_schema.MFAAccepted:
    """Hand the user's MFA code to the login waiting for it.

    Args:
        user_id: The user linking Garmin Connect.
        mfa_code: The code the user entered.
        mfa_codes: Shared store the code lands in.
        link_states: Shared store of the link attempt's state.

    Returns:
        The acknowledgement.

    Raises:
        ConflictError: When no login is waiting for a code.
    """
    state = link_states.get(user_id)
    if state is None or state.status != garmin_constants.LinkStatus.MFA_REQUIRED:
        raise core_exceptions.ConflictError("No Garmin Connect login is waiting for an MFA code")
    mfa_codes.add_code(user_id, mfa_code)
    return garmin_schema.MFAAccepted(message="MFA code received successfully")


def request_activities_sync(
    user_id: int,
    start_date: date,
    end_date: date,
    storage: platform_providers.StorageProvider,
    db: Session,
) -> activity_ingestion_schema.ActivityIngestionJobRead:
    """Queue a Garmin Connect sync of an explicit date range.

    The range is fetched by a background job, never on the request or an API worker thread.

    Args:
        user_id: The user to sync.
        start_date: First day of the range.
        end_date: Last day of the range.
        storage: The platform storage provider.
        db: Database session.

    Returns:
        The queued job's handle.

    Raises:
        InvalidInputError: When ``start_date`` is after ``end_date``.
    """
    if start_date > end_date:
        raise core_exceptions.InvalidInputError("start_date must not be after end_date")

    job = activity_ingestion_integration.request_provider_sync(
        user_id,
        garmin_constants.PROVIDER_NAME,
        datetime.combine(start_date, datetime.min.time(), tzinfo=UTC),
        datetime.combine(end_date, datetime.max.time(), tzinfo=UTC),
        storage,
        db,
    )
    logger.info(
        "Garmin Connect activities queued",
        extra=core_logger.context(user_id=user_id),
    )
    return job


def unlink_account(user_id: int, db: Session) -> garmin_schema.GarminDetail:
    """Unlink a user's Garmin Connect account.

    Args:
        user_id: The user unlinking Garmin Connect.
        db: Database session.

    Returns:
        The outcome message.
    """
    user_integrations_integration.unlink_garminconnect_account(user_id, db)
    db.commit()
    logger.info(
        "Garmin Connect unlinked",
        extra=core_logger.context(user_id=user_id),
    )
    return garmin_schema.GarminDetail(detail=f"Garmin Connect unlinked for user {user_id} successfully")


def fetch_user_integrations_and_validate_token(
    user_id: int, db: Session
) -> user_integrations_schema.UsersIntegrationsRead | None:
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
    """Return an authenticated Garmin Connect session for a linked user.

    Args:
        user_id: The user whose Garmin Connect account to use.
        db: Database session.

    Returns:
        The session, or ``None`` when Garmin Connect is not linked or the stored session is rejected.
    """
    try:
        user_integrations = fetch_user_integrations_and_validate_token(user_id, db)
    except core_exceptions.NotFoundError:
        logger.warning("Garmin Connect user has no integrations record", extra=core_logger.context(user_id=user_id))
        return None

    if user_integrations is None:
        logger.info(
            "Garmin Connect not linked",
            extra=core_logger.context(user_id=user_id),
        )
        return None

    token = user_integrations.garminconnect_token
    client = garmin_token_utils.login_garminconnect_using_tokens(token)
    return GarminSession(client, token) if client is not None else None


def get_user_garminconnect_client(user_id: int, db: Session) -> garminconnect.Garmin | None:
    """Return an authenticated Garmin Connect client for a linked user.

    Args:
        user_id: The user whose Garmin Connect account to use.
        db: Database session.

    Returns:
        The client, or ``None`` when Garmin Connect is not linked or the stored session is rejected.
    """
    session = get_user_garminconnect_session(user_id, db)
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
                logger.info("Garmin Connect token refreshed", extra=core_logger.context(user_id=user_id))
    except Exception as err:
        logger.error("Failed to store the refreshed Garmin Connect token", exc_info=err)


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
