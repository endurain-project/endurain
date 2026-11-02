"""Persistence operations for known devices."""

from datetime import datetime

from sqlalchemy import delete, exists, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import modules.auth.known_devices.models as known_devices_models


def has_devices(user_id: int, db: Session) -> bool:
    """Return whether any device is known for a user."""
    model = known_devices_models.KnownDevice
    return bool(db.execute(select(exists().where(model.user_id == user_id))).scalar())


def touch_device(user_id: int, device_hash: str, seen_at: datetime, db: Session) -> bool:
    """Stage a new last-seen time for a device the user is known to sign in from.

    Args:
        user_id: The user who signed in.
        device_hash: SHA-256 hex digest of the device id.
        seen_at: When the user signed in.
        db: Database session.

    Returns:
        True when the device is known for the user, False when there is no row to update.
    """
    model = known_devices_models.KnownDevice
    result = db.execute(
        update(model).where(model.user_id == user_id, model.device_hash == device_hash).values(last_seen_at=seen_at)
    )
    db.flush()
    return result.rowcount == 1


def create_device(user_id: int, device_hash: str, seen_at: datetime, db: Session) -> None:
    """Stage a device the user signed in from for the first time.

    The insert runs in a savepoint, so a concurrent sign-in that registered the same device first leaves the
    caller's transaction usable.

    Args:
        user_id: The user who signed in.
        device_hash: SHA-256 hex digest of the device id.
        seen_at: When the user signed in.
        db: Database session.

    Raises:
        ConflictError: When the device is already known for the user.
    """
    row = known_devices_models.KnownDevice(
        user_id=user_id, device_hash=device_hash, created_at=seen_at, last_seen_at=seen_at
    )
    db.flush()
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError as err:
        raise core_exceptions.ConflictError("Device already known for the user") from err


def delete_unseen_since(cutoff: datetime, limit: int, db: Session) -> int:
    """Stage deletion of up to ``limit`` devices last seen before ``cutoff``."""
    model = known_devices_models.KnownDevice
    unseen = select(model.id).where(model.last_seen_at < cutoff).limit(limit)
    result = db.execute(delete(model).where(model.id.in_(unseen)))
    db.flush()
    return result.rowcount or 0
