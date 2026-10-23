"""Garmin Connect gear sync: store the user's gear and assign it to their activities."""

import garminconnect
from sqlalchemy.orm import Session

import core.logger as core_logger
import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity.schema as activity_schema
import modules.garmin.service as garmin_service
import modules.garmin.token_utils as garmin_token_utils
import modules.gears.gear.integration_service as gears_integration
import modules.gears.gear.schema as gears_schema
import modules.users.users_integrations.integration_service as user_integrations_integration
from core.database import SessionLocal

logger = core_logger.get_logger(__name__)


def fetch_and_process_gear(garminconnect_client: garminconnect.Garmin, user_id: int, db: Session) -> int:
    """Fetch the user's Garmin Connect gear and store the pieces not stored yet.

    Args:
        garminconnect_client: A client authenticated as the user.
        user_id: The gear's owner.
        db: Database session.

    Returns:
        The number of gear pieces processed.
    """
    # Fetch Garmin athlete
    last_used_device = garminconnect_client.get_device_last_used()

    # Get the user gear
    gears = garminconnect_client.get_gear(last_used_device["userProfileNumber"])

    # Initialize an empty list for results
    processed_gears = []

    for gear in gears:
        processed_gears.append(process_gear(gear, user_id, db))

    if processed_gears is None:
        # Log an informational event if no gear were found
        logger.info(
            "No new Garmin Connect gear found: garminconnect_gear is None",
            extra=core_logger.context(user_id=user_id),
        )

        # Return 0 to indicate no gear were processed
        return 0

    # Save the gear to the database
    gears_integration.create_multiple_gears(processed_gears, user_id, db)
    db.commit()

    # Return the number of activities processed
    return len(processed_gears)


def process_gear(gear: dict, user_id: int, db: Session) -> gears_schema.GearCreate | None:
    """Build the local gear for a Garmin Connect gear piece.

    Args:
        gear: The Garmin Connect gear payload.
        user_id: The gear's owner.
        db: Database session.

    Returns:
        The gear to create, or ``None`` when it is already stored.
    """
    # Get the gear by garminconnect uuid from user id
    gear_db = gears_integration.get_gear_by_garminconnect_id(gear["uuid"], user_id, db)

    # Skip existing gear
    if gear_db:
        return None

    new_gear = gears_schema.GearCreate(
        brand=gear["gearMakeName"] if gear["gearMakeName"] else None,
        model=gear["gearModelName"] if gear["gearModelName"] else None,
        nickname=(gear["displayName"] if gear["displayName"] else gear["customMakeModel"]),
        gear_type=(gears_schema.GearType.BIKE if gear["gearTypeName"] == "Bike" else gears_schema.GearType.SHOES),
        user_id=user_id,
        active=gear["gearStatusName"] == "active",
        garminconnect_gear_id=gear["uuid"],
    )

    return new_gear


def match_gear_for_activity(
    activity: activity_schema.ActivityRead,
    gears: list[gears_schema.GearRead],
) -> int | None:
    """Return the local gear ID matching this activity's Garmin gear, else None."""
    if activity.garminconnect_gear_id is None:
        return None
    for gear in gears:
        if activity.garminconnect_gear_id == gear.garminconnect_gear_id:
            logger.info(
                "Gear found",
                extra=core_logger.context(gear_nickname=gear.nickname),
            )
            return gear.id
    return None


def resolve_synced_gear_id(user_id: int, garminconnect_gear: list | None, db: Session) -> int | None:
    """Resolve a downloaded activity's Garmin gear to a local gear ID.

    Resolved here, before the file reaches ingestion, so the ingestion seam never
    has to ask a provider module whether gear sync is on or which local gear a
    Garmin UUID maps to.

    Args:
        user_id: Owner user ID.
        garminconnect_gear: Garmin gear metadata (``[{"uuid": ...}, ...]``) from
            the activity download, when the activity has any.
        db: Database session.

    Returns:
        The local gear ID, or None when gear sync is off, the account's token is
        invalid, the activity has no gear, or no local gear matches.
    """
    if not garminconnect_gear:
        return None
    user_integrations = garmin_service.fetch_user_integrations_and_validate_token(user_id, db)
    if user_integrations is None or not user_integrations.garminconnect_sync_gear:
        return None
    gear = gears_integration.get_gear_by_garminconnect_id(garminconnect_gear[0]["uuid"], user_id, db)
    return gear.id if gear is not None else None


def set_activities_gear(user_id: int, db: Session) -> int:
    """Assign local gear to the user's activities that carry a Garmin Connect gear id.

    Args:
        user_id: The activities' owner.
        db: Database session.

    Returns:
        The number of activities whose gear was set.
    """
    # Get user activities
    activities = activity_integration.list_user_activities_with_garminconnect_gear(user_id, db)

    # Skip if no activities
    if not activities:
        logger.info(
            "No activities found",
            extra=core_logger.context(user_id=user_id),
        )
        return 0

    logger.info(
        "Activities found",
        extra=core_logger.context(user_id=user_id, count=len(activities)),
    )

    # Get user gears
    gears = gears_integration.get_gear_user(user_id, db)

    # Skip if no gears
    if gears is None:
        return 0

    # Build {activity_id: gear_id} for all activities with a match
    gear_assignments: dict[int, int | None] = {}
    for activity in activities:
        matched_gear_id = match_gear_for_activity(activity, gears)
        if matched_gear_id is not None:
            gear_assignments[activity.id] = matched_gear_id

    # Persist via CRUD (single UPDATE per distinct gear_id)
    if gear_assignments:
        activity_integration.bulk_set_activities_gear(user_id, gear_assignments, db)
        db.commit()

    return len(gear_assignments)


def get_user_gear(user_id: int) -> None:
    """Fetch a user's Garmin Connect gear, store it and assign it to their activities.

    Args:
        user_id: The user to sync.
    """
    # Create a new database session using context manager
    with SessionLocal() as db:
        # Log the start of the activities processing
        logger.info(
            "Started Garmin Connect gear processing",
            extra=core_logger.context(user_id=user_id),
        )

        # Get the user integrations by user ID
        user_integrations = garmin_service.fetch_user_integrations_and_validate_token(user_id, db)

        if user_integrations is None:
            logger.info(
                "Garmin Connect not linked",
                extra=core_logger.context(user_id=user_id),
            )
            return None

        # Create a Garmin Connect client with the user's access token
        garminconnect_client = garmin_token_utils.login_garminconnect_using_tokens(
            user_integrations.garminconnect_token,
        )

        # Set the user's gear to sync to True
        user_integrations_integration.set_garminconnect_sync_gear(user_id, True, db)

        # Fetch Garmin Connect gear
        num_garmiconnect_gear_processed = fetch_and_process_gear(garminconnect_client, user_id, db)

        # Log an informational event for tracing
        logger.info(
            "Garmin Connect gear processed",
            extra=core_logger.context(user_id=user_id, count=num_garmiconnect_gear_processed),
        )

        # Log an informational event for tracing
        logger.info(
            "Will parse current activities and set gear if applicable",
            extra=core_logger.context(user_id=user_id),
        )

        num_gear_activities_set = set_activities_gear(user_id, db)

        # Log an informational event for tracing
        logger.info(
            "Activities where gear was set",
            extra=core_logger.context(user_id=user_id, count=num_gear_activities_set),
        )
