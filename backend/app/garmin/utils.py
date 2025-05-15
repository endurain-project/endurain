import requests
import asyncio

from datetime import datetime
from fastapi import (
    HTTPException,
    status,
)
import garminconnect

from sqlalchemy.orm import Session

import core.cryptography as core_cryptography

import users.user_integrations.schema as user_integrations_schema
import users.user_integrations.crud as user_integrations_crud

import websocket.schema as websocket_schema

import garmin.schema as garmin_schema

import core.logger as core_logger

async def get_mfa(
    user_id: int,
    mfa_codes: garmin_schema.MFACodeStore,
    websocket_manager: websocket_schema.WebSocketManager,
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
    user_id: int, websocket_manager: websocket_schema.WebSocketManager
):
    # Check if the user has an active WebSocket connection
    websocket = websocket_manager.get_connection(user_id)
    if websocket:
        await websocket.send_json({"message": "MFA_REQUIRED", "user_id": user_id})
    else:
        raise HTTPException(
            status_code=400,
            detail=f"No active WebSocket connection for user {user_id}",
        )


async def link_garminconnect(
    user_id: int,
    email: str,
    password: str,
    db: Session,
    mfa_codes: garmin_schema.MFACodeStore,
    websocket_manager: websocket_schema.WebSocketManager,
):
    # Define MFA callback as a coroutine
    async def async_mfa_callback():
        return await get_mfa(user_id, mfa_codes, websocket_manager)

    def blocking_login():
        # Create a new Garmin object
        garmin = garminconnect.Garmin(
            email=email,
            password=password,
            prompt_mfa=async_mfa_callback,
        )
        garmin.login()

        return garmin

    try:
        # Run the blocking `login()` call in a thread
        garmin = await asyncio.to_thread(blocking_login)

        if not garmin.garth.oauth1_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect Garmin Connect credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )

        user_integrations_crud.link_garminconnect_account(
            user_id,
            serialize_oauth1_token(garmin.garth.oauth1_token),
            serialize_oauth2_token(garmin.garth.oauth2_token),
            db,
        )
    except (
        garminconnect.GarminConnectAuthenticationError,
        requests.exceptions.HTTPError,
    ) as err:
        # Print error info to check dedicated log in main log
        core_logger.print_to_log_and_console(
            "There was an authentication error using Garmin Connect: {err}", "error", err
        )
        
        return None
    except garminconnect.GarminConnectTooManyRequestsError as err:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests to Garmin Connect",
        )
    except TypeError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect MFA code",
            headers={"WWW-Authenticate": "Bearer"},
        )
    finally:
        mfa_codes.delete_code(user_id)


def login_garminconnect_using_tokens(oauth1_token, oauth2_token):
    try:
        # Create a new Garmin object
        garmin = garminconnect.Garmin()

        # Set the tokens directly into the Garmin object
        garmin.garth.oauth1_token = deserialize_oauth1_token(oauth1_token)
        garmin.garth.oauth2_token = deserialize_oauth2_token(oauth2_token)

        return garmin
    except (
        garminconnect.GarminConnectAuthenticationError,
        requests.exceptions.HTTPError,
    ) as err:
        # Print error info to check dedicated log in main log
        core_logger.print_to_log_and_console(
            "There was an authentication error using Garmin Connect: {err}", "error", err
        )
        return None


def serialize_oauth1_token(token):
    return {
        "oauth_token": core_cryptography.encrypt_token_fernet(token.oauth_token),
        "oauth_token_secret": core_cryptography.encrypt_token_fernet(token.oauth_token_secret),
        "mfa_token": core_cryptography.encrypt_token_fernet(token.mfa_token),
        "mfa_expiration_timestamp": (
            token.mfa_expiration_timestamp.isoformat()
            if token.mfa_expiration_timestamp
            else None
        ),
        "domain": token.domain,
    }


def serialize_oauth2_token(token):
    return {
        "scope": token.scope,
        "jti": token.jti,
        "token_type": token.token_type,
        "access_token": core_cryptography.encrypt_token_fernet(token.access_token),
        "refresh_token": core_cryptography.encrypt_token_fernet(token.refresh_token),
        "expires_in": token.expires_in,
        "expires_at": token.expires_at,
        "refresh_token_expires_in": token.refresh_token_expires_in,
        "refresh_token_expires_at": token.refresh_token_expires_at,
    }


def deserialize_oauth1_token(data):
    return garminconnect.garth.auth_tokens.OAuth1Token(
        oauth_token=core_cryptography.decrypt_token_fernet(data["oauth_token"]),
        oauth_token_secret=core_cryptography.decrypt_token_fernet(data["oauth_token_secret"]),
        mfa_token=core_cryptography.decrypt_token_fernet(data.get("mfa_token")),
        mfa_expiration_timestamp=(
            datetime.fromisoformat(data["mfa_expiration_timestamp"])
            if data.get("mfa_expiration_timestamp")
            else None
        ),
        domain=data.get("domain"),
    )


def deserialize_oauth2_token(data):
    return garminconnect.garth.auth_tokens.OAuth2Token(
        scope=data["scope"],
        jti=data["jti"],
        token_type=data["token_type"],
        access_token=core_cryptography.decrypt_token_fernet(data["access_token"]),
        refresh_token=core_cryptography.decrypt_token_fernet(data["refresh_token"]),
        expires_in=data["expires_in"],
        expires_at=data["expires_at"],
        refresh_token_expires_in=data.get("refresh_token_expires_in"),
        refresh_token_expires_at=data.get("refresh_token_expires_at"),
    )


def fetch_user_integrations_and_validate_token(
    user_id: int, db: Session
) -> user_integrations_schema.UsersIntegrations | None:
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
