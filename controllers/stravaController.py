import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
from db.db import get_db_session, User, Activity
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from sqlalchemy import func
from stravalib.client import Client
from pint import Quantity
from concurrent.futures import ThreadPoolExecutor
import logging
import requests

router = APIRouter()

logger = logging.getLogger("myLogger")

# Load the environment variables from config/.env
load_dotenv("config/.env")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


# Strava route to link user Strava account
@router.get("/strava/strava-callback")
async def strava_callback(state: str, code: str):
    token_url = "https://www.strava.com/oauth/token"
    payload = {
        "client_id": os.getenv("STRAVA_CLIENT_ID"),
        "client_secret": os.getenv("STRAVA_CLIENT_SECRET"),
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
    # Strava token refresh endpoint
    token_url = "https://www.strava.com/oauth/token"

    try:
        with get_db_session() as db_session:
            # Query all users from the database
            users = db_session.query(User).all()

            for user in users:
                # expires_at = user.strava_token_expires_at
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
    except NameError as db_err:
        logger.error(f"Database error: {db_err}")


# Define an HTTP PUT route set strava unique state for link logic
@router.put("/strava/set-user-unique-state/{state}")
async def strava_set_user_unique_state(state: str, token: str = Depends(oauth2_scheme)):
    from . import sessionController

    try:
        # Validate the user's access token using the oauth2_scheme
        sessionController.validate_token(token)

        with get_db_session() as db_session:
            payload = jwt.decode(
                token, os.getenv("SECRET_KEY"), algorithms=[os.getenv("ALGORITHM")]
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
    from . import sessionController

    try:
        # Validate the user's access token using the oauth2_scheme
        sessionController.validate_token(token)

        with get_db_session() as db_session:
            payload = jwt.decode(
                token, os.getenv("SECRET_KEY"), algorithms=[os.getenv("ALGORITHM")]
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


# Strava logic to refresh user Strava account refresh account
def get_strava_activities(start_date: datetime):
    # Strava token refresh endpoint
    # activities_url = 'https://www.strava.com/api/v3/athlete/activities'

    try:
        with get_db_session() as db_session:
            # Query all users from the database
            users = db_session.query(User).all()

            for user in users:
                if user.strava_token_expires_at is not None:
                    # Calculate the start date (7 days ago from today)
                    # start_date = (datetime.utcnow() - timedelta(days=7)).strftime('%Y-%m-%dT%H:%M:%SZ')

                    # Set parameters for the API request
                    # params = {
                    #    'access_token': user.strava_token,
                    #    'after': start_date,
                    # }

                    # try:
                    # Make a GET request to retrieve activities
                    #    response = requests.get(activities_url, params=params)
                    #    response.raise_for_status()  # Raise an error for bad responses

                    # store_strava_activities_stravaLib(response.json(), user.id, user.strava_token)
                    #store_strava_activities_stravaLib(user.id, user.strava_token, start_date)

                    stravaClient = Client(access_token=user.strava_token)

                    strava_activities = list(stravaClient.get_activities(after=start_date))
                    chunk_size = len(strava_activities) // 4  # Adjust the number of threads as needed
                    activity_chunks = [strava_activities[i:i + chunk_size] for i in range(0, len(strava_activities), chunk_size)]
                        
                    with ThreadPoolExecutor() as executor:
                        # Process each chunk of activities using threads
                        results = list(executor.map(lambda chunk: process_activities(chunk, user.id, stravaClient), activity_chunks))

                    # Flatten the list of results
                    activities_to_insert = [activity for sublist in results for activity in sublist]

                    # Bulk insert all activities
                    with get_db_session() as db_session:
                        db_session.bulk_save_objects(activities_to_insert)
                        db_session.commit()

                    # except requests.exceptions.RequestException as req_err:
                    # Handle request errors
                    #    logger.error(f"Error retrieving activities for user {user.id}: {req_err}")
                    #    return None
                else:
                    logger.info(f"User {user.id} does not have strava linked")
    except NameError as db_err:
        logger.error(f"Database error: {db_err}")

def process_activities(strava_activities, user_id, stravaClient):
    activities_to_insert = []

    for activity in strava_activities:
        with get_db_session() as db_session:
            activity_record = (
                db_session.query(Activity)
                .filter(Activity.strava_activity_id == activity.id)
                .first()
            )

            if activity_record:
                continue  # Skip existing activities

            # Process the activity and append to the list
            processed_activity = process_activity(activity, user_id, stravaClient)
            activities_to_insert.append(processed_activity)

    return activities_to_insert

def process_activity(activity, user_id, stravaClient):
    start_date_parsed = activity.start_date
    # Ensure activity.elapsed_time is a numerical value
    elapsed_time_seconds = (
        activity.elapsed_time.total_seconds()
        if isinstance(activity.elapsed_time, timedelta)
        else activity.elapsed_time
    )
    end_date_parsed = start_date_parsed + timedelta(
        seconds=elapsed_time_seconds
    )

    latitude = 0
    longitude = 0

    if hasattr(activity, "start_latlng") and activity.start_latlng is not None:
        latitude = activity.start_latlng.lat
        longitude = activity.start_latlng.lon

    city = None
    town = None
    country = None
    if latitude != 0 and longitude != 0:
        url = f"https://geocode.maps.co/reverse?lat={latitude}&lon={longitude}"
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
            # Add other relevant fields based on your requirements
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
        #created_at=func.now(),  # Use func.now() to set 'created_at' to the current timestamp
        created_at=datetime.utcnow(),
        waypoints=waypoints,
        elevation_gain=elevation_gain,
        elevation_loss=elevation_loss,
        pace=average_pace,
        average_speed=average_speed,
        average_power=average_watts,
        strava_activity_id=activity.id,
    )

    return newActivity


def store_strava_activities_stravaLib(user_id, strava_token, start_date):
    stravaClient = Client(access_token=strava_token)
    #start_date = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")

    for activity in stravaClient.get_activities(after=start_date):
        with get_db_session() as db_session:
            # Use SQLAlchemy to query the gear record by ID
            activity_record = (
                db_session.query(Activity)
                .filter(Activity.strava_activity_id == activity.id)
                .first()
            )

            if activity_record:
                # Skip to the next iteration
                continue

            start_date_parsed = activity.start_date
            # Ensure activity.elapsed_time is a numerical value
            elapsed_time_seconds = (
                activity.elapsed_time.total_seconds()
                if isinstance(activity.elapsed_time, timedelta)
                else activity.elapsed_time
            )
            end_date_parsed = start_date_parsed + timedelta(
                seconds=elapsed_time_seconds
            )

            latitude = 0
            longitude = 0

            if hasattr(activity, "start_latlng") and activity.start_latlng is not None:
                latitude = activity.start_latlng.lat
                longitude = activity.start_latlng.lon

            city = None
            town = None
            country = None
            if latitude != 0 and longitude != 0:
                url = f"https://geocode.maps.co/reverse?lat={latitude}&lon={longitude}"
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
                    # Add other relevant fields based on your requirements
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
            activity = Activity(
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
                created_at=func.now(),  # Use func.now() to set 'created_at' to the current timestamp
                waypoints=waypoints,
                elevation_gain=elevation_gain,
                elevation_loss=elevation_loss,
                pace=average_pace,
                average_speed=average_speed,
                average_power=average_watts,
                strava_activity_id=activity.id,
            )

            try:
                # Store the Activity record in the database
                with get_db_session() as db_session:
                    db_session.add(activity)
                    db_session.commit()
                    db_session.refresh(
                        activity
                    )  # This will ensure that the activity object is updated with the ID from the database
                return {"message": "Activities retrieved"}
            except Exception as err:
                print(err)
                logger.error(err)


def store_strava_activities(strava_activities, user_id, strava_token):
    from . import activitiesController

    try:
        params = {
            "access_token": strava_token,
        }

        # start_date = (datetime.utcnow() - timedelta(days=7)).strftime('%Y-%m-%dT%H:%M:%SZ')
        # strava_activities = get_strava_activities(start_date)
        if strava_activities:
            for activity in strava_activities:
                try:
                    with get_db_session() as db_session:
                        # Use SQLAlchemy to query the gear record by ID
                        activity_record = (
                            db_session.query(Activity)
                            .filter(Activity.strava_activity_id == activity.get("id"))
                            .first()
                        )

                        if activity_record:
                            # Skip to the next iteration
                            continue

                    start_date_parsed = activitiesController.parse_timestamp(
                        activity.get("start_date")
                    )
                    end_date_parsed = start_date_parsed + timedelta(
                        seconds=activity.get("elapsed_time")
                    )

                    latitude, longitude = activity.get("start_latlng", [0, 0])
                    city = None
                    town = None
                    country = None
                    if latitude != 0 and longitude != 0:
                        url = f"https://geocode.maps.co/reverse?lat={latitude}&lon={longitude}"
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

                    activity_id = activity.get("id")
                    strava_api_url_streams = f"https://www.strava.com/api/v3/activities/{activity_id}/streams"

                    # List to store constructed waypoints
                    waypoints = []

                    # Initialize variables for elevation gain and loss
                    elevation_gain = 0
                    elevation_loss = 0

                    try:
                        # Make a GET request to retrieve activity streams
                        response = requests.get(strava_api_url_streams, params=params)

                        # Check if the request was successful (status code 200)
                        if response.status_code == 200:
                            # Parse the JSON response
                            activity_streams = response.json()

                            # Extract relevant streams data
                            latlng_stream = activity_streams.get("latlng", {}).get(
                                "data", []
                            )
                            time_stream = activity_streams.get("time", {}).get(
                                "data", []
                            )
                            elevation_stream = activity_streams.get("altitude", {}).get(
                                "data", []
                            )
                            heart_rate_stream = activity_streams.get(
                                "heartrate", {}
                            ).get("data", [])
                            cadence_stream = activity_streams.get("cadence", {}).get(
                                "data", []
                            )
                            power_stream = activity_streams.get("watts", {}).get(
                                "data", []
                            )
                            velocity_stream = activity_streams.get(
                                "velocity_smooth", {}
                            ).get("data", [])

                            # Ensure all streams have the same length (adjust as needed)
                            stream_length = min(
                                len(latlng_stream),
                                len(time_stream),
                                len(elevation_stream),
                                len(heart_rate_stream),
                                len(cadence_stream),
                                len(power_stream),
                                len(velocity_stream),
                            )

                            # Iterate over the streams and construct waypoints
                            for i in range(stream_length):
                                latitude, longitude = (
                                    latlng_stream[i]
                                    if i < len(latlng_stream)
                                    else (0, 0)
                                )
                                time = time_stream[i] if i < len(time_stream) else ""
                                elevation = (
                                    elevation_stream[i]
                                    if i < len(elevation_stream)
                                    else 0
                                )
                                heart_rate = (
                                    heart_rate_stream[i]
                                    if i < len(heart_rate_stream)
                                    else 0
                                )
                                cadence = (
                                    cadence_stream[i] if i < len(cadence_stream) else 0
                                )
                                power = power_stream[i] if i < len(power_stream) else 0
                                velocity = (
                                    velocity_stream[i]
                                    if i < len(velocity_stream)
                                    else 0
                                )

                                elevation_current = (
                                    elevation_stream[i]
                                    if i < len(elevation_stream)
                                    else 0
                                )
                                elevation_previous = (
                                    elevation_stream[i - 1]
                                    if i - 1 < len(elevation_stream)
                                    else 0
                                )

                                # Calculate the difference in elevation
                                elevation_difference = (
                                    elevation_current - elevation_previous
                                )

                                # Update elevation gain and loss based on the difference
                                if elevation_difference > 0:
                                    elevation_gain += elevation_difference
                                elif elevation_difference < 0:
                                    elevation_loss += abs(elevation_difference)

                                # Construct the waypoint dictionary
                                waypoint = {
                                    "lat": latitude,
                                    "lon": longitude,
                                    "ele": elevation,
                                    "time": time,
                                    "hr": heart_rate,
                                    "cad": cadence,
                                    "power": power,
                                    "vel": velocity,
                                    # Add other relevant fields based on your requirements
                                }

                                # Append the constructed waypoint to the waypoints list
                                waypoints.append(waypoint)

                        else:
                            print(f"Error streams: {response.status_code}")
                    except Exception as e:
                        print(f"An error occurred: {e}")

                    average_pace = (
                        1 / activity.get("average_speed", 0)
                        if activity.get("average_speed", 0) != 0
                        else 0
                    )

                    # activitiesController.create_activity([activity.get("distance", 0), activity.get("name", "Unnamed activity"), activity.get("type", "Workout"), start_date_parsed, end_date_parsed, city, town, country, waypoints, elevation_gain, elevation_loss, average_pace, activity.get("average_speed", 0), activity.get("average_watts", 0), activity.get("id")],token)

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
                        "open_water_swimming": 9,
                        "Workout": 10,
                    }
                    auxType = type_mapping.get(activity.get("sport_type", "Workout"), 10)

                    aux = activity.get("sport_type")
                    logger.info(f"No Strava activities returned {aux}")

                    # Create a new Activity record
                    activity = Activity(
                        user_id=user_id,
                        name=activity.get("name", "Unnamed activity"),
                        distance=round(activity.get("distance", 0)),
                        activity_type=auxType,
                        start_time=start_date_parsed,
                        end_time=end_date_parsed,
                        city=city,
                        town=town,
                        country=country,
                        created_at=func.now(),  # Use func.now() to set 'created_at' to the current timestamp
                        waypoints=waypoints,
                        elevation_gain=elevation_gain,
                        elevation_loss=elevation_loss,
                        pace=average_pace,
                        average_speed=activity.get("average_speed", 0),
                        average_power=activity.get("average_watts", 0),
                        strava_activity_id=activity.get("id"),
                    )

                    # Store the Activity record in the database
                    with get_db_session() as db_session:
                        db_session.add(activity)
                        db_session.commit()
                        db_session.refresh(
                            activity
                        )  # This will ensure that the activity object is updated with the ID from the database
                    return {"message": "Activities retrieved"}
                except Exception as err:
                    print(err)
                    logger.error(err)
        else:
            logger.info("No Strava activities returned")
    except JWTError:
        raise HTTPException(status_code=401, detail="Unauthorized")
