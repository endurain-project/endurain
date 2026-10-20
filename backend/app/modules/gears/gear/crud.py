"""CRUD operations for gear."""

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import modules.gears.gear.models as gears_models
import modules.gears.gear.schema as gears_schema
import modules.gears.gear.serializers as gears_serializers

_DUPLICATE_EXTERNAL_ID = "Duplicate entry error. Check if strava_gear_id or garminconnect_gear_id are unique"


def _get_gear_model_or_404(gear_id: int, user_id: int, db: Session) -> gears_models.Gear:
    """Load a user's gear row for a write.

    Args:
        gear_id: Gear ID to fetch.
        user_id: Owner user ID.
        db: Database session.

    Returns:
        The mapped Gear ORM instance.

    Raises:
        NotFoundError: If the user has no such gear.
    """
    stmt = select(gears_models.Gear).where(
        gears_models.Gear.id == gear_id,
        gears_models.Gear.user_id == user_id,
    )
    db_gear = db.execute(stmt).scalar_one_or_none()
    if db_gear is None:
        raise core_exceptions.NotFoundError("Gear not found")
    return db_gear


def get_gear_user_by_id(user_id: int, gear_id: int, db: Session) -> gears_schema.GearRead | None:
    """Retrieve a gear by ID for a specific user.

    Args:
        user_id: Owner user ID.
        gear_id: Gear ID to fetch.
        db: Database session.

    Returns:
        The gear, or None if the user has no such gear.
    """
    stmt = select(gears_models.Gear).where(
        gears_models.Gear.user_id == user_id,
        gears_models.Gear.id == gear_id,
    )
    db_gear = db.execute(stmt).scalar_one_or_none()
    return gears_serializers.to_read_schema(db_gear) if db_gear is not None else None


def get_gears_number(user_id: int, db: Session, *, show_inactive: bool | None = True) -> int:
    """Count a user's gears, honoring the active filter.

    Args:
        user_id: Owner user ID.
        db: Database session.
        show_inactive: Include inactive gears.

    Returns:
        Number of gears matching the filter.
    """
    stmt = select(func.count(gears_models.Gear.id)).where(gears_models.Gear.user_id == user_id)
    if show_inactive is False:
        stmt = stmt.where(gears_models.Gear.active.is_(True))
    return db.execute(stmt).scalar_one()


def get_gear_users_with_pagination(
    user_id: int,
    db: Session,
    *,
    page_number: int | None = None,
    num_records: int | None = None,
    show_inactive: bool | None = True,
) -> list[gears_schema.GearRead]:
    """Retrieve a user's gears ordered by nickname, one page when both page arguments are given.

    Args:
        user_id: Owner user ID.
        db: Database session.
        page_number: Page number (1-indexed).
        num_records: Records per page.
        show_inactive: Include inactive gears.

    Returns:
        The gears on the page, or all of them when unpaginated.
    """
    stmt = select(gears_models.Gear).where(gears_models.Gear.user_id == user_id)
    if show_inactive is False:
        stmt = stmt.where(gears_models.Gear.active.is_(True))
    stmt = stmt.order_by(gears_models.Gear.nickname)
    if page_number is not None and num_records is not None:
        stmt = stmt.offset((page_number - 1) * num_records).limit(num_records)
    return [gears_serializers.to_read_schema(gear) for gear in db.execute(stmt).scalars().all()]


def get_gear_user(user_id: int, db: Session) -> list[gears_schema.GearRead]:
    """Retrieve all gears for a specific user.

    Args:
        user_id: Owner user ID.
        db: Database session.

    Returns:
        The user's gears (empty list if none).
    """
    stmt = select(gears_models.Gear).where(gears_models.Gear.user_id == user_id)
    return [gears_serializers.to_read_schema(gear) for gear in db.execute(stmt).scalars().all()]


def get_gear_user_contains_nickname(user_id: int, nickname: str, db: Session) -> list[gears_schema.GearRead]:
    """Retrieve gears matching a nickname substring, case-insensitively.

    Args:
        user_id: Owner user ID.
        nickname: Substring to search for.
        db: Database session.

    Returns:
        The matching gears (empty list if none).
    """
    parsed_nickname = nickname.lower().strip()
    stmt = select(gears_models.Gear).where(
        func.lower(gears_models.Gear.nickname).like(f"%{parsed_nickname}%"),
        gears_models.Gear.user_id == user_id,
    )
    return [gears_serializers.to_read_schema(gear) for gear in db.execute(stmt).scalars().all()]


def get_gear_user_by_nickname(user_id: int, nickname: str, db: Session) -> gears_schema.GearRead | None:
    """Retrieve a gear by exact, case-insensitive nickname for a user.

    Args:
        user_id: Owner user ID.
        nickname: Gear nickname to match.
        db: Database session.

    Returns:
        The gear, or None if there is no match.
    """
    parsed_nickname = nickname.lower().strip()
    stmt = select(gears_models.Gear).where(
        func.lower(gears_models.Gear.nickname) == parsed_nickname,
        gears_models.Gear.user_id == user_id,
    )
    db_gear = db.execute(stmt).scalar_one_or_none()
    return gears_serializers.to_read_schema(db_gear) if db_gear else None


def get_existing_nicknames(user_id: int, nicknames: set[str], db: Session) -> set[str]:
    """Return which of the given nicknames the user already has, lower-cased.

    One query for the whole set instead of one per gear.

    Args:
        user_id: Owner user ID.
        nicknames: Normalized (lower-cased, trimmed) nicknames to look for.
        db: Database session.

    Returns:
        The subset that already exists for the user, normalized.
    """
    stmt = select(gears_models.Gear.nickname).where(
        gears_models.Gear.user_id == user_id,
        func.lower(gears_models.Gear.nickname).in_(nicknames),
    )
    return {row[0].lower().strip() for row in db.execute(stmt).all()}


def get_gear_by_type_and_user(gear_type: int, user_id: int, db: Session) -> list[gears_schema.GearRead]:
    """Retrieve gears by type for a specific user, ordered by nickname.

    Args:
        gear_type: Gear type identifier.
        user_id: Owner user ID.
        db: Database session.

    Returns:
        The matching gears (empty list if none).
    """
    stmt = (
        select(gears_models.Gear)
        .where(
            gears_models.Gear.gear_type == gear_type,
            gears_models.Gear.user_id == user_id,
        )
        .order_by(gears_models.Gear.nickname)
    )
    return [gears_serializers.to_read_schema(gear) for gear in db.execute(stmt).scalars().all()]


def get_gear_by_strava_id_from_user_id(gear_strava_id: str, user_id: int, db: Session) -> gears_schema.GearRead | None:
    """Retrieve a gear by Strava ID for a user.

    Args:
        gear_strava_id: Strava gear identifier.
        user_id: Owner user ID.
        db: Database session.

    Returns:
        The gear, or None if there is no match.
    """
    stmt = select(gears_models.Gear).where(
        gears_models.Gear.user_id == user_id,
        gears_models.Gear.strava_gear_id == gear_strava_id,
    )
    db_gear = db.execute(stmt).scalar_one_or_none()
    return gears_serializers.to_read_schema(db_gear) if db_gear else None


def get_gear_by_garminconnect_id_from_user_id(
    gear_garminconnect_id: str, user_id: int, db: Session
) -> gears_schema.GearRead | None:
    """Retrieve a gear by Garmin Connect ID for a user.

    Args:
        gear_garminconnect_id: Garmin Connect gear ID.
        user_id: Owner user ID.
        db: Database session.

    Returns:
        The gear, or None if there is no match.
    """
    stmt = select(gears_models.Gear).where(
        gears_models.Gear.user_id == user_id,
        gears_models.Gear.garminconnect_gear_id == gear_garminconnect_id,
    )
    db_gear = db.execute(stmt).scalar_one_or_none()
    return gears_serializers.to_read_schema(db_gear) if db_gear else None


def create_gears(gears: list[gears_schema.GearCreate], user_id: int, db: Session) -> None:
    """Stage new gears for a user.

    Args:
        gears: Gear payloads to create.
        user_id: Owner user ID.
        db: Database session.

    Raises:
        ConflictError: If a Strava or Garmin Connect gear ID is already taken.
    """
    try:
        db.add_all([gears_serializers.to_orm(gear, user_id) for gear in gears])
        db.flush()
    except IntegrityError as err:
        raise core_exceptions.ConflictError(_DUPLICATE_EXTERNAL_ID) from err


def create_gear(gear: gears_schema.GearCreate, user_id: int, db: Session) -> gears_schema.GearRead:
    """Stage a new gear for a user.

    Args:
        gear: Gear payload to create.
        user_id: Owner user ID.
        db: Database session.

    Returns:
        The staged gear with its generated ID.

    Raises:
        ConflictError: If a Strava or Garmin Connect gear ID is already taken.
    """
    new_gear = gears_serializers.to_orm(gear, user_id)
    try:
        db.add(new_gear)
        db.flush()
    except IntegrityError as err:
        raise core_exceptions.ConflictError(_DUPLICATE_EXTERNAL_ID) from err
    db.refresh(new_gear)
    return gears_serializers.to_read_schema(new_gear)


def edit_gear(gear: gears_schema.GearUpdate, user_id: int, db: Session) -> gears_schema.GearRead:
    """Stage an update to a user's gear.

    Args:
        gear: Gear payload with the fields to change.
        user_id: Owner user ID.
        db: Database session.

    Returns:
        The updated gear.

    Raises:
        NotFoundError: If the user has no such gear.
    """
    db_gear = _get_gear_model_or_404(gear.id, user_id, db)
    for key, value in gears_serializers.to_update_values(gear).items():
        setattr(db_gear, key, value)
    db.flush()
    db.refresh(db_gear)
    return gears_serializers.to_read_schema(db_gear)


def delete_gear(gear_id: int, user_id: int, db: Session) -> None:
    """Stage the deletion of a user's gear.

    Args:
        gear_id: Gear ID to delete.
        user_id: Owner user ID.
        db: Database session.

    Raises:
        NotFoundError: If the user has no such gear.
    """
    db.delete(_get_gear_model_or_404(gear_id, user_id, db))
    db.flush()


def delete_all_strava_gear_for_user(user_id: int, db: Session) -> None:
    """Stage the deletion of every Strava-linked gear a user has.

    Args:
        user_id: Owner user ID.
        db: Database session.
    """
    db.execute(
        delete(gears_models.Gear).where(
            gears_models.Gear.user_id == user_id,
            gears_models.Gear.strava_gear_id.isnot(None),
        )
    )
    db.flush()
