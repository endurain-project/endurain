from fastapi import HTTPException, status
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from stravalib.client import Client
from stravalib.exc import AccessUnauthorized
from timezonefinder import TimezoneFinder

import core.logger as core_logger
import core.config as core_config

import activities.activity.schema as activities_schema
import activities.activity.crud as activities_crud
import activities.activity.utils as activities_utils

import activities.activity_laps.crud as activity_laps_crud

import activities.activity_streams.schema as activity_streams_schema
import activities.activity_streams.crud as activity_streams_crud

import users.user_integrations.models as user_integrations_models
import users.user_integrations.schema as user_integrations_schema

import users.user_default_gear.utils as user_default_gear_utils

import users.user_privacy_settings.crud as users_privacy_settings_crud
import users.user_privacy_settings.schema as users_privacy_settings_schema

import users.user.crud as users_crud

import gears.gear.crud as gears_crud

import strava.utils as strava_utils

import websocket.manager as websocket_manager

from core.database import SessionLocal


async def fetch_and_process_activities(
    strava_client: Client,
    start_date: datetime,
    end_date: datetime,
    user_id: int,
    user_integrations: user_integrations_models.UsersIntegrations,
    ws_manager: websocket_manager.WebSocketManager,
    db: Session,
    is_startup: bool = False,
) -> int:
    # set the strava activities to None
    strava_activities = None

    # Fetch Strava activities after the specified start date
    try:
        strava_activities = list(
            strava_client.get_activities(after=start_date, before=end_date)
        )
    except AccessUnauthorized as auth_err:
        # Log a more specific error message for authentication issues
        core_logger.print_to_log(
            f"User {user_id}: Authentication error with Strava: {str(auth_err)}",
            "error",
            exc=auth_err,
        )
        # Attempt to refresh token or notify user about authentication issues
        if not is_startup:
            raise HTTPException(
                status_code=status.HTTP_424_FAILED_DEPENDENCY,
                detail="Strava authentication failed. Please reconnect your Strava account.",
            ) from auth_err
        # Return 0 to indicate no activities were processed
        return 0
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Log an error event if an exception occurred
        core_logger.print_to_log(
            f"User {user_id}: Error fetching Strava activities: {str(err)}",
            "error",
            exc=err,
        )
        # Raise an HTTPException with a 424 Failed Dependency status code
        if not is_startup:
            raise HTTPException(
                status_code=status.HTTP_424_FAILED_DEPENDENCY,
                detail="Not able to fetch Strava activities",
            ) from err
        # Return 0 to indicate no activities were processed
        return 0

    if strava_activities is None:
        # Log an informational event if no activities were found
        core_logger.print_to_log(
            f"User {user_id}: No new Strava activities found after {start_date}: strava_activities is None"
        )

        # Return 0 to indicate no activities were processed
        return 0

    user = users_crud.get_user_by_id(user_id, db)
    if user is None:
        if not is_startup:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

    user_privacy_settings = (
        users_privacy_settings_crud.get_user_privacy_settings_by_user_id(user.id, db)
    )

    processed_activities = []

    # Process the activities
    for activity in strava_activities:
        processed_activities.append(
            await process_activity(
                activity,
                user_id,
                user_privacy_settings,
                strava_client,
                user_integrations,
                ws_manager,
                db,
            )
        )

    # Return the activities processed
    return processed_activities if processed_activities else None


def parse_activity(
    activity,
    user_id: int,
    user_privacy_settings: users_privacy_settings_schema.UsersPrivacySettingsRead,
    strava_client: Client,
    user_integrations: user_integrations_models.UsersIntegrations,
    db: Session,
) -> dict:
    # Create an instance of TimezoneFinder
    tf = TimezoneFinder()
    timezone = core_config.TZ

    # Get the detailed activity
    try:
        detailedActivity = strava_client.get_activity(activity.id)
    except Exception as err:
        # Log an error event if an exception occurred
        core_logger.print_to_log(
            f"User {user_id}: Error fetching detailed Strava activity {activity.id}: {str(err)}",
            "error",
            exc=err,
        )
        # Return None to indicate the activity was not processed
        # return None
        raise HTTPException(
            status_code=status.HTTP_424_FAILED_DEPENDENCY,
            detail="Not able to fetch Strava activity",
        )

    # Parse start and end dates
    start_date_parsed = detailedActivity.start_date

    # Ensure activity.elapsed_time is a numerical value
    total_elapsed_time = (
        detailedActivity.elapsed_time.total_seconds()
        if isinstance(detailedActivity.elapsed_time, timedelta)
        else detailedActivity.elapsed_time
    )

    total_timer_time = (
        detailedActivity.moving_time.total_seconds()
        if isinstance(detailedActivity.moving_time, timedelta)
        else detailedActivity.moving_time
    )

    end_date_parsed = start_date_parsed + timedelta(seconds=total_elapsed_time)

    # Initialize location variables
    city, town, country = None, None, None
    if detailedActivity.location_city is not None:
        city = detailedActivity.location_city
    if detailedActivity.location_state is not None:
        town = detailedActivity.location_state
    if detailedActivity.location_country is not None:
        country = detailedActivity.location_country

    # Fetch and process activity streams
    (
        lat_lon_waypoints,
        is_lat_lon_set,
        ele_waypoints,
        is_elevation_set,
        hr_waypoints,
        is_heart_rate_set,
        cad_waypoints,
        is_cadence_set,
        power_waypoints,
        is_power_set,
        vel_waypoints,
        is_velocity_set,
        pace_waypoints,
    ) = fetch_and_process_activity_streams(
        strava_client,
        activity.id,
        user_id,
    )

    ele_gain, ele_loss = None, None
    # Calculate elevation gain and loss
    if ele_waypoints:
        ele_gain, ele_loss = activities_utils.compute_elevation_gain_and_loss(
            ele_waypoints
        )

        if detailedActivity.total_elevation_gain is not None:
            ele_gain = round(detailedActivity.total_elevation_gain)

    # Get average and max speed
    avg_speed = None
    if detailedActivity.average_speed is not None:
        avg_speed = detailedActivity.average_speed

    max_speed = None
    if detailedActivity.max_speed is not None:
        max_speed = detailedActivity.max_speed

    # Calculate average pace
    average_pace = 1 / avg_speed if avg_speed != 0 else None

    avg_hr, max_hr = None, None
    # Get average and max heart rate
    if detailedActivity.average_heartrate is not None:
        avg_hr = detailedActivity.average_heartrate

    if detailedActivity.max_heartrate is not None:
        max_hr = detailedActivity.max_heartrate

    avg_cadence, max_cadence = None, None
    # Calculate average and maximum cadence
    if cad_waypoints:
        avg_cadence, max_cadence = activities_utils.calculate_avg_and_max(
            cad_waypoints, "cad"
        )

        if detailedActivity.average_cadence is not None:
            avg_cadence = detailedActivity.average_cadence

    # Get average and max power
    avg_power = None
    if detailedActivity.average_watts is not None:
        avg_power = detailedActivity.average_watts

    max_power = None
    if detailedActivity.max_watts is not None:
        max_power = detailedActivity.max_watts

    # Calculate normalized power
    np = None
    if power_waypoints:
        np = activities_utils.calculate_np(power_waypoints)

    # List of conditions, stream types, and corresponding waypoints
    stream_data = [
        (is_heart_rate_set, 1, hr_waypoints),
        (is_power_set, 2, power_waypoints),
        (is_cadence_set, 3, cad_waypoints),
        (is_elevation_set, 4, ele_waypoints),
        (is_velocity_set, 5, vel_waypoints),
        (is_velocity_set, 6, pace_waypoints),
        (detailedActivity.start_latlng is not None, 7, lat_lon_waypoints),
    ]

    gear_id = None

    if user_integrations.strava_sync_gear:
        # set the gear id for the activity
        gear = gears_crud.get_gear_by_strava_id_from_user_id(
            detailedActivity.gear_id, user_id, db
        )

        # set the gear id for the activity
        if gear is not None:
            gear_id = gear.id

    # Activity type
    activity_type = activities_utils.define_activity_type(
        detailedActivity.sport_type.root
    )

    if gear_id is None:
        gear_id = user_default_gear_utils.get_user_default_gear_by_activity_type(
            user_id, activity_type, db
        )

    if activity_type != 3 and activity_type != 7:
        if is_lat_lon_set:
            timezone = tf.timezone_at(
                lat=lat_lon_waypoints[0]["lat"],
                lng=lat_lon_waypoints[0]["lon"],
            )

    # Create the activity object
    activity_to_store = activities_schema.Activity(
        user_id=user_id,
        name=detailedActivity.name,
        distance=round(detailedActivity.distance) if detailedActivity.distance else 0,
        description=detailedActivity.description,
        activity_type=activity_type,
        start_time=start_date_parsed.strftime("%Y-%m-%dT%H:%M:%S"),
        end_time=end_date_parsed.strftime("%Y-%m-%dT%H:%M:%S"),
        timezone=timezone,
        total_elapsed_time=total_elapsed_time,
        total_timer_time=total_timer_time,
        city=city,
        town=town,
        country=country,
        elevation_gain=round(ele_gain) if ele_gain else None,
        elevation_loss=round(ele_loss) if ele_loss else None,
        pace=average_pace,
        average_speed=avg_speed,
        max_speed=max_speed,
        average_power=round(avg_power) if avg_power else None,
        max_power=max_power,
        normalized_power=round(np) if np else None,
        average_hr=round(avg_hr) if avg_hr else None,
        max_hr=max_hr,
        average_cad=round(avg_cadence) if avg_cadence else None,
        max_cad=max_cadence,
        calories=round(detailedActivity.calories),
        gear_id=gear_id,
        strava_gear_id=detailedActivity.gear_id,
        strava_activity_id=int(activity.id),
        visibility=(
            user_privacy_settings.default_activity_visibility
            if user_privacy_settings.default_activity_visibility is not None
            else 0
        ),
        hide_start_time=user_privacy_settings.hide_activity_start_time or False,
        hide_location=user_privacy_settings.hide_activity_location or False,
        hide_map=user_privacy_settings.hide_activity_map or False,
        hide_hr=user_privacy_settings.hide_activity_hr or False,
        hide_power=user_privacy_settings.hide_activity_power or False,
        hide_cadence=user_privacy_settings.hide_activity_cadence or False,
        hide_elevation=user_privacy_settings.hide_activity_elevation or False,
        hide_speed=user_privacy_settings.hide_activity_speed or False,
        hide_pace=user_privacy_settings.hide_activity_pace or False,
        hide_laps=user_privacy_settings.hide_activity_laps or False,
        hide_workout_sets_steps=user_privacy_settings.hide_activity_workout_sets_steps
        or False,
        hide_gear=user_privacy_settings.hide_activity_gear or False,
    )

    # Fetch and process activity laps
    laps = fetch_and_process_activity_laps(
        strava_client,
        activity.id,
        user_id,
        stream_data,
    )

    # Return the activity and stream data
    return {
        "activity_to_store": activity_to_store,
        "stream_data": stream_data,
        "laps": laps,
    }


async def save_activity_streams_laps(
    activity: activities_schema.Activity,
    stream_data: list,
    laps: dict,
    ws_manager: websocket_manager.WebSocketManager,
    db: Session,
) -> activities_schema.Activity:
    # Create the activity and get the ID
    created_activity = await activities_crud.create_activity(activity, ws_manager, db)

    if stream_data is not None:
        # Create the empty array of activity streams
        activity_streams = []

        # Create the activity streams objects
        for is_set, stream_type, waypoints in stream_data:
            if is_set:
                activity_streams.append(
                    activity_streams_schema.ActivityStreams(
                        activity_id=created_activity.id,
                        stream_type=stream_type,
                        stream_waypoints=waypoints,
                        strava_activity_stream_id=None,
                    )
                )

        # Create the activity streams in the database
        activity_streams_crud.create_activity_streams(activity_streams, db)

    # Append activity id to laps
    if laps is not None:
        # Create the laps in the database
        activity_laps_crud.create_activity_laps(laps, created_activity.id, db)

    # return the created activity
    return created_activity


async def process_activity(
    activity,
    user_id: int,
    user_privacy_settings: users_privacy_settings_schema.UsersPrivacySettingsRead,
    strava_client: Client,
    user_integrations: user_integrations_models.UsersIntegrations,
    ws_manager: websocket_manager.WebSocketManager,
    db: Session,
):
    # Get the activity by Strava ID from the user
    activity_db = strava_utils.fetch_and_validate_activity(activity.id, user_id, db)

    # Check if activity is None and return None if it is
    if activity_db is not None:
        return None

    # Log an informational event for activity processing
    core_logger.print_to_log(
        f"User {user_id}: Strava activity {activity.id} will be processed"
    )

    # Parse the activity and streams
    parsed_activity = parse_activity(
        activity,
        user_id,
        user_privacy_settings,
        strava_client,
        user_integrations,
        db,
    )

    # Save the activity and streams to the database
    return await save_activity_streams_laps(
        parsed_activity["activity_to_store"],
        parsed_activity["stream_data"],
        parsed_activity["laps"],
        ws_manager,
        db,
    )


def fetch_and_process_activity_streams(
    strava_client: Client,
    strava_activity_id: int,
    user_id: int,
):
    # Get streams for the activity
    try:
        streams = strava_client.get_activity_streams(
            strava_activity_id,
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
    except Exception as err:
        # Log an error event if an exception occurred
        core_logger.print_to_log(
            f"User {user_id}: Error fetching Strava activity streams {strava_activity_id}: {str(err)}",
            "error",
            exc=err,
        )
        # Raise exception
        raise HTTPException(
            status_code=status.HTTP_424_FAILED_DEPENDENCY,
            detail="Not able to fetch Strava activity streams",
        )

    # Extract data from streams
    lat_lon = streams["latlng"].data if "latlng" in streams else []
    lat_lon_waypoints = []
    is_lat_lon_set = False
    ele = streams["altitude"].data if "altitude" in streams else []
    ele_waypoints = []
    is_elevation_set = False
    time = streams["time"].data if "time" in streams else []
    hr = streams["heartrate"].data if "heartrate" in streams else []
    hr_waypoints = []
    is_heart_rate_set = False
    cad = streams["cadence"].data if "cadence" in streams else []
    cad_waypoints = []
    is_cadence_set = False
    power = streams["watts"].data if "watts" in streams else []
    power_waypoints = []
    is_power_set = False
    vel = streams["velocity_smooth"].data if "velocity_smooth" in streams else []
    vel_waypoints = []
    is_velocity_set = False
    pace_waypoints = []

    for i in range(len(lat_lon)):
        lat_lon_waypoints.append(
            {
                "time": time[i],
                "lat": lat_lon[i][0],
                "lon": lat_lon[i][1],
            }
        )
        is_lat_lon_set = True

    for i in range(len(ele)):
        ele_waypoints.append({"time": time[i], "ele": ele[i]})
        is_elevation_set = True

    for i in range(len(hr)):
        hr_waypoints.append({"time": time[i], "hr": hr[i]})
        is_heart_rate_set = True

    for i in range(len(cad)):
        cad_waypoints.append({"time": time[i], "cad": cad[i]})
        is_cadence_set = True

    for i in range(len(power)):
        power_waypoints.append({"time": time[i], "power": power[i]})
        is_power_set = True

    for i in range(len(vel)):
        # Append velocity to the velocity waypoints
        vel_waypoints.append({"time": time[i], "vel": vel[i]})

        # Calculate pace on-the-fly. If velocity is 0, pace is 0
        pace_calculation = 0
        if vel[i] != 0:
            pace_calculation = 1 / vel[i]

        # Append pace to the pace waypoints
        pace_waypoints.append({"time": time[i], "pace": pace_calculation})
        is_velocity_set = True

    return (
        lat_lon_waypoints,
        is_lat_lon_set,
        ele_waypoints,
        is_elevation_set,
        hr_waypoints,
        is_heart_rate_set,
        cad_waypoints,
        is_cadence_set,
        power_waypoints,
        is_power_set,
        vel_waypoints,
        is_velocity_set,
        pace_waypoints,
    )


def fetch_and_process_activity_laps(
    strava_client: Client,
    strava_activity_id: int,
    user_id: int,
    stream_data: list,
):
    # Fetch the activity laps
    try:
        laps = strava_client.get_activity_laps(strava_activity_id)
    except Exception as err:
        # Log an error event if an exception occurred
        core_logger.print_to_log(
            f"User {user_id}: Error fetching Strava activity laps for Strava activity {strava_activity_id}: {str(err)}",
            "error",
            exc=err,
        )
        # Return None to indicate the activity was not processed
        return None

    # Create an array to store the processed laps
    laps_processed = []

    # Process the laps
    for lap in laps:
        cad_avg, cad_max = None, None
        power_avg, power_max = None, None
        np = None
        ele_gain, ele_loss = None, None

        # filter the stream data based on the lap's start and end times
        filtered_stream_data = [
            (enabled, stream_id, waypoints[lap.start_index : lap.end_index + 1])
            for enabled, stream_id, waypoints in stream_data
            if enabled
        ]

        lat_lon_stream = next(
            (
                waypoints
                for enabled, stream_id, waypoints in filtered_stream_data
                if stream_id == 7
            ),
            None,
        )

        cad_stream = next(
            (
                waypoints
                for enabled, stream_id, waypoints in filtered_stream_data
                if stream_id == 3
            ),
            None,
        )

        if cad_stream:
            cad_avg, cad_max = activities_utils.calculate_avg_and_max(cad_stream, "cad")

        power_stream = next(
            (
                waypoints
                for enabled, stream_id, waypoints in filtered_stream_data
                if stream_id == 2
            ),
            None,
        )

        if power_stream:
            power_avg, power_max = activities_utils.calculate_avg_and_max(
                power_stream, "power"
            )
            np = activities_utils.calculate_np(power_stream)

        ele_stream = next(
            (
                waypoints
                for enabled, stream_id, waypoints in filtered_stream_data
                if stream_id == 4
            ),
            None,
        )

        if ele_stream:
            ele_gain, ele_loss = activities_utils.compute_elevation_gain_and_loss(
                ele_stream
            )

        laps_processed.append(
            {
                "start_time": lap.start_date_local.strftime("%Y-%m-%dT%H:%M:%S"),
                "start_position_lat": (
                    lat_lon_stream[0]["lat"] if lat_lon_stream else None
                ),
                "start_position_long": (
                    lat_lon_stream[0]["lon"] if lat_lon_stream else None
                ),
                "end_position_lat": (
                    lat_lon_stream[-1]["lat"] if lat_lon_stream else None
                ),
                "end_position_long": (
                    lat_lon_stream[-1]["lon"] if lat_lon_stream else None
                ),
                "total_elapsed_time": lap.elapsed_time,
                "total_timer_time": lap.moving_time,
                "total_distance": lap.distance,
                "avg_heart_rate": (
                    round(lap.average_heartrate) if lap.average_heartrate else None
                ),
                "max_heart_rate": (
                    round(lap.max_heartrate) if lap.max_heartrate else None
                ),
                "avg_cadence": round(cad_avg) if cad_stream else None,
                "max_cadence": round(cad_max) if cad_stream else None,
                "avg_power": round(power_avg) if power_stream else None,
                "max_power": round(power_max) if power_stream else None,
                "total_ascent": round(ele_gain) if ele_stream else None,
                "total_descent": round(ele_loss) if ele_stream else None,
                "normalized_power": round(np) if np else None,
                "enhanced_avg_pace": (
                    1 / lap.average_speed
                    if lap.average_speed != 0 and lap.average_speed is not None
                    else None
                ),
                "enhanced_avg_speed": lap.average_speed,
                "enhanced_max_pace": (
                    1 / lap.max_speed
                    if lap.max_speed != 0 and lap.max_speed is not None
                    else None
                ),
                "enhanced_max_speed": lap.max_speed,
            }
        )

    # Return the processed laps
    return laps_processed


async def retrieve_strava_users_activities_for_days(
    days: int, is_startup: bool = False
):
    # Create a new database session using context manager
    with SessionLocal() as db:
        try:
            # Get all users
            users = users_crud.get_all_users(db)

            # Calculate the start date and end date
            calculated_start_date = datetime.now(timezone.utc) - timedelta(days=days)
            calculated_end_date = datetime.now(timezone.utc)

            # Process the activities for each user
            if users:
                for user in users:
                    try:
                        await get_user_strava_activities_by_dates(
                            calculated_start_date,
                            calculated_end_date,
                            user.id,
                            None,
                            None,
                            is_startup,
                        )
                    except HTTPException as err:
                        # Log the error but continue processing other users
                        core_logger.print_to_log(
                            f"User {user.id}: Error processing Strava activities: {str(err)}",
                            "error",
                            exc=err,
                        )
                        # Don't reraise the exception if we're in startup mode
                        if not is_startup:
                            raise err
                    except Exception as err:
                        # Log the error but continue processing other users
                        core_logger.print_to_log(
                            f"User {user.id}: Unexpected error processing Strava activities: {str(err)}",
                            "error",
                            exc=err,
                        )
                        # Don't reraise the exception if we're in startup mode
                        if not is_startup:
                            raise HTTPException(
                                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                detail="Internal Server Error",
                            ) from err
        except HTTPException as err:
            # Log an error event if an HTTPException occurred
            core_logger.print_to_log(
                f"Error retrieving users: {str(err)}",
                "error",
                exc=err,
            )
            # Raise the HTTPException to propagate the error
            if not is_startup:
                raise err
        except Exception as err:
            # Log an error event if an exception occurred
            core_logger.print_to_log(
                f"Error retrieving users: {str(err)}",
                "error",
                exc=err,
            )
            # Raise an HTTPException with a 500 Internal Server Error status code
            if not is_startup:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Internal Server Error",
                ) from err


async def get_user_strava_activities_by_dates(
    start_date: datetime,
    end_date: datetime,
    user_id: int,
    ws_manager: websocket_manager.WebSocketManager = None,
    db: Session = None,
    is_startup: bool = False,
) -> list[activities_schema.Activity] | None:
    close_session = False
    if db is None:
        # Create a new database session
        db = SessionLocal()
        close_session = True

    if ws_manager is None:
        # Get the websocket manager instance
        ws_manager = websocket_manager.get_websocket_manager()

    try:
        # Get the user integrations by user ID
        user_integrations = strava_utils.fetch_user_integrations_and_validate_token(
            user_id, db
        )

        if user_integrations is None:
            core_logger.print_to_log(f"User {user_id}: Strava not linked")
            return None

        # Log the start of the activities processing
        core_logger.print_to_log(
            f"User {user_id}: Started Strava activities processing"
        )

        # Create a Strava client with the user's access token
        strava_client = strava_utils.create_strava_client(user_integrations)

        try:
            # Fetch Strava activities after the specified start date
            strava_activities_processed = await fetch_and_process_activities(
                strava_client,
                start_date,
                end_date,
                user_id,
                user_integrations,
                ws_manager,
                db,
                is_startup,
            )

            # Log an informational event for tracing
            core_logger.print_to_log(
                f"User {user_id}: {len(strava_activities_processed) if strava_activities_processed else 0} Strava activities processed"
            )

            return strava_activities_processed
        except HTTPException as err:
            # Log an error event if an exception occurred
            core_logger.print_to_log(
                f"User {user_id}: Error processing Strava activities: {str(err)}",
                "error",
                exc=err,
            )
            # Raise the HTTPException to propagate the error
            if not is_startup:
                raise err
        except Exception as err:
            # Log an error event if an exception occurred
            core_logger.print_to_log(
                f"User {user_id}: Error processing Strava activities: {str(err)}",
                "error",
                exc=err,
            )
            # Raise an HTTPException with a 500 Internal Server Error status code
            if not is_startup:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Internal Server Error",
                ) from err
    except HTTPException as err:
        # Log an error event if an exception occurred
        core_logger.print_to_log(
            f"User {user_id}: Error getting user integrations and Strava client: {str(err)}",
            "error",
            exc=err,
        )
        # Raise the HTTPException to propagate the error
        if not is_startup:
            raise err
    except Exception as err:
        # Log an error event if an exception occurred
        core_logger.print_to_log(
            f"User {user_id}: Error getting user integrations and Strava client: {str(err)}",
            "error",
            exc=err,
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        if not is_startup:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal Server Error",
            ) from err
    finally:
        if close_session:
            # Ensure the session is closed after use
            db.close()
