import os
import fitdecode

from enum import Enum
from datetime import datetime
from timezonefinder import TimezoneFinder
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

import activities.crud as activities_crud
import activities.utils as activities_utils

import activity_exercise_titles.schema as activity_exercise_titles_schema

import activity_streams.crud as activity_streams_crud

import activity_workout_steps.schema as activity_workout_steps_schema

import migrations.crud as migrations_crud

import health_data.crud as health_data_crud

import core.logger as core_logger

import fit.utils as fit_utils


class StreamType(Enum):
    HEART_RATE = 1
    POWER = 2
    CADENCE = 3
    ELEVATION = 4
    SPEED = 5
    PACE = 6
    LATLONG = 7


def check_migrations_not_executed(db: Session):
    migrations_not_executed = migrations_crud.get_migrations_not_executed(db)

    if migrations_not_executed:
        for migration in migrations_not_executed:
            # Log the migration not executed
            core_logger.print_to_log(
                f"Migration not executed: {migration.name} - Migration will be executed"
            )

            if migration.id == 1:
                # Execute the migration
                process_migration_1(db)

            if migration.id == 2:
                # Execute the migration
                process_migration_2(db)

            if migration.id == 3:
                # Execute the migration
                process_migration_3(db)


def process_migration_1(db: Session):
    core_logger.print_to_log("Started migration 1")

    activities_processed_with_no_errors = True

    try:
        activities = activities_crud.get_all_activities(db)
    except Exception as err:
        core_logger.print_to_log(
            f"Migration 1 - Error fetching activities: {err}", "error", exc=err
        )
        return

    if activities:
        for activity in activities:
            try:
                # Ensure start_time and end_time are datetime objects
                if isinstance(activity.start_time, str):
                    activity.start_time = datetime.strptime(
                        activity.start_time, "%Y-%m-%d %H:%M:%S"
                    )
                if isinstance(activity.end_time, str):
                    activity.end_time = datetime.strptime(
                        activity.end_time, "%Y-%m-%d %H:%M:%S"
                    )

                # Initialize additional fields
                metrics = {
                    "avg_hr": None,
                    "max_hr": None,
                    "avg_power": None,
                    "max_power": None,
                    "np": None,
                    "avg_cadence": None,
                    "max_cadence": None,
                    "avg_speed": None,
                    "max_speed": None,
                }

                # Get activity streams
                try:
                    activity_streams = activity_streams_crud.get_activity_streams(
                        activity.id, db
                    )
                except Exception as err:
                    core_logger.print_to_log(
                        f"Migration 1 - Failed to fetch streams for activity {activity.id}: {err}",
                        "warning",
                        exc=err,
                    )
                    activities_processed_with_no_errors = False
                    continue

                # Map stream processing functions
                stream_processing = {
                    StreamType.HEART_RATE: ("avg_hr", "max_hr", "hr"),
                    StreamType.POWER: ("avg_power", "max_power", "power", "np"),
                    StreamType.CADENCE: ("avg_cadence", "max_cadence", "cad"),
                    StreamType.ELEVATION: None,
                    StreamType.SPEED: ("avg_speed", "max_speed", "vel"),
                    StreamType.PACE: None,
                    StreamType.LATLONG: None,
                }

                for stream in activity_streams:
                    stream_type = StreamType(stream.stream_type)
                    if (
                        stream_type in stream_processing
                        and stream_processing[stream_type] is not None
                    ):
                        attr_avg, attr_max, stream_key = stream_processing[stream_type][
                            :3
                        ]
                        metrics[attr_avg], metrics[attr_max] = (
                            activities_utils.calculate_avg_and_max(
                                stream.stream_waypoints, stream_key
                            )
                        )
                        # Special handling for normalized power
                        if stream_type == StreamType.POWER:
                            metrics["np"] = activities_utils.calculate_np(
                                stream.stream_waypoints
                            )

                # Calculate elapsed time once
                elapsed_time_seconds = (
                    activity.end_time - activity.start_time
                ).total_seconds()

                # Set fields on the activity object
                activity.total_elapsed_time = elapsed_time_seconds
                activity.total_timer_time = elapsed_time_seconds
                activity.max_speed = metrics["max_speed"]
                activity.max_power = metrics["max_power"]
                activity.normalized_power = metrics["np"]
                activity.average_hr = metrics["avg_hr"]
                activity.max_hr = metrics["max_hr"]
                activity.average_cad = metrics["avg_cadence"]
                activity.max_cad = metrics["max_cadence"]

                # Update the activity in the database
                activities_crud.edit_activity(activity.user_id, activity, db)
                core_logger.print_to_log(
                    f"Migration 1 - Processed activity: {activity.id} - {activity.name}"
                )
            except Exception as err:
                activities_processed_with_no_errors = False
                core_logger.print_to_log(
                    f"Migration 1 - Failed to process activity {activity.id}: {err}",
                    "error",
                    exc=err,
                )

    # Mark migration as executed
    if activities_processed_with_no_errors:
        try:
            migrations_crud.set_migration_as_executed(1, db)
        except Exception as err:
            core_logger.print_to_log(
                f"Migration 1 - Failed to set migration as executed: {err}",
                "error",
                exc=err,
            )
            return
    else:
        core_logger.print_to_log(
            "Migration 1 failed to process all activities. Will try again later.",
            "error",
        )

    core_logger.print_to_log("Finished migration 1")


def process_migration_2(db: Session):
    core_logger.print_to_log("Started migration 2")

    # Create an instance of TimezoneFinder
    tf = TimezoneFinder()

    # Initialize flag to track if all activities and health_data were processed without errors
    activities_processed_with_no_errors = True
    health_data_processed_with_no_errors = True

    # Fetch all activities and health_data
    try:
        activities = activities_crud.get_all_activities(db)
        health_data = health_data_crud.get_all_health_data(db)
    except Exception as err:
        core_logger.print_to_log(
            f"Migration 2 - Error fetching activities and/or health_data: {err}",
            "error",
            exc=err,
        )
        return

    if activities:
        # Process each activity and add timezone
        for activity in activities:
            try:
                # Skip if activity already has timezone
                if activity.timezone:
                    core_logger.print_to_log(
                        f"Migration 2 - {activity.id} already has timezone defined. Skipping.",
                        "info",
                    )
                    continue

                timezone = os.environ.get("TZ")

                # Get activity stream
                try:
                    activity_stream_coord = (
                        activity_streams_crud.get_activity_stream_by_type(
                            activity.id, 7, db
                        )
                    )
                except Exception as err:
                    core_logger.print_to_log(
                        f"Migration 2 - Failed to fetch streams for activity {activity.id}: {err}",
                        "warning",
                        exc=err,
                    )
                    activities_processed_with_no_errors = False
                    continue

                if activity_stream_coord:
                    timezone = tf.timezone_at(
                        lat=activity_stream_coord.stream_waypoints[0]["lat"],
                        lng=activity_stream_coord.stream_waypoints[0]["lon"],
                    )

                activity.timezone = timezone

                # Update the activity in the database
                activities_crud.edit_activity(activity.user_id, activity, db)

                core_logger.print_to_log(
                    f"Migration 2 - Processed activity: {activity.id} - {activity.name}"
                )

            except Exception as err:
                activities_processed_with_no_errors = False
                core_logger.print_to_log(
                    f"Migration 2 - Failed to process activity {activity.id}: {err}",
                    "error",
                    exc=err,
                )

    if health_data:
        # Process each weight and add timezone
        for data in health_data:
            try:
                # Skip if weight already has timezone
                if data.bmi:
                    core_logger.print_to_log(
                        f"Migration 2 - {data.id} already has BMI defined. Skipping.",
                        "info",
                    )
                    continue

                # Update the weight in the database
                health_data_crud.edit_health_data(data.user_id, data, db)

                core_logger.print_to_log(f"Migration 2 - Processed BMI: {data.id}")

            except Exception as err:
                health_data_processed_with_no_errors = False
                core_logger.print_to_log(
                    f"Migration 2 - Failed to process BMI {data.id}: {err}",
                    "error",
                    exc=err,
                )

    # Mark migration as executed
    if activities_processed_with_no_errors and health_data_processed_with_no_errors:
        try:
            migrations_crud.set_migration_as_executed(2, db)
        except Exception as err:
            core_logger.print_to_log(
                f"Migration 2 - Failed to set migration as executed: {err}",
                "error",
                exc=err,
            )
            return
    else:
        core_logger.print_to_log(
            "Migration 2 failed to process all activities. Will try again later.",
            "error",
        )

    core_logger.print_to_log("Finished migration 2")


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
                print(activity.id)
                # check if activity file exists
                activity_fit_file_path = os.path.join(
                    "files/processed", f"{activity.id}.fit"
                )
                activity_gpx_file_path = os.path.join(
                    "files/processed", f"{activity.id}.gpx"
                )
                if not os.path.exists(activity_fit_file_path) and not os.path.exists(
                    activity_gpx_file_path
                ):
                    core_logger.print_to_log(
                        f"Migration 3 - Activity {activity.id} does not have a file. Skipping.",
                        "info",
                    )
                    continue
                else:
                    # Array to store laps
                    laps = []

                    # Array to store workout steps
                    workout_steps = []

                    # Array to store exercise titles
                    exercises_titles = []

                    if os.path.exists(activity_fit_file_path):
                        print(f"Migration 3 - Activity {activity.id} has a fit file.")
                        try:
                            # Open the FIT file
                            with open(activity_fit_file_path, "rb") as fit_file:
                                fit_data = fitdecode.FitReader(fit_file)

                                # Iterate over FIT messages
                                for frame in fit_data:
                                    if isinstance(frame, fitdecode.FitDataMessage):
                                        # Parse lap data
                                        if frame.name == "lap":
                                            lap_data = fit_utils.parse_frame_lap(frame)
                                            lap_keys = [
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
                                            lap_dict = dict(zip(lap_keys, lap_data))

                                            # Ensure start_time and end_time is timezone-naive
                                            if isinstance(
                                                lap_dict["start_time"], datetime
                                            ):
                                                lap_dict["start_time"] = lap_dict[
                                                    "start_time"
                                                ].replace(tzinfo=None)

                                            (
                                                lap_dict["start_position_lat"],
                                                lap_dict["start_position_long"],
                                            ) = fit_utils.convert_coordinates_to_degrees(
                                                lap_dict["start_position_lat"],
                                                lap_dict["start_position_long"],
                                            )
                                            (
                                                lap_dict["end_position_lat"],
                                                lap_dict["end_position_long"],
                                            ) = fit_utils.convert_coordinates_to_degrees(
                                                lap_dict["end_position_lat"],
                                                lap_dict["end_position_long"],
                                            )

                                            if lap_dict["enhanced_avg_speed"]:
                                                lap_dict["enhanced_avg_pace"] = (
                                                    1 / lap_dict["enhanced_avg_speed"]
                                                )

                                            if lap_dict["enhanced_max_speed"]:
                                                lap_dict["enhanced_max_pace"] = (
                                                    1 / lap_dict["enhanced_max_speed"]
                                                )

                                            laps.append(lap_dict)

                                        # Extract workout step data
                                        if frame.name == "workout_step":
                                            set_data = fit_utils.parse_frame_workout_step(frame)
                                            set_data = list(set_data)
                                            if set_data[4] == 7:
                                                set_data[4] = "active"
                                            workout_steps.append(
                                                activity_workout_steps_schema.ActivityWorkoutSteps(
                                                    message_index=set_data[0] if set_data[0] else 0,
                                                    duration_type=set_data[1],
                                                    duration_value=set_data[2],
                                                    target_type=set_data[3],
                                                    intensity=set_data[4] if type(set_data[4]) == str else "",
                                                    notes=set_data[5],
                                                    exercise_name=set_data[6],
                                                    exercise_weight=set_data[7],
                                                    weight_display_unit=set_data[8],
                                                )
                                            )


                                        # Extract exercise title data
                                        if frame.name == "exercise_title":
                                            set_data = fit_utils.parse_frame_exercise_title(frame)
                                            exercises_titles.append(
                                                activity_exercise_titles_schema.ActivityExerciseTitles(
                                                    exercise_category=str(set_data[0]),
                                                    exercise_name=set_data[1],
                                                    wkt_step_name=str(set_data[2]),
                                                )
                                            )
                        except Exception as err:
                            activities_processed_with_no_errors = False
                            core_logger.print_to_log(
                                f"Migration 3 - Failed to process activity {activity.id} file: {err}",
                                "error",
                                exc=err,
                            )
                    else:
                        print(f"Migration 3 - Activity {activity.id} has a gpx file.")

                    
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
            # migrations_crud.set_migration_as_executed(3, db)
            print("Skipped migration 3")
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
