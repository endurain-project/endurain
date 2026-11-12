"""Record each sign-in against the devices a user is known to sign in from, and announce a new one."""

import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

import core.database as core_database
import core.exceptions as core_exceptions
import core.hashing as core_hashing
import core.logger as core_logger
import core.pagination as core_pagination
import modules.auth.known_devices.constants as known_devices_constants
import modules.auth.known_devices.contracts as known_devices_contracts
import modules.auth.known_devices.crud as known_devices_crud
import modules.auth.known_devices.event_publishers as known_devices_event_publishers
import modules.auth.known_devices.events as known_devices_events
import modules.auth.known_devices.schema as known_devices_schema
import modules.auth.security_generation.integration_service as security_generation_integration
import modules.auth.sessions.integration_service as sessions_integration
import modules.users.users.integration_service as users_integration

logger = core_logger.get_logger(__name__)


def _describe(user_agent: str) -> known_devices_contracts.DeviceDescription:
    """Return how a user agent describes the device, as sessions record it."""
    device = sessions_integration.parse_user_agent(user_agent)
    return known_devices_contracts.DeviceDescription(
        browser=device.browser, operating_system=device.operating_system, device_type=device.device_type.value
    )


def _publish_new_device_sign_in(
    user_id: int,
    description: known_devices_contracts.DeviceDescription,
    ip_address: str,
    method: known_devices_events.SignInMethod,
    signed_in_at: datetime,
    db: Session,
) -> None:
    """Stage the event of a sign-in from a new device, naming the device as its description does."""
    known_devices_event_publishers.publish_new_device_sign_in(
        user_id,
        db,
        browser=description.browser,
        operating_system=description.operating_system,
        device_type=description.device_type,
        ip_address=ip_address,
        method=method,
        signed_in_at=signed_in_at,
    )


def is_known_device(user_id: int, device_id: str | None, db: Session) -> bool:
    """Return whether a device id names a device the user signed in from since their last security change.

    Args:
        user_id: The user the device would belong to.
        device_id: The device id the client sent, or None when it sent no valid one.
        db: Database session.

    Returns:
        True when the id hashes to a device of the user registered under the account's current security generation,
        so a security change makes every device unknown; a lookup changes nothing.
    """
    if device_id is None:
        return False
    generation = security_generation_integration.current_generation(user_id, db)
    return known_devices_crud.has_device(user_id, core_hashing.sha256_hex(device_id), generation, db)


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
    device registered under the account's current security generation is only seen again, and its description is
    refreshed; any other, including one a security change made unknown, is registered under the id the client
    already holds, or a new one when it holds none, and announced with ``auth.new_device_sign_in``. The first
    device of a user who has none is registered without the announcement only while the account is younger than
    ``FIRST_DEVICE_GRACE``, so a new account sends none. The first device of an older account, such as one that
    never signed in or whose devices were all forgotten, is announced.

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
    generation = security_generation_integration.current_generation(user_id, db)
    description = _describe(user_agent)
    if known_devices_crud.touch_device(user_id, device_hash, generation, signed_in_at, description, db):
        return known_devices_contracts.SignInRecord(device_id=device_id, new_device=False)

    silent = not known_devices_crud.has_devices(user_id, db) and users_integration.was_created_after(
        user_id, signed_in_at - known_devices_constants.FIRST_DEVICE_GRACE, db
    )
    if not known_devices_crud.restamp_device(user_id, device_hash, generation, signed_in_at, description, db):
        try:
            known_devices_crud.create_device(user_id, device_hash, generation, signed_in_at, description, db)
        except core_exceptions.ConflictError:
            # A concurrent sign-in from the same client registered the device first and announces it.
            return known_devices_contracts.SignInRecord(device_id=device_id, new_device=False)
    logger.debug("Registered a new device for user <user_id>", extra=core_logger.context(user_id=user_id))
    if not silent:
        _publish_new_device_sign_in(user_id, description, ip_address, method, signed_in_at, db)
    return known_devices_contracts.SignInRecord(device_id=device_id, new_device=not silent)


def list_devices(
    user_id: int, device_id: str | None, page: core_pagination.PageParams, db: Session
) -> known_devices_schema.KnownDevicePage:
    """Return one page of the devices the user is known to sign in from, marking the one the request comes from.

    Args:
        user_id: The user whose devices to list.
        device_id: The device id the request carries, or None when it carries no valid one.
        page: The requested window.
        db: Database session.

    Returns:
        The devices registered under the account's current security generation, latest sign-in first.
    """
    generation = security_generation_integration.current_generation(user_id, db)
    current_hash = None if device_id is None else core_hashing.sha256_hex(device_id)
    devices = known_devices_crud.get_devices_page(
        user_id, generation, page.num_records, (page.page_number - 1) * page.num_records, db
    )
    return known_devices_schema.KnownDevicePage.build(
        [
            known_devices_schema.KnownDeviceRead.model_validate(device).model_copy(
                update={"current": device.device_hash == current_hash}
            )
            for device in devices
        ],
        known_devices_crud.count_devices(user_id, generation, db),
        page.page_number,
        page.num_records,
    )


def forget_device(device_id: uuid.UUID, user_id: int, current_device_id: str | None, db: Session) -> int:
    """Stage the deletion of a known device and of the sessions that signed in from it; the caller commits.

    A session created before sessions recorded their device has no hash and is not ended.

    Args:
        device_id: ID of the device to forget.
        user_id: The user who owns the device.
        current_device_id: The device id the request carries, or None when it carries no valid one.
        db: Database session.

    Returns:
        The number of sessions ended.

    Raises:
        NotFoundError: When the user has no such known device.
        ConflictError: When the device is the one the request comes from.
    """
    generation = security_generation_integration.current_generation(user_id, db)
    device_hash = known_devices_crud.get_device_hash(device_id, user_id, generation, db)
    if device_hash is None:
        raise core_exceptions.NotFoundError("Device not found")
    if current_device_id is not None and device_hash == core_hashing.sha256_hex(current_device_id):
        raise core_exceptions.ConflictError("The current device cannot be forgotten")
    known_devices_crud.delete_device(device_id, user_id, generation, db)
    return sessions_integration.delete_sessions_by_device(user_id, device_hash, db)


def forget_other_devices(user_id: int, device_id: str | None, db: Session) -> int:
    """Stage the deletion of the user's known devices but the request's own, and of their sessions; the caller commits.

    A session created before sessions recorded their device has no hash and is not ended.

    Args:
        user_id: The user who owns the devices.
        device_id: The device id the request carries, or None when it carries no valid one, which keeps no device.
        db: Database session.

    Returns:
        The number of sessions ended.
    """
    generation = security_generation_integration.current_generation(user_id, db)
    keep_hash = None if device_id is None else core_hashing.sha256_hex(device_id)
    device_hashes = known_devices_crud.delete_devices_except(user_id, generation, keep_hash, db)
    return sum(
        sessions_integration.delete_sessions_by_device(user_id, device_hash, db) for device_hash in device_hashes
    )


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
