"""CRUD operations for user default gear."""

import uuid
from collections.abc import Collection

from sqlalchemy import case, or_, select
from sqlalchemy import update as sa_update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import core.etag as core_etag
import core.exceptions as core_exceptions
import modules.users.users_default_gear.constants as users_default_gear_constants
import modules.users.users_default_gear.models as users_default_gear_models
import modules.users.users_default_gear.schema as users_default_gear_schema
import modules.users.users_default_gear.serializers as users_default_gear_serializers


def _select_by_user_id(user_id: uuid.UUID, db: Session) -> users_default_gear_models.UsersDefaultGear | None:
    """Select a user's default gear ORM row.

    Args:
        user_id: The ID of the user.
        db: Database session.

    Returns:
        The ORM row, or None if the user has none.
    """
    stmt = select(users_default_gear_models.UsersDefaultGear).where(
        users_default_gear_models.UsersDefaultGear.user_id == user_id
    )
    return db.execute(stmt).scalar_one_or_none()


def get_user_default_gear_by_user_id(
    user_id: uuid.UUID,
    db: Session,
) -> users_default_gear_schema.UserDefaultGearRead | None:
    """Retrieve default gear settings for a specific user.

    Args:
        user_id: The ID of the user to fetch settings for.
        db: Database session.

    Returns:
        The default gear settings, or None if not found.
    """
    db_default_gear = _select_by_user_id(user_id, db)
    return users_default_gear_serializers.to_read_schema(db_default_gear) if db_default_gear else None


def create_user_default_gear(
    user_id: uuid.UUID,
    db: Session,
) -> users_default_gear_schema.UserDefaultGearRead:
    """Stage empty default gear settings for a user (flushed, not committed).

    Args:
        user_id: The ID of the user to create settings for.
        db: Database session.

    Returns:
        The created default gear settings.

    Raises:
        ConflictError: If settings already exist for the user.
    """
    db_default_gear = users_default_gear_models.UsersDefaultGear(user_id=user_id)
    try:
        db.add(db_default_gear)
        db.flush()
        db.refresh(db_default_gear)
    except IntegrityError as err:
        raise core_exceptions.ConflictError("Default gear settings already exist for this user") from err

    return users_default_gear_serializers.to_read_schema(db_default_gear)


def edit_user_default_gear(
    user_default_gear: users_default_gear_schema.UserDefaultGearUpdate,
    user_id: uuid.UUID,
    db: Session,
    *,
    if_match: str,
) -> users_default_gear_schema.UserDefaultGearRead:
    """Stage an update of a user's default gear settings (flushed, not committed).

    Performs no ownership check on the gears: that is decided by
    :mod:`modules.users.users_default_gear.service`.

    Args:
        user_default_gear: Schema with gear fields to update.
        user_id: The ID of the user.
        db: Database session.
        if_match: The ``If-Match`` precondition.

    Returns:
        The updated default gear settings.

    Raises:
        NotFoundError: If the user has no default gear settings.
        PreconditionFailedError: When ``if_match`` does not name the row's version.
    """
    db_default_gear = _select_by_user_id(user_id, db)
    if db_default_gear is None:
        raise core_exceptions.NotFoundError("User default gear not found")
    core_etag.require_if_match(if_match, db_default_gear.version, "default gear")

    for key, value in user_default_gear.model_dump(exclude_unset=True).items():
        setattr(db_default_gear, key, value)

    db.flush()
    db.refresh(db_default_gear)

    return users_default_gear_serializers.to_read_schema(db_default_gear)


def clear_gears(gear_ids: Collection[uuid.UUID], user_id: uuid.UUID, db: Session) -> None:
    """Stage unassigning gears from every default-gear column of a user that names them.

    The gear foreign keys null a column when the gear is deleted, but they do not touch
    ``version``, so the statement nulls the columns and bumps the version itself. It changes
    nothing, version included, when no column names one of the gears.

    Args:
        gear_ids: The gears being removed.
        user_id: The owning user ID.
        db: Database session.
    """
    if not gear_ids:
        return
    columns = [
        getattr(users_default_gear_models.UsersDefaultGear, name)
        for name in sorted(set(users_default_gear_constants.ACTIVITY_TYPE_TO_GEAR_ATTR.values()))
    ]
    stmt = (
        sa_update(users_default_gear_models.UsersDefaultGear)
        .where(
            users_default_gear_models.UsersDefaultGear.user_id == user_id,
            or_(*(column.in_(gear_ids) for column in columns)),
        )
        .values(
            {
                **{column.key: case((column.in_(gear_ids), None), else_=column) for column in columns},
                # Core UPDATEs bypass the ORM version bump, so an ETag would survive a
                # change it should have invalidated.
                "version": users_default_gear_models.UsersDefaultGear.version + 1,
            }
        )
        .execution_options(synchronize_session=False)
    )
    db.execute(stmt)
    db.flush()
