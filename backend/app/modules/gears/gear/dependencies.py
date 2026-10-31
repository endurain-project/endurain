"""Gear dependency validators."""

from collections.abc import Iterable

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

import core.dependencies as core_dependencies
import core.exceptions as core_exceptions
import modules.gears.gear.crud as gears_crud
import modules.gears.gear.schema as gears_schema


def validate_gear_id(gear_id: int) -> None:
    """
    Validate that gear_id is greater than zero.

    Args:
        gear_id: The ID of the gear to validate.

    Raises:
        HTTPException: If gear_id is invalid.
    """
    core_dependencies.validate_id(
        identifier=gear_id,
        min_value=0,
        message="Invalid gear ID",
    )


def validate_gear_type(gear_type: int) -> None:
    """
    Validate that gear_type maps to a known GearType.

    Args:
        gear_type: The type of gear to validate.

    Raises:
        HTTPException: If gear_type is invalid.
    """
    try:
        gears_schema.GearType(gear_type)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid gear type",
        ) from err


def require_owned_gears(user_id: int, gear_ids: Iterable[int | None], db: Session) -> None:
    """
    Require every given gear to belong to the user.

    Gear ids arrive from the client on several write paths, and they are small
    sequential integers, so each must be resolved through the owner-scoped lookup
    before it is stored. ``None`` (clearing a gear) is always allowed.

    Args:
        user_id: The user who must own the gears.
        gear_ids: Client-supplied gear IDs; ``None`` entries are skipped.
        db: Database session.

    Raises:
        NotFoundError: If a gear does not exist or is not the user's.
    """
    for gear_id in {gear_id for gear_id in gear_ids if gear_id is not None}:
        if gears_crud.get_gear_user_by_id(user_id, gear_id, db) is None:
            raise core_exceptions.NotFoundError("Gear not found")
