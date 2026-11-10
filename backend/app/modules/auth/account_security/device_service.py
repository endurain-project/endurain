"""Known-device operations owned by account security: listing and forgetting a user's devices."""

import jasil.audit as jasil_audit
from sqlalchemy.orm import Session

import core.logger as core_logger
import core.pagination as core_pagination
import modules.auth.account_security.audit_actions as account_security_audit_actions
import modules.auth.account_security.step_up_service as step_up_service
import modules.auth.account_security.step_up_store as step_up_store_module
import modules.auth.identity_providers.constants as identity_providers_constants
import modules.auth.known_devices.integration_service as known_devices_integration
import modules.auth.known_devices.schema as known_devices_schema
import modules.auth.schema as auth_schema

logger = core_logger.get_logger(__name__)


def list_user_devices(
    user_id: int, device_id: str | None, page: core_pagination.PageParams, db: Session
) -> known_devices_schema.KnownDevicePage:
    """Return one page of the user's known devices, marking the one the request comes from."""
    return known_devices_integration.list_devices(user_id, device_id, page, db)


def forget_user_device(
    device_id: int,
    user_id: int,
    session_id: str,
    step_up: auth_schema.StepUpVerification,
    step_up_store: step_up_store_module.StepUpStore,
    db: Session,
) -> None:
    """Verify step-up, then forget one of the user's known devices and commit.

    Args:
        device_id: ID of the device to forget.
        user_id: The authenticated user.
        session_id: The caller's session, which the step-up is bound to.
        step_up: The step-up verification.
        step_up_store: Step-up lockout store.
        db: Database session.

    Raises:
        NotFoundError: When the user has no such known device.
    """
    step_up_service.verify_step_up_credentials(
        user_id,
        step_up.current_password,
        step_up.mfa_code,
        step_up_store,
        db,
        idp_reauth=step_up.idp_reauth,
        session_id=session_id,
        action=identity_providers_constants.StepUpAction.PROFILE_DEVICE_FORGET,
    )
    known_devices_integration.forget_device(device_id, user_id, db)
    jasil_audit.stage(
        db,
        account_security_audit_actions.DEVICE_FORGET,
        target_type="device",
        target_id=str(device_id),
        target_owner_id=str(user_id),
    )
    db.commit()
    logger.info("Known device forgotten", extra=core_logger.context(user_id=user_id, device_id=device_id))
