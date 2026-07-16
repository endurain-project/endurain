"""Migration 7: backfill pre-computed HR zone_percentages for existing streams."""

from sqlalchemy.orm import Session

import core.logger as core_logger
import migrations.crud as migrations_crud
import modules.activities.activity.crud as activity_crud
import modules.activities.activity.schema as activity_schema
import modules.activities.activity_streams.crud as activity_streams_crud
import modules.activities.activity_streams.schema as activity_streams_schema
import modules.activities.activity_streams.utils as activity_streams_utils
import modules.users.users.crud as users_crud
import modules.users.users.schema as users_schema


async def process_migration_7(db: Session) -> None:
    """
    Backfill zone_percentages for existing HR streams.

    Args:
        db: The SQLAlchemy database session.

    Returns:
        None.
    """
    core_logger.print_to_log_and_console("Started migration 7")

    streams_processed_with_no_errors: bool = True
    last_id: int = 0

    while True:
        try:
            batch_streams: list[activity_streams_schema.ActivityStreamsRead] = (
                activity_streams_crud.get_hr_streams_without_zone_percentages(db=db, after_id=last_id)
            )
            if not batch_streams:
                break

            activity_cache: dict[int, activity_schema.Activity] = {}
            user_cache: dict[int, users_schema.UsersRead] = {}

            computed_streams: list[dict[str, int | dict[str, dict]]] = []

            for stream in batch_streams:
                zone_percentages: dict[str, dict] | None = None

                activity: activity_schema.Activity | None = activity_cache.get(stream.activity_id)
                if activity is None:
                    activity = activity_crud.get_activity_by_id(stream.activity_id, db)
                    if activity is None:
                        continue
                    activity_cache[stream.activity_id] = activity

                if activity.user_id is None:
                    continue

                user: users_schema.UsersRead | None = user_cache.get(activity.user_id)
                if user is None:
                    user = users_crud.get_user_by_id(activity.user_id, db)
                    if user is None:
                        continue
                    user_cache[activity.user_id] = user

                try:
                    zone_percentages = await activity_streams_utils.build_zone_percentages(
                        user,
                        activity,
                        stream.stream_waypoints,
                    )
                except Exception as err:
                    core_logger.print_to_log(
                        f"Zone % computation failed for stream (activity {stream.activity_id}): {err}",
                        "error",
                        exc=err,
                    )

                if zone_percentages:
                    computed_streams.append({"stream_id": stream.id, "zone_percentages": zone_percentages})

            if computed_streams:
                activity_streams_crud.backfill_zone_percentages_for_missing_hr_streams(computed_streams, db)

            last_id = batch_streams[-1].id

        except Exception as err:
            streams_processed_with_no_errors = False
            core_logger.print_to_log_and_console(
                f"Migration 7 - Error fetching streams: {err}",
                "error",
                exc=err,
            )
            return

    if streams_processed_with_no_errors:
        try:
            migrations_crud.set_migration_as_executed(7, db)
        except Exception as err:
            core_logger.print_to_log_and_console(
                f"Migration 7 - Failed to set migration as executed: {err}",
                "error",
                exc=err,
            )
            return
    else:
        core_logger.print_to_log_and_console(
            "Migration 7 failed to process all streams. Will try again later.",
            "error",
        )

    core_logger.print_to_log_and_console("Finished migration 7")
