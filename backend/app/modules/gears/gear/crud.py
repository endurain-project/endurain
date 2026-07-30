from typing import Any, overload

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import core.decorators as core_decorators
import core.logger as core_logger
import modules.activities.activity.models as activity_models
import modules.gears.gear.models as gears_models
import modules.gears.gear.schema as gears_schema
import modules.gears.gear_components.models as gear_components_models

logger = core_logger.get_logger(__name__)

# Fields that must never be reassigned through an update payload
_IMMUTABLE_FIELDS: frozenset[str] = frozenset({"id", "user_id"})

# Gear text fields trimmed of surrounding whitespace on write
_TEXT_FIELDS: tuple[str, ...] = ("brand", "model", "nickname")

# Private internal helpers


@overload
def _transform_gears(
    gears: gears_models.Gear,
) -> gears_schema.GearRead: ...


@overload
def _transform_gears(
    gears: list[gears_models.Gear],
) -> list[gears_schema.GearRead]: ...


def _transform_gears(
    gears: gears_models.Gear | list[gears_models.Gear],
) -> gears_schema.GearRead | list[gears_schema.GearRead]:
    """
    Transform a gear or list of gears to a Pydantic schema.

    Args:
        gears: The gear ORM instance or list of instances.

    Returns:
        The gear(s) as a schema.
    """
    if isinstance(gears, list):
        return [gears_schema.GearRead.model_validate(g) for g in gears]
    return gears_schema.GearRead.model_validate(gears)


def _normalize_gear_payload(data: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize a gear payload mapping for persistence.

    Args:
        data: Mapping of gear field names to values.

    Returns:
        The mapping with text fields trimmed and a None
        ``created_at`` removed so the column default applies.
    """
    for field in _TEXT_FIELDS:
        value = data.get(field)
        if isinstance(value, str):
            data[field] = value.strip()
    if data.get("created_at") is None:
        data.pop("created_at", None)
    return data


@core_decorators.handle_db_errors
def _get_gear_model_by_id_and_user_id_or_404(gear_id: int, user_id: int, db: Session) -> gears_models.Gear:
    """
    Retrieve gear model by ID and user ID.

    Args:
        gear_id: Gear ID to fetch.
        user_id: User ID to fetch record for.
        db: Database session.

    Returns:
        Mapped ``Gear`` ORM instance.

    Raises:
        HTTPException: If database error occurs.
    """
    # Get the gear from the database
    stmt = select(gears_models.Gear).where(
        gears_models.Gear.id == gear_id,
        gears_models.Gear.user_id == user_id,
    )
    db_gear = db.execute(stmt).scalar_one_or_none()

    if db_gear is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Gear not found",
        )

    return db_gear


# Public CRUD functions


@core_decorators.handle_db_errors
def get_gear_user_by_id(user_id: int, gear_id: int, db: Session) -> gears_schema.GearRead | None:
    """
    Retrieve a gear by ID for a specific user.

    Args:
        user_id: Owner user ID.
        gear_id: Gear ID to fetch.
        db: Database session.

    Returns:
        GearRead schema if found, None otherwise.

    Raises:
        HTTPException: If a database error occurs.
    """
    stmt = select(gears_models.Gear).where(
        gears_models.Gear.user_id == user_id,
        gears_models.Gear.id == gear_id,
    )
    db_gear = db.execute(stmt).scalar_one_or_none()
    return _transform_gears(db_gear) if db_gear is not None else None


@core_decorators.handle_db_errors
def get_gear_activity_stats(
    gear_id: int,
    db: Session,
) -> dict[str, float]:
    """
    Get aggregated activity stats for a gear.

    Args:
        gear_id: Gear ID to aggregate.
        db: Database session.

    Returns:
        Dict with total_distance (meters)
        and total_time (seconds).

    Raises:
        HTTPException: On database error.
    """
    stmt = select(
        func.coalesce(
            func.sum(activity_models.Activity.distance),
            0,
        ),
        func.coalesce(
            func.sum(activity_models.Activity.total_timer_time),
            0,
        ),
    ).where(
        activity_models.Activity.gear_id == gear_id,
    )
    row = db.execute(stmt).one()
    return {
        "total_distance": float(row[0]),
        "total_time": float(row[1]),
    }


@core_decorators.handle_db_errors
def get_gear_components_total_cost(
    gear_id: int,
    user_id: int,
    db: Session,
) -> float:
    """
    Get total purchase value of all components.

    Args:
        gear_id: Gear to sum costs for.
        user_id: Owner user ID.
        db: Database session.

    Returns:
        Total component cost as float.

    Raises:
        HTTPException: On database error.
    """
    stmt = select(
        func.coalesce(
            func.sum(gear_components_models.GearComponents.purchase_value),
            0,
        ),
    ).where(
        gear_components_models.GearComponents.gear_id == gear_id,
        gear_components_models.GearComponents.user_id == user_id,
    )
    result = db.execute(stmt).scalar_one()
    return float(result or 0)


@core_decorators.handle_db_errors
def get_gears_number(
    user_id: int,
    db: Session,
    show_inactive: bool | None = True,
) -> int:
    """
    Count a user's gears, honoring the active filter.

    Args:
        user_id: Owner user ID.
        db: Database session.
        show_inactive: Include inactive gears. Defaults to True.

    Returns:
        Number of gears matching the filter.

    Raises:
        HTTPException: If a database error occurs.
    """
    stmt = select(func.count(gears_models.Gear.id)).where(
        gears_models.Gear.user_id == user_id,
    )

    if show_inactive is False:
        stmt = stmt.where(
            gears_models.Gear.active.is_(True),
        )

    return db.execute(stmt).scalar_one()


@core_decorators.handle_db_errors
def get_gear_users_with_pagination(
    user_id: int,
    db: Session,
    page_number: int | None = None,
    num_records: int | None = None,
    show_inactive: bool | None = True,
) -> list[gears_schema.GearRead]:
    """
    Retrieve paginated gears for a user.

    Args:
        user_id: Owner user ID.
        db: Database session.
        page_number: Page number (1-indexed). Defaults to None.
        num_records: Records per page. Defaults to None.
        show_inactive: Include inactive gears. Defaults to True.

    Returns:
        List of GearRead schemas ordered by nickname.

    Raises:
        HTTPException: If a database error occurs.
    """
    stmt = select(gears_models.Gear).where(
        gears_models.Gear.user_id == user_id,
    )

    if show_inactive is False:
        stmt = stmt.where(
            gears_models.Gear.active.is_(True),
        )

    stmt = stmt.order_by(gears_models.Gear.nickname)

    if page_number is not None and num_records is not None:
        stmt = stmt.offset(
            (page_number - 1) * num_records,
        ).limit(num_records)

    db_gears = db.execute(stmt).scalars().all()
    return _transform_gears(list(db_gears))


@core_decorators.handle_db_errors
def get_gear_user(user_id: int, db: Session) -> list[gears_schema.GearRead]:
    """
    Retrieve all gears for a specific user.

    Args:
        user_id: Owner user ID.
        db: Database session.

    Returns:
        List of GearRead schemas for the user.

    Raises:
        HTTPException: If a database error occurs.
    """
    stmt = select(gears_models.Gear).where(
        gears_models.Gear.user_id == user_id,
    )
    db_gears = db.execute(stmt).scalars().all()
    return _transform_gears(list(db_gears))


@core_decorators.handle_db_errors
def get_gear_user_contains_nickname(user_id: int, nickname: str, db: Session) -> list[gears_schema.GearRead]:
    """
    Retrieve gears matching a nickname substring.

    Args:
        user_id: Owner user ID.
        nickname: Substring to search for.
        db: Database session.

    Returns:
        List of GearRead schemas matching criteria.

    Raises:
        HTTPException: If a database error occurs.
    """
    parsed_nickname = nickname.lower().strip()

    stmt = select(gears_models.Gear).where(
        func.lower(
            gears_models.Gear.nickname,
        ).like(f"%{parsed_nickname}%"),
        gears_models.Gear.user_id == user_id,
    )
    db_gears = db.execute(stmt).scalars().all()
    return _transform_gears(list(db_gears))


@core_decorators.handle_db_errors
def get_gear_user_by_nickname(user_id: int, nickname: str, db: Session) -> gears_schema.GearRead | None:
    """
    Retrieve a gear by exact nickname for a user.

    Args:
        user_id: Owner user ID.
        nickname: Gear nickname to match.
        db: Database session.

    Returns:
        GearRead schema if found, None otherwise.

    Raises:
        HTTPException: If a database error occurs.
    """
    parsed_nickname = nickname.lower().strip()

    stmt = select(gears_models.Gear).where(
        func.lower(
            gears_models.Gear.nickname,
        )
        == parsed_nickname,
        gears_models.Gear.user_id == user_id,
    )
    db_gear = db.execute(stmt).scalar_one_or_none()
    return _transform_gears(db_gear) if db_gear else None


@core_decorators.handle_db_errors
def get_gear_by_type_and_user(gear_type: int, user_id: int, db: Session) -> list[gears_schema.GearRead]:
    """
    Retrieve gears by type for a specific user.

    Args:
        gear_type: Gear type identifier.
        user_id: Owner user ID.
        db: Database session.

    Returns:
        List of GearRead schemas ordered by nickname.

    Raises:
        HTTPException: If a database error occurs.
    """
    stmt = (
        select(gears_models.Gear)
        .where(
            gears_models.Gear.gear_type == gear_type,
            gears_models.Gear.user_id == user_id,
        )
        .order_by(gears_models.Gear.nickname)
    )
    db_gears = db.execute(stmt).scalars().all()
    return _transform_gears(list(db_gears))


@core_decorators.handle_db_errors
def get_gear_by_strava_id_from_user_id(
    gear_strava_id: str,
    user_id: int,
    db: Session,
) -> gears_schema.GearRead | None:
    """
    Retrieve a gear by Strava ID for a user.

    Args:
        gear_strava_id: Strava gear identifier.
        user_id: Owner user ID.
        db: Database session.

    Returns:
        GearRead schema if found, None otherwise.

    Raises:
        HTTPException: If a database error occurs.
    """
    stmt = select(gears_models.Gear).where(
        gears_models.Gear.user_id == user_id,
        gears_models.Gear.strava_gear_id == gear_strava_id,
    )
    db_gear = db.execute(stmt).scalar_one_or_none()
    return _transform_gears(db_gear) if db_gear else None


@core_decorators.handle_db_errors
def get_gear_by_garminconnect_id_from_user_id(
    gear_garminconnect_id: str,
    user_id: int,
    db: Session,
) -> gears_schema.GearRead | None:
    """
    Retrieve a gear by Garmin Connect ID for a user.

    Args:
        gear_garminconnect_id: Garmin Connect gear ID.
        user_id: Owner user ID.
        db: Database session.

    Returns:
        GearRead schema if found, None otherwise.

    Raises:
        HTTPException: If a database error occurs.
    """
    stmt = select(gears_models.Gear).where(
        gears_models.Gear.user_id == user_id,
        gears_models.Gear.garminconnect_gear_id == gear_garminconnect_id,
    )
    db_gear = db.execute(stmt).scalar_one_or_none()
    return _transform_gears(db_gear) if db_gear else None


@core_decorators.handle_db_errors
def create_multiple_gears(
    gears: list[gears_schema.GearCreate],
    user_id: int,
    db: Session,
) -> None:
    """
    Create multiple gears for a user.

    Filters invalid entries, deduplicates by
    nickname, skips existing gears, and persists
    the rest.

    Args:
        gears: List of gear schemas to create.
        user_id: Owner user ID.
        db: Database session.

    Returns:
        None.

    Raises:
        HTTPException: If a database or
            integrity error occurs.
    """
    # Filter out None and gears without a nickname
    valid_gears = [
        gear
        for gear in (gears or [])
        if gear is not None and getattr(gear, "nickname", None) and str(gear.nickname).strip()
    ]

    # De-dupe by nickname (case-insensitive)
    seen: set[str] = set()
    deduped: list[gears_schema.GearCreate] = []
    for gear in valid_gears:
        nickname_normalized = str(gear.nickname).lower().strip()
        if nickname_normalized not in seen:
            seen.add(nickname_normalized)
            deduped.append(gear)
        else:
            logger.warning(
                f"Duplicate nickname '{gear.nickname}' in request for user {user_id}, skipping",
                extra=core_logger.context(console=True),
            )

    # Fetch all already-existing nicknames for this user in one query
    # instead of one SELECT per gear.
    candidate_nicknames: set[str] = {str(g.nickname).lower().strip() for g in deduped}
    existing_stmt = select(gears_models.Gear.nickname).where(
        gears_models.Gear.user_id == user_id,
        func.lower(gears_models.Gear.nickname).in_(candidate_nicknames),
    )
    existing_nicknames: set[str] = {row[0].lower().strip() for row in db.execute(existing_stmt).all()}

    gears_to_create: list[gears_schema.GearCreate] = []
    for gear in deduped:
        normalised = str(gear.nickname).lower().strip()
        if normalised in existing_nicknames:
            logger.warning(
                f"Gear with nickname '{gear.nickname}' already exists for user {user_id}, skipping",
                extra=core_logger.context(console=True),
            )
        else:
            gears_to_create.append(gear)

    # Persist any remaining
    if gears_to_create:
        new_gears = [
            gears_models.Gear(**{**_normalize_gear_payload(gear.model_dump(exclude_unset=True)), "user_id": user_id})
            for gear in gears_to_create
        ]
        try:
            db.add_all(new_gears)
            db.commit()
            for new_gear in new_gears:
                db.refresh(new_gear)
        except IntegrityError as integrity_err:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=("Duplicate entry error. Check if strava_gear_id or garminconnect_gear_id are unique"),
            ) from integrity_err


@core_decorators.handle_db_errors
def create_gear(
    gear: gears_schema.GearCreate,
    user_id: int,
    db: Session,
) -> gears_schema.GearRead:
    """
    Create a single gear for a user.

    Args:
        gear: Gear schema with data to create.
        user_id: Owner user ID.
        db: Database session.

    Returns:
        Created GearRead schema.

    Raises:
        HTTPException: If gear already exists or
            a database error occurs.
    """
    gear_check = get_gear_user_by_nickname(
        user_id,
        gear.nickname,
        db,
    )

    if gear_check is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(f"Gear with nickname {gear.nickname} already exists for user {user_id}"),
        )

    gear_data = _normalize_gear_payload(gear.model_dump(exclude_unset=True))
    new_gear = gears_models.Gear(**{**gear_data, "user_id": user_id})

    try:
        db.add(new_gear)
        db.commit()
        db.refresh(new_gear)
    except IntegrityError as integrity_err:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=("Duplicate entry error. Check if strava_gear_id or garminconnect_gear_id are unique"),
        ) from integrity_err

    return _transform_gears(new_gear)


@core_decorators.handle_db_errors
def edit_gear(
    gear: gears_schema.GearUpdate,
    user_id: int,
    db: Session,
) -> gears_schema.GearRead:
    """
    Edit an existing gear by ID and user ID.

    Args:
        gear: Gear schema with updated fields.
        user_id: Owner user ID.
        db: Database session.

    Returns:
        Updated GearRead schema.

    Raises:
        HTTPException: If a database error occurs.
    """
    db_gear = _get_gear_model_by_id_and_user_id_or_404(
        gear.id,
        user_id,
        db,
    )

    gear_data = _normalize_gear_payload(
        gear.model_dump(exclude_unset=True),
    )

    for key, value in gear_data.items():
        if key in _IMMUTABLE_FIELDS or value is None:
            continue
        setattr(db_gear, key, value)

    db.commit()
    db.refresh(db_gear)

    return _transform_gears(db_gear)


@core_decorators.handle_db_errors
def delete_gear(gear_id: int, user_id: int, db: Session) -> None:
    """
    Delete a gear by ID and user ID.

    Args:
        gear_id: Gear ID to delete.
        user_id: Owner user ID.
        db: Database session.

    Returns:
        None.

    Raises:
        HTTPException: If gear not found or
            a database error occurs.
    """
    db_gear = _get_gear_model_by_id_and_user_id_or_404(
        gear_id,
        user_id,
        db,
    )

    db.delete(db_gear)
    db.commit()


@core_decorators.handle_db_errors
def delete_all_strava_gear_for_user(user_id: int, db: Session) -> None:
    """
    Delete all Strava-linked gears for a user.

    Args:
        user_id: Owner user ID.
        db: Database session.

    Returns:
        None.

    Raises:
        HTTPException: If a database error occurs.
    """
    stmt = delete(gears_models.Gear).where(
        gears_models.Gear.user_id == user_id,
        gears_models.Gear.strava_gear_id.isnot(
            None,
        ),
    )
    db.execute(stmt)
    db.commit()


@core_decorators.handle_db_errors
def delete_all_garminconnect_gear_for_user(user_id: int, db: Session) -> None:
    """
    Delete all Garmin Connect-linked gears for a
    user.

    Args:
        user_id: Owner user ID.
        db: Database session.

    Returns:
        None.

    Raises:
        HTTPException: If a database error occurs.
    """
    stmt = delete(gears_models.Gear).where(
        gears_models.Gear.user_id == user_id,
        gears_models.Gear.garminconnect_gear_id.isnot(None),
    )
    db.execute(stmt)
    db.commit()
