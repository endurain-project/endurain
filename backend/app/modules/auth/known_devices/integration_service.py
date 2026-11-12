"""Known-device operations exposed to auth peers."""

import uuid

from sqlalchemy.orm import Session

import core.pagination as core_pagination
import modules.auth.known_devices.contracts as known_devices_contracts
import modules.auth.known_devices.events as known_devices_events
import modules.auth.known_devices.schema as known_devices_schema
import modules.auth.known_devices.service as known_devices_service


def is_known_device(user_id: int, device_id: str | None, db: Session) -> bool:
    """Return whether the device id names a device the user signed in from since their last security change.

    It changes nothing.
    """
    return known_devices_service.is_known_device(user_id, device_id, db)


def record_sign_in(
    user_id: int,
    device_id: str | None,
    ip_address: str,
    user_agent: str,
    method: known_devices_events.SignInMethod,
    db: Session,
) -> known_devices_contracts.SignInRecord:
    """Stage a successful sign-in against the user's known devices, announcing a new one; the caller commits."""
    return known_devices_service.record_sign_in(user_id, device_id, ip_address, user_agent, method, db)


def list_devices(
    user_id: int, device_id: str | None, page: core_pagination.PageParams, db: Session
) -> known_devices_schema.KnownDevicePage:
    """Return one page of the user's known devices, marking the one the request's device id names."""
    return known_devices_service.list_devices(user_id, device_id, page, db)


def forget_device(device_id: uuid.UUID, user_id: int, current_device_id: str | None, db: Session) -> int:
    """Stage the deletion of one of the user's known devices but the request's own and its sessions.

    Returns how many sessions ended.
    """
    return known_devices_service.forget_device(device_id, user_id, current_device_id, db)


def forget_other_devices(user_id: int, device_id: str | None, db: Session) -> int:
    """Stage the deletion of the user's known devices but the request's own and their sessions; returns how many ended."""
    return known_devices_service.forget_other_devices(user_id, device_id, db)
