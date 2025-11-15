from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
)
import requests
import datetime
from garth.exc import GarthHTTPError
import os
from getpass import getpass

email = os.getenv("EMAIL")
password = os.getenv("PASSWORD")
tokenstore = os.getenv("GARMINTOKENS") or ".garminconnect"
api = None
today = datetime.date.today()


def get_date():
    """Get date from user input."""

    return input("Enter date (dd-mm-yyyy): ")


def get_credentials():
    """Get user credentials."""

    email = input("Login e-mail: ")
    password = getpass("Enter password: ")

    return email, password


def get_mfa():
    """Get MFA."""

    return input("MFA one-time code: ")


def init_api(email, password):
    """Initialize Garmin API with your credentials."""

    try:
        # Using Oauth1 and OAuth2 token files from directory
        print(
            f"Trying to login to Garmin Connect using token data from directory '{tokenstore}'...\n"
        )

        garmin = Garmin()
        garmin.login(tokenstore)

    except (FileNotFoundError, GarthHTTPError, GarminConnectAuthenticationError):
        # Session is expired. You'll need to log in again
        print(
            "Login tokens not present, login with your Garmin Connect credentials to generate them.\n"
            f"They will be stored in '{tokenstore}' for future use.\n"
        )
        try:
            # Ask for credentials if not set as environment variables
            if not email or not password:
                email, password = get_credentials()

            garmin = Garmin(
                email=email, password=password, is_cn=False, prompt_mfa=get_mfa
            )
            garmin.login()
            # Save Oauth1 and Oauth2 token files to directory for next login
            garmin.garth.dump(tokenstore)
            print(
                f"Oauth tokens stored in '{tokenstore}' directory for future use. (first method)\n"
            )
        except (
            FileNotFoundError,
            GarthHTTPError,
            GarminConnectAuthenticationError,
            requests.exceptions.HTTPError,
        ) as err:
            print(err)
            return None

    return garmin


date = get_date()
date_object = datetime.datetime.strptime(date, "%d-%m-%Y")
date_string = date_object.strftime("%Y-%m-%d")

if not api:
    api = init_api(email, password)

if api:
    garmin_bc = api.get_body_composition(date_string, date_string)

    if garmin_bc is None:
        # Log an informational event if no body composition were found
        print(
            f"User: No new Garmin Connect body composition found after {today}: garmin_bc is None"
        )

    # Return the number of body compositions processed
    print(garmin_bc)
