import os
import fitdecode
import zipfile

from sqlalchemy.orm import Session

import activities.crud as activities_crud
import activities.utils as activities_utils
import activities.schema as activities_schema

import activity_streams.crud as activity_streams_crud

import activity_exercise_titles.crud as activity_exercise_titles_crud

import activity_laps.crud as activity_laps_crud

import activity_sets.crud as activity_sets_crud

import activity_streams.crud as activity_streams_crud

import activity_workout_steps.crud as activity_workout_steps_crud

import garmin.activity_utils as garmin_activity_utils

import migrations.crud as migrations_crud
from migrations.schema import StreamType

import strava.utils as strava_utils
import strava.activity_utils as strava_activity_utils

import core.logger as core_logger

import fit.utils as fit_utils
import gpx.utils as gpx_utils


def process_migration_3(db: Session):
    core_logger.print_to_log("Started migration 3")

    activities_processed_with_no_errors = True

    try:
        activities = activities_crud.get_all_activities(db)
    except Exception as err:
        core_logger.print_to_log(
            f"Migration 3 - Error fetching activities: {err}", "error", exc=err
        )
        return

    if activities:
        for activity in activities:
            try:
                if activity.strava_activity_id is None:
                    # check if activity file exists
                    activity_fit_file_path = os.path.join(
                        "files/processed", f"{activity.id}.fit"
                    )
                    activity_gpx_file_path = os.path.join(
                        "files/processed", f"{activity.id}.gpx"
                    )

                    if (
                        not os.path.exists(activity_fit_file_path)
                        and activity.garminconnect_activity_id is not None
                    ):
                        activity_fit_file_path = get_fit_file_from_garminconnect(
                            activity, db
                        )

                    # if .gpx and .fit for activity do not exist, skip
                    if not os.path.exists(
                        activity_fit_file_path
                    ) and not os.path.exists(activity_gpx_file_path):
                        core_logger.print_to_log(
                            f"Migration 3 - Activity {activity.id} does not have a file. Will process it using activity streams.",
                            "info",
                        )
                        # Process the activity using streams
                        process_activity_using_streams(
                            activity,
                            db,
                        )
                    # if exists, process it
                    else:
                        if os.path.exists(activity_fit_file_path):
                            # Process the .fit file
                            process_fit_file(
                                activity,
                                activity_fit_file_path,
                                db,
                            )
                        else:
                            # Process the .gpx activity
                            process_activity_using_streams(
                                activity,
                                db,
                            )
                else:
                    if process_strava_activity(activity, db) is False:
                        continue
            except Exception as err:
                activities_processed_with_no_errors = False
                core_logger.print_to_log(
                    f"Migration 3 - Failed to process activity {activity.id}: {err}",
                    "error",
                    exc=err,
                )

    # Mark migration as executed
    if activities_processed_with_no_errors:
        try:
            migrations_crud.set_migration_as_executed(3, db)
        except Exception as err:
            core_logger.print_to_log(
                f"Migration 3 - Failed to set migration as executed: {err}",
                "error",
                exc=err,
            )
            return
    else:
        core_logger.print_to_log(
            "Migration 3 failed to process all activities. Will try again later.",
            "error",
        )

    core_logger.print_to_log("Finished migration 3")


def get_fit_file_from_garminconnect(activity: activities_schema.Activity, db: Session):
    # Log getting file from Garmin Connect
    core_logger.print_to_log(
        f"Migration 3 - Activity {activity.id} does not have a file, but it is a Garmin Connect activity. Will retrieve file from Garmin.",
        "info",
    )

    # Get the user Garmin Connect client
    garminconnect_client = garmin_activity_utils.get_user_garminconnect_client(
        activity.user_id, db
    )

    # Download the activity in original format (.zip file)
    zip_data = garminconnect_client.download_activity(
        activity.garminconnect_activity_id,
        dl_fmt=garminconnect_client.ActivityDownloadFormat.ORIGINAL,
    )

    # Save the zip file
    output_file = f"files/{str(activity.garminconnect_activity_id)}.zip"

    # Write the ZIP data to the output file
    with open(output_file, "wb") as fb:
        fb.write(zip_data)

    # Array to store the names of extracted files
    extracted_files = []

    # Open the ZIP file
    with zipfile.ZipFile(output_file, "r") as zip_ref:
        # Extract all contents to the specified directory
        zip_ref.extractall("files")
        # Populate the array with file names
        extracted_files = zip_ref.namelist()

    # Remove the zip file
    try:
        os.remove(output_file)
    except OSError as err:
        core_logger.print_to_log(
            f"Error removing file {output_file}: {err}",
            "error",
            exc=err,
        )

    try:
        # Define the directory where the processed files will be stored
        processed_dir = "files/processed"

        for file in extracted_files:
            _, file_extension = os.path.splitext(f"files/{file}")

            # Define new file path with activity ID as filename
            new_file_name = f"{activity.id}{file_extension}"

            # Move the file to the processed directory
            activities_utils.move_file(processed_dir, new_file_name, f"files/{file}")
    except Exception as err:
        core_logger.print_to_log(
            f"Migration 3 - Failed to move activity {activity.id} file: {err}",
            "error",
            exc=err,
        )

    # check if activity file exists
    return os.path.join("files/processed", f"{activity.id}.fit")


def process_fit_file(
    activity: activities_schema.Activity, activity_fit_file_path: str, db: Session
):
    # Array to store laps
    laps = []

    # Array to store workout steps
    workout_steps = []

    # Array to store exercise titles
    exercises_titles = []

    # Array to store sets
    sets = []

    core_logger.print_to_log(
        f"Migration 3 - Activity {activity.id} has a fit file. Will process it."
    )
    try:
        # Open the FIT file
        with open(activity_fit_file_path, "rb") as fit_file:
            fit_data = fitdecode.FitReader(fit_file)

            # Iterate over FIT messages
            for frame in fit_data:
                if isinstance(frame, fitdecode.FitDataMessage):
                    # Parse lap data
                    if frame.name == "lap":
                        laps.append(fit_utils.parse_frame_lap(frame))

                    # Extract workout step data
                    if frame.name == "workout_step":
                        workout_steps.append(fit_utils.parse_frame_workout_step(frame))

                    # Extract exercise title data
                    if frame.name == "exercise_title":
                        exercises_titles.append(
                            fit_utils.parse_frame_exercise_title(frame)
                        )

                    # Extract set data
                    if frame.name == "set":
                        sets.append(fit_utils.parse_frame_set(frame))
        # Store data in the database
        store_data_in_db(
            activity,
            laps,
            workout_steps,
            exercises_titles,
            sets,
            db,
        )
    except Exception as err:
        core_logger.print_to_log(
            f"Migration 3 - Failed to process activity {activity.id} file: {err}",
            "error",
            exc=err,
        )
        raise err


def process_activity_using_streams(activity: activities_schema.Activity, db: Session):
    core_logger.print_to_log(
        f"Migration 3 - Activity {activity.id} has a gpx file. Will process it."
    )

    try:
        streams = activity_streams_crud.get_activity_streams(activity.id, db)
        stream_map = {stream.stream_type: stream.stream_waypoints for stream in streams}

        laps = gpx_utils.generate_activity_laps(
            stream_map.get(StreamType.LATLONG.value) if stream_map.get(StreamType.LATLONG.value) else [],
            stream_map.get(StreamType.ELEVATION.value) if stream_map.get(StreamType.ELEVATION.value) else [],
            stream_map.get(StreamType.POWER.value) if stream_map.get(StreamType.POWER.value) else [],
            stream_map.get(StreamType.HEART_RATE.value) if stream_map.get(StreamType.HEART_RATE.value) else [],
            stream_map.get(StreamType.CADENCE.value) if stream_map.get(StreamType.CADENCE.value) else [],
            stream_map.get(StreamType.SPEED.value) if stream_map.get(StreamType.SPEED.value) else [],
        )

        store_data_in_db(activity, laps, [], [], [], db)
    except Exception as err:
        core_logger.print_to_log(
            f"Migration 3 - Failed to process activity {activity.id} file: {err}",
            "error",
            exc=err,
        )
        raise


def process_strava_activity(activity: activities_schema.Activity, db: Session):
    # Get the user integrations by user ID
    user_integrations = strava_utils.fetch_user_integrations_and_validate_token(
        activity.user_id, db
    )

    if user_integrations is None:
        core_logger.print_to_log(
            f"Migration 3 - User {activity.user_id} does not have a Strava account linked. Skipping.",
            "info",
        )
        # Skip the activity if the user does not have a Strava account linked
        return False

    activity_streams = activity_streams_crud.get_activity_streams(activity.user_id, db)

    # Create a dictionary from stream_type to waypoints
    stream_map = {
        stream.stream_type: stream.stream_waypoints for stream in activity_streams
    }

    # Create flags for which streams are available
    is_heart_rate_set = StreamType.HEART_RATE in stream_map
    is_power_set = StreamType.POWER in stream_map
    is_cadence_set = StreamType.CADENCE in stream_map
    is_elevation_set = StreamType.ELEVATION in stream_map
    is_velocity_set = StreamType.SPEED in stream_map
    is_pace_set = StreamType.PACE in stream_map
    is_lat_lon_set = (
        StreamType.LATLONG in stream_map
    )  # Or: detailedActivity.start_latlng is not None

    # Extract waypoints (empty list if not set)
    hr_waypoints = stream_map.get(StreamType.HEART_RATE, [])
    power_waypoints = stream_map.get(StreamType.POWER, [])
    cad_waypoints = stream_map.get(StreamType.CADENCE, [])
    ele_waypoints = stream_map.get(StreamType.ELEVATION, [])
    vel_waypoints = stream_map.get(StreamType.SPEED, [])
    pace_waypoints = stream_map.get(StreamType.PACE, [])
    lat_lon_waypoints = stream_map.get(StreamType.LATLONG, [])

    # Assemble final stream data list
    stream_data = [
        (is_heart_rate_set, StreamType.HEART_RATE, hr_waypoints),
        (is_power_set, StreamType.POWER, power_waypoints),
        (is_cadence_set, StreamType.CADENCE, cad_waypoints),
        (is_elevation_set, StreamType.ELEVATION, ele_waypoints),
        (is_velocity_set, StreamType.SPEED, vel_waypoints),
        (is_pace_set, StreamType.PACE, pace_waypoints),
        (is_lat_lon_set, StreamType.LATLONG, lat_lon_waypoints),
    ]

    # Create a Strava client with the user's access token
    strava_client = strava_utils.create_strava_client(user_integrations)

    # Get laps from Strava
    laps = strava_activity_utils.fetch_and_process_activity_laps(
        strava_client,
        activity.strava_activity_id,
        activity.user_id,
        stream_data,
    )

    # Create activity laps in the database
    activity_laps_crud.create_activity_laps(laps, activity.id, db)

    core_logger.print_to_log(
        f"Migration 3 - Strava activity {activity.id} file processed."
    )

    # Return true if the activity was processed successfully
    return True


def store_data_in_db(
    activity: activities_schema.Activity,
    laps: list,
    workout_steps: list,
    exercises_titles: list,
    sets: list,
    db: Session,
):
    # Create activity laps in the database
    if laps:
        activity_laps_crud.create_activity_laps(laps, activity.id, db)

    # Create activity workout steps in the database
    if workout_steps:
        activity_workout_steps_crud.create_activity_workout_steps(
            workout_steps, activity.id, db
        )

    # Create activity exercise titles in the database
    if exercises_titles:
        activity_exercise_titles_crud.create_activity_exercise_titles(
            exercises_titles, db
        )

    # Create activity sets in the database
    if sets:
        activity_sets_crud.create_activity_sets(sets, activity.id, db)

    core_logger.print_to_log(f"Migration 3 - Activity {activity.id} processed.")
