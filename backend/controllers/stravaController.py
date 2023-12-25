from datetime import datetime, timedelta
from db.db import get_db_session, User, Activity
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from stravalib.client import Client
from pint import Quantity
from concurrent.futures import ThreadPoolExecutor
from fastapi import BackgroundTasks
from opentelemetry import trace
from urllib.parse import urlencode
from . import sessionController 
import logging
import requests
import os

router = APIRouter()

logger = logging.getLogger("myLogger")

# Load the environment variables from config/.env
#load_dotenv("config/.env")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


# Strava route to link user Strava account
@router.get("/strava/strava-callback")
async def strava_callback(state: str, code: str, background_tasks: BackgroundTasks):
    """
    Callback endpoint for Strava OAuth2 authorization.

    This endpoint is used as a callback URL for Strava OAuth2 authorization. It receives
    the authorization code from Strava and exchanges it for an access token and refresh
    token. It then updates the user's Strava tokens in the database, triggers a background
    task to fetch Strava activities, and redirects the user to a specified URL.

    Args:
    - state (str): The unique state parameter sent during the initial OAuth2 authorization.
    - code (str): The authorization code received from Strava.
    - background_tasks (BackgroundTasks): A FastAPI BackgroundTasks instance used to
      schedule background tasks.

    Raises:
    - HTTPException: If there is an error retrieving tokens from Strava, if the user is
      not found in the database, or if there is an authentication error.
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
            raise HTTPException(
                status_code=response.status_code,
                detail="Error retrieving tokens from Strava.",
            )

        tokens = response.json()

        with get_db_session() as db_session:
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
                )

                # Redirect to the main page or any other desired page after processing
                redirect_url = "https://gearguardian.jvslab.pt/settings/settings.php?profileSettings=1&stravaLinked=1"  # Change this URL to your main page
                return RedirectResponse(url=redirect_url)
            else:
                raise HTTPException(status_code=404, detail="User not found.")

    except JWTError:
        raise HTTPException(status_code=401, detail="Unauthorized")
    except NameError as err:
        print(err)


# Strava logic to refresh user Strava account refresh account
def refresh_strava_token():
    """
    Refresh Strava access tokens for all users.

    This function iterates through all users in the database and checks if their
    Strava access tokens are about to expire. If so, it makes a request to the Strava
    token refresh endpoint to obtain a new access token.

    Note: The function assumes that the user model has the following fields:
    - strava_refresh_token: Strava refresh token for each user
    - strava_token_expires_at: Expiry timestamp of the Strava access token

    Raises:
    - HTTPError: If there is an error in the token refresh request.
    - Exception: If there is an unexpected error during the token refresh process.
    """
    # Get the tracer from the main module
    tracer = trace.get_tracer(__name__)

    with tracer.start_as_current_span("refresh_strava_token"):
        # Strava token refresh endpoint
        token_url = "https://www.strava.com/oauth/token"

        try:
            with get_db_session() as db_session:
                # Query all users from the database
                users = db_session.query(User).all()

                for user in users:
                    # expires_at = user.strava_token_expires_at
                    if user.strava_token_expires_at is not None:
                        refresh_time = user.strava_token_expires_at - timedelta(
                            minutes=60
                        )

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
                                    db_user.strava_refresh_token = tokens[
                                        "refresh_token"
                                    ]
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
        except NameError as db_err:
            logger.error(f"Database error: {db_err}")


# Define an HTTP PUT route set strava unique state for link logic
@router.put("/strava/set-user-unique-state/{state}")
async def strava_set_user_unique_state(state: str, token: str = Depends(oauth2_scheme)):
    """
    Set the Strava unique state for a user.

    This route handles the HTTP PUT request to set the Strava unique state for a user.
    The user is authenticated using the provided access token. If successful, the user's
    Strava state is set to the provided state in the database.

    Parameters:
    - state (str): The Strava unique state to set for the user.
    - token (str): The access token used for user authentication.

    Returns:
    dict: A dictionary containing a success message if the operation is successful.
          Raises appropriate HTTPExceptions for authentication or database errors.
    """
    try:
        # Validate the user's access token using the oauth2_scheme
        sessionController.validate_token(token)

        with get_db_session() as db_session:
            # From the token retrieve the user_id
            payload = jwt.decode(
                token, os.environ.get("SECRET_KEY"), algorithms=[os.environ.get("ALGORITHM")]
            )
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
        raise HTTPException(
            status_code=500, detail="Failed to update user strava state"
        )

    # Return a success message
    return {"message": f"Strava state for user {user_id} has been updated"}


# Define an HTTP PUT route set strava unique state for link logic
@router.put("/strava/unset-user-unique-state")
async def strava_unset_user_unique_state(token: str = Depends(oauth2_scheme)):
    """
    Unset the Strava unique state for a user.

    This route handles the HTTP PUT request to unset the Strava unique state for a user.
    The user is authenticated using the provided access token. If successful, the user's
    Strava state is set to None in the database.

    Parameters:
    - token (str): The access token used for user authentication.

    Returns:
    dict: A dictionary containing a success message if the operation is successful.
          Raises appropriate HTTPExceptions for authentication or database errors.
    """
    try:
        # Validate the user's access token using the oauth2_scheme
        sessionController.validate_token(token)

        with get_db_session() as db_session:
            # From the token retrieve the user_id
            payload = jwt.decode(
                token, os.environ.get("SECRET_KEY"), algorithms=[os.environ.get("ALGORITHM")]
            )
            user_id = payload.get("id")

            # Query the database to find the user by their ID
            user = db_session.query(User).filter(User.id == user_id).first()

            # Check if the user with the given ID exists
            if not user:
                raise HTTPException(status_code=404, detail="User not found")

            # Set the user's photo paths to None to delete the photo
            user.strava_state = None

            # Commit the changes to the database
            db_session.commit()
    except JWTError:
        # Handle JWT (JSON Web Token) authentication error
        raise HTTPException(status_code=401, detail="Unauthorized")
    except Exception as err:
        # Handle any other unexpected exceptions
        print(err)
        raise HTTPException(
            status_code=500, detail="Failed to update user strava state"
        )

    # Return a success message
    return {"message": f"Strava state for user {user_id} has been updated"}


def get_strava_activities(start_date: datetime):
    """
    Retrieve and process Strava activities for all users in the database.

    This function iterates over all users with linked Strava accounts,
    retrieves their activities after the specified start date, and processes
    and inserts those activities into the database.

    Parameters:
    - start_date (datetime): The start date for retrieving activities.

    Returns:
    None
    """
    # Get the tracer from the main module
    tracer = trace.get_tracer(__name__)

    with tracer.start_as_current_span("get_strava_activities"):
        try:
            with get_db_session() as db_session:
                # Query all users from the database
                users = db_session.query(User).all()

                for user in users:
                    if user.strava_token_expires_at is not None:
                        # Log an informational event for tracing
                        trace.get_current_span().add_event(
                            "InfoEvent",
                            {
                                "message": f"User {user.id}: Started periodic activities processing"
                            },
                        )

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
                                            activity, user.id, stravaClient
                                        ),
                                        strava_activities,
                                    )
                                )

                                # Append non-empty and non-None results to the overall results list
                                all_results.extend(results)

                            # Flatten the list of results
                            activities_to_insert = [
                                activity
                                for sublist in all_results
                                for activity in sublist
                            ]

                            # Bulk insert all activities into the database
                            with get_db_session() as db_session:
                                db_session.bulk_save_objects(activities_to_insert)
                                db_session.commit()

                            # Log an informational event for tracing
                            trace.get_current_span().add_event(
                                "InfoEvent",
                                {
                                    "message": f"User {user.id}: {len(strava_activities)} periodic activities processed"
                                },
                            )

                        else:
                            # Log an informational event if no activities were found
                            trace.get_current_span().add_event(
                                "InfoEvent",
                                {
                                    "message": f"User {user.id}: No new activities found after {start_date}"
                                },
                            )

                    else:
                        # Log an informational event if the user does not have Strava linked
                        logger.info(f"User {user.id} does not have Strava linked")
                        trace.get_current_span().add_event(
                            "InfoEvent",
                            {"message": f"User {user.id} does not have Strava linked"},
                        )
        except NameError as db_err:
            # Log an error event if a NameError occurs (e.g., undefined function or variable)
            logger.error(f"Database error: {db_err}")
            trace.get_current_span().add_event(
                "ErrorEvent",
                {"message": f"Database error: {db_err}"},
            )


def get_user_strava_activities(start_date: datetime, user_id: int):
    """
    Retrieve Strava activities for a user, process them, and store in the database.

    This function fetches Strava activities for a specified user after a given start date.
    It processes the activities using parallel execution, creates corresponding database
    records, and bulk inserts them into the database.

    Parameters:
    - start_date (datetime): The start date for retrieving Strava activities.
    - user_id (int): The ID of the user for whom activities are to be processed.

    Returns:
    None
    """

    # Get the tracer from the main module
    tracer = trace.get_tracer(__name__)

    with tracer.start_as_current_span("get_user_strava_activities"):
        with get_db_session() as db_session:
            # Query user from the database
            db_user = db_session.query(User).get(user_id)

            # Check if db returned an user object and variable is set
            if db_user:
                if db_user.strava_token_expires_at is not None:
                    # Log an informational event for tracing
                    trace.get_current_span().add_event(
                        "InfoEvent",
                        {
                            "message": f"User {db_user.id}: Started initial activities processing"
                        },
                    )

                    # Create a Strava client with the user's access token
                    stravaClient = Client(access_token=db_user.strava_token)

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
                                        activity, db_user.id, stravaClient
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
                        with get_db_session() as db_session:
                            db_session.bulk_save_objects(activities_to_insert)
                            db_session.commit()

                        # Log an informational event for tracing
                        trace.get_current_span().add_event(
                            "InfoEvent",
                            {
                                "message": f"User {db_user.id}: {len(strava_activities)} initial activities processed"
                            },
                        )

                    else:
                        # Log an informational event if no activities were found
                        trace.get_current_span().add_event(
                            "InfoEvent",
                            {
                                "message": f"User {db_user.id}: No new activities found after {start_date}"
                            },
                        )

                else:
                    # Log an informational event if the user does not have Strava linked
                    logger.info(f"User {db_user.id} does not have Strava linked")
                    trace.get_current_span().add_event(
                        "InfoEvent",
                        {"message": f"User {db_user.id} does not have Strava linked"},
                    )

            else:
                # Log an informational event if the user is not found
                logger.info(f"User with ID {user_id} not found.")
                trace.get_current_span().add_event(
                    "InfoEvent",
                    {"message": f"User with ID {user_id} not found"},
                )


def process_activity(activity, user_id, stravaClient):
    """
    Process a Strava activity and create a corresponding database record.

    This function takes a Strava activity, retrieves relevant data such as
    waypoints, elevation gain, and other details, and creates a new database
    record for the activity.

    Parameters:
    - activity: The Strava activity object.
    - user_id (int): The ID of the user associated with the activity.
    - stravaClient: The Strava client object for making API requests.

    Returns:
    - newActivity: The newly created database record for the activity.
    """

    # Get the tracer from the main module
    tracer = trace.get_tracer(__name__)

    with tracer.start_as_current_span("process_activity"):
        activities_to_insert = []

        with get_db_session() as db_session:
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
                    print(f"Error location: {response.status_code}")
                    print(f"Error location: {url}")
            except Exception as e:
                print(f"An error occurred: {e}")

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
