import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
from db.db import get_db_session, User
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
import logging
import requests

router = APIRouter()

logger = logging.getLogger("myLogger")

# Load the environment variables from config/.env
load_dotenv('config/.env')

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

@router.get("/strava/strava-callback")
async def strava_callback(state: str, code: str):
    token_url = 'https://www.strava.com/oauth/token'
    payload = {
        'client_id': os.getenv("STRAVA_CLIENT_ID"),
        'client_secret': os.getenv("STRAVA_CLIENT_SECRET"),
        'code': code,
        'grant_type': 'authorization_code'
    }
    try:
        response = requests.post(token_url, data=payload)
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail="Error retrieving tokens from Strava.")

        tokens = response.json()

        with get_db_session() as db_session:

            # Query the activities records using SQLAlchemy
            db_user = db_session.query(User).filter(User.strava_state == state).first()

            if db_user:
                db_user.strava_token = tokens['access_token']
                db_user.strava_refresh_token = tokens['refresh_token']
                db_user.strava_token_expires_at = datetime.fromtimestamp(tokens['expires_at'])
                db_session.commit()  # Commit the changes to the database

                # Redirect to the main page or any other desired page after processing
                redirect_url = "https://gearguardian.jvslab.pt/settings/settings.php?profileSettings=1&stravaLinked=1"  # Change this URL to your main page
                return RedirectResponse(url=redirect_url)
            else:
                raise HTTPException(status_code=404, detail="User not found.")

    except JWTError:
        raise HTTPException(status_code=401, detail="Unauthorized")
    except Error as err:
        print(err)

def refresh_strava_token():
    # Strava token refresh endpoint
    token_url = 'https://www.strava.com/oauth/token'

    try:
        with get_db_session() as db_session:
            # Query all users from the database
            users = db_session.query(User).all()

            for user in users:
                #expires_at = user.strava_token_expires_at
                if user.strava_token_expires_at is not None:
                    refresh_time = user.strava_token_expires_at - timedelta(minutes=60)

                    if datetime.utcnow() > refresh_time:
                        # Parameters for the token refresh request
                        payload = {
                            "client_id": os.getenv("STRAVA_CLIENT_ID"),
                            "client_secret": os.getenv("STRAVA_CLIENT_SECRET"),
                            "refresh_token": user.strava_refresh_token,
                            "grant_type": "refresh_token",
                        }

                        try:
                            # Make a POST request to refresh the Strava token
                            response = requests.post(token_url, data=payload)
                            response.raise_for_status()  # Raise an error for bad responses

                            tokens = response.json()

                            # Update the user in the database
                            db_user = db_session.query(User).filter(User.id == user.id).first()

                            if db_user:
                                db_user.strava_token = tokens['access_token']
                                db_user.strava_refresh_token = tokens['refresh_token']
                                db_user.strava_token_expires_at = datetime.fromtimestamp(tokens['expires_at'])
                                db_session.commit()  # Commit the changes to the database
                                logger.info(f"Token refreshed successfully for user {user.id}.")
                            else:
                                logger.error("User not found in the database.")
                        except requests.exceptions.RequestException as req_err:
                            logger.error(f"Error refreshing token for user {user.id}: {req_err}")
                    else:
                        logger.info(f"Token not refreshed for user {user.id}. Will not expire in less than 60min")
                else:
                    logger.info(f"User {user.id} does not have strava linked")
    except Error as db_err:
        logger.error(f"Database error: {db_err}")

# Define an HTTP PUT route to delete a user's photo
@router.put("/strava/set-user-unique-state/{state}")
async def strava_set_user_unique_state(
    state: str, 
    token: str = Depends(oauth2_scheme)
):
    from . import sessionController
    try:
        # Validate the user's access token using the oauth2_scheme
        sessionController.validate_token(token)

        with get_db_session() as db_session:
            payload = jwt.decode(token, os.getenv("SECRET_KEY"), algorithms=[os.getenv("ALGORITHM")])
            user_id = payload.get("id")

            # Query the database to find the user by their ID
            user = db_session.query(User).filter(User.id == user_id).first()
            
            # Check if the user with the given ID exists
            if not user:
                raise HTTPException(status_code=404, detail="User not found")

            # Set the user's photo paths to None to delete the photo
            user.strava_state = state

            # Commit the changes to the database
            db_session.commit()
    except JWTError:
        # Handle JWT (JSON Web Token) authentication error
        raise HTTPException(status_code=401, detail="Unauthorized")
    except Exception as err:
        # Handle any other unexpected exceptions
        print(err)
        raise HTTPException(status_code=500, detail="Failed to update user strava state")

    # Return a success message
    return {"message": f"Strava state for user {user_id} has been updated"}