"""Migration 1: compute elapsed time, HR, power, cadence, speed."""

from datetime import datetime

from sqlalchemy.orm import Session

import core.logger as core_logger
import migrations.crud as migrations_crud
import modules.activities.activity.crud as activities_crud
import modules.activities.activity_file_import.computation as activities_computation
import modules.activities.activity_streams.constants as activity_streams_constants
import modules.activities.activity_streams.crud as activity_streams_crud

logger = core_logger.get_logger(__name__)


def _optional_float_to_int(value: float | None) -> int | None:
    """Convert optional float metrics to optional integers for int-typed model fields."""
    if value is None:
        return None
    return round(value)


def process_migration_1(db: Session) -> None:
    """
    Run migration 1: populate elapsed time and stream metrics.

    Args:
        db: The SQLAlchemy database session.

    Returns:
        None

    Raises:
        Exception: Logs errors per-activity; does not re-raise.
    """
    logger.info("Started migration 1", extra=core_logger.context(console=True))

    activities_processed_with_no_errors = True

    try:
        activities = activities_crud.get_all_activities(db)
    except Exception as err:
        logger.error(
            f"Migration 1 - Error fetching activities: {err}", exc_info=err, extra=core_logger.context(console=True)
        )
        return

    if activities:
        for activity in activities:
            if not activity.user_id or not activity.id or not activity.start_time or not activity.end_time:
                logger.warning(
                    f"Migration 1 - Skipping activity with missing user_id, id, start_time, or end_time: {activity}",
                    extra=core_logger.context(console=True),
                )
                continue
            try:
                # Ensure start_time and end_time are datetime objects
                if isinstance(activity.start_time, str):
                    activity.start_time = datetime.strptime(activity.start_time, "%Y-%m-%d %H:%M:%S")
                if isinstance(activity.end_time, str):
                    activity.end_time = datetime.strptime(activity.end_time, "%Y-%m-%d %H:%M:%S")

                # Initialize additional fields
                metrics: dict[str, float | None] = {
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
                    activity_streams = activity_streams_crud.get_activity_streams(activity.id, db)
                except Exception as err:
                    logger.warning(
                        f"Migration 1 - Failed to fetch streams for activity {activity.id}: {err}",
                        exc_info=err,
                        extra=core_logger.context(console=True),
                    )
                    activities_processed_with_no_errors = False
                    continue

                if not activity_streams:
                    logger.info(
                        f"Migration 1 - No streams found for activity {activity.id}. Skipping stream processing.",
                        extra=core_logger.context(console=True),
                    )
                    continue

                # Map stream processing functions
                stream_processing = {
                    activity_streams_constants.STREAM_TYPE_HR: ("avg_hr", "max_hr", "hr"),
                    activity_streams_constants.STREAM_TYPE_POWER: ("avg_power", "max_power", "power", "np"),
                    activity_streams_constants.STREAM_TYPE_CADENCE: ("avg_cadence", "max_cadence", "cad"),
                    activity_streams_constants.STREAM_TYPE_ELEVATION: None,
                    activity_streams_constants.STREAM_TYPE_SPEED: ("avg_speed", "max_speed", "vel"),
                    activity_streams_constants.STREAM_TYPE_PACE: None,
                    activity_streams_constants.STREAM_TYPE_MAP: None,
                }

                for stream in activity_streams:
                    stream_type = stream.stream_type
                    proc = stream_processing.get(stream_type)
                    if proc is not None:
                        attr_avg, attr_max, stream_key = proc[:3]
                        metrics[attr_avg], metrics[attr_max] = activities_computation.calculate_avg_and_max(
                            stream.stream_waypoints,
                            stream_key,
                        )
                        # Special handling for normalized power
                        if stream_type == activity_streams_constants.STREAM_TYPE_POWER:
                            metrics["np"] = activities_computation.calculate_np(stream.stream_waypoints)

                # Calculate elapsed time once
                elapsed_time_seconds = round((activity.end_time - activity.start_time).total_seconds())

                # Set fields on the activity object
                activity.total_elapsed_time = elapsed_time_seconds
                activity.total_timer_time = elapsed_time_seconds
                activity.max_speed = metrics["max_speed"]
                activity.max_power = _optional_float_to_int(metrics["max_power"])
                activity.normalized_power = _optional_float_to_int(metrics["np"])
                activity.average_hr = _optional_float_to_int(metrics["avg_hr"])
                activity.max_hr = _optional_float_to_int(metrics["max_hr"])
                activity.average_cad = _optional_float_to_int(metrics["avg_cadence"])
                activity.max_cad = _optional_float_to_int(metrics["max_cadence"])

                # Update the activity in the database
                activities_crud.edit_activity(activity.user_id, activity.id, activity, db)
                logger.info(
                    f"Migration 1 - Processed activity: {activity.id} - {activity.name}",
                    extra=core_logger.context(console=True),
                )
            except Exception as err:
                activities_processed_with_no_errors = False
                logger.error(
                    f"Migration 1 - Failed to process activity {activity.id}: {err}",
                    exc_info=err,
                    extra=core_logger.context(console=True),
                )

    # Mark migration as executed
    if activities_processed_with_no_errors:
        try:
            migrations_crud.set_migration_as_executed(1, db)
        except Exception as err:
            logger.error(
                f"Migration 1 - Failed to set migration as executed: {err}",
                exc_info=err,
                extra=core_logger.context(console=True),
            )
            return
    else:
        logger.error(
            "Migration 1 failed to process all activities. Will try again later.",
            extra=core_logger.context(console=True),
        )

    logger.info("Finished migration 1", extra=core_logger.context(console=True))
