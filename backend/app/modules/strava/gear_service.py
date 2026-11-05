"""Strava gear: syncing the athlete's gear and importing a Strava export's gear CSVs."""

import csv
import functools
import tempfile
from collections.abc import Callable

import jasil.audit as jasil_audit
from fastapi import UploadFile
from sqlalchemy.orm import Session
from stravalib.client import Client
from stravalib.strava_model import DetailedGear, SummaryGear

import core.database as core_database
import core.exceptions as core_exceptions
import core.file_uploads as core_file_uploads
import core.logger as core_logger
import core.text_imports as core_text_imports
import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity.schema as activity_schema
import modules.gears.gear.integration_service as gears_integration
import modules.gears.gear.schema as gears_schema
import modules.strava.audit_actions as strava_audit_actions
import modules.strava.client_service as strava_client_service
import modules.strava.constants as strava_constants
import modules.strava.rate_limit_store as strava_rate_limit_store
import modules.users.users_integrations.integration_service as user_integrations_integration
import modules.users.users_integrations.schema as user_integrations_schema

logger = core_logger.get_logger(__name__)

# The name, brand and model columns of each gear type's CSV in a Strava export.
_CSV_COLUMNS = {
    gears_schema.GearType.BIKE: ("Bike Name", "Bike Brand", "Bike Model"),
    gears_schema.GearType.SHOES: ("Shoe Name", "Shoe Brand", "Shoe Model"),
}

# The export file each gear type is imported from, as the audit trail names it.
_IMPORT_TYPES = {
    gears_schema.GearType.BIKE: strava_audit_actions.GearImportType.BIKES,
    gears_schema.GearType.SHOES: strava_audit_actions.GearImportType.SHOES,
}


def _call_strava[ResultT](
    call: Callable[[Client], ResultT | None],
    strava_client: Client,
    description: str,
    client_id: str,
    user_id: int,
    user_integrations: user_integrations_schema.UsersIntegrationsRead,
    rate_limits: strava_rate_limit_store.StravaRateLimitStore,
) -> ResultT:
    """Make one Strava call, turning its failures into domain errors.

    Args:
        call: Makes the Strava call with the client it is given.
        strava_client: A client authenticated as the user.
        description: What is being fetched, for the log and the error.
        client_id: The Strava application (client ID) making the call.
        user_id: The user the call is for.
        user_integrations: The integration settings the call is made with.
        rate_limits: The shared Strava rate-limit state.

    Returns:
        What the call returned.

    Raises:
        TooManyRequestsError: When Strava's rate limit is active or was just hit.
        StravaTokenRejectedError: When Strava refused the refresh token or the refreshed access token, so the
            account was unlinked.
        DependencyFailedError: When Strava cannot return the result.
    """
    strava_client_service.raise_if_rate_limit_active(client_id, user_id, rate_limits)
    try:
        result = strava_client_service.call_strava(call, strava_client, user_id, user_integrations, rate_limits)
    except core_exceptions.DomainError:
        raise
    except Exception as err:
        strava_client_service.raise_if_rate_limited(err, client_id, rate_limits)
        logger.warning(
            "Error fetching from Strava", extra=core_logger.context(user_id=user_id, fetching=description), exc_info=err
        )
        raise core_exceptions.DependencyFailedError(f"Not able to fetch {description}") from err
    if result is None:
        raise core_exceptions.DependencyFailedError(f"Not able to fetch {description}")
    return result


def _get_gear(strava_gear_id: str, client: Client) -> DetailedGear | None:
    """Fetch one piece of gear from Strava.

    Args:
        strava_gear_id: Strava's id of the gear.
        client: A client authenticated as the user.

    Returns:
        The gear.
    """
    return client.get_gear(strava_gear_id)


def _strava_gear_id(gear: SummaryGear, user_id: int) -> str:
    """Return the id of a gear piece Strava listed on the athlete.

    stravalib types the id as optional; without it the gear can be neither fetched nor matched to activities.

    Args:
        gear: The gear piece as listed on the athlete.
        user_id: The gear's owner, for the log.

    Returns:
        The gear's Strava id.

    Raises:
        DependencyFailedError: When Strava listed the gear without an id.
    """
    if gear.id is None:
        logger.warning("Strava gear has no id", extra=core_logger.context(user_id=user_id))
        raise core_exceptions.DependencyFailedError("Strava gear has no id")
    return gear.id


#: Activities read per page when matching a user's history to their gear.
_ACTIVITY_PAGE_SIZE = 200


def match_gear_for_activity(
    activity: activity_schema.ActivityRead,
    gears: list[gears_schema.GearRead],
) -> int | None:
    """Return the local gear ID matching this activity's Strava gear, else None."""
    if activity.strava_gear_id is None:
        return None
    for gear in gears:
        if activity.strava_gear_id == gear.strava_gear_id:
            return gear.id
    return None


def set_activities_gear(user_id: int, db: Session) -> int:
    """Stage the assignment of the user's Strava-linked activities to the matching local gear.

    Args:
        user_id: The user whose activities to update.
        db: Database session; the caller commits.

    Returns:
        The number of activities that were given gear.
    """
    gears = gears_integration.get_gear_user(user_id, db)
    if not gears:
        return 0

    # A page at a time, so a long history is never held in memory; only the matched ids are kept.
    gear_assignments: dict[int, int | None] = {}
    page_number = 1
    while page := activity_integration.list_user_activities_page(
        user_id, db, page_number=page_number, num_records=_ACTIVITY_PAGE_SIZE
    ):
        for activity in page:
            matched_gear_id = match_gear_for_activity(activity, gears)
            if matched_gear_id is not None:
                gear_assignments[activity.id] = matched_gear_id
        if len(page) < _ACTIVITY_PAGE_SIZE:
            break
        page_number += 1
    if not gear_assignments:
        return 0

    activity_integration.bulk_set_activities_gear(user_id, gear_assignments, db)
    logger.debug("Strava activities gear set", extra=core_logger.context(user_id=user_id, count=len(gear_assignments)))
    return len(gear_assignments)


def get_user_gear(user_id: int, rate_limits: strava_rate_limit_store.StravaRateLimitStore) -> bool:
    """Import the user's Strava gear and assign it to their activities.

    Runs on a worker. The Strava round trips happen with no database session open;
    the new gear, the gear-sync preference and the activity assignments are then
    written in one short transaction, so a failed sync leaves nothing half done.

    Args:
        user_id: The user whose gear to import.
        rate_limits: The shared Strava rate-limit state.

    Returns:
        True once synced, False when Strava is not linked.

    Raises:
        TooManyRequestsError: When Strava's rate limit is active or was just hit.
        DependencyFailedError: When Strava cannot return the gear, or returns a piece without an id or name.
    """
    strava_client_service.refresh_user_strava_token(user_id, rate_limits)

    with core_database.SessionLocal() as db:
        user_integrations = strava_client_service.fetch_user_integrations_and_validate_token(user_id, db)
    if user_integrations is None:
        logger.debug("Strava not linked, skipping the gear sync", extra=core_logger.context(user_id=user_id))
        return False

    logger.info("Started Strava gear processing", extra=core_logger.context(user_id=user_id))
    client_id = strava_client_service.get_client_id(user_integrations)
    strava_client: Client = strava_client_service.create_strava_client(user_integrations)

    athlete = _call_strava(
        lambda client: client.get_athlete(),
        strava_client,
        "Strava athlete",
        client_id,
        user_id,
        user_integrations,
        rate_limits,
    )
    summaries = [(gears_schema.GearType.BIKE, _strava_gear_id(gear, user_id)) for gear in athlete.bikes or []] + [
        (gears_schema.GearType.SHOES, _strava_gear_id(gear, user_id)) for gear in athlete.shoes or []
    ]

    with core_database.SessionLocal() as db:
        new_summaries = [
            (gear_type, gear_id)
            for gear_type, gear_id in summaries
            if gears_integration.get_gear_by_strava_id(gear_id, user_id, db) is None
        ]

    new_gear = []
    for gear_type, strava_gear_id in new_summaries:
        strava_gear = _call_strava(
            functools.partial(_get_gear, strava_gear_id),
            strava_client,
            "Strava gear",
            client_id,
            user_id,
            user_integrations,
            rate_limits,
        )
        # stravalib types the name as optional too; without it the gear has no nickname to be stored with.
        if strava_gear.name is None:
            logger.warning("Strava gear has no name", extra=core_logger.context(user_id=user_id))
            raise core_exceptions.DependencyFailedError("Strava gear has no name")
        new_gear.append(
            gears_schema.GearCreate(
                brand=strava_gear.brand_name,
                model=strava_gear.model_name,
                nickname=strava_gear.name,
                gear_type=gear_type,
                user_id=user_id,
                active=True,
                strava_gear_id=strava_gear_id,
            )
        )

    with core_database.SessionLocal() as db:
        gears_integration.create_multiple_gears(new_gear, user_id, db)
        user_integrations_integration.set_strava_sync_gear(user_id, True, db)
        assigned = set_activities_gear(user_id, db)
        db.commit()

    logger.info(
        "Strava gear processed",
        extra=core_logger.context(user_id=user_id, created=len(new_gear), activities_assigned=assigned),
    )
    return True


def parse_gear_csv(path: str, gear_type: gears_schema.GearType) -> list[dict[str, str]]:
    """Read a Strava gear CSV and check it has the columns its gear type needs.

    Args:
        path: Path of the uploaded CSV.
        gear_type: Which export file it is: bikes or shoes.

    Returns:
        One dictionary per data row, keyed by column header.

    Raises:
        InvalidInputError: When the file cannot be parsed or lacks the required columns.
    """
    try:
        rows = list(core_text_imports.read_bounded_csv(path))
    except (csv.Error, UnicodeDecodeError) as err:
        logger.debug("Unreadable Strava gear CSV", extra=core_logger.context(gear_type=gear_type), exc_info=err)
        raise core_exceptions.InvalidInputError("The Strava gear CSV could not be parsed") from err

    required = _CSV_COLUMNS[gear_type]
    if rows and not set(required) <= rows[0].keys():
        logger.debug(
            "Strava gear import refused: required columns missing",
            extra=core_logger.context(gear_type=gear_type, required=required),
        )
        raise core_exceptions.InvalidInputError(f"Invalid file. Required columns not found: {', '.join(required)}")
    logger.info("Strava gear CSV parsed", extra=core_logger.context(gear_type=gear_type, row_count=len(rows)))
    return rows


def _clean(value: str | None) -> str | None:
    """Strip a CSV cell, mapping a blank one to ``None``."""
    return value.strip() or None if value else None


def transform_csv_bike_gear_to_schema_gear(rows: list[dict[str, str]], user_id: int) -> list[gears_schema.GearCreate]:
    """Turn parsed bikes CSV rows into gear to create.

    A bike is identified by its name, so the last of several rows with one name wins
    and a row without a name is skipped.

    Args:
        rows: Parsed ``bikes.csv`` rows.
        user_id: The user the bikes belong to.

    Returns:
        The bikes to create.
    """
    name_column, brand_column, model_column = _CSV_COLUMNS[gears_schema.GearType.BIKE]
    by_name = {}
    for row in rows:
        name = _clean(row[name_column])
        if name is None:
            logger.warning("Skipping a bike without a name", extra=core_logger.context(user_id=user_id))
            continue
        by_name[name] = row
    return [
        gears_schema.GearCreate(
            user_id=user_id,
            brand=_clean(row[brand_column]),
            model=_clean(row[model_column]),
            nickname=name,
            gear_type=gears_schema.GearType.BIKE,
            active=True,
            strava_gear_id=None,
        )
        for name, row in by_name.items()
    ]


def transform_csv_shoe_gear_to_schema_gear(
    rows: list[dict[str, str]], user_id: int, db: Session
) -> list[gears_schema.GearCreate]:
    """Turn parsed shoes CSV rows into gear to create.

    Strava allows nameless shoes and Endurain does not, so each one gets the default
    name plus the next number not taken by the user's gear or an earlier shoe.

    Args:
        rows: Parsed ``shoes.csv`` rows.
        user_id: The user the shoes belong to.
        db: Database session.

    Returns:
        The shoes to create.
    """
    name_column, brand_column, model_column = _CSV_COLUMNS[gears_schema.GearType.SHOES]
    taken = {gear.nickname for gear in gears_integration.get_gear_user(user_id, db)}
    next_number = 1
    renamed = 0
    shoes = []
    for row in rows:
        raw_name = row[name_column] or ""
        name = _clean(raw_name) if raw_name.replace("+", " ").strip() else None
        if name is None:
            while f"{strava_constants.UNNAMED_SHOE_NICKNAME_PREFIX}{next_number}" in taken:
                next_number += 1
            name = f"{strava_constants.UNNAMED_SHOE_NICKNAME_PREFIX}{next_number}"
            taken.add(name)
            renamed += 1
            logger.debug("Shoe name was blank, it has been renamed", extra=core_logger.context(nickname=name))
        shoes.append(
            gears_schema.GearCreate(
                user_id=user_id,
                brand=_clean(row[brand_column]),
                model=_clean(row[model_column]),
                nickname=name,
                gear_type=gears_schema.GearType.SHOES,
                active=True,
                strava_gear_id=None,
            )
        )
    if renamed:
        logger.info("Nameless Strava shoes were renamed", extra=core_logger.context(count=renamed))
    return shoes


def _save_gear_csv(file: UploadFile) -> tuple[tempfile.TemporaryDirectory[str], str]:
    """Stream an uploaded gear CSV to a private temp directory.

    Args:
        file: The uploaded CSV.

    Returns:
        The temp directory (the caller closes it) and the saved file's path.
    """
    work_dir = tempfile.TemporaryDirectory(prefix="strava-gear-")
    try:
        path = core_file_uploads.save_text_upload_sync(
            file, upload_dir=work_dir.name, filename="gear.csv", max_bytes=strava_constants.GEAR_CSV_MAX_BYTES
        )
    except BaseException:
        work_dir.cleanup()
        raise
    return work_dir, path


def import_gear(file: UploadFile, user_id: int, gear_type: gears_schema.GearType, db: Session) -> int:
    """Create the bikes or shoes listed in an uploaded Strava gear CSV.

    Args:
        file: The uploaded CSV.
        user_id: The user the gear belongs to.
        gear_type: Which export file it is: bikes or shoes.
        db: Database session.

    Returns:
        The number of gear entries handed to the gear module.

    Raises:
        InvalidInputError: When the file cannot be parsed or lacks the required columns.
    """
    work_dir, path = _save_gear_csv(file)
    try:
        rows = parse_gear_csv(path, gear_type)
        if gear_type == gears_schema.GearType.BIKE:
            gears = transform_csv_bike_gear_to_schema_gear(rows, user_id)
        else:
            gears = transform_csv_shoe_gear_to_schema_gear(rows, user_id, db)
        if gears:
            gears_integration.create_multiple_gears(gears, user_id, db)
            jasil_audit.stage(
                db,
                strava_audit_actions.GEAR_IMPORT,
                target_type="user",
                target_id=str(user_id),
                target_owner_id=str(user_id),
                details=strava_audit_actions.GearImportDetails(gear_type=_IMPORT_TYPES[gear_type], count=len(gears)),
            )
            db.commit()
        logger.info("Strava gear import complete", extra=core_logger.context(gear_type=gear_type, count=len(gears)))
        return len(gears)
    finally:
        work_dir.cleanup()
