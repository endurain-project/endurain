import garminconnect
from sqlalchemy.orm import Session

import core.logger as core_logger
import modules.activities.activity.integration_service as activities_integration
import modules.activities.activity.schema as activities_schema
import modules.garmin.utils as garmin_utils
import modules.gears.gear.crud as gears_crud
import modules.gears.gear.schema as gears_schema
import modules.users.users_integrations.crud as user_integrations_crud
from core.database import SessionLocal

logger = core_logger.get_logger(__name__)


def fetch_and_process_gear(garminconnect_client: garminconnect.Garmin, user_id: int, db: Session) -> int:
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
        logger.info(f"User {user_id}: No new Garmin Connect gear found: garminconnect_gear is None")

        # Return 0 to indicate no gear were processed
        return 0

    # Save the gear to the database
    gears_crud.create_multiple_gears(processed_gears, user_id, db)

    # Return the number of activities processed
    return len(processed_gears)


def process_gear(gear, user_id: int, db: Session) -> gears_schema.GearCreate | None:
    # Get the gear by garminconnect uuid from user id
    gear_db = gears_crud.get_gear_by_garminconnect_id_from_user_id(gear["uuid"], user_id, db)

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
    activity: activities_schema.Activity,
    gears: list[gears_schema.GearRead],
) -> int | None:
    """Return the local gear ID matching this activity's Garmin gear, else None."""
    if activity.garminconnect_gear_id is None:
        return None
    for gear in gears:
        if activity.garminconnect_gear_id == gear.garminconnect_gear_id:
            logger.info(f"Gear found: {gear.nickname}")
            return gear.id
    return None


def resolve_synced_gear_id(user_id: int, garminconnect_gear: list | None, db: Session) -> int | None:
    """
    Resolve a downloaded activity's Garmin gear to a local gear ID.

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

    Raises:
        None.
    """
    if not garminconnect_gear:
        return None
    user_integrations = garmin_utils.fetch_user_integrations_and_validate_token(user_id, db)
    if user_integrations is None or not user_integrations.garminconnect_sync_gear:
        return None
    gear = gears_crud.get_gear_by_garminconnect_id_from_user_id(garminconnect_gear[0]["uuid"], user_id, db)
    return gear.id if gear is not None else None


def set_activities_gear(user_id: int, db: Session) -> int:
    # Get user activities
    activities = activities_integration.list_user_activities_with_garminconnect_gear(user_id, db)

    # Skip if no activities
    if activities is None:
        logger.info(f"User {user_id}: 0 activities found")
        return 0

    logger.info(f"User {user_id}: {len(activities)} activities found")

    # Get user gears
    gears = gears_crud.get_gear_user(user_id, db)

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
        activities_integration.bulk_set_activities_gear(user_id, gear_assignments, db)

    return len(gear_assignments)


def get_user_gear(user_id: int):
    # Create a new database session using context manager
    with SessionLocal() as db:
        # Log the start of the activities processing
        logger.info(f"User {user_id}: Started Garmin Connect gear processing")

        # Get the user integrations by user ID
        user_integrations = garmin_utils.fetch_user_integrations_and_validate_token(user_id, db)

        if user_integrations is None:
            logger.info(f"User {user_id}: Garmin Connect not linked")
            return None

        # Create a Garmin Connect client with the user's access token
        garminconnect_client = garmin_utils.login_garminconnect_using_tokens(
            user_integrations.garminconnect_token,
        )

        # Set the user's gear to sync to True
        user_integrations_crud.set_user_garminconnect_sync_gear(user_id, True, db)

        # Fetch Garmin Connect gear
        num_garmiconnect_gear_processed = fetch_and_process_gear(garminconnect_client, user_id, db)

        # Log an informational event for tracing
        logger.info(f"User {user_id}: {num_garmiconnect_gear_processed} Garmin Connect gear processed")

        # Log an informational event for tracing
        logger.info(f"User {user_id}: Will parse current activities and set gear if applicable")

        num_gear_activities_set = set_activities_gear(user_id, db)

        # Log an informational event for tracing
        logger.info(f"User {user_id}: {num_gear_activities_set} activities where gear was set")
