"""
API Router for Strava Integration and Activity Processing.

This module defines FastAPI routes and functions for integrating Strava accounts,
refreshing Strava tokens, and processing Strava activities. It includes endpoints
for handling Strava callback, setting/unsetting unique user states for Strava link logic,
and background tasks for fetching and processing Strava activities.

Endpoints:
- GET /strava/strava-callback: Handle Strava callback to link user Strava accounts.
- PUT /strava/set-user-unique-state/{state}: Set unique state for user Strava link logic.
- PUT /strava/unset-user-unique-state: Unset unique state for user Strava link logic.

Functions:
- refresh_strava_token: Refresh Strava tokens for all users in the database.
- get_strava_activities: Fetch and process Strava activities for all users.
- get_user_strava_activities: Fetch and process Strava activities for a specific user.
- process_activity: Process individual Strava activity and store in the database.
- update_strava_user_tokens: Common function to update Strava tokens and perform additional tasks.

Dependencies:
- OAuth2PasswordBearer: FastAPI security scheme for handling OAuth2 password bearer tokens.
- get_db_session: Dependency function to get a database session.
- create_error_response: Function to create a standardized error response.
- BackgroundTasks: FastAPI class for handling background tasks.
- Session: SQLAlchemy session for database interactions.

Models:
- User: SQLAlchemy model for user records.
- Activity: SQLAlchemy model for Strava activity records.

Logger:
- Logger named "myLogger" for logging errors, exceptions, and informational events.
"""
from datetime import datetime, timedelta
from db.db import User, Activity
from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from stravalib.client import Client
from pint import Quantity
from concurrent.futures import ThreadPoolExecutor
from fastapi import BackgroundTasks
from urllib.parse import urlencode
from . import sessionController
from dependencies import get_db_session, create_error_response
from sqlalchemy.orm import Session
from fastapi.responses import JSONResponse
import logging
import requests
import os

# Define the API router
router = APIRouter()

# Define a loggger created on main.py
logger = logging.getLogger("myLogger")

# Define the OAuth2 scheme for handling bearer tokens
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


# Strava logic to refresh user Strava account refresh account
def refresh_strava_token(db_session: Session):
    """
    Refresh Strava tokens for all users in the database.

    Parameters:
    - db_session (Session): SQLAlchemy database session.

    Returns:
    - None: The function updates Strava tokens in the database and logs the results.

    Raises:
    - Exception: For unexpected errors during token refresh.
    """
    # Strava token refresh endpoint
    token_url = "https://www.strava.com/oauth/token"

    try:
        # Query all users from the database
        users = db_session.query(User).all()

        for user in users:
            # expires_at = user.strava_token_expires_at
            if user.strava_token_expires_at is not None:
                refresh_time = user.strava_token_expires_at - timedelta(minutes=60)

                if datetime.utcnow() > refresh_time:
                    # Parameters for the token refresh request
                    payload = {
                        "client_id": os.environ.get("STRAVA_CLIENT_ID"),
                        "client_secret": os.environ.get("STRAVA_CLIENT_SECRET"),
                        "refresh_token": user.strava_refresh_token,
                        "grant_type": "refresh_token",
                    }

                    try:
                        # Make a POST request to refresh the Strava token
                        response = requests.post(token_url, data=payload)
                        response.raise_for_status()  # Raise an error for bad responses

                        tokens = response.json()

                        # Update the user in the database
                        db_user = (
                            db_session.query(User)
                            .filter(User.id == user.id)
                            .first()
                        )

                        if db_user:
                            db_user.strava_token = tokens["access_token"]
                            db_user.strava_refresh_token = tokens["refresh_token"]
                            db_user.strava_token_expires_at = (
                                datetime.fromtimestamp(tokens["expires_at"])
                            )
                            db_session.commit()  # Commit the changes to the database
                            logger.info(
                                f"Token refreshed successfully for user {user.id}."
                            )
                        else:
                            logger.error("User not found in the database.")
                    except requests.exceptions.RequestException as req_err:
                        logger.error(
                            f"Error refreshing token for user {user.id}: {req_err}"
                        )
                else:
                    logger.info(
                        f"Token not refreshed for user {user.id}. Will not expire in less than 60min"
                    )
            else:
                logger.info(f"User {user.id} does not have strava linked")
    except Exception as err:
        # Log the error and return an error response
        logger.error(f"Error in refresh_strava_token: {err}", exc_info=True)
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )


def get_strava_activities(start_date: datetime, db_session: Session):
    """
    Fetch and process Strava activities for all users.

    Parameters:
    - start_date (datetime): The start date to retrieve activities after.
    - db_session (Session): SQLAlchemy database session.

    Returns:
    - None: The function fetches Strava activities, processes them, and stores in the database.

    Raises:
    - Exception: For unexpected errors during activity fetching and processing.
    """
    try:
        # Query all users from the database
        users = db_session.query(User).all()

        for user in users:
            if user.strava_token_expires_at is not None:

                # Create a Strava client with the user's access token
                stravaClient = Client(access_token=user.strava_token)

                # Fetch Strava activities after the specified start date
                strava_activities = list(
                    stravaClient.get_activities(after=start_date)
                )

                if strava_activities:
                    # Initialize an empty list for results
                    all_results = []

                    # Use ThreadPoolExecutor for parallel processing of activities
                    with ThreadPoolExecutor() as executor:
                        results = list(
                            executor.map(
                                lambda activity: process_activity(
                                    activity, user.id, stravaClient, db_session
                                ),
                                strava_activities,
                            )
                        )

                        # Append non-empty and non-None results to the overall results list
                        all_results.extend(results)

                    # Flatten the list of results
                    activities_to_insert = [
                        activity for sublist in all_results for activity in sublist
                    ]

                    # Bulk insert all activities into the database
                    db_session.bulk_save_objects(activities_to_insert)
                    db_session.commit()

                    # Log an informational event for tracing
                    logger.info(f"User {user.id}: {len(strava_activities)} periodic activities processed")
                else:
                    # Log an informational event if no activities were found
                    logger.info(f"User {user.id}: No new activities found after {start_date}")
            else:
                # Log an informational event if the user does not have Strava linked
                logger.info(f"User {user.id} does not have Strava linked")
    except Exception as err:
        # Log the error, rollback the transaction, and return an error response
        db_session.rollback()
        logger.error(f"Error in strava_set_user_unique_state: {err}", exc_info=True)
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )


def get_user_strava_activities(start_date: datetime, user_id: int, db_session: Session):
    """
    Fetch and process Strava activities for a specific user.

    Parameters:
    - start_date (datetime): The start date to retrieve activities after.
    - user_id (int): The user ID for whom to fetch and process Strava activities.
    - db_session (Session): SQLAlchemy database session.

    Returns:
    - None: The function fetches Strava activities for the specified user,
    processes them, and stores in the database.

    Raises:
    - Exception: For unexpected errors during user-specific activity fetching and processing.
    """
    # Query user from the database
    db_user = db_session.query(User).get(user_id)

    # Check if db returned an user object and variable is set
    if db_user:
        if db_user.strava_token_expires_at is not None:
            # Log an informational event for tracing
            logger.info(f"User {db_user.id}: Started initial activities processing")

            # Create a Strava client with the user's access token
            stravaClient = Client(access_token=db_user.strava_token)

            # Fetch Strava activities after the specified start date
            strava_activities = list(stravaClient.get_activities(after=start_date))

            if strava_activities:
                # Initialize an empty list for results
                all_results = []

                # Use ThreadPoolExecutor for parallel processing of activities
                with ThreadPoolExecutor() as executor:
                    results = list(
                        executor.map(
                            lambda activity: process_activity(
                                activity, db_user.id, stravaClient, db_session
                            ),
                            strava_activities,
                        )
                    )

                    # Append non-empty and non-None results to the overall results list
                    all_results.extend(results)

                # Flatten the list of results
                activities_to_insert = [
                    activity for sublist in all_results for activity in sublist
                ]

                # Bulk insert all activities into the database
                db_session.bulk_save_objects(activities_to_insert)
                db_session.commit()

                # Log an informational event for tracing
                logger.info(f"User {db_user.id}: {len(strava_activities)} initial activities processed")

            else:
                # Log an informational event if no activities were found
                logger.info(f"User {db_user.id}: No new activities found after {start_date}")
        else:
            # Log an informational event if the user does not have Strava linked
            logger.info(f"User {db_user.id} does not have Strava linked")

    else:
        # Log an informational event if the user is not found
        logger.info(f"User with ID {user_id} not found.")


def process_activity(activity, user_id, stravaClient, db_session: Session):
    """
    Process individual Strava activity and store in the database.

    Parameters:
    - activity: Strava activity object obtained from the Strava API.
    - user_id (int): The user ID associated with the Strava activity.
    - stravaClient: Strava client instance for making API requests.
    - db_session (Session): SQLAlchemy database session.

    Returns:
    - List[Activity]: List of Activity objects constructed from the Strava activity.

    Raises:
    - Exception: For unexpected errors during activity processing.
    """
    activities_to_insert = []

    # Check if the activity already exists in the database
    activity_record = (
        db_session.query(Activity)
        .filter(Activity.strava_activity_id == activity.id)
        .first()
    )

    if activity_record:
        # Skip existing activities
        return activities_to_insert

    # Parse start and end dates
    start_date_parsed = activity.start_date
    # Ensure activity.elapsed_time is a numerical value
    elapsed_time_seconds = (
        activity.elapsed_time.total_seconds()
        if isinstance(activity.elapsed_time, timedelta)
        else activity.elapsed_time
    )
    end_date_parsed = start_date_parsed + timedelta(seconds=elapsed_time_seconds)

    # Initialize location variables
    latitude, longitude = 0, 0

    if hasattr(activity, "start_latlng") and activity.start_latlng is not None:
        latitude = activity.start_latlng.lat
        longitude = activity.start_latlng.lon

    city, town, country = None, None, None

    # Retrieve location details using reverse geocoding
    if latitude != 0 and longitude != 0:
        # Encode URL with query parameters to ensure proper encoding and protection against special characters.
        url_params = {"lat": latitude, "lon": longitude}
        url = f"https://geocode.maps.co/reverse?{urlencode(url_params)}"
        # url = f"https://geocode.maps.co/reverse?lat={latitude}&lon={longitude}"
        try:
            # Make a GET request
            response = requests.get(url)

            # Check if the request was successful (status code 200)
            if response.status_code == 200:
                # Parse the JSON response
                data = response.json()

                # Extract the town and country from the address components
                city = data.get("address", {}).get("city", None)
                town = data.get("address", {}).get("town", None)
                country = data.get("address", {}).get("country", None)
            else:
                logger.error(f"Error location: {response.status_code}")
                logger.error(f"Error location: {url}")
        except Exception as err:
            # Log the error and return an error response
            logger.error(f"Error in process_activity: {err}", exc_info=True)

    # List to store constructed waypoints
    waypoints = []

    # Initialize variables for elevation gain and loss
    elevation_gain = 0
    elevation_loss = 0
    previous_elevation = None

    # Get streams for the activity
    streams = stravaClient.get_activity_streams(
        activity.id,
        types=[
            "latlng",
            "altitude",
            "time",
            "heartrate",
            "cadence",
            "watts",
            "velocity_smooth",
        ],
    )

    # Extract data from streams
    latitudes = streams["latlng"].data if "latlng" in streams else []
    longitudes = streams["latlng"].data if "latlng" in streams else []
    elevations = streams["altitude"].data if "altitude" in streams else []
    times = streams["time"].data if "time" in streams else []
    heart_rates = streams["heartrate"].data if "heartrate" in streams else []
    cadences = streams["cadence"].data if "cadence" in streams else []
    powers = streams["watts"].data if "watts" in streams else []
    velocities = (
        streams["velocity_smooth"].data if "velocity_smooth" in streams else []
    )

    # Iterate through stream data to construct waypoints
    for i in range(len(heart_rates)):
        waypoint = {
            "lat": latitudes[i] if i < len(latitudes) else None,
            "lon": longitudes[i] if i < len(longitudes) else None,
            "ele": elevations[i] if i < len(elevations) else None,
            "time": times[i] if i < len(times) else None,
            "hr": heart_rates[i] if i < len(heart_rates) else None,
            "cad": cadences[i] if i < len(cadences) else None,
            "power": powers[i] if i < len(powers) else None,
            "vel": velocities[i] if i < len(velocities) else None,
            "pace": 1 / velocities[i]
            if i < len(velocities) and velocities[i] != 0
            else None,
        }

        # Calculate elevation gain and loss on-the-fly
        current_elevation = elevations[i] if i < len(elevations) else None

        if current_elevation is not None:
            if previous_elevation is not None:
                elevation_change = current_elevation - previous_elevation

                if elevation_change > 0:
                    elevation_gain += elevation_change
                else:
                    elevation_loss += abs(elevation_change)

            previous_elevation = current_elevation

        # Append the constructed waypoint to the waypoints list
        waypoints.append(waypoint)

    # Calculate average speed, pace, and watts
    average_speed = 0
    if activity.average_speed is not None:
        average_speed = (
            float(activity.average_speed.magnitude)
            if isinstance(activity.average_speed, Quantity)
            else activity.average_speed
        )

    average_pace = 1 / average_speed if average_speed != 0 else 0

    average_watts = 0
    if activity.average_watts is not None:
        average_watts = activity.average_watts

    # Map activity type to a numerical value
    auxType = 10  # Default value
    type_mapping = {
        "running": 1,
        "Run": 1,
        "trail running": 2,
        "TrailRun": 2,
        "VirtualRun": 3,
        "cycling": 4,
        "Ride": 4,
        "GravelRide": 5,
        "EBikeRide": 6,
        "EMountainBikeRide": 6,
        "VirtualRide": 7,
        "virtual_ride": 7,
        "MountainBikeRide": 8,
        "swimming": 9,
        "Swim": 9,
        "open_water_swimming": 9,
        "Workout": 10,
    }
    auxType = type_mapping.get(activity.sport_type, 10)

    # Create a new Activity record
    newActivity = Activity(
        user_id=user_id,
        name=activity.name,
        distance=round(float(activity.distance))
        if isinstance(activity.distance, Quantity)
        else round(activity.distance),
        activity_type=auxType,
        start_time=start_date_parsed,
        end_time=end_date_parsed,
        city=city,
        town=town,
        country=country,
        created_at=datetime.utcnow(),
        waypoints=waypoints,
        elevation_gain=elevation_gain,
        elevation_loss=elevation_loss,
        pace=average_pace,
        average_speed=average_speed,
        average_power=average_watts,
        strava_activity_id=activity.id,
    )

    activities_to_insert.append(newActivity)

    return activities_to_insert


# Strava route to link user Strava account
@router.get("/strava/strava-callback")
async def strava_callback(
    state: str,
    code: str,
    background_tasks: BackgroundTasks,
    db_session: Session = Depends(get_db_session),
):
    """
    Handle Strava callback to link user Strava accounts.

    Parameters:
    - state (str): Unique state associated with the user Strava link process.
    - code (str): Authorization code received from Strava callback.
    - background_tasks (BackgroundTasks): FastAPI class for handling background tasks.
    - db_session (Session): SQLAlchemy database session.

    Returns:
    - RedirectResponse: Redirects to the main page or specified URL after processing.

    Raises:
    - JWTError: If the user's access token is invalid or expired.
    - Exception: For other unexpected errors during Strava callback processing.
    """
    token_url = "https://www.strava.com/oauth/token"
    payload = {
        "client_id": os.environ.get("STRAVA_CLIENT_ID"),
        "client_secret": os.environ.get("STRAVA_CLIENT_SECRET"),
        "code": code,
        "grant_type": "authorization_code",
    }
    try:
        response = requests.post(token_url, data=payload)
        if response.status_code != 200:
            return create_error_response("ERROR", "Error retrieving tokens from Strava.", response.status_code)

        tokens = response.json()

        # Query the activities records using SQLAlchemy
        db_user = db_session.query(User).filter(User.strava_state == state).first()

        if db_user:
            db_user.strava_token = tokens["access_token"]
            db_user.strava_refresh_token = tokens["refresh_token"]
            db_user.strava_token_expires_at = datetime.fromtimestamp(
                tokens["expires_at"]
            )
            db_session.commit()  # Commit the changes to the database

            # get_strava_activities((datetime.utcnow() - timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%SZ"))
            background_tasks.add_task(
                get_user_strava_activities,
                (
                    datetime.utcnow()
                    - timedelta(
                        days=int(os.environ.get("STRAVA_DAYS_ACTIVITIES_ONLINK"))
                    )
                ).strftime("%Y-%m-%dT%H:%M:%SZ"),
                db_user.id,
                db_session,
            )

            # Redirect to the main page or any other desired page after processing
            redirect_url = "https://"+os.environ.get("API_ENDPOINT")+"/settings/settings.php?profileSettings=1&stravaLinked=1"  # Change this URL to your main page
            return RedirectResponse(url=redirect_url)
        else:
            return create_error_response("NOT_FOUND", "User not found", 404)

    except JWTError:
        # Return an error response if the user is not authenticated
        return create_error_response("UNAUTHORIZED", "Unauthorized", 401)
    except Exception as err:
        # Log the error, rollback the transaction, and return an error response
        db_session.rollback()
        logger.error(f"Error in read_users_all: {err}", exc_info=True)
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )
    
# Define an HTTP PUT route set strava unique state for link logic
@router.put("/strava/set-user-unique-state/{state}")
async def strava_set_user_unique_state(
    state: str,
    token: str = Depends(oauth2_scheme),
    db_session: Session = Depends(get_db_session),
):
    """
    Set unique state for user Strava link logic.

    Parameters:
    - state (str): Unique state associated with the user Strava link process.
    - token (str): The access token for user authentication.
    - db_session (Session): SQLAlchemy database session.

    Returns:
    - JSONResponse: JSON response indicating the success of setting the Strava user state.

    Raises:
    - JWTError: If the user's access token is invalid or expired.
    - Exception: For other unexpected errors during setting Strava user state.
    """
    try:
        # Validate the user's access token using the oauth2_scheme
        sessionController.validate_token(token)

        # Get the user ID from the token
        user_id = sessionController.get_user_id_from_token(token)

        # Query the database to find the user by their ID
        user = db_session.query(User).filter(User.id == user_id).first()

        # Check if the user with the given ID exists
        if not user:
            return create_error_response("NOT_FOUND", "User not found", 404)

        # Set the user's photo paths to None to delete the photo
        user.strava_state = state

        # Commit the changes to the database
        db_session.commit()

        # Return a success message
        return JSONResponse(
                content={"message": f"Strava state for user {user_id} has been updated"}, status_code=200
            )
    except JWTError:
        # Return an error response if the user is not authenticated
        return create_error_response("UNAUTHORIZED", "Unauthorized", 401)
    except Exception as err:
        # Log the error, rollback the transaction, and return an error response
        db_session.rollback()
        logger.error(f"Error in strava_set_user_unique_state: {err}", exc_info=True)
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )


# Define an HTTP PUT route set strava unique state for link logic
@router.put("/strava/unset-user-unique-state")
async def strava_unset_user_unique_state(
    token: str = Depends(oauth2_scheme), db_session: Session = Depends(get_db_session)
):
    """
    Unset unique state for user Strava link logic.

    Parameters:
    - token (str): The access token for user authentication.
    - db_session (Session): SQLAlchemy database session.

    Returns:
    - JSONResponse: JSON response indicating the success of unsetting the Strava user state.

    Raises:
    - JWTError: If the user's access token is invalid or expired.
    - Exception: For other unexpected errors during unsetting Strava user state.
    """
    try:
        # Validate the user's access token using the oauth2_scheme
        sessionController.validate_token(token)

        # Get the user ID from the token
        user_id = sessionController.get_user_id_from_token(token)

        # Query the database to find the user by their ID
        user = db_session.query(User).filter(User.id == user_id).first()

        # Check if the user with the given ID exists
        if not user:
            return create_error_response("NOT_FOUND", "User not found", 404)

        # Set the user's photo paths to None to delete the photo
        user.strava_state = None

        # Commit the changes to the database
        db_session.commit()

        # Return a success message
        return JSONResponse(
                content={"message": f"Strava state for user {user_id} has been updated"}, status_code=200
            )
    except JWTError:
        # Return an error response if the user is not authenticated
        return create_error_response("UNAUTHORIZED", "Unauthorized", 401)
    except Exception as err:
        # Log the error, rollback the transaction, and return an error response
        db_session.rollback()
        logger.error(f"Error in strava_set_user_unique_state: {err}", exc_info=True)
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )