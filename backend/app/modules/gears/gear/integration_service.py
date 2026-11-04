"""The gear surface other modules may call.

Provider sync (Strava, Garmin Connect), the profile export/import and the modules that
store a gear id on their own rows. Every function returns schemas, never an ORM row. The
writes stage and the caller commits.
"""

from collections.abc import Iterable
from typing import Any

from sqlalchemy.orm import Session

import modules.gears.gear.crud as gears_crud
import modules.gears.gear.schema as gears_schema
import modules.gears.gear.service as gears_service


def get_gear_user(user_id: int, db: Session) -> list[gears_schema.GearRead]:
    """Return all of a user's gears.

    Args:
        user_id: Owner user ID.
        db: Database session.

    Returns:
        The user's gears (empty list if none).
    """
    return gears_crud.get_gear_user(user_id, db)


def get_gear_user_by_id(user_id: int, gear_id: int, db: Session) -> gears_schema.GearRead | None:
    """Return a user's gear by ID.

    Args:
        user_id: Owner user ID.
        gear_id: Gear ID to fetch.
        db: Database session.

    Returns:
        The gear, or None if the user has no such gear.
    """
    return gears_crud.get_gear_user_by_id(user_id, gear_id, db)


def get_gear_by_strava_id(strava_gear_id: str, user_id: int, db: Session) -> gears_schema.GearRead | None:
    """Return the user's gear imported from the given Strava gear.

    Args:
        strava_gear_id: Strava gear identifier.
        user_id: Owner user ID.
        db: Database session.

    Returns:
        The gear, or None if the user has no such import.
    """
    return gears_crud.get_gear_by_strava_id_from_user_id(strava_gear_id, user_id, db)


def get_gear_by_garminconnect_id(garminconnect_gear_id: str, user_id: int, db: Session) -> gears_schema.GearRead | None:
    """Return the user's gear imported from the given Garmin Connect gear.

    Args:
        garminconnect_gear_id: Garmin Connect gear ID.
        user_id: Owner user ID.
        db: Database session.

    Returns:
        The gear, or None if the user has no such import.
    """
    return gears_crud.get_gear_by_garminconnect_id_from_user_id(garminconnect_gear_id, user_id, db)


def restore_profile_gears(
    records: list[dict[str, Any]], user_id: int, ids: dict[str, dict[int, int]], db: Session
) -> int:
    """Stage the gears of a profile archive; the caller commits.

    Args:
        records: The archived gears.
        user_id: The importing user.
        ids: The ids restored so far; receives the archived-to-stored gear ids under ``"gears"``.
        db: Database session.

    Returns:
        How many gears were restored or matched.
    """
    return gears_service.restore_profile_gears(records, user_id, ids, db)


def create_multiple_gears(gears: Iterable[gears_schema.GearCreate | None], user_id: int, db: Session) -> None:
    """Stage the gears a user does not have yet; the caller commits.

    Entries without a nickname and nicknames the user already has are skipped.

    Args:
        gears: Gear payloads to create.
        user_id: Owner user ID.
        db: Database session.

    Raises:
        ConflictError: If a provider gear ID is already taken.
    """
    gears_service.stage_gears(gears, user_id, db)


def delete_all_strava_gear_for_user(user_id: int, db: Session) -> None:
    """Stage the deletion of every Strava-linked gear a user has; the caller commits.

    Args:
        user_id: Owner user ID.
        db: Database session.
    """
    gears_service.delete_all_strava_gear_for_user(user_id, db)


def require_owned_gears(user_id: int, gear_ids: Iterable[int | None], db: Session) -> None:
    """Require every given gear to belong to the user.

    Args:
        user_id: The user who must own the gears.
        gear_ids: Client-supplied gear IDs; ``None`` entries are skipped.
        db: Database session.

    Raises:
        NotFoundError: If a gear does not exist or is not the user's.
    """
    gears_service.require_owned_gears(user_id, gear_ids, db)
