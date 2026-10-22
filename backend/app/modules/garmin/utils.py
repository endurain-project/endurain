import json
import time
from concurrent.futures import ThreadPoolExecutor

import garminconnect
import requests
from fastapi import (
    HTTPException,
    status,
)
from sqlalchemy.orm import Session

import core.cryptography as core_cryptography
import core.database as core_database
import core.logger as core_logger
import modules.garmin.link_state_store as garmin_link_state_store
import modules.garmin.mfa_code_store as garmin_mfa_code_store
import modules.notifications.integration_service as notifications_integration
import modules.users.users_integrations.crud as user_integrations_crud
import modules.users.users_integrations.schema as user_integrations_schema

logger = core_logger.get_logger(__name__)


# Logins run here, not on the request threadpool: one waits up to MFA_WAIT_SECONDS for the
# user's code, and a few users linking at once must not leave the API without worker threads.
_LINK_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="garmin-link")

MFA_WAIT_SECONDS = 60


def wait_for_mfa_code(
    user_id: int,
    mfa_codes: garmin_mfa_code_store.GarminMFACodeStore,
    link_states: garmin_link_state_store.GarminLinkStateStore,
) -> str | None:
    """
    Ask for an MFA code through the shared link state and wait for the user to submit it.

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
    link_states.set_status(user_id, garmin_link_state_store.LinkStatus.MFA_REQUIRED)
    for _ in range(MFA_WAIT_SECONDS):
        code = mfa_codes.get_code(user_id)
        if code is not None:
            link_states.set_status(user_id, garmin_link_state_store.LinkStatus.PENDING)
            return code
        time.sleep(1)
    return None


def start_garminconnect_link(
    user_id: int,
    email: str,
    password: str,
    mfa_codes: garmin_mfa_code_store.GarminMFACodeStore,
    link_states: garmin_link_state_store.GarminLinkStateStore,
    is_cn: bool = False,
) -> None:
    """
    Run a Garmin Connect link on a dedicated worker thread and return at once.

    The outcome is recorded in the shared link state. The credentials stay in this
    process's memory and are never stored, which is why this is not a durable job.

    Args:
        user_id: The user linking Garmin Connect.
        email: Garmin Connect username.
        password: Garmin Connect password.
        mfa_codes: Shared store the submitted MFA code lands in.
        link_states: Shared store of the link attempt's state.
        is_cn: Whether to authenticate against Garmin's China region.
    """
    _LINK_EXECUTOR.submit(link_garminconnect, user_id, email, password, mfa_codes, link_states, is_cn)


def link_garminconnect(
    user_id: int,
    email: str,
    password: str,
    mfa_codes: garmin_mfa_code_store.GarminMFACodeStore,
    link_states: garmin_link_state_store.GarminLinkStateStore,
    is_cn: bool = False,
) -> None:
    """
    Log in to Garmin Connect, store the token and record the outcome in the link state.

    Blocking; call it through :func:`start_garminconnect_link`. It never raises: every
    outcome, including a failure, ends as the recorded state.

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
    try:
        garmin = garminconnect.Garmin(
            email=email,
            password=password,
            is_cn=is_cn,
            prompt_mfa=lambda: wait_for_mfa_code(user_id, mfa_codes, link_states),
        )
        garmin.login()

        if not garmin.client.di_token:
            raise garminconnect.GarminConnectAuthenticationError("Garmin Connect returned no token")

        with core_database.SessionLocal() as db:
            user_integrations_crud.link_garminconnect_account(
                user_id,
                serialize_garmin_token(garmin.client, is_cn),
                db,
            )
    except (
        garminconnect.GarminConnectAuthenticationError,
        requests.exceptions.HTTPError,
    ) as err:
        logger.error(
            "There was an authentication error using Garmin Connect. Check credentials",
            exc_info=err,
            extra=core_logger.context(console=True),
        )
        link_states.set_status(
            user_id, garmin_link_state_store.LinkStatus.FAILED, garmin_link_state_store.LinkFailure.INVALID_CREDENTIALS
        )
    except garminconnect.GarminConnectTooManyRequestsError:
        link_states.set_status(
            user_id, garmin_link_state_store.LinkStatus.FAILED, garmin_link_state_store.LinkFailure.TOO_MANY_REQUESTS
        )
    except TypeError:
        # The library fails this way when the MFA prompt returns no code or a wrong one.
        link_states.set_status(
            user_id, garmin_link_state_store.LinkStatus.FAILED, garmin_link_state_store.LinkFailure.INCORRECT_MFA
        )
    except Exception as err:
        logger.error(
            "Internal error while linking Garmin Connect",
            exc_info=err,
            extra=core_logger.context(console=True),
        )
        link_states.set_status(
            user_id, garmin_link_state_store.LinkStatus.FAILED, garmin_link_state_store.LinkFailure.INTERNAL
        )
    else:
        link_states.set_status(user_id, garmin_link_state_store.LinkStatus.COMPLETED)
    finally:
        mfa_codes.delete_code(user_id)


def login_garminconnect_using_tokens(token):
    try:
        # Retrieve the China flag stored at link time (default to False for
        # tokens created before this feature was introduced)
        is_cn = token.get("is_cn", False) if isinstance(token, dict) else False

        # Create a new Garmin object
        garmin = garminconnect.Garmin(is_cn=is_cn)

        # Restore session from stored DI tokens
        garmin.client.loads(deserialize_garmin_token(token))
        return garmin
    except (
        garminconnect.GarminConnectAuthenticationError,
        garminconnect.GarminConnectConnectionError,
        requests.exceptions.HTTPError,
    ) as err:
        # Print error info to check dedicated log in main log
        logger.error(
            "There was an authentication error using Garmin Connect: {err}",
            exc_info=err,
            extra=core_logger.context(console=True),
        )
        return None


def serialize_garmin_token(client, is_cn: bool = False) -> dict:
    try:
        return {
            "di_token": (core_cryptography.encrypt_token_fernet(client.di_token) if client.di_token else None),
            "di_refresh_token": (
                core_cryptography.encrypt_token_fernet(client.di_refresh_token) if client.di_refresh_token else None
            ),
            "di_client_id": client.di_client_id,
            "is_cn": is_cn,
        }
    except Exception as err:
        logger.error(f"Error in serialize_garmin_token: {err}", exc_info=err, extra=core_logger.context(console=True))
        raise err


def deserialize_garmin_token(data: dict) -> str:
    try:
        return json.dumps(
            {
                "di_token": (
                    core_cryptography.decrypt_token_fernet(data["di_token"]) if data.get("di_token") else None
                ),
                "di_refresh_token": (
                    core_cryptography.decrypt_token_fernet(data["di_refresh_token"])
                    if data.get("di_refresh_token")
                    else None
                ),
                "di_client_id": data.get("di_client_id"),
            }
        )
    except Exception as err:
        logger.error(f"Error in deserialize_garmin_token: {err}", exc_info=err, extra=core_logger.context(console=True))
        raise err


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

    # Check if user_integrations.garminconnect_token is None
    if user_integrations.garminconnect_token is None:
        return None

    # Return the user integrations
    return user_integrations


def unlink_expired_account(user_id: int, db: Session) -> None:
    """Unlink an account whose Garmin Connect token expired and tell the user.

    The notification row is written in the same session as the unlink; the
    live push is published after the commit.

    Args:
        user_id: The user whose account to unlink.
        db: The caller's session, which this commits.
    """
    user_integrations_crud.unlink_garminconnect_account(user_id, db)
    notification, ws_message = notifications_integration.create_garmin_token_expired_notification(user_id, db)
    db.commit()
    notifications_integration.push_notification(user_id, notification, ws_message)
