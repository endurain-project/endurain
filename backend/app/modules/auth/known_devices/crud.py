"""Persistence operations for known devices."""

from datetime import datetime

from sqlalchemy import delete, exists, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import core.database as core_database
import core.exceptions as core_exceptions
import modules.auth.known_devices.contracts as known_devices_contracts
import modules.auth.known_devices.models as known_devices_models


def has_devices(user_id: int, db: Session) -> bool:
    """Return whether the user has any registered device, whatever its security generation."""
    model = known_devices_models.KnownDevice
    return bool(db.execute(select(exists().where(model.user_id == user_id))).scalar())


def has_device(user_id: int, device_hash: str, generation: int, db: Session) -> bool:
    """Return whether the device is known for the user under the account's security generation."""
    model = known_devices_models.KnownDevice
    return bool(
        db.execute(
            select(
                exists().where(
                    model.user_id == user_id,
                    model.device_hash == device_hash,
                    model.security_generation == generation,
                )
            )
        ).scalar()
    )


def touch_device(
    user_id: int,
    device_hash: str,
    generation: int,
    seen_at: datetime,
    description: known_devices_contracts.DeviceDescription,
    db: Session,
) -> bool:
    """Stage a new last-seen time and description for a device known under the current security generation.

    Args:
        user_id: The user who signed in.
        device_hash: SHA-256 hex digest of the device id.
        generation: The account's current security generation.
        seen_at: When the user signed in.
        description: How the sign-in's user agent describes the device.
        db: Database session.

    Returns:
        True when the device is known for the user, False when there is no row of the current generation to update.
    """
    model = known_devices_models.KnownDevice
    matched = core_database.rowcount(
        db,
        update(model)
        .where(model.user_id == user_id, model.device_hash == device_hash, model.security_generation == generation)
        .values(
            last_seen_at=seen_at,
            browser=description.browser,
            operating_system=description.operating_system,
            device_type=description.device_type,
        ),
    )
    db.flush()
    return matched == 1


def restamp_device(
    user_id: int,
    device_hash: str,
    generation: int,
    seen_at: datetime,
    description: known_devices_contracts.DeviceDescription,
    db: Session,
) -> bool:
    """Stage the registration of a device a security change made unknown, under the current security generation.

    Args:
        user_id: The user who signed in.
        device_hash: SHA-256 hex digest of the device id.
        generation: The account's current security generation.
        seen_at: When the user signed in.
        description: How the sign-in's user agent describes the device.
        db: Database session.

    Returns:
        True when a row of an older generation was re-registered, False when there is none.
    """
    model = known_devices_models.KnownDevice
    matched = core_database.rowcount(
        db,
        update(model)
        .where(model.user_id == user_id, model.device_hash == device_hash, model.security_generation != generation)
        .values(
            security_generation=generation,
            created_at=seen_at,
            last_seen_at=seen_at,
            browser=description.browser,
            operating_system=description.operating_system,
            device_type=description.device_type,
        ),
    )
    db.flush()
    return matched == 1


def create_device(
    user_id: int,
    device_hash: str,
    generation: int,
    seen_at: datetime,
    description: known_devices_contracts.DeviceDescription,
    db: Session,
) -> None:
    """Stage a device the user signed in from for the first time.

    The insert runs in a savepoint, so a concurrent sign-in that registered the same device first leaves the
    caller's transaction usable.

    Args:
        user_id: The user who signed in.
        device_hash: SHA-256 hex digest of the device id.
        generation: The account's current security generation.
        seen_at: When the user signed in.
        description: How the sign-in's user agent describes the device.
        db: Database session.

    Raises:
        ConflictError: When the device is already registered for the user.
    """
    row = known_devices_models.KnownDevice(
        user_id=user_id,
        device_hash=device_hash,
        created_at=seen_at,
        last_seen_at=seen_at,
        security_generation=generation,
        browser=description.browser,
        operating_system=description.operating_system,
        device_type=description.device_type,
    )
    db.flush()
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError as err:
        raise core_exceptions.ConflictError("Device already known for the user") from err


def get_devices_page(
    user_id: int, generation: int, limit: int, offset: int, db: Session
) -> list[known_devices_models.KnownDevice]:
    """Return one page of the user's devices known under the current security generation, latest sign-in first."""
    model = known_devices_models.KnownDevice
    stmt = (
        select(model)
        .where(model.user_id == user_id, model.security_generation == generation)
        .order_by(model.last_seen_at.desc(), model.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(db.execute(stmt).scalars().all())


def count_devices(user_id: int, generation: int, db: Session) -> int:
    """Return how many devices the user has under the current security generation."""
    model = known_devices_models.KnownDevice
    stmt = (
        select(func.count()).select_from(model).where(model.user_id == user_id, model.security_generation == generation)
    )
    return db.execute(stmt).scalar_one()


def delete_device(device_id: int, user_id: int, generation: int, db: Session) -> str | None:
    """Stage the deletion of one of the user's devices known under the current security generation.

    Returns:
        The SHA-256 hex digest of the deleted device's id, or None when the user has no such device.
    """
    model = known_devices_models.KnownDevice
    device_hash = db.execute(
        delete(model)
        .where(model.id == device_id, model.user_id == user_id, model.security_generation == generation)
        .returning(model.device_hash)
    ).scalar_one_or_none()
    db.flush()
    return device_hash


def delete_unseen_since(cutoff: datetime, limit: int, db: Session) -> int:
    """Stage deletion of up to ``limit`` devices last seen before ``cutoff``."""
    model = known_devices_models.KnownDevice
    unseen = select(model.id).where(model.last_seen_at < cutoff).limit(limit)
    matched = core_database.rowcount(db, delete(model).where(model.id.in_(unseen)))
    db.flush()
    return matched
