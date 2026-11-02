"""Known-device operations exposed to auth peers."""

from sqlalchemy.orm import Session

import modules.auth.known_devices.contracts as known_devices_contracts
import modules.auth.known_devices.events as known_devices_events
import modules.auth.known_devices.service as known_devices_service


def record_sign_in(
    user_id: int,
    client_type: str,
    device_id: str | None,
    ip_address: str,
    user_agent: str,
    method: known_devices_events.SignInMethod,
    db: Session,
) -> known_devices_contracts.SignInRecord:
    """Stage a successful sign-in against the user's known devices, announcing a new one; the caller commits."""
    return known_devices_service.record_sign_in(user_id, client_type, device_id, ip_address, user_agent, method, db)
