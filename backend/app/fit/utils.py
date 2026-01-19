import fitdecode
from enum import Enum

from fastapi import HTTPException, status
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from timezonefinder import TimezoneFinder
from zoneinfo import ZoneInfo, available_timezones

import activities.activity.utils as activities_utils
import activities.activity.schema as activities_schema

import activities.activity_exercise_titles.schema as activity_exercise_titles_schema
import activities.activity_exercise_titles.crud as activity_exercise_titles_crud

import activities.activity_workout_steps.schema as activity_workout_steps_schema

import users.users_default_gear.utils as user_default_gear_utils

import garmin.utils as garmin_utils

import gears.gear.crud as gears_crud

import users.users_privacy_settings.models as users_privacy_settings_models

import core.logger as core_logger

import core.config as core_config


def create_activity_objects(
    sessions_records: dict,
    user_id: int,
    user_privacy_settings: users_privacy_settings_models.UsersPrivacySettings,
    garmin_activity_id: int | None = None,
    garminconnect_gear: dict | None = None,
    db: Session = None,
) -> list:
    try:
        # Create an instance of TimezoneFinder
        tf = TimezoneFinder()
        timezone = core_config.TZ

        # Define variables
        gear_id = None

        if garminconnect_gear:
            user_integrations = garmin_utils.fetch_user_integrations_and_validate_token(
                user_id, db
            )

            if user_integrations.garminconnect_sync_gear:
                # set the gear id for the activity
                gear = gears_crud.get_gear_by_garminconnect_id_from_user_id(
                    garminconnect_gear[0]["uuid"], user_id, db
                )

                # set the gear id for the activity
                if gear is not None:
                    gear_id = gear.id

        activities = []

        for session_record in sessions_records:
            # Define default values
            activity_type = 10
            activity_name = "Workout"
            pace = 0

            if session_record["session"]["activity_type"]:
                # Set the activity type based on the session record
                activity_type = activities_utils.define_activity_type(
                    session_record["session"]["activity_type"]
                )

                if gear_id is None:
                    gear_id = (
                        user_default_gear_utils.get_user_default_gear_by_activity_type(
                            user_id, activity_type, db
                        )
                    )

            if (
                session_record["activity_name"]
                and session_record["activity_name"] != "Workout"
            ):
                activity_name = session_record["activity_name"]

            # Calculate elevation gain/loss, pace, average speed, and average power
            total_timer_time, pace = calculate_pace(
                session_record["session"]["distance"],
                session_record["session"]["total_timer_time"],
                session_record["session"]["activity_type"],
                session_record["split_summary"],
                session_record["lengths"],
            )

            if activity_type != 3 and activity_type != 7:
                if session_record["is_lat_lon_set"]:
                    timezone = tf.timezone_at(
                        lat=session_record["lat_lon_waypoints"][0]["lat"],
                        lng=session_record["lat_lon_waypoints"][0]["lon"],
                    )
                else:
                    if session_record["time_offset"]:
                        timezone = find_timezone_name(
                            session_record["time_offset"],
                            session_record["session"]["first_waypoint_time"],
                        )

            avg_power = session_record["session"]["avg_power"]
            max_power = session_record["session"]["max_power"]
            if avg_power is None:
                if session_record["is_power_set"]:
                    avg_power, max_power = activities_utils.calculate_avg_and_max(
                        session_record["power_waypoints"], "power"
                    )

            np_power = session_record["session"]["np"]
            if np_power is None:
                if session_record["is_power_set"]:
                    np_power = activities_utils.calculate_np(
                        session_record["power_waypoints"]
                    )

            parsed_activity = {
                # Create an Activity object with parsed data
                "activity": activities_schema.Activity(
                    user_id=user_id,
                    name=activity_name,
                    distance=(
                        round(session_record["session"]["distance"])
                        if session_record["session"]["distance"]
                        else 0
                    ),
                    activity_type=activity_type,
                    start_time=session_record["session"][
                        "first_waypoint_time"
                    ].strftime("%Y-%m-%dT%H:%M:%S"),
                    end_time=session_record["session"]["last_waypoint_time"].strftime(
                        "%Y-%m-%dT%H:%M:%S"
                    ),
                    timezone=timezone,
                    total_elapsed_time=session_record["session"]["total_elapsed_time"],
                    total_timer_time=total_timer_time,
                    city=session_record["session"]["city"],
                    town=session_record["session"]["town"],
                    country=session_record["session"]["country"],
                    elevation_gain=session_record["session"]["ele_gain"],
                    elevation_loss=session_record["session"]["ele_loss"],
                    pace=pace,
                    average_speed=session_record["session"]["avg_speed"],
                    max_speed=session_record["session"]["max_speed"],
                    average_power=round(avg_power) if avg_power else None,
                    max_power=round(max_power) if max_power else None,
                    normalized_power=round(np_power) if np_power else None,
                    average_hr=session_record["session"]["avg_hr"],
                    max_hr=session_record["session"]["max_hr"],
                    average_cad=session_record["session"]["avg_cadence"],
                    max_cad=session_record["session"]["max_cadence"],
                    workout_feeling=session_record["session"]["workout_feeling"],
                    workout_rpe=session_record["session"]["workout_rpe"],
                    calories=session_record["session"]["calories"],
                    visibility=(
                        user_privacy_settings.default_activity_visibility
                        if user_privacy_settings.default_activity_visibility is not None
                        else 0
                    ),
                    gear_id=gear_id,
                    strava_gear_id=None,
                    strava_activity_id=None,
                    garminconnect_activity_id=garmin_activity_id,
                    garminconnect_gear_id=(
                        garminconnect_gear[0]["uuid"] if garminconnect_gear else None
                    ),
                    hide_start_time=user_privacy_settings.hide_activity_start_time
                    or False,
                    hide_location=user_privacy_settings.hide_activity_location or False,
                    hide_map=user_privacy_settings.hide_activity_map or False,
                    hide_hr=user_privacy_settings.hide_activity_hr or False,
                    hide_power=user_privacy_settings.hide_activity_power or False,
                    hide_cadence=user_privacy_settings.hide_activity_cadence or False,
                    hide_elevation=user_privacy_settings.hide_activity_elevation
                    or False,
                    hide_speed=user_privacy_settings.hide_activity_speed or False,
                    hide_pace=user_privacy_settings.hide_activity_pace or False,
                    hide_laps=user_privacy_settings.hide_activity_laps or False,
                    hide_workout_sets_steps=user_privacy_settings.hide_activity_workout_sets_steps
                    or False,
                    hide_gear=user_privacy_settings.hide_activity_gear or False,
                    tracker_manufacturer=session_record["file_id"].get(
                        "manufacturer", None
                    ),
                    tracker_model=str(session_record["file_id"].get("product", None)),
                ),
                "is_elevation_set": session_record["is_elevation_set"],
                "ele_waypoints": session_record["ele_waypoints"],
                "is_power_set": session_record["is_power_set"],
                "power_waypoints": session_record["power_waypoints"],
                "is_heart_rate_set": session_record["is_heart_rate_set"],
                "hr_waypoints": session_record["hr_waypoints"],
                "is_velocity_set": session_record["is_velocity_set"],
                "vel_waypoints": session_record["vel_waypoints"],
                "pace_waypoints": session_record["pace_waypoints"],
                "is_cadence_set": session_record["is_cadence_set"],
                "cad_waypoints": session_record["cad_waypoints"],
                "is_lat_lon_set": session_record["is_lat_lon_set"],
                "lat_lon_waypoints": session_record["lat_lon_waypoints"],
                "laps": session_record["laps"],
                "sets": session_record["sets"],
                "workout_steps": session_record["workout_steps"],
            }

            activities.append(parsed_activity)

        return activities
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in create_activity_objects: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Can't parse FIT file sessions",
        ) from err


def split_records_by_activity(parsed_data: dict) -> dict:
    sessions = parsed_data["sessions"]
    lat_lon_waypoints = parsed_data["lat_lon_waypoints"]
    ele_waypoints = parsed_data.get("ele_waypoints", [])
    hr_waypoints = parsed_data.get("hr_waypoints", [])
    cad_waypoints = parsed_data.get("cad_waypoints", [])
    power_waypoints = parsed_data.get("power_waypoints", [])
    vel_waypoints = parsed_data.get("vel_waypoints", [])
    pace_waypoints = parsed_data.get("pace_waypoints", [])

    # Check for each auxiliary flag
    is_lat_lon_set = parsed_data.get("is_lat_lon_set", False)
    is_elevation_set = parsed_data.get("is_elevation_set", False)
    is_heart_rate_set = parsed_data.get("is_heart_rate_set", False)
    is_cadence_set = parsed_data.get("is_cadence_set", False)
    is_power_set = parsed_data.get("is_power_set", False)
    is_velocity_set = parsed_data.get("is_velocity_set", False)

    # Dictionary to hold split waypoints per activity
    activity_waypoints = {
        i: {
            "lat_lon_waypoints": [] if is_lat_lon_set else None,
            "ele_waypoints": [] if is_elevation_set else None,
            "hr_waypoints": [] if is_heart_rate_set else None,
            "cad_waypoints": [] if is_cadence_set else None,
            "power_waypoints": [] if is_power_set else None,
            "vel_waypoints": [] if is_velocity_set else None,
            "pace_waypoints": [] if is_velocity_set else None,
        }
        for i in range(len(sessions))
    }

    sessions_records = []

    # Convert session times to datetime objects for easier comparison
    for i, session in enumerate(sessions):
        # Use the time as is if it’s already a datetime object; otherwise, parse it
        start_time = session["first_waypoint_time"]
        if not isinstance(start_time, datetime):
            start_time = datetime.strptime(start_time, "%Y-%m-%dT%H:%M:%S")

        end_time = session.get("last_waypoint_time", start_time)
        if not isinstance(end_time, datetime):
            end_time = datetime.strptime(end_time, "%Y-%m-%dT%H:%M:%S")

        # Make both timezone-naive (removes timezone info).
        start_time = start_time.replace(tzinfo=None)
        end_time = end_time.replace(tzinfo=None)

        laps_records = []

        if parsed_data["laps"]:
            for lap in parsed_data["laps"]:
                # Check if the lap's start time is within the session's start and end times
                if start_time <= lap["start_time"] <= end_time:
                    # Append the lap to the session's laps
                    laps_records.append(lap)

        # Initialize a parsed session dictionary
        parsed_session = {
            "session": session,
            "time_offset": parsed_data["time_offset"],
            "activity_name": parsed_data["activity_name"],
            "lat_lon_waypoints": [],
            "is_lat_lon_set": False,
            "ele_waypoints": [],
            "is_elevation_set": False,
            "hr_waypoints": [],
            "is_heart_rate_set": False,
            "cad_waypoints": [],
            "is_cadence_set": False,
            "power_waypoints": [],
            "is_power_set": False,
            "vel_waypoints": [],
            "pace_waypoints": [],
            "is_velocity_set": False,
            "laps": laps_records,
            "split_summary": parsed_data["split_summary"],
            "workout_steps": parsed_data["workout_steps"],
            "sets": parsed_data["sets"],
            "lengths": parsed_data["lengths"],
            "file_id": parsed_data["file_id"],
        }

        # Only parse arrays if the respective flag is set
        if is_lat_lon_set:
            activity_waypoints[i]["lat_lon_waypoints"] = [
                wp
                for wp in lat_lon_waypoints
                if start_time
                <= datetime.strptime(wp["time"], "%Y-%m-%dT%H:%M:%S")
                <= end_time
            ]
            # If there are waypoints, set the parsed session's waypoints and flag
            if activity_waypoints[i]["lat_lon_waypoints"]:
                parsed_session["lat_lon_waypoints"] = activity_waypoints[i][
                    "lat_lon_waypoints"
                ]
                parsed_session["is_lat_lon_set"] = True

                # If initial latitude and longitude are not set, set them to the first waypoint's coordinates
                if (
                    parsed_session["session"]["initial_latitude"] is None
                    or parsed_session["session"]["initial_longitude"] is None
                ):
                    # Set initial latitude and longitude to the first waypoint's coordinates
                    parsed_session["session"]["initial_latitude"] = activity_waypoints[
                        i
                    ]["lat_lon_waypoints"][0]["lat"]
                    parsed_session["session"]["initial_longitude"] = activity_waypoints[
                        i
                    ]["lat_lon_waypoints"][0]["lon"]

                # Use geocoding API to get city, town, and country based on coordinates
                location_data = activities_utils.location_based_on_coordinates(
                    session["initial_latitude"], session["initial_longitude"]
                )

                # Extract city, town, and country from location data
                if location_data:
                    parsed_session["session"]["city"] = location_data["city"]
                    parsed_session["session"]["town"] = location_data["town"]
                    parsed_session["session"]["country"] = location_data["country"]

        if is_elevation_set:
            activity_waypoints[i]["ele_waypoints"] = [
                wp
                for wp in ele_waypoints
                if start_time
                <= datetime.strptime(wp["time"], "%Y-%m-%dT%H:%M:%S")
                <= end_time
            ]
            # If there are waypoints, set the parsed session's waypoints and flag
            if activity_waypoints[i]["ele_waypoints"]:
                parsed_session["ele_waypoints"] = activity_waypoints[i]["ele_waypoints"]
                parsed_session["is_elevation_set"] = True
        if is_heart_rate_set:
            activity_waypoints[i]["hr_waypoints"] = [
                wp
                for wp in hr_waypoints
                if start_time
                <= datetime.strptime(wp["time"], "%Y-%m-%dT%H:%M:%S")
                <= end_time
            ]
            # If there are waypoints, set the parsed session's waypoints and flag
            if activity_waypoints[i]["hr_waypoints"]:
                parsed_session["hr_waypoints"] = activity_waypoints[i]["hr_waypoints"]
                parsed_session["is_heart_rate_set"] = True
        if is_cadence_set:
            activity_waypoints[i]["cad_waypoints"] = [
                wp
                for wp in cad_waypoints
                if start_time
                <= datetime.strptime(wp["time"], "%Y-%m-%dT%H:%M:%S")
                <= end_time
            ]
            # If there are waypoints, set the parsed session's waypoints and flag
            if activity_waypoints[i]["cad_waypoints"]:
                parsed_session["cad_waypoints"] = activity_waypoints[i]["cad_waypoints"]
                parsed_session["is_cadence_set"] = True
        if is_power_set:
            activity_waypoints[i]["power_waypoints"] = [
                wp
                for wp in power_waypoints
                if start_time
                <= datetime.strptime(wp["time"], "%Y-%m-%dT%H:%M:%S")
                <= end_time
            ]
            # If there are waypoints, set the parsed session's waypoints and flag
            if activity_waypoints[i]["power_waypoints"]:
                parsed_session["power_waypoints"] = activity_waypoints[i][
                    "power_waypoints"
                ]
                parsed_session["is_power_set"] = True
        if is_velocity_set:
            activity_waypoints[i]["vel_waypoints"] = [
                wp
                for wp in vel_waypoints
                if start_time
                <= datetime.strptime(wp["time"], "%Y-%m-%dT%H:%M:%S")
                <= end_time
            ]
            # If there are waypoints, set the parsed session's waypoints and flag
            if activity_waypoints[i]["vel_waypoints"]:
                parsed_session["vel_waypoints"] = activity_waypoints[i]["vel_waypoints"]
                parsed_session["is_velocity_set"] = True
            activity_waypoints[i]["pace_waypoints"] = [
                wp
                for wp in pace_waypoints
                if start_time
                <= datetime.strptime(wp["time"], "%Y-%m-%dT%H:%M:%S")
                <= end_time
            ]
            # If there are waypoints, set the parsed session's waypoints and flag
            if activity_waypoints[i]["pace_waypoints"]:
                parsed_session["pace_waypoints"] = activity_waypoints[i][
                    "pace_waypoints"
                ]
                parsed_session["is_velocity_set"] = True

        # Append the parsed session to the sessions list
        sessions_records.append(parsed_session)

    # Return dictionary with each activity's waypoints
    return sessions_records


def parse_fit_file(
    file: str, db: Session, activity_name_input: str | None = None
) -> dict:
    try:
        # Initialize default values for various variables
        sessions = []
        time_offset = 0
        last_waypoint_time = None
        activity_name = activity_name_input if activity_name_input else "Workout"

        # Arrays to store waypoint data
        lat_lon_waypoints = []
        ele_waypoints = []
        hr_waypoints = []
        cad_waypoints = []
        power_waypoints = []
        vel_waypoints = []
        pace_waypoints = []

        # Array to store laps
        laps = []

        # Array to store split waypoints
        splits = []

        # Array to store split summary info
        split_summary = []

        # Array to store sets
        sets = []

        # Array to store workout steps
        workout_steps = []

        # Array to store exercises titles
        exercises_titles = []

        # Array to store lengths
        lengths = []

        # Dictionary to store file ID data
        file_id = {}

        # Initialize variables to store previous latitude and longitude
        prev_latitude, prev_longitude = None, None

        # Initialize variables to store whether elevation, power, heart rate, cadence, and velocity are set
        is_lat_lon_set = False
        is_elevation_set = False
        is_power_set = False
        is_heart_rate_set = False
        is_cadence_set = False
        is_velocity_set = False

        # Open the FIT file
        with open(file, "rb") as fit_file:
            fit_data = fitdecode.FitReader(fit_file)

            # Iterate over FIT messages
            for frame in fit_data:
                if isinstance(frame, fitdecode.FitDataMessage):
                    if frame.name == "session":
                        # Initialize session data
                        city, town, country = None, None, None

                        # Extract session data
                        (
                            initial_latitude,
                            initial_longitude,
                            activity_type,
                            first_waypoint_time,
                            total_elapsed_time,
                            total_timer_time,
                            calories,
                            distance,
                            avg_hr,
                            max_hr,
                            avg_cadence,
                            max_cadence,
                            avg_power,
                            max_power,
                            ele_gain,
                            ele_loss,
                            np,
                            avg_speed,
                            max_speed,
                            workout_feeling,
                            workout_rpe,
                        ) = parse_frame_session(frame)

                        # If initial latitude and longitude are set, use them to get city, town, and country
                        if (
                            initial_latitude is not None
                            and initial_longitude is not None
                        ):
                            # Use geocoding API to get city, town, and country based on coordinates
                            location_data = (
                                activities_utils.location_based_on_coordinates(
                                    initial_latitude, initial_longitude
                                )
                            )

                            # Extract city, town, and country from location data
                            if location_data:
                                city = location_data["city"]
                                town = location_data["town"]
                                country = location_data["country"]

                        # Initialize the session dictionary with parsed data
                        session_data = {
                            "initial_latitude": initial_latitude,
                            "initial_longitude": initial_longitude,
                            "city": city,
                            "town": town,
                            "country": country,
                            "activity_type": activity_type,
                            "first_waypoint_time": first_waypoint_time,
                            "last_waypoint_time": first_waypoint_time
                            + timedelta(seconds=total_elapsed_time),
                            "total_elapsed_time": total_elapsed_time,
                            "total_timer_time": total_timer_time,
                            "calories": calories,
                            "distance": distance,
                            "avg_hr": avg_hr,
                            "max_hr": max_hr,
                            "avg_cadence": avg_cadence,
                            "max_cadence": max_cadence,
                            "avg_power": avg_power,
                            "max_power": max_power,
                            "ele_gain": ele_gain,
                            "ele_loss": ele_loss,
                            "np": np,
                            "avg_speed": avg_speed,
                            "max_speed": max_speed,
                            "workout_feeling": workout_feeling,
                            "workout_rpe": workout_rpe,
                        }

                        # Append the session data to the sessions list
                        sessions.append(session_data)

                    # unknown_147 Sensor Accessories

                    # Extract activity name
                    if frame.name == "workout":
                        activity_name = parse_frame_workout(frame)

                    # Extract lap data
                    if frame.name == "lap":
                        laps.append(parse_frame_lap(frame))

                    # Extract split data
                    if frame.name in {"split", "unknown_312"}:
                        split_data = parse_frame_split(frame)
                        split_keys = [
                            "split_type",
                            "total_elapsed_time",
                            "total_timer_time",
                            "total_distance",
                            "avg_speed",
                            "start_time",
                            "total_ascent",
                            "total_descent",
                            "start_position_lat",
                            "start_position_long",
                            "end_position_lat",
                            "end_position_long",
                            "max_speed",
                            "end_time",
                            "total_calories",
                            "start_elevation",
                        ]
                        splits.append(dict(zip(split_keys, split_data)))

                    # Extract split summary data
                    if frame.name in {"split_summary", "unknown_313"}:
                        split_summary_split_type, split_summary_total_timer_time = (
                            parse_frame_split_summary(frame)
                        )
                        split_summary.append(
                            {
                                "split_type": split_summary_split_type,
                                "total_timer_time": split_summary_total_timer_time,
                            }
                        )

                    # Extract set data
                    if frame.name == "set":
                        sets.append(parse_frame_set(frame))

                    # Extract workout step data
                    if frame.name == "workout_step":
                        workout_steps.append(parse_frame_workout_step(frame))

                    # Extract exercise title data
                    if frame.name == "exercise_title":
                        exercises_titles.append(parse_frame_exercise_title(frame))

                    # Extract waypoint data
                    if frame.name == "record":
                        # Extract values from record frame
                        (
                            latitude,
                            longitude,
                            elevation,
                            time,
                            heart_rate,
                            cadence,
                            power,
                        ) = parse_frame_record(frame)

                        # Check elevation
                        if elevation is not None:
                            is_elevation_set = True

                        # Check if heart rate, cadence, power are set
                        if heart_rate is not None:
                            is_heart_rate_set = True

                        if cadence is not None:
                            is_cadence_set = True

                        if power is not None:
                            is_power_set = True

                        instant_speed = None
                        # Calculate instant speed, pace, and update waypoint arrays
                        if (
                            latitude is not None
                            and prev_latitude is not None
                            and longitude is not None
                            and prev_longitude is not None
                        ):
                            instant_speed = activities_utils.calculate_instant_speed(
                                last_waypoint_time,
                                time,
                                latitude,
                                longitude,
                                prev_latitude,
                                prev_longitude,
                            )

                        # Calculate instance pace
                        instant_pace = None
                        if instant_speed:
                            instant_pace = 1 / instant_speed
                            is_velocity_set = True

                        timestamp = time.strftime("%Y-%m-%dT%H:%M:%S")

                        # Append waypoint data to respective arrays
                        if latitude is not None and longitude is not None:
                            lat_lon_waypoints.append(
                                {
                                    "time": timestamp,
                                    "lat": latitude,
                                    "lon": longitude,
                                }
                            )
                            is_lat_lon_set = True

                        activities_utils.append_if_not_none(
                            ele_waypoints, timestamp, elevation, "ele"
                        )
                        activities_utils.append_if_not_none(
                            hr_waypoints, timestamp, heart_rate, "hr"
                        )
                        activities_utils.append_if_not_none(
                            cad_waypoints, timestamp, cadence, "cad"
                        )
                        activities_utils.append_if_not_none(
                            power_waypoints, timestamp, power, "power"
                        )
                        activities_utils.append_if_not_none(
                            vel_waypoints, timestamp, instant_speed, "vel"
                        )
                        activities_utils.append_if_not_none(
                            pace_waypoints, timestamp, instant_pace, "pace"
                        )

                        # Update previous latitude, longitude, and last waypoint time
                        prev_latitude, prev_longitude, last_waypoint_time = (
                            latitude,
                            longitude,
                            time,
                        )

                    if frame.name == "device_settings":
                        time_offset = parse_frame_device_settings(frame)
                        time_offset = interpret_time_offset(time_offset)

                    if frame.name == "length":
                        lengths.append(parse_frame_length(frame))

                    if frame.name == "file_id":
                        file_id = parse_frame_file_id(frame)

        # Check if exercises titles is not none
        if exercises_titles:
            activity_exercise_titles_crud.create_activity_exercise_titles(
                exercises_titles, db
            )

        # Return parsed data as a dictionary
        return {
            "sessions": sessions,
            "time_offset": time_offset,
            "activity_name": activity_name,
            "is_elevation_set": is_elevation_set,
            "ele_waypoints": ele_waypoints,
            "is_power_set": is_power_set,
            "power_waypoints": power_waypoints,
            "is_heart_rate_set": is_heart_rate_set,
            "hr_waypoints": hr_waypoints,
            "is_velocity_set": is_velocity_set,
            "vel_waypoints": vel_waypoints,
            "pace_waypoints": pace_waypoints,
            "is_cadence_set": is_cadence_set,
            "cad_waypoints": cad_waypoints,
            "is_lat_lon_set": is_lat_lon_set,
            "lat_lon_waypoints": lat_lon_waypoints,
            "laps": laps,
            "splits": splits,
            "split_summary": split_summary,
            "sets": sets,
            "workout_steps": workout_steps,
            "lengths": lengths,
            "file_id": file_id,
        }
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(f"Error in parse_fit_file: {err}", "error", exc=err)
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Can't parse FIT file",
        ) from err


def parse_frame_session(frame):
    # Extracting coordinates
    initial_latitude, initial_longitude = convert_coordinates_to_degrees(
        get_value_from_frame(frame, "start_position_lat"),
        get_value_from_frame(frame, "start_position_long"),
    )

    # Activity type logic
    activity_type = get_value_from_frame(frame, "sport", "Workout")
    sub_sport = get_value_from_frame(frame, "sub_sport")
    if sub_sport and sub_sport != "generic":
        if activity_type == "cycling" and sub_sport == "virtual_activity":
            activity_type = "virtual_ride"
        elif activity_type == "cycling" and sub_sport == "commuting":
            activity_type = "commuting_ride"
        elif activity_type == "cycling" and sub_sport == "mixed_surface":
            activity_type = "mixed_surface_ride"
        elif (
            activity_type == "generic" and sub_sport == "breathing"
        ) or activity_type == 62:
            activity_type = "hiit"
        elif activity_type == 64 and sub_sport == 85:
            activity_type = "padel"
        else:
            activity_type = sub_sport

    # Extracting time values
    start_time = get_value_from_frame(frame, "start_time")
    total_elapsed_time = get_value_from_frame(frame, "total_elapsed_time")
    total_timer_time = get_value_from_frame(frame, "total_timer_time")

    # Extracting other values
    return (
        initial_latitude,
        initial_longitude,
        activity_type,
        start_time,
        total_elapsed_time,
        total_timer_time,
        get_value_from_frame(frame, "total_calories"),
        get_value_from_frame(frame, "total_distance"),
        get_value_from_frame(frame, "avg_heart_rate"),
        get_value_from_frame(frame, "max_heart_rate"),
        get_value_from_frame(frame, "avg_cadence"),
        get_value_from_frame(frame, "max_cadence"),
        get_value_from_frame(frame, "avg_power"),
        get_value_from_frame(frame, "max_power"),
        get_value_from_frame(frame, "total_ascent"),
        get_value_from_frame(frame, "total_descent"),
        get_value_from_frame(frame, "normalized_power"),
        get_value_from_frame(frame, "enhanced_avg_speed"),
        get_value_from_frame(frame, "enhanced_max_speed"),
        get_value_from_frame(frame, "workout_feel"),
        get_value_from_frame(frame, "workout_rpe"),
    )


def parse_frame_workout(frame):
    # Return the extracted name
    return get_value_from_frame(frame, "wkt_name", "Workout")


def parse_frame_record(frame):
    # Extracting data using the helper function
    latitude = get_value_from_frame(frame, "position_lat")
    longitude = get_value_from_frame(frame, "position_long")
    elevation = get_value_from_frame(frame, "enhanced_altitude")
    time = get_value_from_frame(frame, "timestamp")
    if time:
        time = time.replace(tzinfo=None)
    heart_rate = get_value_from_frame(frame, "heart_rate")
    cadence = get_value_from_frame(frame, "cadence")
    power = get_value_from_frame(frame, "power")

    latitude, longitude = convert_coordinates_to_degrees(latitude, longitude)

    # Return all extracted values
    return latitude, longitude, elevation, time, heart_rate, cadence, power


def parse_frame_lap(frame):
    keys = [
        "start_time",
        "start_position_lat",
        "start_position_long",
        "end_position_lat",
        "end_position_long",
        "total_elapsed_time",
        "total_timer_time",
        "total_distance",
        "total_cycles",
        "total_calories",
        "avg_heart_rate",
        "max_heart_rate",
        "avg_cadence",
        "max_cadence",
        "avg_power",
        "max_power",
        "total_ascent",
        "total_descent",
        "intensity",
        "lap_trigger",
        "sport",
        "sub_sport",
        "normalized_power",
        "total_work",
        "avg_vertical_oscillation",
        "avg_stance_time",
        "avg_fractional_cadence",
        "max_fractional_cadence",
        "enhanced_avg_speed",
        "enhanced_max_speed",
        "enhanced_min_altitude",
        "enhanced_max_altitude",
        "avg_vertical_ratio",
        "avg_step_length",
    ]

    lap_data = tuple(get_value_from_frame(frame, key) for key in keys)
    lap_dict = dict(zip(keys, lap_data))

    # Ensure start_time and end_time is timezone-naive
    if isinstance(lap_dict["start_time"], datetime):
        lap_dict["start_time"] = lap_dict["start_time"].replace(tzinfo=None)

    (
        lap_dict["start_position_lat"],
        lap_dict["start_position_long"],
    ) = convert_coordinates_to_degrees(
        lap_dict["start_position_lat"],
        lap_dict["start_position_long"],
    )
    lap_dict["end_position_lat"], lap_dict["end_position_long"] = (
        convert_coordinates_to_degrees(
            lap_dict["end_position_lat"],
            lap_dict["end_position_long"],
        )
    )

    if lap_dict["enhanced_avg_speed"]:
        lap_dict["enhanced_avg_pace"] = 1 / lap_dict["enhanced_avg_speed"]

    if lap_dict["enhanced_max_speed"]:
        lap_dict["enhanced_max_pace"] = 1 / lap_dict["enhanced_max_speed"]

    return lap_dict


def parse_frame_split(frame):
    # Define a list of keys and their default values
    keys_defaults = [
        ("split_type", 0),
        ("total_elapsed_time", 1),
        ("total_timer_time", 2),
        ("total_distance", 3),
        ("avg_speed", 4),
        ("start_time", 9),
        ("total_ascent", 13),
        ("total_descent", 14),
        ("start_position_lat", 21),
        ("start_position_long", 22),
        ("end_position_lat", 23),
        ("end_position_long", 24),
        ("max_speed", 25),
        ("end_time", 27),
        ("total_calories", 28),
        ("start_elevation", 74),
    ]

    # Extract values using the keys and defaults
    values = [
        get_value_from_frame(frame, key, get_value_from_frame(frame, default))
        for key, default in keys_defaults
    ]

    return tuple(values)


def parse_frame_split_summary(frame):
    # split type
    split_type = get_value_from_frame(frame, "split_type")
    if split_type is None:
        split_type = get_value_from_frame(frame, 0)
    # total working time
    total_timer_time = get_value_from_frame(frame, "total_timer_time")
    if total_timer_time is None:
        total_timer_time = get_value_from_frame(frame, 4)
        if total_timer_time is not None:
            total_timer_time = total_timer_time / 1000

    return split_type, total_timer_time


def parse_frame_set(frame):
    keys_value = [
        "duration",
        "repetitions",
        "weight",
        "set_type",
        "start_time",
    ]

    keys_raw = [
        "category",
        "category_subtype",
    ]

    set_data = [get_value_from_frame(frame, key) for key in keys_value]
    set_data.extend(get_raw_value_from_frame(frame, key) for key in keys_raw)

    # Adjust category based on category_subtype
    if set_data[5] is None:
        set_data[5] = 0 if set_data[6] is not None else None

    return list(set_data)


def parse_frame_workout_step(frame):
    keys_value = [
        "message_index",
        "duration_type",
        "duration_value",
        "target_type",
        "target_value",
        "intensity",
        "notes",
        "exercise_weight",
        "weight_display_unit",
    ]

    keys_raw = [
        "exercise_category",
        "exercise_name",
    ]

    workout_set_data = [get_value_from_frame(frame, key) for key in keys_value]
    workout_set_data.extend(get_raw_value_from_frame(frame, key) for key in keys_raw)

    secondary_target_value = None

    if workout_set_data[3] == "swim_stroke":
        if isinstance(workout_set_data[4], str):
            secondary_target_value = workout_set_data[4]
            workout_set_data[4] = None
        elif isinstance(workout_set_data[4], int) and workout_set_data[4] == 255:
            secondary_target_value = "any stroke"
            workout_set_data[4] = None

    if workout_set_data[5] == 7:
        workout_set_data[5] = "active"

    if workout_set_data[9] is None:
        workout_set_data[9] = 0 if workout_set_data[10] is not None else None

    return activity_workout_steps_schema.ActivityWorkoutSteps(
        message_index=workout_set_data[0] if workout_set_data[0] else 0,
        duration_type=workout_set_data[1],
        duration_value=workout_set_data[2],
        target_type=workout_set_data[3],
        target_value=workout_set_data[4] if workout_set_data[4] else None,
        intensity=workout_set_data[5] if type(workout_set_data[5]) == str else None,
        notes=workout_set_data[6],
        exercise_category=workout_set_data[9],
        exercise_name=workout_set_data[10] if workout_set_data[10] else None,
        exercise_weight=workout_set_data[7],
        weight_display_unit=workout_set_data[8],
        secondary_target_value=secondary_target_value,
    )


def parse_frame_exercise_title(frame):
    keys_value = [
        "wkt_step_name",
    ]

    keys_raw = [
        "exercise_category",
        "exercise_name",
    ]

    exercise_title_data = [get_value_from_frame(frame, key) for key in keys_value]
    exercise_title_data.extend(get_raw_value_from_frame(frame, key) for key in keys_raw)

    return activity_exercise_titles_schema.ActivityExerciseTitles(
        exercise_category=exercise_title_data[1] if exercise_title_data[1] else 0,
        exercise_name=exercise_title_data[2] if exercise_title_data[2] else 0,
        wkt_step_name=str(exercise_title_data[0]),
    )


def parse_frame_device_settings(frame):
    return get_value_from_frame(frame, "time_offset")


def parse_frame_length(frame):
    return {
        "message_index": get_value_from_frame(frame, "message_index"),
        "start_time": get_value_from_frame(frame, "start_time"),
        "total_elapsed_time": get_value_from_frame(frame, "total_elapsed_time"),
        "total_timer_time": get_value_from_frame(frame, "total_timer_time"),
        "total_strokes": get_value_from_frame(frame, "total_strokes"),
        "avg_speed": get_value_from_frame(frame, "avg_speed"),
        "swim_stroke": get_value_from_frame(frame, "swim_stroke"),
        "avg_swimming_cadence": get_value_from_frame(frame, "avg_swimming_cadence"),
        "length_type": get_value_from_frame(frame, "length_type"),
    }


def parse_frame_file_id(frame):
    return {
        "type": get_value_from_frame(frame, "type"),
        "manufacturer": get_value_from_frame(frame, "manufacturer"),
        "product": get_value_from_frame(frame, "product"),
        "serial_number": get_value_from_frame(frame, "serial_number"),
        "time_created": get_value_from_frame(frame, "time_created"),
    }


def interpret_time_offset(raw_offset):
    # Check for two's complement representation (values > 2^31)
    if raw_offset != 0 and raw_offset is not None:
        if raw_offset > 2**31 - 1:
            return raw_offset - 2**32
    return raw_offset


def get_value_from_frame(frame, key, default=None):
    try:
        value = frame.get_value(key)
        return value if value else default
    except KeyError:
        return default


def get_raw_value_from_frame(frame, key, default=None):
    try:
        raw_value = frame.get_raw_value(key)
        return raw_value if raw_value else default
    except KeyError:
        return default


def convert_coordinates_to_degrees(latitude, longitude):
    # Convert FIT coordinates to degrees if available
    if latitude is not None and longitude is not None:
        latitude = latitude * (180 / 2**31)
        longitude = longitude * (180 / 2**31)

    return latitude, longitude


def append_if_not_none(waypoint_list, time, value, key):
    if value is not None:
        waypoint_list.append({"time": time, key: value})


def calculate_pace(distance, total_timer_time, activity_type, split_summary, lengths):
    if distance:
        if activity_type != "lap_swimming" or (
            activity_type == "lap_swimming" and not split_summary and not lengths
        ):
            return total_timer_time, total_timer_time / distance
        if activity_type == "lap_swimming" and lengths:
            # Swimming pace calculation based on lengths
            time_active = 0
            for length in lengths:
                if length["length_type"] == "active":
                    time_active += length["total_timer_time"]

            return time_active, time_active / distance
        # Swimming pace calculation based on split summary
        time_active = 0
        for split in split_summary:
            if split["split_type"] != 4:
                time_active += split["total_timer_time"]

        return time_active, time_active / distance
    return total_timer_time, 0


def find_timezone_name(offset_seconds, reference_date):
    for tz_name in available_timezones():
        tz = ZoneInfo(tz_name)
        if reference_date.utcoffset() is None:  # Skip invalid timezones
            continue

        # Get the UTC offset for the reference date
        utc_offset = reference_date.astimezone(tz).utcoffset()

        if utc_offset.total_seconds() == offset_seconds:
            return tz_name
