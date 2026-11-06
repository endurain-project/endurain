"""Linking a Garmin Connect account: the background login, the MFA hand-off and the link status.

Owns the dedicated login threads. Unlinking and the sessions a linked account's syncs use live in
:mod:`modules.garmin.service`.
"""

import time

import garminconnect
import jasil.audit as jasil_audit

import core.database as core_database
import core.exceptions as core_exceptions
import core.logger as core_logger
import core.sync_runner as core_sync_runner
import modules.garmin.audit_actions as garmin_audit_actions
import modules.garmin.constants as garmin_constants
import modules.garmin.link_state_store as garmin_link_state_store
import modules.garmin.mfa_code_store as garmin_mfa_code_store
import modules.garmin.schema as garmin_schema
import modules.garmin.token_utils as garmin_token_utils
import modules.users.users_integrations.integration_service as user_integrations_integration
import modules.websocket.integration_service as websocket_integration

logger = core_logger.get_logger(__name__)

# Logins run here, not on the request threadpool: one waits up to MFA_WAIT_SECONDS for the
# user's code, and a few users linking at once must not leave the API without worker threads.
_link_pool = core_sync_runner.link_pool("garmin-link")


class _MfaCodeTimeoutError(Exception):
    """No MFA code arrived within ``MFA_WAIT_SECONDS``, so the login is abandoned before Garmin is asked."""


def shutdown_link_pool(*, wait: bool = False) -> None:
    """Stop accepting link attempts and release the login threads.

    Args:
        wait: Whether to wait for logins still running.
    """
    _link_pool.shutdown(wait=wait)


def wait_for_mfa_code(
    user_id: int,
    mfa_codes: garmin_mfa_code_store.GarminMFACodeStore,
    link_states: garmin_link_state_store.GarminLinkStateStore,
) -> str:
    """Ask for an MFA code through the shared link state and wait for the user to submit it.

    The prompt is the ``mfa_required`` state the browser polls, so it reaches the user on
    whichever replica answers the poll. The code arrives through the shared code store the
    same way.

    Args:
        user_id: The user linking Garmin Connect.
        mfa_codes: Shared store the submitted code lands in.
        link_states: Shared store of the link attempt's state.

    Returns:
        The submitted code.

    Raises:
        _MfaCodeTimeoutError: When no code arrived within ``MFA_WAIT_SECONDS``.
    """
    link_states.set_status(user_id, garmin_constants.LinkStatus.MFA_REQUIRED)
    websocket_integration.push_job_changed(user_id, garmin_constants.LINK_JOB)
    for _ in range(garmin_constants.MFA_WAIT_SECONDS):
        code = mfa_codes.get_code(user_id)
        if code is not None:
            link_states.set_status(user_id, garmin_constants.LinkStatus.PENDING)
            return code
        time.sleep(1)
    raise _MfaCodeTimeoutError


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
        PoolFullError: When every login thread of this process is busy.
    """
    # Checked before the attempt is recorded, so a refused login leaves no pending state to poll.
    _link_pool.require_capacity()
    core_sync_runner.start_claimed(
        lambda: link_states.begin(user_id),
        "A Garmin Connect link is already in progress",
        lambda: _link_pool.submit(
            link_garminconnect,
            user_id,
            login.username,
            login.password.get_secret_value(),
            mfa_codes,
            link_states,
            login.is_cn,
        ),
        lambda: link_states.release(user_id),
        status_route="garminconnect_link_status",
    )
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
    mfa_timed_out = False

    def prompt_mfa() -> str:
        """Mark the login as prompted and wait for the user's MFA code.

        Returns:
            The submitted code.

        Raises:
            _MfaCodeTimeoutError: When none arrived in time; the library's login may rewrap it, so the
                timeout is also flagged for :func:`link_garminconnect`.
        """
        nonlocal mfa_prompted, mfa_timed_out
        mfa_prompted = True
        try:
            return wait_for_mfa_code(user_id, mfa_codes, link_states)
        except _MfaCodeTimeoutError:
            mfa_timed_out = True
            raise

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
            jasil_audit.stage(
                db,
                garmin_audit_actions.ACCOUNT_LINK,
                target_type="user",
                target_id=str(user_id),
                target_owner_id=str(user_id),
            )
            db.commit()
    except garminconnect.GarminConnectAuthenticationError:
        # The library raises this for a refused password and for a refused MFA code alike.
        reason = (
            garmin_constants.LinkFailure.INCORRECT_MFA
            if mfa_prompted
            else garmin_constants.LinkFailure.INVALID_CREDENTIALS
        )
        logger.warning(
            "Garmin Connect refused the link attempt",
            extra=core_logger.context(user_id=user_id, reason=reason),
        )
        link_states.set_status(user_id, garmin_constants.LinkStatus.FAILED, reason)
        _record_refused_link(user_id, garmin_audit_actions.LinkFailureReason(reason))
    except garminconnect.GarminConnectTooManyRequestsError:
        logger.warning(
            "Garmin Connect refused the link attempt: too many requests",
            extra=core_logger.context(user_id=user_id),
        )
        link_states.set_status(
            user_id, garmin_constants.LinkStatus.FAILED, garmin_constants.LinkFailure.TOO_MANY_REQUESTS
        )
        _record_refused_link(user_id, garmin_audit_actions.LinkFailureReason.TOO_MANY_REQUESTS)
    except Exception as err:
        if mfa_timed_out:
            # The library rewraps the timeout, so it is told apart by the flag. Recorded as an incorrect
            # code, the reason that covers a code that did not arrive in time.
            logger.warning(
                "Garmin Connect link abandoned: no MFA code arrived in time",
                exc_info=err,
                extra=core_logger.context(user_id=user_id),
            )
            link_states.set_status(
                user_id, garmin_constants.LinkStatus.FAILED, garmin_constants.LinkFailure.INCORRECT_MFA
            )
            _record_refused_link(user_id, garmin_audit_actions.LinkFailureReason.INCORRECT_MFA)
        else:
            logger.error(
                "Internal error while linking Garmin Connect",
                exc_info=err,
                extra=core_logger.context(user_id=user_id),
            )
            link_states.set_status(user_id, garmin_constants.LinkStatus.FAILED, garmin_constants.LinkFailure.INTERNAL)
    else:
        link_states.set_status(user_id, garmin_constants.LinkStatus.COMPLETED)
    finally:
        mfa_codes.delete_code(user_id)
        # Whatever the outcome was, it is recorded by now.
        websocket_integration.push_job_changed(user_id, garmin_constants.LINK_JOB)


def _record_refused_link(user_id: int, reason: garmin_audit_actions.LinkFailureReason) -> None:
    """Record that Garmin Connect refused the link.

    Args:
        user_id: The user linking Garmin Connect.
        reason: Why Garmin Connect refused it.
    """
    jasil_audit.record_detached(
        garmin_audit_actions.ACCOUNT_LINK,
        outcome=jasil_audit.Outcome.FAILURE,
        target_type="user",
        target_id=str(user_id),
        target_owner_id=str(user_id),
        details=garmin_audit_actions.LinkFailureDetails(reason=reason),
    )


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
) -> None:
    """Hand the user's MFA code to the login waiting for it.

    Args:
        user_id: The user linking Garmin Connect.
        mfa_code: The code the user entered.
        mfa_codes: Shared store the code lands in.
        link_states: Shared store of the link attempt's state.

    Raises:
        ConflictError: When no login is waiting for a code.
    """
    state = link_states.get(user_id)
    if state is None or state.status != garmin_constants.LinkStatus.MFA_REQUIRED:
        raise core_exceptions.ConflictError("No Garmin Connect login is waiting for an MFA code")
    mfa_codes.add_code(user_id, mfa_code)
