import logging
import requests

from fastapi import (
    HTTPException,
    status,
)
import garminconnect

from sqlalchemy.orm import Session

import user_integrations.schema as user_integrations_schema
import user_integrations.crud as user_integrations_crud

# Define a loggger created on main.py
mainLogger = logging.getLogger("myLogger")

# Create loggger
logger = logging.getLogger("migration_logger")
logger.setLevel(logging.DEBUG)

file_handler = logging.FileHandler("logs/garminconnect.log")
file_handler.setLevel(logging.DEBUG)

formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
file_handler.setFormatter(formatter)

logger.addHandler(file_handler)


def link_garminconnect(user_id: int, email: str, password: str, db: Session):
    try:
        # Create a new Garmin object
        garmin = garminconnect.Garmin(email=email, password=password)

        # Login to Garmin Connect portal
        garmin.login()

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
        # Print error info to check dedicated log in console
        print(
            "There was an authentication error using Garmin Connect. Please check Garmin Connect logs."
        )
        # Print error info to check dedicated log in main log
        mainLogger.error(
            "There was an authentication error using Garmin Connect. Please check Garmin Connect logs."
        )
        # Print error info to check dedicated log in garmin connect log
        logger.error(f"Error authenticating: {err}")
        return None


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
        # Print error info to check dedicated log in console
        print(
            "There was an authentication error using Garmin Connect. Please check Garmin Connect logs."
        )
        # Print error info to check dedicated log in main log
        mainLogger.error(
            "There was an authentication error using Garmin Connect. Please check Garmin Connect logs."
        )
        # Print error info to check dedicated log in garmin connect log
        logger.error(f"Error authenticating: {err}")
        return None


def serialize_oauth1_token(token):
    return {
        "oauth_token": token.oauth_token,
        "oauth_token_secret": token.oauth_token_secret,
        "mfa_token": token.mfa_token,
        "mfa_expiration_timestamp": token.mfa_expiration_timestamp,
        "domain": token.domain,
    }


def serialize_oauth2_token(token):
    return {
        "scope": token.scope,
        "jti": token.jti,
        "token_type": token.token_type,
        "access_token": token.access_token,
        "refresh_token": token.refresh_token,
        "expires_in": token.expires_in,
        "expires_at": token.expires_at,
        "refresh_token_expires_in": token.refresh_token_expires_in,
        "refresh_token_expires_at": token.refresh_token_expires_at,
    }


def deserialize_oauth1_token(data):
    return garminconnect.garth.auth_tokens.OAuth1Token(
        oauth_token=data["oauth_token"],
        oauth_token_secret=data["oauth_token_secret"],
        mfa_token=data.get("mfa_token"),
        mfa_expiration_timestamp=data.get("mfa_expiration_timestamp"),
        domain=data.get("domain"),
    )


def deserialize_oauth2_token(data):
    return garminconnect.garth.auth_tokens.OAuth2Token(
        scope=data["scope"],
        jti=data["jti"],
        token_type=data["token_type"],
        access_token=data["access_token"],
        refresh_token=data["refresh_token"],
        expires_in=data["expires_in"],
        expires_at=data["expires_at"],
        refresh_token_expires_in=data.get("refresh_token_expires_in"),
        refresh_token_expires_at=data.get("refresh_token_expires_at"),
    )


def fetch_user_integrations_and_validate_token(
    user_id: int, db: Session
) -> user_integrations_schema.UserIntegrations | None:
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
