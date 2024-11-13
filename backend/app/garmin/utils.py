import logging
import requests

from fastapi import (
    HTTPException,
    status,
)
import garminconnect

from sqlalchemy.orm import Session

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
        print("aqui antes")
        # Create a new Garmin object
        garmin = garminconnect.Garmin(email=email, password=password)

        # Login to Garmin Connect portal
        garmin.login()

        print("aqui")
        print(serialize_oauth1_token(garmin.garth.oauth1_token))
        print(serialize_oauth2_token(garmin.garth.oauth2_token))

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
