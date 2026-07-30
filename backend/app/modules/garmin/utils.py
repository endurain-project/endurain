import asyncio
import json

import garminconnect
import requests
from fastapi import (
    HTTPException,
    status,
)
from sqlalchemy.orm import Session

import core.cryptography as core_cryptography
import core.logger as core_logger
import modules.garmin.mfa_code_store as garmin_mfa_code_store
import modules.users.users_integrations.crud as user_integrations_crud
import modules.users.users_integrations.models as user_integrations_models
import modules.websocket.manager as websocket_manager
import modules.websocket.utils as websocket_utils

logger = core_logger.get_logger(__name__)


async def get_mfa(
    user_id: int,
    mfa_codes: garmin_mfa_code_store.GarminMFACodeStore,
    websocket_manager: websocket_manager.WebSocketManager,
) -> str:
    # Notify frontend that MFA is required
    await notify_frontend_mfa_required(user_id, websocket_manager)

    # Wait for the MFA code
    for _ in range(60):  # Timeout after 60 seconds
        if mfa_codes.has_code(user_id):
            return mfa_codes.get_code(user_id)
        await asyncio.sleep(1)

    return None


async def notify_frontend_mfa_required(user_id: int, websocket_manager: websocket_manager.WebSocketManager):
    try:
        json_data = {"message": "MFA_REQUIRED", "user_id": user_id}
        await websocket_utils.notify_frontend(user_id, websocket_manager, json_data)
    except HTTPException as http_err:
        raise http_err


async def link_garminconnect(
    user_id: int,
    email: str,
    password: str,
    db: Session,
    mfa_codes: garmin_mfa_code_store.GarminMFACodeStore,
    websocket_manager: websocket_manager.WebSocketManager,
    is_cn: bool = False,
):
    # Capture the running event loop so the thread can schedule async work on it
    loop = asyncio.get_running_loop()

    def blocking_login():
        # Bridge sync→async: schedule the async MFA prompt on the event loop
        # and block the thread until the user submits the code (timeout 65 s)
        def sync_mfa_callback():
            future = asyncio.run_coroutine_threadsafe(get_mfa(user_id, mfa_codes, websocket_manager), loop)
            return future.result(timeout=65)

        # Create a new Garmin object
        garmin = garminconnect.Garmin(
            email=email,
            password=password,
            is_cn=is_cn,
            prompt_mfa=sync_mfa_callback,
        )
        garmin.login()

        return garmin

    try:
        # Run the blocking `login()` call in a thread
        garmin = await asyncio.to_thread(blocking_login)

        if not garmin.client.di_token:
            raise HTTPException(
                status_code=status.HTTP_424_FAILED_DEPENDENCY,
                detail="Incorrect Garmin Connect credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )

        user_integrations_crud.link_garminconnect_account(
            user_id,
            serialize_garmin_token(garmin.client, is_cn),
            db,
        )
    except HTTPException as http_err:
        raise http_err
    except (
        garminconnect.GarminConnectAuthenticationError,
        requests.exceptions.HTTPError,
    ) as err:
        # Print error info to check dedicated log in main log
        logger.error(
            "There was an authentication error using Garmin Connect. Check credentials: {err}",
            exc_info=err,
            extra=core_logger.context(console=True),
        )
        raise HTTPException(
            status_code=status.HTTP_424_FAILED_DEPENDENCY,
            detail="There was an authentication error using Garmin Connect. Check credentials.",
        ) from err
    except garminconnect.GarminConnectTooManyRequestsError as err:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests to Garmin Connect",
        ) from err
    except TypeError as err:
        raise HTTPException(
            status_code=status.HTTP_424_FAILED_DEPENDENCY,
            detail="Incorrect MFA code",
        ) from err
    except Exception as err:
        logger.error(
            f"Internal server error while linking Garmin Connect: {err}",
            exc_info=err,
            extra=core_logger.context(console=True),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while linking Garmin Connect",
        ) from err
    finally:
        if mfa_codes.has_code(user_id):
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
) -> user_integrations_models.UsersIntegrations | None:
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
