"""Known devices as the application stores them, for tests on the real database."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

import modules.auth.constants as auth_constants
import modules.auth.known_devices.contracts as known_devices_contracts
import modules.auth.known_devices.crud as known_devices_crud
import modules.auth.known_devices.models as known_devices_models
import modules.auth.security_generation.integration_service as security_generation_integration
import modules.auth.sessions.integration_service as sessions_integration
import modules.users.users.schema as users_schema


def make_known_device(db: Session, user_id: uuid.UUID, device_hash: str) -> uuid.UUID:
    """Stage a device the user signed in from, under the account's current security generation.

    Args:
        db: Database session; the device is flushed, not committed.
        user_id: The device's owner.
        device_hash: SHA-256 hex digest of the device id; a test gives each device its own.

    Returns:
        The device's id, which the routes name it by.
    """
    known_devices_crud.create_device(
        user_id,
        device_hash,
        security_generation_integration.current_generation(user_id, db),
        datetime.now(UTC),
        known_devices_contracts.DeviceDescription(browser="Firefox", operating_system="Linux", device_type="PC"),
        db,
    )
    return db.scalars(
        select(known_devices_models.KnownDevice.id).where(
            known_devices_models.KnownDevice.user_id == user_id,
            known_devices_models.KnownDevice.device_hash == device_hash,
        )
    ).one()


def make_device_session(db: Session, user: users_schema.UserRead, device_hash: str | None) -> uuid.UUID:
    """Stage a web session of the user, tied to a known device when a hash is given.

    Args:
        db: Database session; the session is flushed, not committed.
        user: The session's owner.
        device_hash: SHA-256 hex digest of the device id the session signed in from, or None for a session that
            predates device tracking.

    Returns:
        The session's id.
    """
    session_id = uuid.uuid4()
    sessions_integration.create_session(
        session_id,
        user,
        auth_constants.ClientType.WEB,
        "203.0.113.7",
        "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0",
        "refresh-token",
        datetime.now(UTC) + timedelta(days=1),
        db,
        amr=["pwd"],
        device_hash=device_hash,
    )
    db.flush()
    return session_id
