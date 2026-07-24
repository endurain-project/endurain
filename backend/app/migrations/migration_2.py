"""Migration 2: populate activity timezones and health BMI."""

from sqlalchemy.orm import Session
from timezonefinder import TimezoneFinder

import core.config as core_config
import core.logger as core_logger
import migrations.crud as migrations_crud
import modules.activities.activity.crud as activities_crud
import modules.activities.activity_streams.constants as activity_streams_constants
import modules.activities.activity_streams.crud as activity_streams_crud
import modules.health.health_weight.crud as health_weight_crud
import modules.health.health_weight.schema as health_weight_schema


def process_migration_2(db: Session) -> None:
    """
    Run migration 2: backfill timezone and BMI fields.

    Args:
        db: The SQLAlchemy database session.

    Returns:
        None

    Raises:
        Exception: Logs errors per-record; does not re-raise.
    """
    core_logger.print_to_log_and_console("Started migration 2")

    # Create an instance of TimezoneFinder
    tf = TimezoneFinder()

    # Track if all records were processed without errors
    activities_processed_with_no_errors = True
    health_weight_processed_with_no_errors = True

    # Fetch all activities and health_weight
    try:
        activities = activities_crud.get_all_activities(db)
        health_weight = health_weight_crud.get_all_health_weight(db)
    except Exception as err:
        core_logger.print_to_log_and_console(
            f"Migration 2 - Error fetching activities and/or health_weight: {err}",
            "error",
            exc=err,
        )
        return

    if activities:
        # Process each activity and add timezone
        for activity in activities:
            if not activity.user_id or not activity.id:
                core_logger.print_to_log_and_console(
                    f"Migration 2 - Skipping activity with missing user_id or id: {activity}",
                    "warning",
                )
                continue
            try:
                # Skip if activity already has timezone
                if activity.timezone:
                    core_logger.print_to_log_and_console(
                        f"Migration 2 - {activity.id} already has timezone defined. Skipping.",
                        "info",
                    )
                    continue

                timezone: str = core_config.settings.TZ

                # Get activity stream
                try:
                    activity_stream_coord = activity_streams_crud.get_activity_stream_by_type(
                        activity.id, activity_streams_constants.STREAM_TYPE_MAP, activity.user_id, db
                    )
                except Exception as err:
                    core_logger.print_to_log_and_console(
                        f"Migration 2 - Failed to fetch streams for activity {activity.id}: {err}",
                        "warning",
                        exc=err,
                    )
                    activities_processed_with_no_errors = False
                    continue

                if activity_stream_coord:
                    detected_timezone = tf.timezone_at(
                        lat=activity_stream_coord.stream_waypoints[0]["lat"],
                        lng=activity_stream_coord.stream_waypoints[0]["lon"],
                    )
                    if detected_timezone is not None:
                        timezone = detected_timezone

                activity.timezone = timezone

                # Update the activity in the database
                activities_crud.edit_activity(activity.user_id, activity.id, activity, db)

                core_logger.print_to_log_and_console(
                    f"Migration 2 - Processed activity: {activity.id} - {activity.name}"
                )

            except Exception as err:
                activities_processed_with_no_errors = False
                core_logger.print_to_log_and_console(
                    f"Migration 2 - Failed to process activity {activity.id}: {err}",
                    "error",
                    exc=err,
                )

    if health_weight:
        # Process each weight and add timezone
        for data in health_weight:
            try:
                # Skip if weight already has timezone
                if data.bmi:
                    core_logger.print_to_log_and_console(
                        f"Migration 2 - {data.id} already has BMI defined. Skipping.",
                        "info",
                    )
                    continue

                # Update the weight in the database
                data_to_update = health_weight_schema.HealthWeightUpdate.model_validate(data)
                health_weight_crud.edit_health_weight(data.user_id, data_to_update, db)

                core_logger.print_to_log_and_console(f"Migration 2 - Processed BMI: {data.id}")

            except Exception as err:
                health_weight_processed_with_no_errors = False
                core_logger.print_to_log_and_console(
                    f"Migration 2 - Failed to process BMI {data.id}: {err}",
                    "error",
                    exc=err,
                )

    # Mark migration as executed
    if activities_processed_with_no_errors and health_weight_processed_with_no_errors:
        try:
            migrations_crud.set_migration_as_executed(2, db)
        except Exception as err:
            core_logger.print_to_log_and_console(
                f"Migration 2 - Failed to set migration as executed: {err}",
                "error",
                exc=err,
            )
            return
    else:
        core_logger.print_to_log_and_console(
            "Migration 2 failed to process all activities. Will try again later.",
            "error",
        )

    core_logger.print_to_log_and_console("Finished migration 2")
