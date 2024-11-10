import logging

from enum import Enum
from datetime import datetime

from sqlalchemy.orm import Session

import activities.crud as activities_crud
import activities.utils as activities_utils

import activity_streams.crud as activity_streams_crud

import migrations.crud as migrations_crud

# Define a loggger created on main.py
mainLogger = logging.getLogger("myLogger")

# Create loggger
logger = logging.getLogger("migration_logger")
logger.setLevel(logging.DEBUG)

file_handler = logging.FileHandler("logs/migrations.log")
file_handler.setLevel(logging.DEBUG)

formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
file_handler.setFormatter(formatter)

logger.addHandler(file_handler)


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
            logger.info(
                f"Migration not executed: {migration.name} - Migration will be executed"
            )

            if migration.id == 1:
                # Execute the migration
                process_migration_1(db)


def process_migration_1(db: Session):
    logger.info("Started migration 1")

    activities_processed_with_no_errors = True

    try:
        activities = activities_crud.get_all_activities(db)
    except Exception as e:
        logger.error(f"Error fetching activities: {e}")
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
                    logger.warning(
                        f"Failed to fetch streams for activity {activity.id}: {err}",
                        exc_info=True,
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
                        attr_avg, attr_max, stream_key = stream_processing[stream_type][:3]
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
                logger.info(f"Processed activity: {activity.id} - {activity.name}")

            except Exception as err:
                activities_processed_with_no_errors = False
                print(
                    f"Failed to process activity {activity.id}. Please check migrations log for more details."
                )
                mainLogger.error(
                    f"Failed to process activity {activity.id}. Please check migrations log for more details."
                )
                logger.error(
                    f"Failed to process activity {activity.id}: {err}", exc_info=True
                )

    # Mark migration as executed
    if activities_processed_with_no_errors:
        try:
            migrations_crud.set_migration_as_executed(1, db)
        except Exception as err:
            logger.error(f"Failed to set migration as executed: {err}", exc_info=True)
            return
    else:
        logger.error(
            "Migration 1 failed to process all activities. Will try again later."
        )

    logger.info("Finished migration 1")
