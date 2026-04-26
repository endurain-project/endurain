import requests
import asyncio
import json

from fastapi import (
    HTTPException,
    status,
)
import garminconnect

from sqlalchemy.orm import Session

import core.cryptography as core_cryptography

import users.users_integrations.crud as user_integrations_crud
import users.users_integrations.models as user_integrations_models

import websocket.manager as websocket_manager
import websocket.utils as websocket_utils

import garmin.schema as garmin_schema

import core.logger as core_logger


async def get_mfa(
    user_id: int,
    mfa_codes: garmin_schema.MFACodeStore,
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


async def notify_frontend_mfa_required(
    user_id: int, websocket_manager: websocket_manager.WebSocketManager
):
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
    mfa_codes: garmin_schema.MFACodeStore,
    websocket_manager: websocket_manager.WebSocketManager,
):
    # Capture the running event loop so the thread can schedule async work on it
    loop = asyncio.get_running_loop()

    def blocking_login():
        # Bridge sync→async: schedule the async MFA prompt on the event loop
        # and block the thread until the user submits the code (timeout 65 s)
        def sync_mfa_callback():
            future = asyncio.run_coroutine_threadsafe(
                get_mfa(user_id, mfa_codes, websocket_manager), loop
            )
            return future.result(timeout=65)

        # Create a new Garmin object
        garmin = garminconnect.Garmin(
            email=email,
            password=password,
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
            serialize_garmin_token(garmin.client),
            None,
            db,
        )
    except HTTPException as http_err:
        raise http_err
    except (
        garminconnect.GarminConnectAuthenticationError,
        requests.exceptions.HTTPError,
    ) as err:
        # Print error info to check dedicated log in main log
        core_logger.print_to_log_and_console(
            "There was an authentication error using Garmin Connect. Check credentials: {err}",
            "error",
            err,
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
        core_logger.print_to_log_and_console(
            f"Internal server error while linking Garmin Connect: {err}",
            "error",
            err,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while linking Garmin Connect",
        ) from err
    finally:
        if mfa_codes.has_code(user_id):
            mfa_codes.delete_code(user_id)


def login_garminconnect_using_tokens(oauth1_token, oauth2_token):
    try:
        # Create a new Garmin object
        garmin = garminconnect.Garmin()

        # Restore session from stored DI tokens
        garmin.client.loads(
            deserialize_garmin_token(oauth1_token)
        )
        return garmin
    except (
        garminconnect.GarminConnectAuthenticationError,
        garminconnect.GarminConnectConnectionError,
        requests.exceptions.HTTPError,
    ) as err:
        # Print error info to check dedicated log in main log
        core_logger.print_to_log_and_console(
            "There was an authentication error using Garmin Connect: {err}",
            "error",
            err,
        )
        return None


def serialize_garmin_token(client) -> dict:
    try:
        return {
            "di_token": (
                core_cryptography.encrypt_token_fernet(
                    client.di_token
                )
                if client.di_token
                else None
            ),
            "di_refresh_token": (
                core_cryptography.encrypt_token_fernet(
                    client.di_refresh_token
                )
                if client.di_refresh_token
                else None
            ),
            "di_client_id": client.di_client_id,
        }
    except Exception as err:
        core_logger.print_to_log_and_console(
            f"Error in serialize_garmin_token: {err}", "error", err
        )
        raise err


def deserialize_garmin_token(data: dict) -> str:
    try:
        return json.dumps({
            "di_token": (
                core_cryptography.decrypt_token_fernet(
                    data["di_token"]
                )
                if data.get("di_token")
                else None
            ),
            "di_refresh_token": (
                core_cryptography.decrypt_token_fernet(
                    data["di_refresh_token"]
                )
                if data.get("di_refresh_token")
                else None
            ),
            "di_client_id": data.get("di_client_id"),
        })
    except Exception as err:
        core_logger.print_to_log_and_console(
            f"Error in deserialize_garmin_token: {err}", "error", err
        )
        raise err


def fetch_user_integrations_and_validate_token(
    user_id: int, db: Session
) -> user_integrations_models.UsersIntegrations | None:
    # Get the user integrations by user ID
    user_integrations = user_integrations_crud.get_user_integrations_by_user_id(
        user_id, db
    )

    # Check if user integrations is None
    if user_integrations is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User information not found",
        )

    # Check if user_integrations.garminconnect_oauth1 is None
    if user_integrations.garminconnect_oauth1 is None:
        return None

    # Return the user integrations
    return user_integrations
