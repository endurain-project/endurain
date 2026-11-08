"""Record each sign-in against the devices a user is known to sign in from, and announce a new one."""

import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

import core.database as core_database
import core.exceptions as core_exceptions
import core.hashing as core_hashing
import core.logger as core_logger
import modules.auth.known_devices.constants as known_devices_constants
import modules.auth.known_devices.contracts as known_devices_contracts
import modules.auth.known_devices.crud as known_devices_crud
import modules.auth.known_devices.event_publishers as known_devices_event_publishers
import modules.auth.known_devices.events as known_devices_events
import modules.auth.sessions.integration_service as sessions_integration
import modules.users.users.integration_service as users_integration

logger = core_logger.get_logger(__name__)


def _publish_new_device_sign_in(
    user_id: int,
    ip_address: str,
    user_agent: str,
    method: known_devices_events.SignInMethod,
    signed_in_at: datetime,
    db: Session,
) -> None:
    """Stage the event of a sign-in from a new device, naming the device as the user agent describes it."""
    device = sessions_integration.parse_user_agent(user_agent)
    known_devices_event_publishers.publish_new_device_sign_in(
        user_id,
        db,
        browser=device.browser,
        operating_system=device.operating_system,
        device_type=device.device_type.value,
        ip_address=ip_address,
        method=method,
        signed_in_at=signed_in_at,
    )


def is_known_device(user_id: int, device_id: str | None, db: Session) -> bool:
    """Return whether a device id names a device the user signed in from before.

    Args:
        user_id: The user the device would belong to.
        device_id: The device id the client sent, or None when it sent no valid one.
        db: Database session.

    Returns:
        True when the id hashes to a device of the user; a lookup changes nothing.
    """
    if device_id is None:
        return False
    return known_devices_crud.has_device(user_id, core_hashing.sha256_hex(device_id), db)


def record_sign_in(
    user_id: int,
    device_id: str | None,
    ip_address: str,
    user_agent: str,
    method: known_devices_events.SignInMethod,
    db: Session,
) -> known_devices_contracts.SignInRecord:
    """Stage a successful sign-in against the user's known devices; the caller commits.

    A client is known by the device id it sends: the web app's cookie or the mobile app's ``X-Device-Id`` header. A
    device the user signed in from before is only seen again; any other is registered under the id the client
    already holds, or a new one when it holds none, and announced with ``auth.new_device_sign_in``. The first device
    of a user who has none is registered without the announcement only while the account is younger than
    ``FIRST_DEVICE_GRACE``, so a new account, or the first sign-in just after this feature arrived, sends none. The
    first device of an older account, such as one that never signed in or whose devices were all forgotten, is
    announced.

    Args:
        user_id: The user who signed in.
        device_id: The device id the client sent, or None when it sent no valid one.
        ip_address: The client address of the sign-in.
        user_agent: The client user agent of the sign-in.
        method: How the user signed in.
        db: Database session.

    Returns:
        The device id the client must keep and whether the sign-in was announced as one from a new device.
    """
    signed_in_at = datetime.now(UTC)
    if device_id is None:
        device_id = secrets.token_urlsafe(known_devices_constants.DEVICE_ID_BYTES)
    device_hash = core_hashing.sha256_hex(device_id)
    if known_devices_crud.touch_device(user_id, device_hash, signed_in_at, db):
        return known_devices_contracts.SignInRecord(device_id=device_id, new_device=False)

    silent = not known_devices_crud.has_devices(user_id, db) and users_integration.was_created_after(
        user_id, signed_in_at - known_devices_constants.FIRST_DEVICE_GRACE, db
    )
    try:
        known_devices_crud.create_device(user_id, device_hash, signed_in_at, db)
    except core_exceptions.ConflictError:
        # A concurrent sign-in from the same client registered the device first and announces it.
        return known_devices_contracts.SignInRecord(device_id=device_id, new_device=False)
    logger.debug("Registered a new device for user <user_id>", extra=core_logger.context(user_id=user_id))
    if not silent:
        _publish_new_device_sign_in(user_id, ip_address, user_agent, method, signed_in_at, db)
    return known_devices_contracts.SignInRecord(device_id=device_id, new_device=not silent)


def delete_unseen_devices(now: datetime, db: Session) -> int:
    """Delete devices no sign-in has used for the retention period, one batch per commit.

    Args:
        now: The current time.
        db: Database session.

    Returns:
        The number of devices deleted.
    """
    cutoff = now - timedelta(days=known_devices_constants.DEVICE_RETENTION_DAYS)
    return core_database.delete_in_batches(lambda limit: known_devices_crud.delete_unseen_since(cutoff, limit, db), db)
